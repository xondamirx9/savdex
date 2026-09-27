"""
Лента «IT-услуги» (дополнительные услуги) — копия ItTaskController::index.

Открытые задачи компаний (или выполненные — «done»), с поиском по
search_text, фильтрами направления, города, проверки и бюджета, по 20
на странице. Ничего не пишет: счётчик просмотров — у страницы задачи,
она пока у Laravel. Машинный перевод заголовка и описания — общий
ContentTranslation (savdex/web/content.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.web import content, inertia, paginator, search_text
from savdex.web.directory import _named, logo_url
from savdex.web.home import _utc
from savdex.web.news import day_month_year
from savdex.web.phpquery import laravel_input, php_int, text
from savdex.web.request import context
from savdex.web.resumes import SERVICE_SECTIONS, section_tree
from savdex.web.seo import Seo, _limit
from savdex.web.shared import Context, initials

PER_PAGE = 20

#: ItTask::SERVICE_TYPES — конечные виды (в колонке service_type)
SERVICE_TYPES = (
    "web", "mobile", "erp", "integration", "design", "automation", "support",
    "logistics", "hr", "customs", "accounting", "other",
)  # fmt: skip

#: $request->boolean(): FILTER_VALIDATE_BOOLEAN
_TRUE = ("1", "true", "on", "yes")


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def filterable_types() -> list[str]:
    """ItTask::filterableTypes: конечные виды и направления."""
    return [*SERVICE_TYPES, *SERVICE_SECTIONS]


def types_under(code: str) -> list[str]:
    """ItTask::typesUnder: у направления — его виды, у вида — он сам."""
    return SERVICE_SECTIONS.get(code) or [code]


def _date(moment: Any, locale: str) -> str | None:  # noqa: ANN401
    """DateHelper::dayMonthYear: нет даты — null; срок — дата без времени."""
    if moment is None:
        return None

    if not isinstance(moment, datetime):
        moment = datetime(moment.year, moment.month, moment.day, tzinfo=UTC)

    return day_month_year(_utc(moment), locale)


def result_host(url: str) -> str:
    """parse_url(PHP_URL_HOST) без «www.»; регистр не меняется, как у PHP."""
    rest = url.split("://", 1)[1] if "://" in url else (url[2:] if url.startswith("//") else "")
    netloc = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = netloc.rsplit("@", 1)[-1]

    if not host.startswith("["):
        host = host.split(":", 1)[0]

    return host[4:] if host.startswith("www.") else host


def _company(
    ctx: Context, row: dict[str, Any], prefix: str, cities: dict[int, str]
) -> dict[str, Any]:
    card = {
        "name": row[f"{prefix}_name"],
        "slug": row[f"{prefix}_slug"],
        "initials": initials(row[f"{prefix}_name"]),
        "logo": logo_url(ctx, row[f"{prefix}_logo"]),
    }

    if prefix == "company":
        card["verified"] = row["company_verification"] >= 2
        city = row["company_city"]
        card["city"] = cities.get(city) if city is not None else None

    return card


def card(
    ctx: Context, row: dict[str, Any], translations: content.Translations, cities: dict[int, str]
) -> dict[str, Any]:
    """ItTaskController::card."""
    completed = row["status"] == "completed"
    description = (translations.text(row["description"]) or "").strip(" \t\n\r\0\x0b")
    url = row["result_url"]

    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": translations.text(row["title"]),
        "excerpt": _limit(description, 180, "..."),
        "service_type": row["service_type"],
        "service_label": ctx.t(f"it_tasks.types.{row['service_type']}"),
        "stack": row["stack"] or [],
        "budget_type": row["budget_type"],
        "budget_from": float(row["budget_from"]) if row["budget_from"] is not None else None,
        "budget_to": float(row["budget_to"]) if row["budget_to"] is not None else None,
        "currency": row["currency"],
        "deadline": _date(row["deadline_at"], ctx.locale),
        "published": _date(row["published_at"], ctx.locale),
        "responses": row["responses_count"],
        "active": row["status"] == "active",
        "completed": completed,
        "completed_on": _date(row["completed_at"], ctx.locale),
        "result_url": url if completed else None,
        "result_host": result_host(url) if completed and url is not None else None,
        "result_summary": row["result_summary"] if completed else None,
        "contractor": _company(ctx, row, "contractor", cities)
        if completed and row["contractor_name"] is not None
        else None,
        "company": _company(ctx, row, "company", cities),
    }


def _cities(locale: str) -> list[dict[str, Any]]:
    """
    Города, где есть компании с открытыми задачами; нет ни одного —
    все города, чтобы фильтр не пропадал с панели.
    """
    names = _named("cities", locale)
    taken = _rows(
        "select distinct c.city_id from companies c where c.status = 'active' "
        "and c.deleted_at is null and c.city_id is not null "
        "and c.id in (select t.company_id from it_tasks t where t.status = 'active')"
    )
    ids = [r["city_id"] for r in taken]
    query = "select id from cities where is_active"

    if ids:
        query += " and id in (" + ", ".join(["%s"] * len(ids)) + ")"

    rows = _rows(query + " order by id", ids)

    return sorted(
        [{"id": r["id"], "name": names[r["id"]]} for r in rows], key=lambda item: item["name"]
    )


def _viewer(ctx: Context) -> dict[str, bool]:
    user = ctx.user

    if user is None:
        return {"guest": True, "provider": False}

    provider = False

    if user["company_id"] is not None:
        rows = _rows(
            "select is_it_provider from companies where id = %s and deleted_at is null",
            [user["company_id"]],
        )
        provider = bool(rows and rows[0]["is_it_provider"])

    return {"guest": False, "provider": provider}


def index(request: HttpRequest) -> HttpResponse:
    """ItTaskController::index."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    query = laravel_input(ctx.query)

    def string(key: str) -> str:
        value = query.get(key)

        return text(value) if isinstance(value, str) else ""

    def boolean(key: str) -> bool:
        return string(key).strip().lower() in _TRUE

    term = string("q")
    kind = string("type")
    kind = kind if kind in filterable_types() else ""
    done = boolean("done")
    city = php_int(string("city"), 0)
    verified = boolean("verified")
    with_budget = boolean("with_budget")

    where = [
        "t.status = %s",
        "c.status = 'active'",
        "c.deleted_at is null",
    ]
    params: list[Any] = ["completed" if done else "active"]

    if term != "":
        where.append("t.search_text like %s")
        params.append(f"%{search_text.normalize(term)}%")

    if kind != "":
        types = types_under(kind)
        where.append("t.service_type in (" + ", ".join(["%s"] * len(types)) + ")")
        params += types

    if city != 0:
        where.append("c.city_id = %s")
        params.append(city)

    if verified:
        where.append("c.verification_level >= 2")

    if with_budget:
        where.append("t.budget_type != 'negotiable'")

    condition = " and ".join(where)
    source = "from it_tasks t join companies c on c.id = t.company_id"
    total = _rows(f"select count(*) as n {source} where {condition}", params)[0]["n"]
    current, offset = paginator.offset(ctx, PER_PAGE)
    order = "t.completed_at desc" if done else "t.published_at desc"
    rows = _rows(
        "select t.*, c.name as company_name, c.slug as company_slug, "
        "c.logo_path as company_logo, c.verification_level as company_verification, "
        "c.city_id as company_city, k.name as contractor_name, k.slug as contractor_slug, "
        f"k.logo_path as contractor_logo {source} "
        "left join companies k on k.id = t.contractor_company_id and k.deleted_at is null "
        f"where {condition} order by {order}, t.id desc limit %s offset %s",
        [*params, PER_PAGE, offset],
    )
    page = paginator.Page(rows, total, PER_PAGE, current)
    translations = content.Translations(ctx.locale)
    cities = _named("cities", ctx.locale)

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("it_tasks.meta_title")).description(ctx.t("it_tasks.meta_description"))
    seo.canonical(ctx.url("it-services"))
    seo.noindex = term != "" or kind != "" or city != 0 or verified or with_budget or current > 1

    return inertia.render(
        ctx,
        "it-tasks/Index",
        {
            "tasks": paginator.to_array(ctx, page, lambda r: card(ctx, r, translations, cities)),
            "filters": {
                "q": term,
                "type": kind,
                "done": done,
                "city": city or None,
                "verified": verified,
                "with_budget": with_budget,
            },
            "types": section_tree(ctx),
            "cities": _cities(ctx.locale),
            "total": total,
            "viewer": _viewer(ctx),
        },
        seo,
    )
