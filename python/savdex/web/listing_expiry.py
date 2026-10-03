"""
Снятие истёкших объявлений — копия команды Laravel listings:expire
(app/Console/Commands/ExpireListings.php), этап 4: хозяин listings —
Django, и расписание переехало вместе с таблицей.

Запускает savdex/schedule.py в 06:00 UTC. Без неё expires_at — просто
дата в базе: объявления висели бы в выдаче вечно. Раз в сутки:

- активные с истёкшим сроком — в «истёкшие» (сохранение как у модели:
  search_text и updated_at), компании — событие в ленте и уведомление
  каждому сотруднику;
- истекающим через три дня — предупреждение. Окно — сутки, чтобы
  следующий проход не повторил то же самое.

Отличие от Laravel: окно предупреждения отсчитывается от назначенного
времени прохода (06:00 UTC), а не от «сейчас». Проход, запущенный позже
(перезапуск контейнера), не сдвигает окно — объявления на стыке суток
не пропадают и не получают предупреждение дважды.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial
from typing import Any

from savdex.web import ui
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _notify_company, _now, save_listing

EXPIRED = "expired"

Row = dict[str, Any]


def _with_company(query: str, params: list[Any]) -> list[tuple[Row, Row | None]]:
    """Объявления с компанией (->with('company')): удалённой компании нет."""
    listings = _rows(query, params)
    ids = sorted({row["company_id"] for row in listings})
    companies = {
        c["id"]: c
        for c in _rows("select * from companies where id = any(%s) and deleted_at is null", [ids])
    }

    return [(row, companies.get(row["company_id"])) for row in listings]


def expire(now: datetime) -> int:
    """ExpireListings::expire: снять истёкшие, сказать компании."""
    found = _with_company(
        "select * from listings where deleted_at is null and status = 'active' "
        "and expires_at is not null and expires_at <= %s order by id",
        [now],
    )

    for listing, company in found:
        save_listing(None, listing, {"status": EXPIRED})

        if company is not None:
            _notify_company(
                None,
                company,
                "listing_expiring",
                partial(ui.t, "messages.listing.expired_title", title=listing["title"]),
                "warning",
                f"/cabinet/listings?status={EXPIRED}",
                lambda locale: ui.t("messages.listing.expired_body", locale),
            )

    return len(found)


def warn(anchor: datetime) -> int:
    """ExpireListings::warn3DaysBefore: истекает через 3–4 суток от прохода."""
    found = _with_company(
        "select * from listings where deleted_at is null and status = 'active' "
        "and expires_at is not null and expires_at between %s and %s order by id",
        [anchor + timedelta(days=3), anchor + timedelta(days=4)],
    )

    for listing, company in found:
        if company is None:
            continue

        _notify_company(
            None,
            company,
            "listing_expiring",
            partial(ui.t, "messages.listing.expiring_title", title=listing["title"]),
            "warning",
            "/cabinet/listings",
            lambda locale: ui.t("messages.listing.expiring_body", locale),
        )

    return len(found)


def run(now: datetime | None = None, anchor: datetime | None = None) -> tuple[int, int]:
    """Один проход: (снято, предупреждено)."""
    moment = now or _now()

    return expire(moment), warn(anchor or moment)
