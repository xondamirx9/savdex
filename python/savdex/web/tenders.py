"""
Закупки (тендеры) — вкладка «Тендеры» каталога: копия
CatalogController::tenders и TenderCard.

Тендер — закупка внешнего заказчика, своя таблица. Вкладка живёт в
каталоге (/catalog?type=tender) под throttle:120,1; остальные вкладки
каталога — объявления — пока у Laravel, Apache отдаёт сюда только
адрес с type=tender. Ничего не пишет.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex import access, audit
from savdex.guards import allowed_writes
from savdex.web import inertia, paginator, search_text
from savdex.web.directory import _named
from savdex.web.home import _utc, banner, visible_in
from savdex.web.it_tasks import _date
from savdex.web.phpquery import php_int
from savdex.web.request import context
from savdex.web.seo import Seo, _limit
from savdex.web.shared import Context

PER_PAGE = 20

#: CatalogController::SORT_KEYS
SORT_KEYS = ("relevant", "fresh", "cheap", "expensive")

_TRUE = ("1", "true", "on", "yes")
_TRIM = " \t\n\r\0\x0b"


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _localized(row: dict[str, Any], field: str, locale: str) -> str | None:
    """Tender::localizedTitle / localizedDescription."""
    original: str | None = row[field]

    if locale == "ru":
        return original

    translated = (row[f"{field}_i18n"] or {}).get(locale)

    return translated if str(translated or "").strip(_TRIM) != "" else original


def card(
    row: dict[str, Any],
    locale: str,
    categories: dict[int, str],
    countries: dict[int, str],
    now: datetime,
) -> dict[str, Any]:
    """TenderCard::present."""
    deadline = _utc(row["deadline_at"])
    description = (_localized(row, "description", locale) or "").strip(_TRIM)

    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": _localized(row, "title", locale),
        "excerpt": _limit(description, 180, "..."),
        "customer": row["customer"],
        "category": categories.get(row["category_id"]) if row["category_id"] else None,
        "country": countries.get(row["country_id"]) if row["country_id"] else None,
        "location": row["location"],
        "budget": float(row["budget"]) if row["budget"] is not None else None,
        "currency": row["currency"],
        "deadline": _date(row["deadline_at"], locale),
        # Дней до конца приёма: полночь к полуночи, в UTC (часовой пояс приложения)
        "days_left": (deadline.date() - now.date()).days if deadline is not None else None,
        "closed": deadline is not None and deadline < now,
        "published": _date(row["published_at"], locale),
    }


def sorts(ctx: Context) -> dict[str, str]:
    return {key: ctx.t(f"catalog.sort_{key}") for key in SORT_KEYS}


def categories(locale: str) -> list[dict[str, Any]]:
    """CatalogController::categories: активные разделы и все их подкатегории."""
    names = _named("categories", locale)
    roots = _rows(
        "select id from categories where parent_id is null and is_active order by sort, id"
    )
    children: dict[int, list[int]] = {}

    for r in _rows(
        "select id, parent_id from categories where parent_id is not null order by sort, id"
    ):
        children.setdefault(r["parent_id"], []).append(r["id"])

    return [
        {
            "id": r["id"],
            "name": names[r["id"]],
            "children": [{"id": c, "name": names[c]} for c in children.get(r["id"], [])],
        }
        for r in roots
    ]


def cities(locale: str) -> list[dict[str, Any]]:
    """CatalogController::cities: города с живыми объявлениями на этом языке."""
    names = _named("cities", locale)
    visible, params = visible_in(locale)
    rows = _rows(
        "select c.id from cities c where c.is_active and exists (select 1 from listings l "
        f"where l.city_id = c.id and l.status = 'active' and l.deleted_at is null{visible}) "
        "order by c.id",
        params,
    )

    return sorted([{"id": r["id"], "name": names[r["id"]]} for r in rows], key=lambda c: c["name"])


def tenders_tab(ctx: Context, string: Callable[[str], str]) -> HttpResponse:
    """CatalogController::tenders."""
    term = string("q").strip(_TRIM)
    closed = string("closed").strip().lower() in _TRUE
    category = php_int(string("category"), 0)
    now = datetime.now(UTC).replace(microsecond=0)
    naive = now.replace(tzinfo=None)

    where = [
        "t.status = 'published'",
        "(t.published_at is null or t.published_at <= %s)",
    ]
    params: list[Any] = [naive]

    if closed:
        where.append("t.deadline_at is not null and t.deadline_at < %s")
    else:
        where.append("(t.deadline_at is null or t.deadline_at >= %s)")

    params.append(naive)

    if term != "":
        where.append("t.search_text like %s")
        params.append(f"%{search_text.normalize(term)}%")

    if category:
        where.append("t.category_id in (select id from categories where id = %s or parent_id = %s)")
        params += [category, category]

    condition = " and ".join(where)
    order = "t.deadline_at desc" if closed else "t.deadline_at is null, t.deadline_at asc"
    total = _rows(f"select count(*) as n from tenders t where {condition}", params)[0]["n"]
    current, offset = paginator.offset(ctx, PER_PAGE)
    rows = _rows(
        f"select t.* from tenders t where {condition} "
        f"order by {order}, t.published_at desc, t.id desc limit %s offset %s",
        [*params, PER_PAGE, offset],
    )
    page = paginator.Page(rows, total, PER_PAGE, current)
    category_names = _named("categories", ctx.locale)
    countries = _named("countries", ctx.locale)

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("tenders.meta_title")).description(ctx.t("tenders.meta_description"))
    seo.canonical(ctx.url("catalog") + "?type=tender")
    seo.noindex = term != "" or closed or category != 0 or current > 1

    return inertia.render(
        ctx,
        "catalog/Index",
        {
            "banner": banner(ctx, "catalog"),
            "tenders": paginator.to_array(
                ctx, page, lambda r: card(r, ctx.locale, category_names, countries, now)
            ),
            "filters": {
                "q": term,
                "type": "tender",
                "category": category or None,
                "city": None,
                "verified": False,
                "with_price": False,
                "sort": "relevant",
                "closed": closed,
            },
            "sorts": sorts(ctx),
            "categories": categories(ctx.locale),
            "cities": cities(ctx.locale),
            "total": total,
        },
        seo,
    )


def _full(row: dict[str, Any], card_: dict[str, Any], parent: str | None) -> dict[str, Any]:
    """TenderController::full: карточка и то, что есть только на странице."""
    description = (_localized(row, "description", "ru") or "").strip(_TRIM)

    return {
        **card_,
        "description": re.split(r"(?:\r\n|\n|\r|\x0b|\x0c|\x85| | ){2,}", description),
        "source_url": row["source_url"],
        "contact_name": row["contact_name"],
        "contact_phone": row["contact_phone"],
        "contact_email": row["contact_email"],
        "parent_category": parent,
    }


def _count_view(ctx: Context, row: dict[str, Any]) -> None:
    """
    $tender->increment('views_count'): +1 и updated_at, без событий
    сохранения. Администратор — ещё и строка журнала, как AuditObserver
    на событии updated.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    with allowed_writes("tenders"), connection.cursor() as cursor:
        cursor.execute(
            "update tenders set views_count = views_count + 1, updated_at = %s where id = %s",
            [now, row["id"]],
        )

    admin = _admin(ctx)

    if admin is None:
        return

    before = row["views_count"]
    audit.record(
        connection,
        action="updated",
        section="tenders",
        actor=admin,
        subject_type="App\\Models\\Tender",
        subject_id=row["id"],
        subject_label=audit.label(row, "Tender", row["id"]),
        changes={"before": {"views_count": before}, "after": {"views_count": before + 1}},
        ip=audit.client_ip(ctx.request),
    )


def _admin(ctx: Context) -> access.Admin | None:
    """AdminLog::actorIsAdmin: вошедший с is_admin."""
    user = ctx.user

    if user is None or not user["is_admin"]:
        return None

    row = _rows("select admin_role, status from users where id = %s", [user["id"]])[0]

    return access.Admin(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        is_admin=True,
        role=row["admin_role"],
        status=row["status"],
    )


def show(request: HttpRequest, slug: str) -> HttpResponse:
    """TenderController::show — страница закупки; каждый показ +1 к просмотрам."""
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    now = datetime.now(UTC).replace(microsecond=0)
    naive = now.replace(tzinfo=None)
    found = _rows(
        "select t.* from tenders t where t.status = 'published' "
        "and (t.published_at is null or t.published_at <= %s) and t.slug = %s limit 1",
        [naive, slug],
    )

    if not found:
        return not_found(ctx)

    row = found[0]
    _count_view(ctx, row)

    locale = ctx.locale
    category_names = _named("categories", locale)
    countries = _named("countries", locale)
    card_ = card(row, locale, category_names, countries, now)
    title = card_["title"]
    description = _limit(_localized(row, "description", locale) or "", 160, "...")
    parent = None

    if row["category_id"]:
        parents = _rows("select parent_id from categories where id = %s", [row["category_id"]])

        if parents and parents[0]["parent_id"] is not None:
            parent = category_names.get(parents[0]["parent_id"])

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", locale)
    seo.title(title).description(description if description != "" else None)
    seo.canonical(ctx.url(f"tenders/{row['slug']}"))
    seo.schema(
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": ctx.t("tenders.h1"),
                    "item": ctx.url("catalog") + "?type=tender",
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": title,
                    "item": ctx.url(f"tenders/{row['slug']}"),
                },
            ],
        }
    )

    params: list[Any] = [naive, naive, row["id"]]
    same_category = ""

    if row["category_id"]:
        same_category = " and t.category_id = %s"
        params.append(row["category_id"])

    similar = _rows(
        "select t.* from tenders t where t.status = 'published' "
        "and (t.published_at is null or t.published_at <= %s) "
        "and (t.deadline_at is null or t.deadline_at >= %s) "
        f"and t.id != %s{same_category} "
        "order by t.deadline_at is null, t.deadline_at asc, t.id desc limit 3",
        params,
    )

    return inertia.render(
        ctx,
        "tenders/Show",
        {
            "tender": {
                **_full(row, card_, parent),
                "description": _paragraphs(_localized(row, "description", locale)),
            },
            "similar": [card(t, locale, category_names, countries, now) for t in similar],
        },
        seo,
    )


def _paragraphs(text_: str | None) -> list[str]:
    """preg_split('/\\R{2,}/u', trim(…)) ?: [] — пустая строка тоже абзац."""
    return re.split(r"(?:\r\n|\n|\r|\x0b|\x0c|\x85| | ){2,}", (text_ or "").strip(_TRIM))
