"""
«Страны» и «Партнёры» — копия PageController::countries и ::partners.

Порядок стран — как Country::listed: сперва поле sort, затем название
по правилам языка (Collator ICU у PHP). То же сравнение делает
PostgreSQL — collation «<язык>-x-icu», так что порядок совпадает без
отдельной библиотеки ICU в Python.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex import laravel_storage
from savdex.web import inertia
from savdex.web.request import context
from savdex.web.seo import Seo
from savdex.web.shared import Context, initials

#: PageController::COMPANIES_PER_COUNTRY
COMPANIES_PER_COUNTRY = 12

#: Company::FALLBACK_TYPES — если справочник типов пуст
FALLBACK_TYPES = {
    "manufacturer": "Производитель",
    "importer": "Импортёр",
    "distributor": "Дистрибьютор",
    "trader": "Торговая компания",
    "service": "Услуги",
}

LEGAL_FORMS = ("legal", "individual", "freelancer")


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


#: Справочники с названиями на языках: таблица → (таблица названий, ключ, запасное поле)
_DIRECTORIES = {
    "countries": ("country_translations", "country_id", "code"),
    "cities": ("city_translations", "city_id", "slug"),
}


def _named(table: str, locale: str) -> dict[int, str]:
    """name() справочника: язык посетителя, затем русский, затем код/slug."""
    names, key, fallback = _DIRECTORIES[table]
    rows = _rows(
        f"select r.id, r.{fallback} as fb, "
        f"(select name from {names} t where t.{key} = r.id and t.locale = %s) as own, "
        f"(select name from {names} t where t.{key} = r.id and t.locale = 'ru') as ru "
        f"from {table} r",
        [locale],
    )

    return {r["id"]: r["own"] or r["ru"] or r["fb"] for r in rows}


def type_options(locale: str) -> dict[str, str]:
    """Company::typeOptions: справочник типов (CompanyType::options) или запасной список."""
    rows = _rows(
        "select code, coalesce((select name from company_type_translations t where "
        "t.company_type_id = c.id and t.locale = %s), (select name from "
        "company_type_translations t where t.company_type_id = c.id and t.locale = 'ru'), "
        "code) as name from company_types c where is_active order by sort",
        [locale],
    )

    return {r["code"]: r["name"] for r in rows} or dict(FALLBACK_TYPES)


def type_label(ctx: Context, company: dict[str, Any], options: dict[str, str]) -> str | None:
    """Company::typeLabel."""
    if company["type"] is not None:
        label: str = options.get(company["type"], company["type"])

        return label

    if company["legal_form"] in ("individual", "freelancer"):
        form = company["legal_form"] if company["legal_form"] in LEGAL_FORMS else "legal"

        return ctx.t(f"legal_form.{form}")

    return None


def logo_url(ctx: Context, path: str | None) -> str | None:
    """Company::logoUrl: asset('storage/…'), если файл на месте."""
    if not path or not (laravel_storage.public_root() / path).is_file():
        return None

    return ctx.url("storage/" + path)


def _rating(value: Decimal | float | None) -> float:
    return float(value or 0)


def _seo(ctx: Context, key: str, path: str) -> Seo:
    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)

    return (
        seo.title(ctx.t(f"seo.{key}_title"))
        .description(ctx.t(f"seo.{key}_description"))
        .canonical(ctx.url(path))
    )


def listed_countries(locale: str) -> list[dict[str, Any]]:
    """Country::listed: активные, по sort, затем по названию (ICU)."""
    rows = _rows("select id, code, sort from countries where is_active")
    names = _named("countries", locale)
    # Порядок названий — по правилам языка, как Collator
    ordered = [
        r["name"]
        for r in _rows(
            f'select n as name from unnest(%s::text[]) as n order by n collate "{locale}-x-icu"',
            [sorted({names[r["id"]] for r in rows})],
        )
    ]
    rank = {name: i for i, name in enumerate(ordered)}

    for row in rows:
        row["name"] = names[row["id"]]

    return sorted(rows, key=lambda r: (r["sort"], rank[r["name"]]))


def countries(request: HttpRequest) -> HttpResponse:
    """PageController::countries."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    counts = {
        r["country_id"]: r["total"]
        for r in _rows(
            "select country_id, count(*) as total from companies where status = 'active' "
            "and deleted_at is null and country_id is not null group by country_id"
        )
    }
    options = type_options(ctx.locale)
    cities = _named("cities", ctx.locale)
    showcase: dict[int, list[dict[str, Any]]] = {}

    for c in _rows(
        "select * from (select m.*, row_number() over (partition by country_id order by "
        "verification_level desc, rating desc, id) as country_rank, (select count(*) from "
        "listings l where l.company_id = m.id and l.status = 'active' and l.deleted_at is null) "
        "as listings_count from companies m where m.status = 'active' and m.deleted_at is null "
        "and m.country_id is not null) companies where country_rank <= %s order by country_rank",
        [COMPANIES_PER_COUNTRY],
    ):
        showcase.setdefault(c["country_id"], []).append(
            {
                "slug": c["slug"],
                "name": c["name"],
                "type_label": type_label(ctx, c, options),
                "city": cities.get(c["city_id"]) if c["city_id"] else None,
                "verification_level": c["verification_level"],
                "rating": _rating(c["rating"]),
                "listings_count": int(c["listings_count"]),
                "initials": initials(c["name"]),
                "logo": logo_url(ctx, c["logo_path"]),
            }
        )

    listed = [
        {
            "code": c["code"],
            "name": c["name"],
            "companies": int(counts.get(c["id"], 0)),
            "items": showcase.get(c["id"], []),
        }
        for c in listed_countries(ctx.locale)
    ]
    # sortByDesc('companies') — устойчивая, при равенстве порядок listed
    listed.sort(key=lambda c: -c["companies"])

    return inertia.render(
        ctx,
        "Countries",
        {
            "countries": [c for c in listed if c["companies"] > 0],
            "planned": [c for c in listed if c["companies"] == 0],
        },
        _seo(ctx, "countries", "countries"),
    )


def partners(request: HttpRequest) -> HttpResponse:
    """PageController::partners."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    options = type_options(ctx.locale)
    cities = _named("cities", ctx.locale)
    country_names = _named("countries", ctx.locale)
    rows = _rows(
        "select m.*, (select count(*) from listings l where l.company_id = m.id and "
        "l.status = 'active' and l.deleted_at is null) as listings_count from companies m "
        "where m.status = 'active' and m.deleted_at is null and m.partner_tier in "
        "('general', 'partner') order by m.partner_sort, m.rating desc, m.id"
    )

    def present(c: dict[str, Any]) -> dict[str, Any]:
        return {
            "slug": c["slug"],
            "name": c["name"],
            "type_label": type_label(ctx, c, options),
            "city": cities.get(c["city_id"]) if c["city_id"] else None,
            "country": country_names.get(c["country_id"]) if c["country_id"] else None,
            "verification_level": c["verification_level"],
            "rating": _rating(c["rating"]),
            "reviews_count": c["reviews_count"],
            "listings_count": int(c["listings_count"]),
            "initials": initials(c["name"]),
            "logo": logo_url(ctx, c["logo_path"]),
        }

    def count(query: str) -> int:
        return int(_rows(query)[0]["n"])

    return inertia.render(
        ctx,
        "Partners",
        {
            "general": [present(c) for c in rows if c["partner_tier"] == "general"],
            "partners": [present(c) for c in rows if c["partner_tier"] == "partner"],
            "stats": {
                "total": count(
                    "select count(*) as n from companies where status = 'active' "
                    "and deleted_at is null"
                ),
                "verified": count(
                    "select count(*) as n from companies where status = 'active' "
                    "and deleted_at is null and verification_level >= 2"
                ),
                "listings": count(
                    "select count(*) as n from listings where status = 'active' "
                    "and deleted_at is null"
                ),
            },
        },
        _seo(ctx, "partners", "partners"),
    )
