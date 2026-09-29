"""
Мастер объявления — формы на Django (этап 5, шаг 38): новый черновик
(GET /cabinet/listings/create) и публикация. Копия
App\\Http\\Controllers\\Cabinet\\ListingWizardController (create, publish);
автосохранение — отдельным шагом.

Посредник verified, как у группы маршрутов мастера. Незаполненный
черновик переиспользуется: GET дёргают предзагрузка и обновление
страницы. Публикация — сразу на витрину (постмодерация), срок 90 дней,
адрес из заголовка, уведомление компании. Запись — как Eloquent:
search_text (событие saving), у администратора — строки журнала.
Перевод опубликованного подбирает обработчик Python.

Сверка с настоящим Laravel — tests/test_web_wizard_actions.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.tenders.slug import slugify
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of, company_plan
from savdex.web.chat_actions import _unverified
from savdex.web.company_contact_actions import _php_boolean
from savdex.web.forms import _store, action, back, flash, input_of, invalid, redirect
from savdex.web.listing_actions import LIFETIME_DAYS, _notify_company, _search_text, _stamp
from savdex.web.resume_actions import _exists
from savdex.web.shared import Context
from savdex.web.validation import validate
from savdex.web.views import not_found

#: Приведения Listing для сравнения
CASTS = {
    "price": "decimal:2",
    "bundle_price": "decimal:2",
    "price_negotiable": "bool",
    "tags": "json",
    "title_i18n": "json",
    "description_i18n": "json",
    "delivery_terms_i18n": "json",
    "payment_terms_i18n": "json",
}


def _saving(listing: dict[str, Any]) -> dict[str, Any]:
    """Listing saving: search_text из заголовка, описания и переводов заголовка."""
    return {"search_text": _search_text(listing)}


def _save(ctx: Context, listing: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    return eloquent.save(
        ctx,
        "listings",
        listing,
        changes,
        section="listings",
        model="Listing",
        saving=_saving,
        casts=CASTS,
    )


def _active(company_id: int, exclude: int | None = None) -> int:
    """$company->activeListings()->count(): не в корзине."""
    sql = (
        "select count(*) as n from listings where company_id = %s and status = 'active' "
        "and deleted_at is null"
    )
    params: list[Any] = [company_id]

    if exclude is not None:
        sql += " and id <> %s"
        params.append(exclude)

    return int(_rows(sql, params)[0]["n"])


@form("GET")
def create(request: HttpRequest) -> HttpResponse:
    """ListingWizardController::create (verified, throttle:30,60)."""
    ctx = action(request, throttle=30, throttle_minutes=60, throttle_prefix="listing-create")

    if (refused := _unverified(ctx)) is not None:
        return refused

    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        _store(ctx).flash("warning", ctx.t("messages.listing.no_company"))

        return redirect(ctx, ctx.url("/cabinet/company"))

    plan = company_plan(company["id"])
    limit = plan.get("listings_limit")

    if limit is not None and _active(company["id"]) >= limit:
        flash(
            ctx,
            "error",
            ctx.t("messages.listing.limit", plan=plan["name"], limit=limit)
            + " "
            + ctx.t("messages.listing.limit_hint"),
        )

        return redirect(ctx, ctx.url("/cabinet/listings"))

    drafts = _rows(
        "select id from listings where company_id = %s and status = 'draft' and title = '' "
        "and description is null and deleted_at is null order by created_at desc, id desc limit 1",
        [company["id"]],
    )

    listing_id = drafts[0]["id"] if drafts else _insert_draft(ctx, company)

    return redirect(ctx, ctx.url(f"/cabinet/listings/{listing_id}/edit"))


def _insert_draft(ctx: Context, company: dict[str, Any]) -> int:
    """$company->listings()->create([...]): черновик с пустым заголовком."""
    assert ctx.user is not None
    now = _stamp(eloquent.now())
    row: dict[str, Any] = {
        "user_id": ctx.user["id"],
        "city_id": company["city_id"],
        "status": "draft",
        "type": "supply",
        "title": "",
        "currency": "UZS",
        "wizard_step": 1,
        "company_id": company["id"],
    }
    row["search_text"] = _search_text({**row, "description": None, "title_i18n": None})
    row.update(updated_at=now, created_at=now)
    columns = list(row)

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into listings ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            list(row.values()),
        )
        listing_id = int(cursor.fetchone()[0])

    row["id"] = listing_id
    eloquent.journal(ctx, "created", "listings", "Listing", row, {"after": row})

    return listing_id


def _owned(ctx: Context, listing_id: int) -> dict[str, Any] | None:
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from listings where company_id = %s and id = %s and deleted_at is null",
        [company["id"], listing_id],
    )

    return rows[0] if rows else None


@form()
def publish(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ListingWizardController::publish (verified): строгая проверка перед витриной."""
    ctx = action(request)

    if (refused := _unverified(ctx)) is not None:
        return refused

    listing = _owned(ctx, int(listing_id))

    if listing is None:
        return not_found(ctx)

    if listing["status"] == "rejected":
        flash(ctx, "error", ctx.t("messages.listing.resubmit_closed"))

        return back(ctx)

    data = input_of(request)
    errors = validate(
        data,
        {
            "category_id": ["required", _exists("categories")],
            "title": ["required", "string", "min:10", "max:90"],
            "description": ["required", "string", "min:30", "max:5000"],
            "price": ["nullable", "numeric", "min:0"],
            "bundle_price": ["nullable", "numeric", "min:0"],
            "price_negotiable": ["boolean"],
        },
        ctx.locale,
        {
            "category_id.required": ctx.t("messages.listing.category_required"),
            "title.required": ctx.t("messages.listing.title_required"),
            "title.min": ctx.t("messages.listing.title_min"),
            "description.required": ctx.t("messages.listing.description_required"),
            "description.min": ctx.t("messages.listing.description_min"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    negotiable = _php_boolean(data.get("price_negotiable")) if "price_negotiable" in data else False

    if not negotiable and data.get("price") is None:
        # ValidationException::withMessages — как ошибка проверки
        return invalid(ctx, {"price": [ctx.t("messages.listing.price_required")]})

    company = company_of(ctx)
    assert company is not None
    plan = company_plan(company["id"])
    limit = plan.get("listings_limit")

    if limit is not None and _active(company["id"], listing["id"]) >= limit:
        flash(ctx, "error", ctx.t("messages.listing.limit", plan=plan["name"], limit=limit))

        return back(ctx)

    fields = (
        "category_id", "title", "description", "price", "bundle_price", "currency",
        "unit", "min_order", "delivery_terms", "payment_terms",
    )  # fmt: skip
    now = eloquent.now()
    changes = {k: data[k] for k in fields if k in data}
    changes.update(
        price_negotiable=negotiable,
        status="active",
        wizard_step=4,
        published_at=now,
        expires_at=now + timedelta(days=LIFETIME_DAYS),
    )
    _save(ctx, listing, changes)

    if not listing["slug"]:
        slug = slugify(str(listing["title"]))[:60].rstrip() + f"-{listing['id']}"
        _save(ctx, listing, {"slug": slug})

    _notify_company(
        ctx,
        company,
        "moderation",
        ctx.t("messages.listing.published_notice", title=listing["title"]),
        "success",
        ctx.url("/cabinet/listings"),
    )
    flash(ctx, "success", ctx.t("messages.listing.published"))

    return redirect(ctx, ctx.url("/cabinet/listings"))


# ── Автосохранение (этап 5, шаг 39) ─────────────────────────────────

#: Currencies::codes()
CURRENCIES = ("UZS", "USD", "EUR", "CNY", "TRY", "RUB", "KZT")


def _attribute(listing_id: int, key: str, value: str | None) -> None:
    """$listing->attributes(): updateOrCreate по ключу; None — удалить строку."""
    found = _rows(
        "select * from listing_attributes where listing_id = %s and key = %s order by id limit 1",
        [listing_id, key],
    )
    now = _stamp(eloquent.now())

    with allowed_writes("listing_attributes"), connection.cursor() as cursor:
        if value is None:
            cursor.execute(
                "delete from listing_attributes where listing_id = %s and key = %s",
                [listing_id, key],
            )
        elif not found:
            cursor.execute(
                "insert into listing_attributes (listing_id, key, value, updated_at, created_at) "
                "values (%s, %s, %s, %s, %s)",
                [listing_id, key, value, now, now],
            )
        elif found[0]["value"] != value:
            cursor.execute(
                "update listing_attributes set value = %s, updated_at = %s where id = %s",
                [value, now, found[0]["id"]],
            )


def _php_string(value: Any) -> str:  # noqa: ANN401
    """(string) $value для скаляров."""
    if value is None or value is False:
        return ""

    if value is True:
        return "1"

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def _allowed_specs(category_id: int | None) -> list[str]:
    """ProductSpecs::forCategory: ключи деталей товара для категории объявления."""
    from savdex.web import specs

    if category_id is None:
        return []

    rows = _rows(
        "select c.slug, c.parent_id, p.slug as parent_slug from categories c "
        "left join categories p on p.id = c.parent_id where c.id = %s",
        [category_id],
    )

    if not rows:
        return []

    row = rows[0]
    parent_slug, child_slug = (
        (row["parent_slug"], row["slug"]) if row["parent_id"] is not None else (row["slug"], None)
    )

    return [specs.PREFIX + f for f in specs._set_for(parent_slug, child_slug)]


@form()
def autosave(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ListingWizardController::autosave (verified, throttle:60,1): черновик без строгости."""
    from savdex.audit import _php_json
    from savdex.web import specs
    from savdex.web.cabinet import wizard_tag_options
    from savdex.web.validation import validated

    ctx = action(request, throttle=60, throttle_prefix="listing-autosave")

    if (refused := _unverified(ctx)) is not None:
        return refused

    listing = _owned(ctx, int(listing_id))

    if listing is None:
        return not_found(ctx)

    data = input_of(request)
    rules: dict[str, list[Any]] = {
        "type": ["nullable", "in:supply,demand"],
        "category_id": ["nullable", _exists("categories")],
        "title": ["nullable", "string", "max:90"],
        "description": ["nullable", "string", "max:5000"],
        "price": ["nullable", "numeric", "min:0", "max:99999999999"],
        "bundle_price": ["nullable", "numeric", "min:0", "max:99999999999"],
        "currency": ["nullable", "in:" + ",".join(CURRENCIES)],
        "unit": ["nullable", "string", "max:20"],
        "price_negotiable": ["nullable", "boolean"],
        "min_order": ["nullable", "integer", "min:0"],
        "delivery_terms": ["nullable", "string", "max:500"],
        "payment_terms": ["nullable", "string", "max:500"],
        "step": ["nullable", "integer", "between:1,4"],
        "attributes": ["nullable", "array"],
        "tags": ["nullable", "array", "max:8"],
        "tags.*": ["string", "max:40"],
    }
    errors = validate(data, rules, ctx.locale)

    if errors:
        return invalid(ctx, errors)

    fields = validated(data, rules)
    attributes = fields.pop("attributes", None) or {}
    chosen = fields.pop("tags", None)

    if fields.get("step") is not None:
        fields["wizard_step"] = fields.pop("step")

    changes = {k: v for k, v in fields.items() if v is not None and k != "step"}

    # false — валидное значение, array_filter его выбрасывает
    if "price_negotiable" in data:
        changes["price_negotiable"] = _php_boolean(data["price_negotiable"])

    # Очистка поля должна доехать до базы
    if "bundle_price" in data:
        changes["bundle_price"] = data["bundle_price"]

    _save(ctx, listing, changes)

    items = attributes.items() if isinstance(attributes, dict) else enumerate(attributes)

    for raw_key, value in items:
        key = str(raw_key)

        if key.startswith(specs.PREFIX):
            cleaned = specs.clean(key, value)

            if cleaned == "":
                _attribute(listing["id"], key, None)
            elif cleaned is not None:
                _attribute(listing["id"], key, cleaned)

            continue

        _attribute(listing["id"], key, _php_string(value))

    # Сменили категорию — детали, которых у новой нет, убираются
    allowed = _allowed_specs(listing["category_id"])

    with allowed_writes("listing_attributes"), connection.cursor() as cursor:
        cursor.execute(
            "delete from listing_attributes where listing_id = %s and key like %s "
            "and not (key = any(%s))",
            [listing["id"], specs.PREFIX + "%", allowed],
        )

    company = company_of(ctx)

    if chosen is not None:
        options = wizard_tag_options(ctx.locale, listing, company)
        picked = chosen.values() if isinstance(chosen, dict) else chosen
        _save(ctx, listing, {"tags": [str(t) for t in picked if str(t) in options]})

    body = {
        "saved_at": eloquent.now().strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        # Свежий список вариантов: заголовок мог измениться
        "tag_options": wizard_tag_options(ctx.locale, listing, company),
    }

    return HttpResponse(_php_json(body), content_type="application/json")
