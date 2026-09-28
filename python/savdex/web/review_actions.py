"""
Отзывы о своей компании — формы на Django (этап 5, шаг 25): ответ на
отзыв и спор с ним. Копия App\\Http\\Controllers\\Cabinet\\ReviewController.

Запись — как Eloquent: только изменившиеся поля и updated_at, у
администратора — строка журнала (AuditObserver, раздел reviews).
Рейтинг компании не пересчитывается: событие saved у Review
пересчитывает его только при смене оценки, статуса или компании.

Сверка с настоящим Laravel — tests/test_web_review_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _now, _stamp
from savdex.web.shared import Context
from savdex.web.tenders import _admin
from savdex.web.validation import validate
from savdex.web.views import not_found


def _owned(ctx: Context, review_id: int) -> dict[str, Any] | None:
    """ReviewController::owned: опубликованный отзыв о своей компании, иначе None (404)."""
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from reviews where company_id = %s and status = 'published' and id = %s",
        [company["id"], review_id],
    )

    return rows[0] if rows else None


def _save(ctx: Context, row: dict[str, Any], changes: dict[str, Any]) -> None:
    """$review->forceFill($changes)->save()."""
    dirty = {c: v for c, v in changes.items() if _stamp(v) != _stamp(row[c])}

    if not dirty:
        return

    # Поля журнала — в порядке столбцов таблицы, как getChanges()
    dirty = {c: dirty[c] for c in row if c in dirty}
    sets = ", ".join(f"{c} = %s" for c in dirty)

    with allowed_writes("reviews"), connection.cursor() as cursor:
        cursor.execute(
            f"update reviews set {sets}, updated_at = %s where id = %s",
            [*(_stamp(v) for v in dirty.values()), _stamp(_now()), row["id"]],
        )

    admin = _admin(ctx)

    if admin is not None:
        audit.record(
            connection,
            action="updated",
            section="reviews",
            actor=admin,
            subject_type="App\\Models\\Review",
            subject_id=row["id"],
            subject_label=audit.label(row, "Review", row["id"]),
            changes={
                "before": {c: _stamp(row[c]) for c in dirty},
                "after": {c: _stamp(v) for c, v in dirty.items()},
            },
            ip=audit.client_ip(ctx.request),
        )


@form()
def reply(request: HttpRequest, review_id: str) -> HttpResponse:
    """ReviewController::reply: ответ 10–2000 знаков, повторный заменяет прежний."""
    ctx = action(request)
    row = _owned(ctx, int(review_id))

    if row is None:
        return not_found(ctx)

    data = input_of(request)
    errors = validate(
        data,
        {"reply": ["required", "string", "min:10", "max:2000"]},
        ctx.locale,
        {
            "reply.required": ctx.t("messages.review.reply_required"),
            "reply.min": ctx.t("messages.review.reply_min"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    _save(ctx, row, {"reply": data["reply"], "replied_at": _now()})
    flash(ctx, "success", ctx.t("messages.review.reply_published"))

    return back(ctx)


@form()
def dispute(request: HttpRequest, review_id: str) -> HttpResponse:
    """ReviewController::dispute: спор один, причина 20–1000 знаков."""
    ctx = action(request)
    row = _owned(ctx, int(review_id))

    if row is None:
        return not_found(ctx)

    if row["dispute_status"] is not None:
        flash(ctx, "error", ctx.t("messages.review.already_disputed"))

        return back(ctx)

    data = input_of(request)
    errors = validate(
        data,
        {"reason": ["required", "string", "min:20", "max:1000"]},
        ctx.locale,
        {
            "reason.required": ctx.t("messages.review.reason_required"),
            "reason.min": ctx.t("messages.review.reason_min"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    _save(ctx, row, {"dispute_status": "pending", "dispute_reason": data["reason"]})
    flash(ctx, "success", ctx.t("messages.review.dispute_sent"))

    return back(ctx)
