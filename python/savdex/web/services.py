"""
Страница направления «Доп. услуг» (/services/<направление>) — копия
ServiceSectionController::show (этап 5, шаг 48).

Всё про одно направление: что это, сколько задач и исполнителей,
открытые и выполненные задачи, исполнители, у HR — ещё и резюме.
Ничего не пишет.
"""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, HttpResponse

from savdex.web import content, inertia, ui
from savdex.web.directory import _named, logo_url
from savdex.web.it_tasks import _SELECT, _rows, card, types_under
from savdex.web.request import context
from savdex.web.resumes import FIELDS, LIVE_AUTHOR, SERVICE_SECTIONS, labels
from savdex.web.resumes import card as resume_card
from savdex.web.seo import Seo
from savdex.web.shared import Context, initials

#: ItTask::SERVICE_PAGES: адрес страницы → код направления
SERVICE_PAGES = {
    "it": "it",
    "hr": "hr_services",
    "recruitment": "hr",
    "logistics": "logistics",
    "customs": "customs",
    "accounting": "accounting",
}

TASKS = 6
COMPLETED = 3
PROVIDERS = 8
RESUMES = 6

#: Направления, у которых на странице есть резюме
WITH_RESUMES = ("hr_services", "hr")

_ACTIVE_COMPANY = "c.status = 'active'"


def service_menu() -> list[str]:
    """ItTask::serviceMenu: «Подбор персонала» — вид внутри HR, в меню его нет."""
    return [page for page in SERVICE_PAGES if page != "recruitment"]


def _node(ctx: Context, key: str) -> Any:  # noqa: ANN401
    """__('ui.<key>'): строка или массив; нет — сам ключ."""
    node: Any = ui.translations(ctx.locale)

    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return f"ui.{key}"

        node = node[part]

    return node


def _in(types: list[str]) -> str:
    return "(" + ", ".join(["%s"] * len(types)) + ")"


def _tasks(ctx: Context, types: list[str], status: str, order: str, limit: int) -> list[Any]:
    rows = _rows(
        f"{_SELECT} where t.service_type in {_in(types)} and t.status = %s "
        f"and c.id is not null and {_ACTIVE_COMPANY} "
        f"order by {order} desc, t.id desc limit %s",
        [*types, status, limit],
    )
    translations = content.Translations(ctx.locale)
    cities = _named("cities", ctx.locale)

    return [card(ctx, r, translations, cities) for r in rows]


def _count(types: list[str], status: str) -> int:
    return int(
        _rows(
            "select count(*) as n from it_tasks t join companies c on c.id = t.company_id "
            f"and c.deleted_at is null where t.service_type in {_in(types)} "
            f"and t.status = %s and {_ACTIVE_COMPANY}",
            [*types, status],
        )[0]["n"]
    )


def _providers_where(types: list[str]) -> tuple[str, list[Any]]:
    """Исполнители: в специализациях хоть один вид направления (whereJsonContains)."""
    anyof = " or ".join(["(c.it_specializations)::jsonb @> %s"] * len(types))

    return (
        "from companies c where c.deleted_at is null and c.status = 'active' "
        f"and c.is_it_provider = true and ({anyof})",
        [json.dumps(t) for t in types],
    )


def _providers(ctx: Context, types: list[str]) -> tuple[int, list[dict[str, Any]]]:
    source, params = _providers_where(types)
    total = int(_rows(f"select count(*) as n {source}", params)[0]["n"])
    rows = _rows(
        f"select c.* {source} order by c.verification_level desc, c.rating desc, c.id limit %s",
        [*params, PROVIDERS],
    )
    cities = _named("cities", ctx.locale)
    items = []

    for c in rows:
        own = c["it_specializations"] or []

        if isinstance(own, str):
            own = json.loads(own)

        items.append(
            {
                "slug": c["slug"],
                "name": c["name"],
                "city": cities.get(c["city_id"]) if c["city_id"] is not None else None,
                "verification_level": c["verification_level"],
                "rating": float(c["rating"] or 0),
                "initials": initials(c["name"]),
                "logo": logo_url(ctx, c["logo_path"]),
                # array_intersect: порядок — как у компании
                "specializations": [ctx.t(f"it_tasks.types.{t}") for t in own if t in types],
            }
        )

    return total, items


def _published_resumes() -> int:
    return int(
        _rows(
            "select count(*) as n from resumes r where r.status = 'published' "
            f"and r.deleted_at is null and {LIVE_AUTHOR}"
        )[0]["n"]
    )


def _kinds(ctx: Context, code: str) -> list[dict[str, Any]]:
    """Что входит в направление — плитки со ссылками и счётчиками."""
    counts = {
        r["service_type"]: int(r["total"])
        for r in _rows(
            "select t.service_type, count(*) as total from it_tasks t "
            "where t.status = 'active' and exists (select 1 from companies c "
            "where c.id = t.company_id and c.deleted_at is null and c.status = 'active') "
            "group by t.service_type"
        )
    }

    if code == "hr_services":
        return [
            {
                "label": ctx.t("it_tasks.types.hr"),
                "href": "/services/recruitment",
                "count": counts.get("hr", 0),
                "kind": "tasks",
            },
            {
                "label": ctx.t("nav.resumes"),
                "href": "/resumes",
                "count": _published_resumes(),
                "kind": "resumes",
            },
        ]

    return [
        {
            "label": ctx.t(f"it_tasks.types.{kind}"),
            "href": f"/it-services?type={kind}",
            "count": counts.get(kind, 0),
            "kind": "tasks",
        }
        for kind in SERVICE_SECTIONS.get(code, [])
    ]


def _resumes(ctx: Context) -> list[dict[str, Any]]:
    rows = _rows(
        "select r.*, u.name as user_name from resumes r "
        "left join users u on u.id = r.user_id and u.deleted_at is null "
        f"where r.status = 'published' and r.deleted_at is null and {LIVE_AUTHOR} "
        "order by r.published_at desc, r.id desc limit %s",
        [RESUMES],
    )
    cities = _named("cities", ctx.locale)
    countries = _named("countries", ctx.locale)

    return [resume_card(r, ctx.locale, cities, countries) for r in rows]


def show(request: HttpRequest, slug: str) -> HttpResponse:
    """ServiceSectionController::show."""
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    code = SERVICE_PAGES.get(slug)

    if code is None:
        return not_found(ctx)

    types = types_under(code)
    with_resumes = code in WITH_RESUMES
    title = ctx.t(f"service_pages.{slug}.title")
    lead = ctx.t(f"service_pages.{slug}.lead")

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(title).description(lead)
    seo.canonical(ctx.url(f"services/{slug}"))

    active = _count(types, "active")
    completed = _count(types, "completed")
    providers_total, providers = _providers(ctx, types)

    return inertia.render(
        ctx,
        "it-tasks/Section",
        {
            "section": {
                "slug": slug,
                "code": code,
                "title": title,
                "lead": lead,
                "offers": _node(ctx, f"service_pages.{slug}.offers"),
            },
            "stats": {
                "active": active,
                "completed": completed,
                "providers": providers_total,
                "resumes": _published_resumes() if with_resumes else None,
            },
            "kinds": _kinds(ctx, code),
            "tasks": _tasks(ctx, types, "active", "t.published_at", TASKS),
            "completed": _tasks(ctx, types, "completed", "t.completed_at", COMPLETED),
            "providers": providers,
            "resumes": _resumes(ctx) if with_resumes else [],
            "resumeFields": labels(ctx, "field", FIELDS) if with_resumes else {},
            "pages": [
                {"slug": page, "title": ctx.t(f"service_pages.{page}.title")}
                for page in service_menu()
            ],
        },
        seo,
    )
