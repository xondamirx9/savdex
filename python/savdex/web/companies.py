"""
Каталог компаний /companies — копия CompanyController::index.

Активные компании с поиском (search_text в обеих графиках или ИНН),
фильтрами типа, страны, проверки и возраста на площадке, по 12 на
странице. Рядом с каждым фильтром — сколько компаний даст каждый его
вариант при остальных фильтрах (filtered с $ignore). Ничего не пишет;
под throttle:120,1 — счётчик общий с Laravel (savdex/web/throttle.py).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.web import inertia, news, paginator, search_text, ui
from savdex.web.directory import _named, listed_countries, logo_url, type_label, type_options
from savdex.web.home import _utc, completeness
from savdex.web.phpquery import Array, laravel_input, text
from savdex.web.seo import Seo
from savdex.web.shared import Context, initials
from savdex.web.throttle import throttled

PER_PAGE = 12

#: Company::VERIFICATION_COMPANY
VERIFIED = 2

AGES = ("lt1", "1to5", "gt5")

#: Порядок ключей $request->only([...])
FILTERS = ("q", "type", "verified", "country", "age")

_TRUE = ("1", "true", "on", "yes")

#: trim() у PHP
_TRIM = " \t\n\r\0\x0b"


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _count(where: str, params: list[Any]) -> int:
    return int(_rows(f"select count(*) as n from companies c where {where}", params)[0]["n"])


def sub_years(moment: datetime, years: int) -> datetime:
    """Carbon::subYears: 29 февраля в невисокосный год — 1 марта."""
    try:
        return moment.replace(year=moment.year - years)
    except ValueError:
        return moment.replace(year=moment.year - years, month=3, day=1)


class Filters:
    """CompanyController::filtered — условия отбора, по одному фильтру можно выключить."""

    def __init__(self, query: Array, now: datetime) -> None:
        self.query = query
        self.now = now.replace(microsecond=0, tzinfo=None)

    def string(self, key: str) -> str:
        """$request->string(): null и массив — пустая строка."""
        value = self.query.get(key)

        return text(value) if isinstance(value, str) else ""

    def boolean(self, key: str) -> bool:
        return self.string(key).strip().lower() in _TRUE

    def where(self, ignore: str = "") -> tuple[str, list[Any]]:
        def value(key: str) -> str:
            return "" if ignore == key else self.string(key)

        where = ["c.status = 'active'", "c.deleted_at is null"]
        params: list[Any] = []

        # when(): «0» — ложь, как пустая строка
        if (term := value("q")) not in ("", "0"):
            where.append("(c.search_text like %s or c.tin like %s)")
            params += [f"%{search_text.normalize(term)}%", f"%{term.strip(_TRIM)}%"]

        if (kind := value("type")) not in ("", "0"):
            where.append("c.type = %s")
            params.append(kind)

        if (code := value("country")) not in ("", "0"):
            where.append(
                "exists (select 1 from countries k where k.id = c.country_id and k.code = %s)"
            )
            params.append(code.lower())

        if ignore != "verified" and self.boolean("verified"):
            where.append(f"c.verification_level >= {VERIFIED}")

        if (age := value("age")) not in ("", "0"):
            clause, extra = self.by_age(age)
            where += clause
            params += extra

        return " and ".join(where), params

    def by_age(self, age: str) -> tuple[list[str], list[Any]]:
        """CompanyController::byAge; неизвестное значение — без условия."""
        year, five = sub_years(self.now, 1), sub_years(self.now, 5)

        if age == "lt1":
            return ["c.created_at >= %s"], [year]

        if age == "1to5":
            return ["c.created_at between %s and %s"], [five, year]

        if age == "gt5":
            return ["c.created_at < %s"], [five]

        return [], []


def month_year(moment: datetime | None, locale: str) -> str | None:
    """DateHelper::monthYear: по-русски — родительный падеж («сентября 2026»)."""
    if moment is None:
        return None

    moment = _utc(moment) or moment

    if locale == "ru":
        return f"{news._GENITIVE[moment.month - 1]} {moment.year}"

    return ui.date_template(locale, "month_year", moment.month).replace("{y}", str(moment.year))


#: Домен с зоной из букв: «cement.uz», «сайт.рф», «xn--80aswg.xn--p1ai»
_DOMAIN = re.compile(r"^(?:[^\W_](?:[\w-]*[^\W_])?\.)+(?:[^\W\d_]{2,}|xn--[a-z0-9-]+)\.?$")


def has_domain(url: str | None) -> bool:
    """Адрес ведёт на настоящий домен: «https://fwfwfef» прошёл бы правило url, а не откроется."""
    host = urlsplit(url or "").hostname or ""

    return bool(_DOMAIN.match(host))


def website_url(site: str | None) -> str | None:
    """Company::websiteUrl. Без настоящего домена — None: кнопка «Сайт компании» не появится."""
    site = (site or "").strip(_TRIM)

    if site == "":
        return None

    url = site if site.startswith(("http://", "https://")) else "https://" + site

    return url if has_domain(url) else None


def card(
    ctx: Context,
    c: dict[str, Any],
    options: dict[str, str],
    cities: dict[int, str],
    codes: dict[int, str],
) -> dict[str, Any]:
    return {
        "slug": c["slug"],
        "name": c["name"],
        "tin": c["tin"],
        "type": c["type"],
        "type_label": type_label(ctx, c, options),
        "city": cities.get(c["city_id"]) if c["city_id"] is not None else None,
        "country": codes.get(c["country_id"]) if c["country_id"] is not None else None,
        "verification_level": c["verification_level"],
        "rating": float(c["rating"] or 0),
        "reviews_count": c["reviews_count"],
        "trust": completeness(c, bool(c["has_approved_documents"])),
        "created_at": month_year(c["created_at"], ctx.locale),
        "initials": initials(c["name"]),
        "logo": logo_url(ctx, c["logo_path"]),
        "website": website_url(c["website"]),
    }


def _type_options(ctx: Context, filters: Filters) -> list[dict[str, Any]]:
    where, params = filters.where("type")
    counts = {
        r["type"]: int(r["total"])
        for r in _rows(
            f"select c.type, count(*) as total from companies c where {where} "
            "and c.type is not null group by c.type",
            params,
        )
    }
    selected = filters.string("type")

    return [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in type_options(ctx.locale).items()
        if counts.get(value, 0) > 0 or value == selected
    ]


def _country_options(ctx: Context, filters: Filters) -> list[dict[str, Any]]:
    where, params = filters.where("country")
    counts = {
        r["country_id"]: int(r["total"])
        for r in _rows(
            f"select c.country_id, count(*) as total from companies c where {where} "
            "and c.country_id is not null group by c.country_id",
            params,
        )
    }
    selected = filters.string("country").lower()

    return [
        {"code": c["code"], "name": c["name"], "count": counts.get(c["id"], 0)}
        for c in listed_countries(ctx.locale)
        if counts.get(c["id"], 0) > 0 or c["code"] == selected
    ]


def _age_counts(filters: Filters) -> dict[str, int]:
    where, params = filters.where("age")
    counts = {}

    for age in AGES:
        clause, extra = filters.by_age(age)
        counts[age] = _count(" and ".join([where, *clause]), params + extra)

    return counts


def _only(query: Array) -> dict[str, Any] | list[Any]:
    """$request->only([...]): есть в запросе — попадает, даже null; пусто — []."""
    picked = {key: query[key] for key in FILTERS if key in query}

    return {k: text(v) if isinstance(v, str) else v for k, v in picked.items()} or []


def index(request: HttpRequest) -> HttpResponse:
    """CompanyController::index — под throttle:120,1."""
    return throttled(request, 120, _index)


def _index(ctx: Context) -> HttpResponse:
    query = laravel_input(ctx.query)
    filters = Filters(query, datetime.now(UTC))
    where, params = filters.where()

    total = _count(where, params)
    current, offset = paginator.offset(ctx, PER_PAGE)
    rows = _rows(
        "select c.*, exists (select 1 from company_documents d where d.company_id = c.id "
        "and d.moderation_status = 'approved') as has_approved_documents "
        f"from companies c where {where} "
        "order by c.verification_level desc, c.rating desc, c.id limit %s offset %s",
        [*params, PER_PAGE, offset],
    )
    page = paginator.Page(rows, total, PER_PAGE, current)
    options = type_options(ctx.locale)
    cities = _named("cities", ctx.locale)
    codes = {r["id"]: r["code"] for r in _rows("select id, code from countries")}

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("seo.companies_title"))
    seo.description(ctx.t("seo.companies_description", total=total))
    seo.canonical(ctx.url("companies"))
    seo.noindex = any(key in query for key in FILTERS) or current > 1

    verified_where, verified_params = filters.where("verified")
    active = "c.status = 'active' and c.deleted_at is null"

    return inertia.render(
        ctx,
        "companies/Index",
        {
            "companies": paginator.to_array(
                ctx, page, lambda c: card(ctx, c, options, cities, codes)
            ),
            "filters": _only(query),
            "types": _type_options(ctx, filters),
            "countries": _country_options(ctx, filters),
            "facets": {
                "ages": _age_counts(filters),
                "verified": _count(
                    f"{verified_where} and c.verification_level >= {VERIFIED}", verified_params
                ),
            },
            "stats": {
                "total": _count(active, []),
                "verified": _count(f"{active} and c.verification_level >= {VERIFIED}", []),
            },
        },
        seo,
    )
