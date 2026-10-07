"""
Срок тендеров из кабинета (source = cabinet) — каждый час из
savdex/schedule.py:

- до срока «Приём заявок до» осталось WARN_BEFORE (3 дня) или меньше —
  автору уведомление «через 3 дня тендер истекает» со ссылкой на «Мои
  тендеры», где кнопка «Продлить». Один раз на срок: expiry_warned_at;
  продление его сбрасывает;
- срок прошёл — status = expired: с витрины тендер уходит, автору
  уведомление. Продлить его можно и после этого.

Уведомление — в колокольчик (user_notifications, вид tender_expiring);
на почту и в Telegram его разносит manage.py notify по настройкам
человека («Тендер истекает»). Тендеры администратора (source = admin)
живут по своему сроку: их здесь не трогают.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db import connection

from savdex.guards import allowed_writes
from savdex.web import ui
from savdex.web.listing_actions import _now, _stamp

WARN_BEFORE = timedelta(days=3)

#: Вид уведомления (deliveries.EVENT_OF_TYPE → событие настроек tender_expiring)
TYPE = "tender_expiring"

URL = "/cabinet/tenders"


def _rows(query: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _notify(tender: dict[str, Any], key: str, tone: str, now: datetime) -> None:
    """Автору — на его языке; удалённому и заблокированному — ничего."""
    users = _rows(
        "select id, company_id, locale from users where id = %s and deleted_at is null "
        "and status = 'active'",
        [tender["author_id"]],
    )

    if not users:
        return

    user = users[0]
    locale = user["locale"] or "ru"
    stamp = _stamp(now)

    with allowed_writes("user_notifications"), connection.cursor() as cursor:
        cursor.execute(
            "insert into user_notifications (user_id, company_id, type, title, body, tone, url, "
            "created_at, updated_at) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                user["id"],
                user["company_id"],
                TYPE,
                ui.t(f"messages.tender.{key}_title", locale, title=tender["title"]),
                ui.t(f"messages.tender.{key}_body", locale),
                tone,
                URL,
                stamp,
                stamp,
            ],
        )


def _mark(tender_id: int, changes: dict[str, Any]) -> bool:
    """Записать, только если тендер всё ещё на витрине: правка автора не затирается."""
    columns = ", ".join(f"{c} = %s" for c in changes)

    with allowed_writes("tenders"), connection.cursor() as cursor:
        cursor.execute(
            f"update tenders set {columns} where id = %s and status = 'published'",
            [*changes.values(), tender_id],
        )

        return bool(cursor.rowcount)


def warn(now: datetime) -> int:
    found = _rows(
        "select id, title, author_id from tenders where source = 'cabinet' "
        "and status = 'published' and expiry_warned_at is null and deadline_at is not null "
        "and deadline_at > %s and deadline_at <= %s order by id",
        [now, now + WARN_BEFORE],
    )
    warned = 0

    for tender in found:
        if _mark(tender["id"], {"expiry_warned_at": now}):
            _notify(tender, "expiring", "warning", now)
            warned += 1

    return warned


def expire(now: datetime) -> int:
    found = _rows(
        "select id, title, author_id from tenders where source = 'cabinet' "
        "and status = 'published' and deadline_at is not null and deadline_at <= %s order by id",
        [now],
    )
    expired = 0

    for tender in found:
        if _mark(tender["id"], {"status": "expired", "updated_at": now}):
            _notify(tender, "expired", "warning", now)
            expired += 1

    return expired


def run(now: datetime | None = None) -> tuple[int, int]:
    """Один проход: (истекло, предупреждено). Сначала истёкшие — им предупреждение уже ни к чему."""
    moment = now or _now()

    return expire(moment), warn(moment)
