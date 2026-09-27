"""
Каталог объявлений /catalog — копия CatalogController::index.

Живые объявления активных компаний, видимые на языке страницы, с
поиском по search_text, фильтрами и сортировками, по 20 на странице.
Вкладка «Тендеры» — в tenders.py, сюда её отдаёт общий вход catalog().

Пишет статистику, как StatsRecorder у Laravel:

- показы (impressions): +1 к listings.impressions_count и к дневной
  строке listing_stats — каждому объявлению в выдаче, не чаще раза в
  полчаса на посетителя (ключ stats:imp:<посетитель>:<объявление> в
  файловом кэше Laravel, общий с ним);
- поисковые запросы (search_hits): каждой компании, чьё объявление
  показано по запросу, +1 показ за день — без отсева повторов, как у
  Laravel.

Посетитель — сессия Laravel. У гостя, который ходит только по
страницам Django, её нет (сессию до этапа 5 пишет Laravel): Django
метит его своей кукой savdex_visitor, иначе каждое обновление
страницы засчитывалось бы новым показом.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex import laravel_cache
from savdex.guards import allowed_writes
from savdex.web import content, inertia, paginator, search_text
from savdex.web.directory import _named
from savdex.web.home import _LISTING_COMPANY, Cards, banner, visible_in
from savdex.web.phpquery import Array, laravel_input, php_int, text
from savdex.web.seo import Seo
from savdex.web.shared import Context, settings_values
from savdex.web.tenders import SORT_KEYS, categories, cities, sorts, tenders_tab
from savdex.web.throttle import throttled

PER_PAGE = 20

#: StatsRecorder::DEDUP_MINUTES
DEDUP_MINUTES = 30

#: Продвижения, поднимающие объявление в «Подходящих»
PROMOTED_CODES = ("category_top", "home_top", "bump", "urgent")

#: Своя кука гостя без сессии Laravel — только для отсева повторных показов
VISITOR_COOKIE = "savdex_visitor"

_TRUE = ("1", "true", "on", "yes")

#: $request->hasAny([...]) у Laravel
_FILTERS = ("q", "type", "category", "city", "verified", "with_price", "sort")


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


# ── Статистика (StatsRecorder) ──────────────────────────────────────


def visitor_key(ctx: Context) -> tuple[str | None, str | None]:
    """
    Кем считать посетителя для отсева повторов: сессия Laravel, иначе
    своя кука Django. Второе — новая кука, которую надо поставить.
    """
    if ctx.visitor.session_id is not None:
        return ctx.visitor.session_id, None

    own = ctx.request.COOKIES.get(VISITOR_COOKIE, "")

    if re.fullmatch(r"[A-Za-z0-9]{40}", own):
        return f"py-{own}", None

    fresh = secrets.token_hex(20)

    return f"py-{fresh}", fresh


def without_recent(ids: list[int], kind: str, visitor: str | None) -> list[int]:
    """StatsRecorder::withoutRecent: add() ставит ключ, только если его нет."""
    if not ids or visitor is None or not laravel_cache.is_file_store():
        return ids

    return [
        i for i in ids if laravel_cache.add(f"stats:{kind}:{visitor}:{i}", True, DEDUP_MINUTES * 60)
    ]


def _now() -> tuple[str, str]:
    now = datetime.now(UTC)

    return now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d")


def bump_daily(listing_ids: list[int], column: str) -> None:
    """StatsRecorder::bumpDaily: строка дня есть у каждого, затем +1."""
    stamp, today = _now()

    with (
        allowed_writes("listing_stats"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "insert into listing_stats (listing_id, date, impressions, views, favorites, "
            "unlocks, created_at, updated_at) select id, %s, 0, 0, 0, 0, %s, %s "
            "from unnest(%s::bigint[]) as id on conflict do nothing",
            [today, stamp, stamp, listing_ids],
        )
        cursor.execute(
            f"update listing_stats set {column} = {column} + 1, updated_at = %s "
            "where listing_id = any(%s) and date = %s",
            [stamp, listing_ids, today],
        )


def impressions(listing_ids: list[int], visitor: str | None) -> None:
    """StatsRecorder::impressions."""
    listing_ids = without_recent(listing_ids, "imp", visitor)

    if not listing_ids:
        return

    stamp, _ = _now()

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            "update listings set impressions_count = impressions_count + 1, updated_at = %s "
            "where id = any(%s) and deleted_at is null",
            [stamp, listing_ids],
        )

    bump_daily(listing_ids, "impressions")


def search_hits(company_ids: list[int], query: str) -> None:
    """StatsRecorder::search: запрос как видит его «по каким запросам находили»."""
    normalized = re.sub(r"\s+", " ", query).strip(" \t\n\r\0\x0b").lower()

    if normalized == "" or len(normalized) > 190 or not company_ids:
        return

    stamp, today = _now()
    unique = list(dict.fromkeys(company_ids))

    with allowed_writes("search_hits"), connection.cursor() as cursor:
        cursor.execute(
            "insert into search_hits (company_id, query, date, impressions, clicks, "
            "created_at, updated_at) select id, %s, %s, 0, 0, %s, %s "
            "from unnest(%s::bigint[]) as id on conflict do nothing",
            [normalized, today, stamp, stamp, unique],
        )
        cursor.execute(
            "update search_hits set impressions = impressions + 1, updated_at = %s "
            "where company_id = any(%s) and query = %s and date = %s",
            [stamp, unique, normalized, today],
        )


# ── Каталог ─────────────────────────────────────────────────────────


def catalog(request: HttpRequest) -> HttpResponse:
    """/catalog под throttle:120,1: вкладка тендеров или объявления."""
    return throttled(request, 120, _catalog)


def _catalog(ctx: Context) -> HttpResponse:
    query = laravel_input(ctx.query)

    def string(key: str) -> str:
        value = query.get(key)

        return text(value) if isinstance(value, str) else ""

    if string("type") == "tender":
        return tenders_tab(ctx, string)

    return listings_tab(ctx, query, string)


def _order(sort: str) -> str:
    """CatalogController::applySort; хвост по id — у любой сортировки."""
    if sort == "fresh":
        order = "l.published_at desc"
    elif sort == "cheap":
        order = "l.price is null, l.price asc"
    elif sort == "expensive":
        order = "l.price is null, l.price desc"
    else:
        codes = ", ".join(f"'{c}'" for c in PROMOTED_CODES)
        order = (
            "(select count(*) from promotions p where p.listing_id = l.id "
            "and p.status = 'active' and exists (select 1 from promotion_types t "
            f"where t.id = p.promotion_type_id and t.code in ({codes}))) desc, "
            "l.published_at desc"
        )

    return order + ", l.id desc"


def listings_tab(ctx: Context, query: Array, string: Callable[[str], str]) -> HttpResponse:
    """CatalogController::index — объявления."""
    term = string("q")
    kind = string("type")
    sort = string("sort")
    sort = sort if sort in SORT_KEYS else "relevant"
    category = php_int(string("category"), 0)
    city = php_int(string("city"), 0)
    verified = string("verified").strip().lower() in _TRUE
    with_price = string("with_price").strip().lower() in _TRUE

    visible, params = visible_in(ctx.locale)
    where = [
        "l.status = 'active'",
        "l.deleted_at is null",
        "c.status = 'active'",
        "c.deleted_at is null",
    ]

    if term != "":
        where.append("l.search_text like %s")
        params.append(f"%{search_text.normalize(term)}%")

    if kind not in ("", "0"):
        where.append("l.type = %s")
        params.append(kind)

    if category:
        where.append("l.category_id in (select id from categories where id = %s or parent_id = %s)")
        params += [category, category]

    if city:
        where.append("l.city_id = %s")
        params.append(city)

    if verified:
        where.append("c.verification_level >= 2")

    if with_price:
        where.append("l.price is not null and l.price_negotiable = false")

    condition = " and ".join(where) + visible
    source = "from listings l join companies c on c.id = l.company_id"
    total = _rows(f"select count(*) as n {source} where {condition}", params)[0]["n"]
    current, offset = paginator.offset(ctx, PER_PAGE)
    rows = _rows(
        f"select l.*, {_LISTING_COMPANY} {source} where {condition} "
        f"order by {_order(sort)} limit %s offset %s",
        [*params, PER_PAGE, offset],
    )

    # Показы засчитываются тому, что реально попало в выдачу
    visitor, fresh_cookie = visitor_key(ctx)

    if rows:
        impressions([r["id"] for r in rows], visitor)

        if term != "":
            search_hits([int(r["company_id"]) for r in rows], term)

    translations = content.Translations(ctx.locale)
    cards = Cards(ctx, settings_values(), translations)
    page = paginator.Page(rows, total, PER_PAGE, current)
    listings = paginator.to_array(ctx, page)
    listings["data"] = cards.present(rows)

    response = inertia.render(
        ctx,
        "catalog/Index",
        {
            "banner": banner(ctx, "catalog"),
            "listings": listings,
            "filters": {
                "q": term,
                "type": kind,
                "category": category or None,
                "city": city or None,
                "verified": verified,
                "with_price": with_price,
                "sort": sort,
                "closed": False,
            },
            "sorts": sorts(ctx),
            "categories": categories(ctx.locale),
            "cities": cities(ctx.locale),
            "total": total,
        },
        _seo(ctx, query, term, category, city, total, current),
    )

    if fresh_cookie is not None:
        response.set_cookie(
            VISITOR_COOKIE,
            fresh_cookie,
            httponly=True,
            samesite="Lax",
            secure=ctx.request.is_secure(),
        )

    return response


def _seo(
    ctx: Context,
    query: Array,
    term: str,
    category: int,
    city: int,
    total: int,
    current: int,
) -> Seo:
    """SeoBuilders::catalog: заголовок из фильтров — «Цемент в Ташкенте»."""
    category_name = _named("categories", ctx.locale).get(category) if category else None
    city_name = _named("cities", ctx.locale).get(city) if city else None
    # ?: у PHP: «0» — тоже пусто
    subject = next(
        (s for s in (term, category_name) if s not in (None, "", "0")),
        ctx.t("seo.catalog_subject"),
    )
    where = (
        ctx.t("seo.catalog_in_city", city=city_name)
        if city_name is not None
        else ctx.t("seo.catalog_in_country")
    )

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(subject + where)
    seo.description(ctx.t("seo.catalog_description", subject=subject, where=where, total=total))
    seo.canonical(ctx.url("catalog"))
    seo.noindex = any(key in query for key in _FILTERS) or current > 1

    return seo
