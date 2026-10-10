"""
Данные компании в настройках профиля — копия Cabinet\\CompanyInfoController
(этап 5, шаг 51). Ответы — JSON: блок на странице настроек грузится и
сохраняется отдельными запросами.

Заполненное меняется раз в полгода (Company::PROFILE_COOLDOWN_MONTHS):
заполнить пустое можно когда угодно, смена заполненного ставит
profile_changed_at и закрывает смену до конца срока. Пока срок идёт,
владелец пишет в поддержку — обращение с сообщением уходит в админку.

Сверка с настоящим Laravel — tests/test_web_company_info_actions.py.
"""

from __future__ import annotations

import calendar
import math
from datetime import UTC, datetime
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import SERVICE_TYPES, _rows, company_of
from savdex.web.city_choice import city_in_country, resolve_other
from savdex.web.company_profile_actions import (
    CASTS,
    PROFILE_FIELDS,
    _country_code,
    _country_id,
    _search_text,
    _tin,
    _unique_tin,
    changed_profile_fields,
    locked_fields,
    normalize_tin,
)
from savdex.web.forms import action, input_of
from savdex.web.listing_actions import _stamp
from savdex.web.resume_actions import _exists
from savdex.web.review_actions import _php_round
from savdex.web.seo import php_json
from savdex.web.shared import Context
from savdex.web.validation import Check, validate, validated

#: Company::PROFILE_COOLDOWN_MONTHS
COOLDOWN_MONTHS = 6


def _json(data: Any, status: int = 200) -> HttpResponse:  # noqa: ANN401
    """response()->json(): json_encode без флагов — «/» и юникод экранированы."""
    return HttpResponse(php_json(data), status=status, content_type="application/json")


def _add_months(moment: datetime, months: int) -> datetime:
    """Carbon::addMonthsNoOverflow: 31 августа + 6 мес. — 28/29 февраля."""
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])

    return moment.replace(year=year, month=month, day=day)


def locked_until(company: dict[str, Any]) -> datetime | None:
    """Company::profileLockedUntil: до какого момента заполненное менять нельзя."""
    changed = company.get("profile_changed_at")

    # Физлицо и фрилансер меняют сведения когда угодно
    if changed is None or not locked_fields(company):
        return None

    # Время в столбце — UTC без пояса, как и eloquent.now()
    until = _add_months(changed.replace(tzinfo=None), COOLDOWN_MONTHS)

    return until if until > eloquent.now().replace(tzinfo=None) else None


def _cooldown(company: dict[str, Any]) -> dict[str, Any]:
    """
    Плашка над формой (#252): сколько дней ждать, какая часть срока прошла
    и с какого дня откроется следующая смена, если сохранить сейчас.
    now() у Laravel — с долями секунды, diffInSeconds — дробное.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    until = locked_until(company)
    changed = company.get("profile_changed_at")
    progress = None

    if until is not None and changed is not None:
        changed = changed.replace(tzinfo=None)
        passed = (now - changed).total_seconds()
        whole = max(1.0, (until - changed).total_seconds())
        progress = _php_round(min(1.0, max(0.0, passed / whole)), 3)

    return {
        "days_left": math.ceil((until - now).total_seconds() / 86400) if until else None,
        "cooldown_progress": progress,
        "next_if_changed": _date(_add_months(now, COOLDOWN_MONTHS)),
    }


def _date(moment: datetime | None) -> str | None:
    """translatedFormat('d.m.Y'): одни цифры, от языка не зависят."""
    return None if moment is None else moment.strftime("%d.%m.%Y")


def _owned(ctx: Context) -> dict[str, Any] | None:
    """Компания владельца; не владелец или без компании — 403."""
    assert ctx.user is not None
    company = company_of(ctx)
    role = _rows("select company_role from users where id = %s", [ctx.user["id"]])[0]

    if company is None or role["company_role"] != "owner":
        return None

    return company


def _forbidden(ctx: Context) -> HttpResponse:
    from savdex.web.views import error

    return error(ctx, 403)


def _payload(ctx: Context, company: dict[str, Any]) -> dict[str, Any]:
    from savdex.web.directory import _named, listed_countries

    specializations = company["it_specializations"]

    if isinstance(specializations, str):
        import json

        specializations = json.loads(specializations)

    cities = _named("cities", ctx.locale)

    return {
        "company": {
            "name": company["name"],
            "legal_name": company["legal_name"],
            "tin": company["tin"],
            "country_id": company["country_id"],
            "city_id": company["city_id"],
            "address": company["address"],
            "employees_range": company["employees_range"],
            "founded_year": company["founded_year"],
            "type": company["type"],
            "description": company["description"],
            "is_it_provider": bool(company["is_it_provider"]),
            "it_specializations": specializations or [],
        },
        "locked_until": _date(locked_until(company)),
        "locked_fields": list(locked_fields(company)),
        "changed_at": _date(company.get("profile_changed_at")),
        "cooldown_months": COOLDOWN_MONTHS,
        **_cooldown(company),
        "countries": [
            {"id": c["id"], "name": c["name"], "code": c["code"]}
            for c in listed_countries(ctx.locale)
        ],
        "cities": [
            {"id": c["id"], "name": cities[c["id"]], "country_id": c["country_id"]}
            # Свой «другой город» (скрытый, city_choice.py) — тоже в списке
            for c in _rows(
                "select id, country_id from cities where is_active or id = %s order by sort, id",
                [company["city_id"]],
            )
        ],
        "serviceTypes": {code: ctx.t(f"it_tasks.types.{code}") for code in SERVICE_TYPES},
    }


def _invalid(errors: dict[str, list[str]]) -> HttpResponse:
    """Ошибки проверки: первая — в message, все — в errors."""
    first = next(iter(errors.values()))[0]

    return _json({"message": first, "errors": errors}, 422)


@form("GET")
def show(request: HttpRequest) -> HttpResponse:
    """CompanyInfoController::show."""
    ctx = action(request)
    company = _owned(ctx)

    if company is None:
        return _forbidden(ctx)

    return _json(_payload(ctx, company))


def _rules(
    ctx: Context, data: dict[str, Any], company: dict[str, Any], tin_messages: list[str]
) -> dict[str, list[str | Check]]:
    """CompanyProfileController::rules — только сведения компании."""
    year = datetime.now().year

    return {
        "name": ["required", "string", "min:2", "max:190"],
        "legal_name": ["nullable", "string", "max:255"],
        "tin": [
            "nullable",
            "string",
            "max:20",
            _tin(ctx, _country_code(data, company), tin_messages),
            _unique_tin(company["id"], _country_id(data, company)),
        ],
        "country_id": ["nullable", _exists("countries")],
        "city_id": ["nullable", _exists("cities"), city_in_country(data, company)],
        "address": ["nullable", "string", "max:255"],
        "description": ["nullable", "string", "max:5000"],
        "founded_year": ["nullable", "integer", f"between:1850,{year}"],
        "employees_range": ["nullable", "string", "max:20"],
        "type": ["nullable", "string", "max:30"],
        "is_it_provider": ["nullable", "boolean"],
        "it_specializations": ["nullable", "array", f"max:{len(SERVICE_TYPES)}"],
        "it_specializations.*": ["in:" + ",".join(SERVICE_TYPES)],
    }


@form("PATCH")
def update(request: HttpRequest) -> HttpResponse:
    """CompanyInfoController::update (throttle:20,1,company-info)."""
    ctx = action(request, throttle=20, throttle_prefix="company-info")
    company = _owned(ctx)

    if company is None:
        return _forbidden(ctx)

    data = dict(input_of(request))
    normalize_tin(data, company)
    resolve_other(data)
    tin_messages: list[str] = []
    rules = _rules(ctx, data, company, tin_messages)
    year = datetime.now().year
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "name.required": ctx.t("messages.company.name_required"),
            "founded_year.between": ctx.t("messages.company.founded_between", year=year),
            "tin.unique": ctx.t("messages.company.tin_unique"),
            "city_id.city_country": ctx.t("messages.company.city_country"),
        },
    )

    if "tin" in errors and tin_messages:
        errors["tin"] = [tin_messages[0] if m == "validation.tin" else m for m in errors["tin"]]

    if errors:
        return _invalid(errors)

    fields = validated(data, rules)

    # Пустое в обязательной колонке — без изменений (было 500)
    if "is_it_provider" in fields and fields["is_it_provider"] is None:
        del fields["is_it_provider"]
    changed = changed_profile_fields(company, fields)
    until = locked_until(company)

    if changed and until is not None:
        return _json(
            {
                "message": ctx.t("cabinet.settings.company_locked", date=_date(until)),
                "errors": {f: [ctx.t("cabinet.settings.company_locked_field")] for f in changed},
            },
            422,
        )

    values = {k: v for k, v in fields.items() if k in PROFILE_FIELDS}

    # Отсчёт полугода — только от смены заполненного
    if changed:
        values["profile_changed_at"] = eloquent.now()

    eloquent.save(
        ctx,
        "companies",
        company,
        values,
        section="companies",
        model="Company",
        saving=_search_text,
        casts=CASTS,
    )
    fresh = _rows("select * from companies where id = %s", [company["id"]])[0]

    return _json({**_payload(ctx, fresh), "message": ctx.t("messages.company.saved")})


@form()
def support(request: HttpRequest) -> HttpResponse:
    """CompanyInfoController::support (throttle:5,60,company-info-support): в поддержку."""
    ctx = action(request, throttle=5, throttle_minutes=60, throttle_prefix="company-info-support")
    company = _owned(ctx)

    if company is None:
        return _forbidden(ctx)

    assert ctx.user is not None
    data = input_of(request)
    rules: dict[str, list[str | Check]] = {"message": ["required", "string", "min:10", "max:3000"]}
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "message.required": ctx.t("cabinet.settings.company_support_required"),
            "message.min": ctx.t("cabinet.settings.company_support_short"),
        },
    )

    if errors:
        return _invalid(errors)

    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    until = locked_until(company)
    now = _stamp(eloquent.now())
    body = (
        f"{validated(data, rules)['message']}\n\n— Компания #{company['id']} «{company['name']}»"
        + (f", смена данных доступна с {until.strftime('%d.%m.%Y')}" if until else "")
    )
    ticket: dict[str, Any] = {
        "subject": ("Смена данных компании: " + company["name"])[:200],
        "user_id": user["id"],
        "company_id": company["id"],
        "author_name": user["name"],
        "author_email": user["email"],
        "status": "open",
        "channel": "form",
        "priority": "normal",
        "last_reply_at": now,
        # Ticket::saving: не закрытое — без даты закрытия
        "closed_at": None,
        "updated_at": now,
        "created_at": now,
    }

    with transaction.atomic():
        # Обращения — таблицы Django (этап 6, раздел «Обращения»)
        with connection.cursor() as cursor:
            cursor.execute(
                f"insert into support_tickets ({', '.join(ticket)}) "
                f"values ({', '.join(['%s'] * len(ticket))}) returning id",
                list(ticket.values()),
            )
            ticket["id"] = cursor.fetchone()[0]
            cursor.execute(
                "insert into support_messages (ticket_id, author_id, from_staff, is_internal, "
                "body, created_at, updated_at) values (%s, %s, false, false, %s, %s, %s)",
                [ticket["id"], user["id"], body, now, now],
            )

        eloquent.journal(ctx, "created", "support", "Support\\Ticket", ticket, {"after": ticket})

    return _json({"message": ctx.t("cabinet.settings.company_support_sent")})


def info(request: HttpRequest) -> HttpResponse:
    """/cabinet/settings/company-info: GET — сведения, PATCH — сохранить."""
    if request.method == "PATCH":
        return update(request)

    return show(request)
