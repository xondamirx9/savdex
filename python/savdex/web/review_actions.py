"""
Отзывы о своей компании — формы на Django (этап 5, шаг 25): ответ на
отзыв и спор с ним. Копия App\\Http\\Controllers\\Cabinet\\ReviewController.

Запись — как Eloquent: только изменившиеся поля и updated_at, у
администратора — строка журнала (AuditObserver, раздел reviews).
Рейтинг компании не пересчитывается: событие saved у Review
пересчитывает его только при смене оценки, статуса или компании.

Отзыв о компании на её визитке (шаг 41) — копия ReviewService::create:
право только у раскрывшего контакты и один раз, автопроверка текста
(ReviewScreening) и премодерация, пересчёт байесовского рейтинга,
уведомление компании об опубликованном отзыве.

Сверка с настоящим Laravel — tests/test_web_review_actions.py.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web import eloquent, ui
from savdex.web import review_screening as screening
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.chat_actions import _php_trim, _unverified, str_limit
from savdex.web.company import review_blocked
from savdex.web.company_profile_actions import CASTS, _search_text
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _notify_company, _now, _stamp
from savdex.web.shared import Context, settings_values
from savdex.web.tenders import _admin
from savdex.web.validation import validate, validated
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


# ── Отзыв о компании на визитке (этап 5, шаг 41) ───────────────────

#: ReviewService::MIN_BODY и ::WEIGHT
MIN_BODY = 30
WEIGHT = 5

#: ReviewService::rules
RULES: dict[str, list[str | Any]] = {
    "rating": ["required", "integer", "between:1,5"],
    "rating_description": ["nullable", "integer", "between:1,5"],
    "rating_response": ["nullable", "integer", "between:1,5"],
    "rating_deadlines": ["nullable", "integer", "between:1,5"],
    "rating_quality": ["nullable", "integer", "between:1,5"],
    "body": ["required", "string", f"min:{MIN_BODY}", "max:2000"],
    "deal_confirmed": ["boolean"],
}

#: Приведения Company для сравнения при пересчёте рейтинга
COMPANY_CASTS = {**CASTS, "rating": "decimal:2", "reviews_count": "int"}


def _php_round(value: float, places: int = 2) -> float:
    """round() PHP 8.4: половина — от нуля, по кратчайшей десятичной записи."""
    step = Decimal(1).scaleb(-places)

    return float(Decimal(repr(value)).quantize(step, ROUND_HALF_UP))


def recalculate(ctx: Context, company: dict[str, Any]) -> None:
    """
    ReviewService::recalculate: байесовский рейтинг — forceFill и save
    (search_text заново, у администратора — строка журнала). Сравнение —
    с тем, что держит переданная строка, как у модели.
    """
    average = _rows("select avg(rating) as a from reviews where status = 'published'")[0]["a"]
    global_average = float(average or 0) or 4.0
    totals = _rows(
        "select count(*) as total, sum(rating) as sum_rating from reviews "
        "where company_id = %s and status = 'published'",
        [company["id"]],
    )[0]
    count = int(totals["total"] or 0)
    total = float(totals["sum_rating"] or 0)

    eloquent.save(
        ctx,
        "companies",
        company,
        {
            "rating": _php_round((WEIGHT * global_average + total) / (WEIGHT + count))
            if count > 0
            else 0.0,
            "reviews_count": count,
        },
        section="companies",
        model="Company",
        saving=_search_text,
        casts=COMPANY_CASTS,
    )


def _premoderation() -> bool:
    """ReviewService::premoderationEnabled: (bool) Setting::get(…, true)."""
    value = settings_values().get("reviews_premoderation")

    return True if value is None else eloquent._php_bool(value)


def _insert(ctx: Context, fields: dict[str, Any]) -> dict[str, Any]:
    """Review::create: умолчание origin первым, как $attributes модели; журнал created."""
    now = _stamp(_now())
    row: dict[str, Any] = {"origin": "buyer", **fields, "updated_at": now, "created_at": now}
    columns = list(row)

    with allowed_writes("reviews"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into reviews ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            list(row.values()),
        )
        row["id"] = cursor.fetchone()[0]

    eloquent.journal(ctx, "created", "reviews", "Review", row, {"after": dict(row)})

    return row


def _create(ctx: Context, target: dict[str, Any], data: dict[str, Any]) -> tuple[bool, str]:
    """ReviewService::create: (удалось ли, сообщение)."""
    assert ctx.user is not None
    reason = review_blocked(ctx, target["id"])

    if reason is not None:
        return False, reason

    author = company_of(ctx)
    assert author is not None
    unlocks = _rows(
        "select id from contact_unlocks where company_id = %s and target_company_id = %s limit 1",
        [author["id"], target["id"]],
    )
    body = _php_trim(str(data["body"]))
    flags = screening.reasons(body)
    needs_review = bool(flags) or _premoderation()
    rating = int(float(str(data["rating"])))

    try:
        with transaction.atomic():
            _insert(
                ctx,
                {
                    "company_id": target["id"],
                    "author_company_id": author["id"],
                    "author_user_id": ctx.user["id"],
                    "contact_unlock_id": unlocks[0]["id"] if unlocks else None,
                    "listing_id": None,
                    "rating": rating,
                    "rating_description": data.get("rating_description"),
                    "rating_response": data.get("rating_response"),
                    "rating_deadlines": data.get("rating_deadlines"),
                    "rating_quality": data.get("rating_quality"),
                    "body": body,
                    "deal_confirmed": eloquent._php_bool(data.get("deal_confirmed", False)),
                    "status": "moderation" if needs_review else "published",
                    "screening_flags": "; ".join(flags) if flags else None,
                },
            )

            # Событие saved у Review: пересчёт по свежей строке компании,
            # затем сам сервис — по строке, прочитанной до отзыва
            fresh = _rows(
                "select * from companies where id = %s and deleted_at is null", [target["id"]]
            )

            if fresh:
                recalculate(ctx, fresh[0])

            recalculate(ctx, target)
    except IntegrityError:
        # Двойное нажатие: «один отзыв на компанию» держит уникальный индекс
        return False, ctx.t("messages.review.already_left")

    if needs_review:
        if not flags:
            return True, ctx.t("messages.review.sent_to_moderation")

        reason = ctx.t(screening.REASON_KEYS[flags[0]])

        return True, ctx.t("messages.review.sent_flagged", reason=reason)

    _notify_company(
        ctx,
        target,
        "review",
        lambda locale: ui.t(
            "messages.review.notify_title", locale, company=author["name"], rating=rating
        ),
        "success" if rating >= 4 else "warning",
        "/cabinet/reviews",
        str_limit(body, 140),
    )

    return True, ctx.t("messages.review.published")


@form()
def store(request: HttpRequest, slug: str) -> HttpResponse:
    """ReviewController::store (verified, throttle:20,60)."""
    ctx = action(request, throttle=20, throttle_minutes=60, throttle_prefix="company-review")

    if (refused := _unverified(ctx)) is not None:
        return refused

    targets = _rows(
        "select * from companies where slug = %s and deleted_at is null limit 1", [slug]
    )

    if not targets:
        return not_found(ctx)

    data = input_of(request)
    errors = validate(
        data,
        RULES,
        ctx.locale,
        {
            "rating.required": ctx.t("messages.review.rating_required"),
            "body.required": ctx.t("messages.review.body_required"),
            "body.min": ctx.t("messages.review.body_min"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    ok, message = _create(ctx, targets[0], validated(data, RULES))
    flash(ctx, "success" if ok else "error", message)

    return back(ctx)
