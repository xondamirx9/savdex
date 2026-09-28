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

#: Tin::FAKE
FAKE_TINS = ("123456789", "987654321", "123123123")

#: Приведения Company для сравнения
CASTS = {"is_it_provider": "bool", "it_specializations": "json", "founded_year": "int"}


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
