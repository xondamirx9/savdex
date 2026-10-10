"""
Второй шаг регистрации и «Оцените SavdEx» — формы на Django (этап 5,
шаг 47). Копия OnboardingController::store и ::skip, ReviewsController::store
с PlatformReviewService::save.

Компания со второго шага — как Company::create: адрес из названия,
search_text, затем направления (company_category, без меток времени —
связь без withTimestamps) и владелец — пользователь. Отзыв о площадке —
updateOrCreate по пользователю: правка возвращает отзыв на проверку.

Сверка с настоящим Laravel — tests/test_web_onboarding_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web import analytics
from savdex.web import review_screening as screening
from savdex.web.actions import form
from savdex.web.auth import (
    CRITERIA,
    LEGAL_FORMS,
    MIN_BODY,
    _blocked_reason,
    onboarding_company_of,
    onboarding_open,
)
from savdex.web.auth_actions import _row, _to
from savdex.web.cabinet import _rows
from savdex.web.chat_actions import _php_trim
from savdex.web.city_choice import city_in_country, resolve_other
from savdex.web.company_profile_actions import (
    _country_code,
    _country_id,
    _create,
    _tin,
    _unique_tin,
    normalize_tin,
)
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.resume_actions import _exists
from savdex.web.review_actions import _premoderation
from savdex.web.shared import Context
from savdex.web.validation import Check, validate, validated

# ── Второй шаг регистрации ──────────────────────────────────────────


def _account_type(user: dict[str, Any]) -> str:
    """OnboardingController::accountType: неизвестное значение — юрлицо."""
    kind = str(user["account_type"] or "")

    return kind if kind in LEGAL_FORMS else "legal"


@form()
def company(request: HttpRequest) -> HttpResponse:
    """OnboardingController::store (auth)."""
    ctx = action(request)
    assert ctx.user is not None
    user = _row(ctx.user["id"])

    # Шаг пройден: компания есть и дополнена
    if not onboarding_open(user["company_id"]):
        return _to(ctx, "/cabinet")

    existing = onboarding_company_of(user["company_id"])

    if existing is not None:
        return _complete(ctx, existing)

    legal_form = _account_type(user)
    person = legal_form != "legal"
    data = dict(input_of(request))
    normalize_tin(data)
    resolve_other(data)
    tin_messages: list[str] = []
    rules: dict[str, list[str | Check]] = {
        "name": ["required", "string", "min:2", "max:190"],
        "type": ["nullable" if person else "required", "string", "max:30"],
        "country_id": ["required", _exists("countries")],
        "city_id": ["required", _exists("cities"), city_in_country(data)],
        "tin": [
            "nullable",
            "string",
            "max:20",
            _tin(ctx, _country_code(data, None), tin_messages, person=person),
            _unique_tin(None, _country_id(data, None)),
        ],
        "primary_role": ["required", "in:supplier,buyer,both"],
        "categories": ["array", "max:5"],
        "categories.*": ["integer", _exists("categories")],
        "custom_category": ["nullable", "string", "max:80"],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "name.required": ctx.t(
                "messages.company.person_name_required"
                if person
                else "messages.company.name_required"
            ),
            "type.required": ctx.t("messages.company.type_required"),
            "country_id.required": ctx.t("messages.company.country_required"),
            "city_id.required": ctx.t("messages.company.city_required"),
            "city_id.city_country": ctx.t("messages.company.city_country"),
            "categories.max": ctx.t("messages.company.categories_max"),
            "tin.unique": ctx.t("messages.company.tin_unique"),
        },
    )

    # Текст ошибки правила Tin выбирает само правило
    if "tin" in errors and tin_messages:
        errors["tin"] = [tin_messages[0] if m == "validation.tin" else m for m in errors["tin"]]

    if errors:
        return invalid(ctx, errors)

    fields = validated(data, rules)
    company_id = _create(
        ctx,
        {
            "name": fields["name"],
            "type": fields.get("type"),
            "legal_form": legal_form,
            "country_id": fields["country_id"],
            "city_id": fields["city_id"],
            "tin": fields.get("tin"),
            "primary_role": fields["primary_role"],
            "custom_category": fields.get("custom_category"),
            "status": "active",
        },
        before_owner=lambda company_id: _sync_categories(
            company_id, fields.get("categories") or []
        ),
    )
    assert company_id
    _profile_completed(ctx, fields)
    flash(ctx, "success", ctx.t("messages.company.created_onboarding"))

    return _to(ctx, "/verify-email")


def _complete(ctx: Context, company: dict[str, Any]) -> HttpResponse:
    """
    OnboardingController::complete: у юрлица название, ИНН и разделы уже
    есть — здесь тип, страна, город и роль; направления услуг добавляются
    к выбранным разделам, всего не больше пяти.
    """
    from savdex.web import eloquent
    from savdex.web.company_profile_actions import CASTS, _search_text

    data = dict(input_of(ctx.request))
    resolve_other(data)
    rules: dict[str, list[str | Check]] = {
        "type": ["required", "string", "max:30"],
        "country_id": ["required", _exists("countries")],
        "city_id": ["required", _exists("cities"), city_in_country(data)],
        "primary_role": ["required", "in:supplier,buyer,both"],
        "categories": ["array", "max:5"],
        "categories.*": ["integer", _exists("categories")],
        "custom_category": ["nullable", "string", "max:80"],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "type.required": ctx.t("messages.company.type_required"),
            "country_id.required": ctx.t("messages.company.country_required"),
            "city_id.required": ctx.t("messages.company.city_required"),
            "city_id.city_country": ctx.t("messages.company.city_country"),
            "categories.max": ctx.t("messages.company.categories_max"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    fields = validated(data, rules)
    eloquent.save(
        ctx,
        "companies",
        company,
        {
            "type": fields["type"],
            "country_id": fields["country_id"],
            "city_id": fields["city_id"],
            "primary_role": fields["primary_role"],
            # $data['custom_category'] ?? $company->custom_category
            "custom_category": company["custom_category"]
            if fields.get("custom_category") is None
            else fields["custom_category"],
        },
        section="companies",
        model="Company",
        saving=_search_text,
        casts=CASTS,
    )

    # Уже выбранные разделы, затем новые; без повторов, не больше пяти
    current = [
        r["category_id"]
        for r in _rows(
            "select category_id from company_category where company_id = %s",
            [company["id"]],
        )
    ]
    merged = list(dict.fromkeys([*current, *(_int(c) for c in fields.get("categories") or [])]))[:5]
    _sync_to(company["id"], current, merged)
    _profile_completed(ctx, {**fields, "tin": company.get("tin")})
    flash(ctx, "success", ctx.t("messages.company.created_onboarding"))

    return _to(ctx, "/verify-email")


def _profile_completed(ctx: Context, fields: dict[str, Any]) -> None:
    """GA4: данные компании сохранены — страна, тип и роль, без названия и ИНН."""
    analytics.queue(
        ctx,
        "company_profile_completed",
        {
            "country": analytics.country_code(fields.get("country_id")),
            "company_type": fields.get("type"),
            "role": fields.get("primary_role"),
            "tin_filled": bool(fields.get("tin")),
        },
    )


def _sync_to(company_id: int, current: list[int], wanted: list[int]) -> None:
    """categories()->sync($wanted): лишние связи прочь, недостающие — вставкой."""
    detach = [c for c in current if c not in wanted]

    if detach:
        with allowed_writes("company_category"), connection.cursor() as cursor:
            cursor.execute(
                "delete from company_category where company_id = %s and category_id = any(%s)",
                [company_id, detach],
            )

    _sync_categories(company_id, [c for c in wanted if c not in current])


def _sync_categories(company_id: int, categories: list[Any]) -> None:
    """categories()->sync(...): новые связи одной вставкой, повторы — один раз."""
    ids: list[int] = []

    for value in categories:
        key = int(str(value).strip())

        if key not in ids:
            ids.append(key)

    if not ids:
        return

    with allowed_writes("company_category"), connection.cursor() as cursor:
        cursor.execute(
            "insert into company_category (company_id, category_id) values "
            + ", ".join(["(%s, %s)"] * len(ids)),
            [v for key in ids for v in (company_id, key)],
        )


@form()
def skip(request: HttpRequest) -> HttpResponse:
    """OnboardingController::skip (auth): аккаунт уже есть — дальше к подтверждению почты."""
    ctx = action(request)
    flash(ctx, "warning", ctx.t("messages.company.skipped"))

    return _to(ctx, "/verify-email")


# ── «Оцените SavdEx» ────────────────────────────────────────────────

#: PlatformReviewService::rules
REVIEW_RULES: dict[str, list[str | Check]] = {
    "rating": ["required", "integer", "between:1,5"],
    "rating_usability": ["nullable", "integer", "between:0,5"],
    "rating_search": ["nullable", "integer", "between:0,5"],
    "rating_support": ["nullable", "integer", "between:0,5"],
    "body": ["required", "string", f"min:{MIN_BODY}", "max:2000"],
}


def _int(value: Any) -> int:  # noqa: ANN401
    """(int) у PHP для прошедшего integer: «5», 5, 5.0 или true."""
    return int(value) if isinstance(value, bool) else int(float(str(value)))


def _save_review(ctx: Context, data: dict[str, Any]) -> tuple[bool, str]:
    """PlatformReviewService::save: (удалось ли, сообщение)."""
    from savdex.web import eloquent

    assert ctx.user is not None
    reason = _blocked_reason(ctx)

    if reason is not None:
        return False, reason

    body = _php_trim(str(data["body"]))
    flags = screening.reasons(body)
    needs_review = bool(flags) or _premoderation()
    values: dict[str, Any] = {
        "company_id": ctx.user["company_id"],
        "rating": _int(data["rating"]),
        **{
            field: _int(data[field])
            if data.get(field) is not None and _int(data[field]) > 0
            else None
            for field in CRITERIA
        },
        "body": body,
        "status": "moderation" if needs_review else "published",
        "screening_flags": "; ".join(flags) if flags else None,
        "moderator_note": None,
        "moderated_by": None,
        "moderated_at": None,
    }
    mine = _rows(
        "select * from platform_reviews where user_id = %s order by id limit 1", [ctx.user["id"]]
    )
    now = _stamp(eloquent.now())

    with allowed_writes("platform_reviews"), connection.cursor() as cursor:
        if not mine:
            row = {"user_id": ctx.user["id"], **values, "updated_at": now, "created_at": now}
            cursor.execute(
                f"insert into platform_reviews ({', '.join(row)}) "
                f"values ({', '.join(['%s'] * len(row))})",
                list(row.values()),
            )
        else:
            # Eloquent save: только изменившееся, и тогда — updated_at
            dirty = {k: v for k, v in values.items() if not eloquent._same(mine[0][k], v)}

            if dirty:
                dirty["updated_at"] = now
                cursor.execute(
                    f"update platform_reviews set {', '.join(f'{k} = %s' for k in dirty)} "
                    "where id = %s",
                    [*dirty.values(), mine[0]["id"]],
                )

    if not needs_review:
        return True, ctx.t("platform_reviews.published")

    if not flags:
        # Отзыв о площадке — не на странице компании, а на /reviews
        return True, ctx.t("messages.review.platform_sent_to_moderation")

    return True, ctx.t("messages.review.sent_flagged", reason=flags[0].lower())


@form()
def review(request: HttpRequest) -> HttpResponse:
    """ReviewsController::store (auth, throttle:10,60,platform-review)."""
    ctx = action(request, throttle=10, throttle_minutes=60, throttle_prefix="platform-review")
    data = input_of(request)
    errors = validate(
        data,
        REVIEW_RULES,
        ctx.locale,
        {
            "rating.required": ctx.t("messages.review.rating_required"),
            "body.required": ctx.t("messages.review.body_required"),
            "body.min": ctx.t("messages.review.body_min"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    ok, message = _save_review(ctx, validated(data, REVIEW_RULES))
    flash(ctx, "success" if ok else "error", message)

    return back(ctx)
