"""
Профиль своей компании — форма на Django (этап 5, шаг 33): правка и
создание компании. Копия App\\Http\\Controllers\\Cabinet\\CompanyProfileController::update;
логотип, обложка и файлы — отдельными шагами.

ИНН — правило App\\Rules\\Tin (цифры, не «учебные» последовательности,
9 цифр для Узбекистана, 6–15 для других стран) и одна компания на ИНН.
Запись — как Eloquent: search_text из названия и юридического имени
(событие saving), у новой — адрес из названия, свободный и среди
удалённых (creating); у администратора — строки журнала (companies и
users).

Сверка с настоящим Laravel — tests/test_web_company_profile_actions.py.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.tenders.slug import slugify
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import SERVICE_TYPES, _rows, company_of
from savdex.web.forms import action, back, flash, input_of, invalid, redirect
from savdex.web.listing_actions import _stamp
from savdex.web.resume_actions import _exists
from savdex.web.search_text import index
from savdex.web.shared import Context
from savdex.web.validation import Check, validate, validated
from savdex.web.views import not_found

#: Tin::FAKE
FAKE_TINS = ("123456789", "987654321", "123123123")

#: Приведения Company для сравнения
CASTS = {"is_it_provider": "bool", "it_specializations": "json", "founded_year": "int"}


#: Company::PROFILE_FIELDS — сведения, которые меняются раз в полгода
PROFILE_FIELDS = (
    "name",
    "legal_name",
    "tin",
    "country_id",
    "city_id",
    "address",
    "employees_range",
    "founded_year",
    "type",
    "description",
    "is_it_provider",
    "it_specializations",
)


def _profile_value(field: str, value: Any) -> str | None:  # noqa: ANN401
    """Company::profileValue: пустое — None, список — отсортирован, флаг «нет» — пусто."""
    if field == "is_it_provider":
        truthy = ("1", "true", "on", "yes")
        on = value if isinstance(value, bool) else str(value).strip().lower() in truthy

        return "1" if on else None

    if field == "it_specializations":
        if isinstance(value, str):
            value = json.loads(value) if value.strip() else []

        items = sorted(str(v) for v in (value or []) if v not in (None, ""))

        return ",".join(items) if items else None

    text = "" if value is None else str(value).strip()

    return text or None


def changed_profile_fields(company: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Company::changedProfileFields: какие из заполненных сведений запрос меняет."""
    changed = []

    for field in PROFILE_FIELDS:
        if field not in data:
            continue

        current = _profile_value(field, company.get(field))

        if current is None:
            continue

        if current != _profile_value(field, data[field]):
            changed.append(field)

    return changed


def _tin(ctx: Context, country: str | None, messages: list[str]) -> Check:
    """App\\Rules\\Tin (не для физлица): текст ошибки — свой у каждого случая."""

    def passes(value: Any) -> bool:  # noqa: ANN401
        tin = "" if value is None else str(value)

        if re.fullmatch(r"\d+", tin, re.ASCII) is None:
            messages.append(ctx.t("messages.tin.digits_only"))

            return False

        if re.fullmatch(r"(\d)\1+", tin, re.ASCII) or tin in FAKE_TINS:
            messages.append(ctx.t("messages.tin.invalid"))

            return False

        if country in (None, "uz"):
            if len(tin) != 9:
                messages.append(ctx.t("messages.tin.uz_length"))

                return False

            return True

        if not 6 <= len(tin) <= 15:
            messages.append(ctx.t("messages.tin.length"))

            return False

        return True

    return Check("tin", passes)


def _country_code(data: dict[str, Any], company: dict[str, Any] | None) -> str | None:
    """Country::find($request->integer('country_id'))?->code ?? страна компании."""
    raw = data.get("country_id")

    try:
        key = int(str(raw).strip()) if raw is not None and not isinstance(raw, dict | list) else 0
    except ValueError:
        key = 0

    for country_id in (key, company["country_id"] if company else None):
        if country_id:
            rows = _rows("select code from countries where id = %s", [country_id])

            if rows:
                return str(rows[0]["code"])

    return None


def _unique_tin(company_id: int | None) -> Check:
    """Rule::unique('companies', 'tin')->ignore($user->company_id)->whereNull('deleted_at')."""

    def passes(value: Any) -> bool:  # noqa: ANN401
        sql = "select count(*) as n from companies where tin = %s and deleted_at is null"
        params: list[Any] = [str(value)]

        if company_id is not None:
            sql += " and id <> %s"
            params.append(company_id)

        return int(_rows(sql, params)[0]["n"]) == 0

    return Check("unique", passes)


def _search_text(company: dict[str, Any]) -> dict[str, Any]:
    """Company saving: search_text из названия и юридического имени."""
    text = f"{company.get('name') or ''} {company.get('legal_name') or ''}".strip()

    return {"search_text": index(text)}


def _slug(name: str) -> str:
    """Company::makeSlug: свободный адрес, в том числе среди удалённых."""
    base = slugify(name) or "company"
    slug, i = base, 2

    while _rows("select 1 from companies where slug = %s limit 1", [slug]):
        slug = f"{base}-{i}"
        i += 1

    return slug


@form("PATCH")
def update(request: HttpRequest) -> HttpResponse:
    """CompanyProfileController::update."""
    ctx = action(request)
    assert ctx.user is not None
    data = input_of(request)
    company = company_of(ctx)
    year = datetime.now(UTC).year
    tin_messages: list[str] = []
    rules: dict[str, list[str | Check]] = {
        "name": ["required", "string", "min:2", "max:190"],
        "legal_name": ["nullable", "string", "max:255"],
        "tin": [
            "nullable",
            "string",
            "max:20",
            _tin(ctx, _country_code(data, company), tin_messages),
            _unique_tin(ctx.user["company_id"]),
        ],
        "country_id": ["nullable", _exists("countries")],
        "city_id": ["nullable", _exists("cities")],
        "address": ["nullable", "string", "max:255"],
        "description": ["nullable", "string", "max:5000"],
        "website": ["nullable", "string", "max:190"],
        "founded_year": ["nullable", "integer", f"between:1850,{year}"],
        "employees_range": ["nullable", "string", "max:20"],
        "type": ["nullable", "string", "max:30"],
        "custom_category": ["nullable", "string", "max:80"],
        "primary_role": ["nullable", "in:supplier,buyer,both"],
        "is_it_provider": ["nullable", "boolean"],
        "it_specializations": ["nullable", "array", f"max:{len(SERVICE_TYPES)}"],
        "it_specializations.*": ["in:" + ",".join(SERVICE_TYPES)],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "name.required": ctx.t("messages.company.name_required"),
            "founded_year.between": ctx.t("messages.company.founded_between", year=year),
            "tin.unique": ctx.t("messages.company.tin_unique"),
        },
    )

    # Текст ошибки правила Tin выбирает само правило
    if "tin" in errors and tin_messages:
        errors["tin"] = [tin_messages[0] if m == "validation.tin" else m for m in errors["tin"]]

    if errors:
        return invalid(ctx, errors)

    fields = validated(data, rules)

    # Заполненные сведения здесь не меняются — только из настроек
    # профиля и раз в полгода (CompanyInfoController у Laravel)
    locked = changed_profile_fields(company, fields) if company is not None else []

    if locked:
        return invalid(ctx, {f: [ctx.t("messages.company.change_in_settings")] for f in locked})

    if company is None:
        _create(ctx, fields)
        flash(ctx, "success", ctx.t("messages.company.created"))

        return redirect(ctx, ctx.url("/cabinet/company"))

    eloquent.save(
        ctx,
        "companies",
        company,
        fields,
        section="companies",
        model="Company",
        saving=_search_text,
        casts=CASTS,
    )
    flash(ctx, "success", ctx.t("messages.company.saved"))

    return back(ctx)


def _create(ctx: Context, fields: dict[str, Any]) -> None:
    """Company::create([...$data, 'status' => 'active']), затем владелец — пользователь."""
    assert ctx.user is not None
    row: dict[str, Any] = {**fields, "status": "active"}
    row.update(_search_text(row))
    row["slug"] = fields.get("slug") or _slug(str(fields["name"]))
    now = _stamp(eloquent.now())
    row.update(updated_at=now, created_at=now)
    columns = list(row)

    with allowed_writes("companies"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into companies ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [eloquent._written(CASTS.get(c), row[c]) for c in columns],
        )
        company_id = cursor.fetchone()[0]

    row["id"] = company_id
    # getAttributes(): массив — текстом, как его держит модель после записи
    after = {c: eloquent._written(CASTS.get(c), v) for c, v in row.items()}
    eloquent.journal(ctx, "created", "companies", "Company", row, {"after": after})

    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    eloquent.save(
        ctx,
        "users",
        user,
        {"company_id": company_id, "company_role": "owner"},
        section="users",
        model="User",
    )


def page(request: HttpRequest) -> HttpResponse:
    """/cabinet/company: GET — страница (cabinet.company_page), PATCH — правка."""
    from savdex.web.cabinet import company_page

    if request.method == "PATCH":
        return update(request)

    return company_page(request)


# ── Логотип и обложка (этап 5, шаг 34) ─────────────────────────────


def _upload(request: HttpRequest, field: str, size: Any, saved: str) -> HttpResponse:  # noqa: ANN401
    """CompanyProfileController::uploadLogo / uploadCover (throttle:30,60)."""
    from savdex.web import image_store

    ctx = action(request, throttle=30, throttle_minutes=60, throttle_prefix=f"company-{field}")
    company = company_of(ctx)

    if company is None:
        flash(ctx, "error", ctx.t("messages.company.fill_first"))

        return back(ctx)

    data = {**input_of(request), **request.FILES.dict()}
    errors = validate(
        data,
        {field: ["required", "file", "mimes:jpg,jpeg,png,webp", "max:8192"]},
        ctx.locale,
        {
            f"{field}.required": ctx.t("messages.file.required"),
            f"{field}.mimes": ctx.t("messages.image.mimes"),
            f"{field}.max": ctx.t("messages.image.max"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    try:
        path = image_store.store(data[field].read(), f"companies/{company['id']}", size)
    except image_store.UnreadableImageError:
        flash(ctx, "error", ctx.t("messages.image.unreadable"))

        return back(ctx)

    column = f"{field}_path"
    previous = company[column]
    eloquent.save(
        ctx,
        "companies",
        company,
        {column: path},
        section="companies",
        model="Company",
        saving=_search_text,
        casts=CASTS,
    )
    image_store.delete(previous)
    flash(ctx, "success", ctx.t(saved))

    return back(ctx)


def _remove(request: HttpRequest, field: str, deleted: str) -> HttpResponse:
    """CompanyProfileController::removeLogo / removeCover."""
    from savdex.web import image_store

    ctx = action(request)
    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    column = f"{field}_path"
    image_store.delete(company[column])
    eloquent.save(
        ctx,
        "companies",
        company,
        {column: None},
        section="companies",
        model="Company",
        saving=_search_text,
        casts=CASTS,
    )
    flash(ctx, "success", ctx.t(deleted))

    return back(ctx)


@form()
def upload_logo(request: HttpRequest) -> HttpResponse:
    from savdex.web import image_store

    return _upload(request, "logo", image_store.LOGO, "messages.company.logo_saved")


@form("DELETE")
def remove_logo(request: HttpRequest) -> HttpResponse:
    return _remove(request, "logo", "messages.company.logo_deleted")


@form()
def upload_cover(request: HttpRequest) -> HttpResponse:
    from savdex.web import image_store

    return _upload(request, "cover", image_store.COVER, "messages.company.cover_saved")


@form("DELETE")
def remove_cover(request: HttpRequest) -> HttpResponse:
    return _remove(request, "cover", "messages.company.cover_deleted")


def logo(request: HttpRequest) -> HttpResponse:
    """/cabinet/company/logo: POST — загрузить, DELETE — убрать."""
    return remove_logo(request) if request.method == "DELETE" else upload_logo(request)


def cover(request: HttpRequest) -> HttpResponse:
    """/cabinet/company/cover: POST — загрузить, DELETE — убрать."""
    return remove_cover(request) if request.method == "DELETE" else upload_cover(request)
