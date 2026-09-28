"""
«Мои объявления» — действия над списком на Django (этап 5, шаг 23):
продлить, снять с публикации, опубликовать заново возвращённое, удалить
и то же самое пачкой. Копия App\\Http\\Controllers\\Cabinet\\ListingController.

Запись объявления — как Eloquent (save_listing): только изменившиеся
поля, updated_at, пересчёт search_text (событие saving), у
администратора — строка журнала (AuditObserver: updated/deleted, поля
в порядке столбцов таблицы). Удаление — мягкое (deleted_at и
updated_at). Перевод опубликованного ставить в очередь не нужно: его
подбирает обработчик Python (manage.py translate).

Сверка с настоящим Laravel — tests/test_web_listing_actions.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web import ui
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of, company_plan
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.search_text import index
from savdex.web.shared import Context
from savdex.web.tenders import _admin
from savdex.web.validation import validate
from savdex.web.views import not_found

#: Listing::LIFETIME_DAYS
LIFETIME_DAYS = 90

#: Листинг-статусы (Listing::STATUS_*)
ACTIVE, ARCHIVED, REJECTED, NEEDS_CHANGES = "active", "archived", "rejected", "needs_changes"


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0, tzinfo=None)


def _stamp(value: Any) -> Any:  # noqa: ANN401
    """Значение атрибута, как его держит Eloquent после записи: дата — строкой."""
    return value.strftime("%Y-%m-%d %H:%M:%S") if isinstance(value, datetime) else value


# ── Запись объявления ────────────────────────────────────────────────


def _search_text(row: dict[str, Any]) -> str:
    titles = row["title_i18n"] if isinstance(row["title_i18n"], dict) else {}
    parts = [row["title"], row["description"] or "", *titles.values()]

    return index(" ".join(str(p) for p in parts if p not in (None, "", "0")))


def save_listing(ctx: Context, row: dict[str, Any], changes: dict[str, Any]) -> bool:
    """
    $listing->forceFill($changes)->save(): изменившиеся поля и
    search_text, updated_at; у администратора — строка журнала.
    """
    after = {**row, **changes}
    after["search_text"] = _search_text(after)
    dirty = {
        column: after[column]
        for column in row
        if column not in ("updated_at",) and _stamp(after[column]) != _stamp(row[column])
    }

    if not dirty:
        return False

    now = _now()
    sets = ", ".join(f"{c} = %s" for c in dirty)

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            f"update listings set {sets}, updated_at = %s where id = %s",
            [*(_stamp(v) for v in dirty.values()), _stamp(now), row["id"]],
        )

    _journal(
        ctx,
        "updated",
        row,
        {
            "before": {c: _stamp(row[c]) for c in dirty},
            "after": {c: _stamp(v) for c, v in dirty.items()},
        },
    )
    row.update(dirty, updated_at=now)

    return True


def delete_listing(ctx: Context, row: dict[str, Any]) -> None:
    """$listing->delete(): мягкое удаление, у администратора — строка журнала."""
    now = _stamp(_now())

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            "update listings set deleted_at = %s, updated_at = %s where id = %s",
            [now, now, row["id"]],
        )

    _journal(ctx, "deleted", row, None)


def _journal(
    ctx: Context, action_: str, row: dict[str, Any], changes: dict[str, Any] | None
) -> None:
    """AuditObserver: только действия администратора."""
    admin = _admin(ctx)

    if admin is None:
        return

    audit.record(
        connection,
        action=action_,
        section="listings",
        actor=admin,
        subject_type="App\\Models\\Listing",
        subject_id=row["id"],
        subject_label=audit.label(row, "Listing", row["id"]),
        changes=changes,
        ip=audit.client_ip(ctx.request),
    )


# ── Общее ────────────────────────────────────────────────────────────


def _owned(ctx: Context, listing_id: int) -> dict[str, Any] | None:
    """ListingController::ownedListing: своё объявление не в корзине, иначе None (404)."""
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from listings where company_id = %s and id = %s and deleted_at is null",
        [company["id"], listing_id],
    )

    return rows[0] if rows else None


def _active_count(company_id: int, exclude: list[int]) -> int:
    rows = _rows(
        "select count(*) as n from listings where company_id = %s and status = 'active' "
        "and deleted_at is null and not (id = any(%s))",
        [company_id, exclude],
    )

    return int(rows[0]["n"])


def _limit_message(ctx: Context, plan: dict[str, Any]) -> str:
    return (
        ctx.t("messages.listing.limit", plan=plan["name"], limit=plan["listings_limit"])
        + " "
        + ctx.t("messages.listing.limit_hint")
    )


def _activate(ctx: Context, row: dict[str, Any], plan: dict[str, Any]) -> None:
    """ListingController::activate: срок от сегодняшнего дня, дата публикации — если не было."""
    now = _now()
    save_listing(
        ctx,
        row,
        {
            "status": ACTIVE,
            "expires_at": now + timedelta(days=plan.get("listing_days") or LIFETIME_DAYS),
            "published_at": row["published_at"] or now,
        },
    )


def _notify_company(
    ctx: Context, company: dict[str, Any], type_: str, title: str, tone: str, url: str
) -> None:
    """Notifier::company: событие в ленте кабинета и уведомление каждому сотруднику."""
    now = _stamp(_now())

    with allowed_writes("activity_events", "user_notifications"), connection.cursor() as cursor:
        cursor.execute(
            "insert into activity_events (company_id, type, tone, message, url, created_at, "
            "updated_at) values (%s, %s, %s, %s, %s, %s, %s)",
            [company["id"], type_, tone, title, url, now, now],
        )

        for user in _rows(
            "select id, company_id from users where company_id = %s and deleted_at is null "
            "order by id",
            [company["id"]],
        ):
            cursor.execute(
                "insert into user_notifications (user_id, company_id, type, title, tone, url, "
                "created_at, updated_at) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                [user["id"], user["company_id"], type_, title, tone, url, now, now],
            )


def _as_id(value: Any) -> int:  # noqa: ANN401
    """Номер из ввода, прошедшего правило integer: 5, «5», 5.0, true."""
    if isinstance(value, bool | int | float):
        return int(value)

    return int(str(value).strip())


# ── Действия ─────────────────────────────────────────────────────────


@form()
def renew(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ListingController::renew."""
    ctx = action(request)
    row = _owned(ctx, int(listing_id))

    if row is None:
        return not_found(ctx)

    if row["status"] == REJECTED:
        flash(ctx, "error", ctx.t("messages.listing.resubmit_closed"))

        return back(ctx)

    plan = company_plan(row["company_id"])
    limit = plan.get("listings_limit")

    if limit is not None and _active_count(row["company_id"], [row["id"]]) >= limit:
        flash(ctx, "error", _limit_message(ctx, plan))

        return back(ctx)

    _activate(ctx, row, plan)
    expires = row["expires_at"]
    flash(ctx, "success", ctx.t("messages.listing.renewed", date=expires.strftime("%d.%m.%Y")))

    return back(ctx)


@form()
def archive(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ListingController::archive."""
    ctx = action(request)
    row = _owned(ctx, int(listing_id))

    if row is None:
        return not_found(ctx)

    save_listing(ctx, row, {"status": ARCHIVED})
    flash(ctx, "success", ctx.t("messages.listing.archived"))

    return back(ctx)


@form("DELETE")
def destroy(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ListingController::destroy."""
    ctx = action(request)
    row = _owned(ctx, int(listing_id))

    if row is None:
        return not_found(ctx)

    delete_listing(ctx, row)
    flash(ctx, "success", ctx.t("messages.listing.deleted"))

    return back(ctx)


@form()
def resubmit(request: HttpRequest, listing_id: str) -> HttpResponse:
    """
    ListingController::resubmit: только возвращённое на исправление;
    лимит тарифа; сразу на витрину и уведомление компании.
    """
    ctx = action(request)
    row = _owned(ctx, int(listing_id))

    if row is None:
        return not_found(ctx)

    if row["status"] != NEEDS_CHANGES:
        flash(ctx, "error", ctx.t("messages.listing.resubmit_closed"))

        return back(ctx)

    plan = company_plan(row["company_id"])
    limit = plan.get("listings_limit")

    if limit is not None and _active_count(row["company_id"], [row["id"]]) >= limit:
        flash(ctx, "error", ctx.t("messages.listing.limit", plan=plan["name"], limit=limit))

        return back(ctx)

    now = _now()
    save_listing(
        ctx,
        row,
        {
            "status": ACTIVE,
            "moderation_note": None,
            "published_at": now,
            "expires_at": now + timedelta(days=LIFETIME_DAYS),
        },
    )
    company = company_of(ctx)
    assert company is not None
    _notify_company(
        ctx,
        company,
        "moderation",
        ctx.t("messages.listing.republished_notice", title=row["title"]),
        "success",
        ctx.url("/cabinet/listings"),
    )
    flash(ctx, "success", ctx.t("messages.listing.republished"))

    return back(ctx)


@form()
def bulk(request: HttpRequest) -> HttpResponse:
    """ListingController::bulk: продлить, снять или удалить выбранные."""
    ctx = action(request)
    data = input_of(request)
    errors = validate(
        data,
        {
            "action": ["required", "in:renew,archive,delete"],
            "ids": ["required", "array", "min:1"],
            "ids.*": ["integer"],
        },
        ctx.locale,
    )

    if errors:
        return invalid(ctx, errors)

    company = company_of(ctx)

    if company is None:
        return back(ctx)

    ids_raw = data["ids"]
    ids = [_as_id(v) for v in (ids_raw.values() if isinstance(ids_raw, dict) else ids_raw)]
    listings = _rows(
        "select * from listings where company_id = %s and id = any(%s) and deleted_at is null "
        "order by id",
        [company["id"], ids],
    )

    if not listings:
        flash(ctx, "error", ctx.t("messages.listing.nothing_selected"))

        return back(ctx)

    what = data["action"]
    plan = company_plan(company["id"])

    if what == "renew":
        # Отклонённые не продлеваются — иначе запрет обходился бы галочками
        listings = [r for r in listings if r["status"] != REJECTED]

        if not listings:
            flash(ctx, "error", ctx.t("messages.listing.resubmit_closed"))

            return back(ctx)

        limit = plan.get("listings_limit")

        if limit is not None:
            others = _active_count(company["id"], [r["id"] for r in listings])

            if others + len(listings) > limit:
                flash(
                    ctx,
                    "error",
                    _limit_message(ctx, plan)
                    + " "
                    + ctx.t(
                        "messages.listing.slots",
                        free=max(0, limit - others),
                        picked=len(listings),
                    ),
                )

                return back(ctx)

    for row in listings:
        if what == "renew":
            _activate(ctx, row, plan)
        elif what == "archive":
            save_listing(ctx, row, {"status": ARCHIVED})
        else:
            delete_listing(ctx, row)

    key = {"renew": "bulk_renewed", "archive": "bulk_archived", "delete": "bulk_deleted"}[what]
    flash(ctx, "success", ui.choice(f"messages.listing.{key}", len(listings), ctx.locale))

    return back(ctx)
