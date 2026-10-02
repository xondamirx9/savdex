"""
Раздел «Резюме» — копия ResumeController::index у Laravel.

Список опубликованных резюме с поиском и фильтрами, по 20 на странице
(paginator — копия LengthAwarePaginator). Ничего не пишет: счётчик
просмотров увеличивает только страница резюме, она пока у Laravel.

Поиск — Resume::scopeSearch: запрос как набран и в транслитерации
(SearchText::variants), по должности, «о себе», навыкам и местам
работы. Навыки и места работы — колонки json; у Laravel на PostgreSQL
lower() от json падал с 500, исправлено приведением к тексту у обеих
сторон.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.web import inertia, paginator, search_text
from savdex.web.directory import _TRIM, _named
from savdex.web.home import _utc
from savdex.web.phpquery import laravel_input, php_int, text
from savdex.web.request import context
from savdex.web.seo import Seo, _limit
from savdex.web.shared import Context, public_url

PER_PAGE = 20

#: ResumeOptions
FIELDS = (
    "sales", "procurement", "logistics", "production", "construction",
    "engineering", "it", "finance", "marketing", "legal", "hr",
    "management", "translation", "other",
)  # fmt: skip
EMPLOYMENT = ("full", "part", "project", "internship")
EXPERIENCE_STEPS = {"none": 0, "from1": 12, "from3": 36, "from6": 72}
SCHEDULE = ("full_day", "shift", "flexible", "remote", "rotational")
LANGUAGE_LEVELS = ("basic", "intermediate", "advanced", "native")
EDUCATION_LEVELS = ("secondary", "vocational", "bachelor", "master", "phd")

#: ItTask::SERVICE_SECTIONS — порядок здесь — порядок в панели фильтра
SERVICE_SECTIONS: dict[str, list[str]] = {
    "it": ["web", "mobile", "erp", "integration", "design", "automation", "support"],
    "hr_services": ["hr"],
    "logistics": [],
    "customs": [],
    "accounting": [],
    "other": [],
}


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def labels(ctx: Context, group: str, values: tuple[str, ...] | list[str]) -> dict[str, str]:
    """ResumeOptions::labels."""
    return {value: ctx.t(f"resume.{group}_{value}") for value in values}


def section_tree(ctx: Context, counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """
    ItTask::sectionTree — дерево направлений для панели фильтра. С
    counts (вид → сколько) у пункта есть count — сумма по его видам;
    без них (резюме) ключа нет вовсе.
    """

    def node(code: str) -> dict[str, Any]:
        item: dict[str, Any] = {"code": code, "label": ctx.t(f"it_tasks.types.{code}")}

        if counts is not None:
            kinds = SERVICE_SECTIONS.get(code) or [code]
            item["count"] = sum(counts.get(kind, 0) for kind in kinds)

        return item

    return [
        {**node(code), "children": [node(child) for child in children]}
        for code, children in SERVICE_SECTIONS.items()
    ]


def _filled(value: object) -> bool:
    """filled() у Laravel: не null и не пустая строка после trim."""
    if value is None:
        return False

    if isinstance(value, str):
        return value.strip() != ""

    return not (isinstance(value, (list, dict)) and not value)


def _localized(row: dict[str, Any], field: str, locale: str) -> str | None:
    """Resume::localized: перевод, пустой — оригинал."""
    original: str | None = row[field]

    if locale == "ru":
        return original

    translated = (row[f"{field}_i18n"] or {}).get(locale)

    return translated if _filled(translated) else original


def _name(row: dict[str, Any]) -> str | None:
    # contact_name ?: user->name — у PHP «0» тоже пусто
    contact: str | None = row["contact_name"]
    user: str | None = row["user_name"]

    return contact if contact not in (None, "", "0") else user


def initials(name: str | None) -> str:
    """Resume::initials: первые буквы двух первых слов."""
    words = [w for w in re.split(r"\s+", (name or "").strip(_TRIM)) if w not in ("", "0")]
    letters = "".join(w[:1].upper() for w in words[:2])

    return letters or "—"


def card(
    row: dict[str, Any], locale: str, cities: dict[int, str], countries: dict[int, str]
) -> dict[str, Any]:
    """ResumeController::card."""
    months = row["experience_months"]
    published = _utc(row["published_at"])
    name = _name(row)

    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": _localized(row, "title", locale) or row["title"],
        "field": row["field"],
        "name": name,
        "initials": initials(name),
        "photo": public_url(row["photo_path"]) if row["photo_path"] is not None else None,
        "city": cities.get(row["city_id"]) if row["city_id"] is not None else None,
        "country": countries.get(row["country_id"]) if row["country_id"] is not None else None,
        "salary": int(row["salary"]) if row["salary"] is not None else None,
        "currency": row["currency"],
        "employment": row["employment"] or [],
        "experience": {"years": months // 12, "months": months % 12},
        "skills": (row["skills"] or [])[:8],
        "published": published.strftime("%d.%m.%Y") if published else None,
    }


#: Автор резюме — живая учётка: резюме удалённого или заблокированного
#: человека не показываем (контакты в нём — его)
LIVE_AUTHOR = (
    "exists (select 1 from users ra where ra.id = r.user_id "
    "and ra.deleted_at is null and ra.status = 'active')"
)


def _cities(locale: str) -> list[dict[str, Any]]:
    """Города, где есть хоть одно опубликованное резюме, по имени."""
    names = _named("cities", locale)
    ids = _rows(
        "select c.id from cities c where c.is_active and exists (select 1 from resumes r "
        "where r.city_id = c.id and r.status = 'published' and r.deleted_at is null "
        f"and {LIVE_AUTHOR}) "
        "order by c.id"
    )
    items = [{"id": r["id"], "name": names[r["id"]]} for r in ids]

    return sorted(items, key=lambda item: item["name"])


def index(request: HttpRequest) -> HttpResponse:
    """ResumeController::index."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    query = laravel_input(ctx.query)

    def string(key: str) -> str:
        """$request->string(): null и массив — пустая строка."""
        value = query.get(key)

        return text(value) if isinstance(value, str) else ""

    term = string("q")
    field = string("field")
    experience = string("experience")
    employment = string("employment")
    city = php_int(string("city"), 0)

    where = ["r.status = 'published'", "r.deleted_at is null", LIVE_AUTHOR]
    params: list[Any] = []

    if term != "":
        needles = search_text.variants(term)
        clauses = []

        for needle in needles:
            clauses.append(
                "lower(r.title) like %s or lower(r.about) like %s "
                "or lower(cast(r.skills as text)) like %s or lower(cast(r.jobs as text)) like %s"
            )
            params += [f"%{needle}%"] * 4

        # where(function) без вариантов — пустая группа, Laravel её выбрасывает
        if clauses:
            where.append("(" + " or ".join(clauses) + ")")

    if field in FIELDS:
        where.append("r.field = %s")
        params.append(field)

    if city:
        where.append("r.city_id = %s")
        params.append(city)

    if experience in EXPERIENCE_STEPS:
        where.append("r.experience_months >= %s")
        params.append(EXPERIENCE_STEPS[experience])

    # when() у Laravel: «0» — ложь, фильтра нет
    if employment not in ("", "0"):
        where.append("(r.employment)::jsonb @> %s")
        params.append(json.dumps(employment))

    condition = " and ".join(where)
    total = _rows(f"select count(*) as n from resumes r where {condition}", params)[0]["n"]
    current, offset = paginator.offset(ctx, PER_PAGE)
    rows = _rows(
        "select r.*, u.name as user_name from resumes r "
        "left join users u on u.id = r.user_id and u.deleted_at is null "
        f"where {condition} order by r.published_at desc, r.id desc limit %s offset %s",
        [*params, PER_PAGE, offset],
    )
    page = paginator.Page(rows, total, PER_PAGE, current)
    cities = _named("cities", ctx.locale)
    countries = _named("countries", ctx.locale)

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("resume.meta_title")).description(ctx.t("resume.meta_description"))
    seo.canonical(ctx.url("resumes"))
    seo.noindex = (
        any(key in query for key in ("q", "field", "city", "experience", "employment"))
        or current > 1
    )

    return inertia.render(
        ctx,
        "resumes/Index",
        {
            "resumes": paginator.to_array(
                ctx, page, lambda r: card(r, ctx.locale, cities, countries)
            ),
            "filters": {
                "q": term,
                "field": field if field != "" else None,
                "city": city or None,
                "experience": experience if experience != "" else None,
                "employment": employment if employment not in ("", "0") else None,
            },
            "options": {
                "fields": labels(ctx, "field", FIELDS),
                "experience": labels(ctx, "experience", list(EXPERIENCE_STEPS)),
                "employment": labels(ctx, "employment", EMPLOYMENT),
            },
            "cities": _cities(ctx.locale),
            "total": total,
            "types": section_tree(ctx),
        },
        seo,
    )


def localized_jobs(row: dict[str, Any], locale: str) -> list[Any]:
    """Resume::localizedJobs: перевод годится, только пока мест столько же."""
    jobs: list[Any] = row["jobs"] or []
    translated = (row["jobs_i18n"] or {}).get(locale)

    if not isinstance(translated, list) or len(translated) != len(jobs):
        return jobs

    return [
        {
            **job,
            "position": tr["position"] if _filled(tr.get("position")) else job.get("position", ""),
            "duties": tr["duties"] if _filled(tr.get("duties")) else job.get("duties", ""),
        }
        for job, tr in zip(jobs, translated, strict=True)
    ]


def _contacts(row: dict[str, Any]) -> dict[str, Any] | list[Any]:
    """array_filter контактов: пустое выпадает; ничего не осталось — []."""
    values = {
        "name": _name(row),
        "phone": row["contact_phone"] if row["show_phone"] else None,
        "email": row["contact_email"] if row["show_email"] else None,
    }

    return {k: v for k, v in values.items() if v not in (None, "", "0")} or []


def count_view(table: str, row_id: int) -> None:
    """$model->increment('views_count'): +1 и updated_at, без событий сохранения."""
    from savdex.guards import allowed_writes

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    with allowed_writes(table), connection.cursor() as cursor:
        cursor.execute(
            f"update {table} set views_count = views_count + 1, updated_at = %s where id = %s",
            [now, row_id],
        )


def show(request: HttpRequest, slug: str) -> HttpResponse:
    """ResumeController::show; просмотр не владельца — +1 к счётчику."""
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    select = (
        "select r.*, u.name as user_name from resumes r "
        "left join users u on u.id = r.user_id and u.deleted_at is null "
        f"where r.status = 'published' and r.deleted_at is null and {LIVE_AUTHOR}"
    )
    found = _rows(f"{select} and r.slug = %s limit 1", [slug])

    if not found:
        return not_found(ctx)

    row = found[0]

    if ctx.visitor.user_id != row["user_id"]:
        count_view("resumes", row["id"])
        row["views_count"] += 1

    locale = ctx.locale
    cities = _named("cities", locale)
    countries = _named("countries", locale)
    about = _localized(row, "about", locale)
    description = _limit((about or "").strip(_TRIM), 160, "...")

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", locale)
    seo.title(_localized(row, "title", locale) or row["title"])
    seo.description(description if description != "" else ctx.t("resume.meta_description"))
    seo.canonical(ctx.url(f"resume/{row['slug']}"))

    params: list[Any] = [row["id"]]
    same_field = ""

    if row["field"] not in (None, "", "0"):
        same_field = " and r.field = %s"
        params.append(row["field"])

    similar = _rows(
        f"{select} and r.id != %s{same_field} order by r.published_at desc, r.id desc limit 4",
        params,
    )

    return inertia.render(
        ctx,
        "resumes/Show",
        {
            "resume": {
                **card(row, locale, cities, countries),
                "about": about,
                "jobs": localized_jobs(row, locale),
                "education": row["education"] or [],
                "languages": row["languages"] or [],
                "schedule": row["schedule"] or [],
                "views": row["views_count"],
                "contacts": None if ctx.user is None else _contacts(row),
            },
            "options": {
                "fields": labels(ctx, "field", FIELDS),
                "employment": labels(ctx, "employment", EMPLOYMENT),
                "schedule": labels(ctx, "schedule", SCHEDULE),
                "language_levels": labels(ctx, "language_level", LANGUAGE_LEVELS),
                "education_levels": labels(ctx, "education_level", EDUCATION_LEVELS),
            },
            "similar": [card(r, locale, cities, countries) for r in similar],
        },
        seo,
    )
