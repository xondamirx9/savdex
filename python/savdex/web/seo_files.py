"""
Служебное для поисковиков — robots.txt и карта сайта (этап 5, шаг 50).
Копия маршрута robots (resources/views/robots.blade.php) и SitemapController.

Карта собирается на лету: объявления появляются и истекают ежедневно.
У каждого адреса — все его языковые версии (hreflang) и x-default;
импортированное объявление — только на языках, где есть его заголовок.
На домене мини-сайтов robots.txt свой: у сайта одна страница.

Сверка с настоящим Laravel — tests/test_web_seo_files.py.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from django.http import HttpRequest, HttpResponse

from savdex.web import locales
from savdex.web.cabinet import _rows
from savdex.web.home import _utc
from savdex.web.inertia import php_escape
from savdex.web.request import CRAWLERS, context
from savdex.web.services import SERVICE_PAGES
from savdex.web.shared import Context

#: SitemapController::CHUNK
CHUNK = 5000

#: Page::DOCS
DOCS = ("help", "guide", "rules")

#: Служебные адреса, закрытые от обхода, — и под префиксом каждого языка
_CLOSED = (
    "/cabinet", "/admin", "/onboarding", "/notifications", "/login", "/register",
    "/forgot-password", "/reset-password", "/verify-email", "/password", "/files/",
)  # fmt: skip

_ROBOTS_HEAD = (
    """# Личный кабинет, админка и служебные адреса закрыты: индексировать
# там нечего, а робот тратит на них лимит обхода, который лучше уходит
# на карточки объявлений и компаний.
User-agent: *
"""
    + "".join(
        f"Disallow: {prefix}{path}\n"
        for prefix in ("", "/uz", "/en", "/zh", "/tr")
        for path in _CLOSED
    )
    + """
# Сортировка и постраничная навигация дают одно и то же содержимое
# под разными адресами. Карточки при этом остаются доступны — робот
# приходит на них по ссылкам из карты сайта.
# Параметр перечислен дважды: в адресе он бывает и первым, и после
# фильтра — «?sort=cheap» и «?category=3&sort=cheap», а правило
# сопоставляется с адресом посимвольно
Disallow: /*?sort=
Disallow: /*&sort=
Disallow: /*?page=
Disallow: /*&page=

# Коммерческие анализаторы ссылок. Они обходят чужие сайты, чтобы
# продавать собранное своим подписчикам, и не приводят ни одного
# покупателя. Площадка отдаёт каждую карточку на пяти языках — для
# такого робота это тысячи полных страниц, и каждый занятый им
# процесс не достаётся человеку.
#
# Поисковики ниже не перечислены намеренно: Google, Яндекс, Bing,
# DuckDuckGo, Apple и Petal приводят покупателей, ради них карта
# сайта и существует.
"""
)

_ROBOTS_TAIL = """# Тем, кто читает это правило: страница в секунду — достаточно.
# Google его игнорирует (частота задаётся в Search Console),
# Яндекс и Bing — соблюдают.
User-agent: *
Crawl-delay: 1

Sitemap: {sitemap}
"""


def _text(body: str) -> HttpResponse:
    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    # Умолчание Symfony для ответа без своих заголовков кэша
    response["Cache-Control"] = "no-cache, private"

    return response


def robots(request: HttpRequest) -> HttpResponse:
    """Маршрут robots: у мини-сайта — «всё можно», у площадки — robots.blade.php."""
    from savdex.web.microsite import matches

    ctx = context(request, redirect=False)

    if isinstance(ctx, HttpResponse):
        return ctx

    if matches(request.get_host().rsplit(":", 1)[0]):
        return _text("User-agent: *\nAllow: /\n")

    greedy = "".join(f"User-agent: {c}\nDisallow: /\n\n" for c in CRAWLERS)

    return _text(
        _ROBOTS_HEAD + greedy + _ROBOTS_TAIL.format(sitemap=php_escape(ctx.url("sitemap.xml")))
    )


# ── Карта сайта ─────────────────────────────────────────────────────


def _atom(moment: Any) -> str | None:  # noqa: ANN401
    """Carbon::toAtomString в поясе приложения (UTC)."""
    if moment is None:
        return None

    return _utc(moment).strftime("%Y-%m-%dT%H:%M:%S+00:00")  # type: ignore[union-attr]


def _xml(body: str) -> HttpResponse:
    response = HttpResponse(body, content_type="application/xml; charset=utf-8")
    # Час: чаще робот не заходит, а собирать карту на каждый запрос — лишняя работа
    response["Cache-Control"] = "max-age=3600, public"

    return response


def _live(table: str) -> str:
    """Условие «компания строки действует»: заблокированных и удалённых в карте нет."""
    return (
        f"exists (select 1 from companies co where co.id = {table}.company_id "
        "and co.status = 'active' and co.deleted_at is null)"
    )


def _count(query: str, params: list[Any] | None = None) -> int:
    return int(_rows(query, params)[0]["n"])


def sitemap(request: HttpRequest) -> HttpResponse:
    """SitemapController::index: список частей карты."""
    ctx = context(request, redirect=False)

    if isinstance(ctx, HttpResponse):
        return ctx

    parts = ["static", "categories", "companies"]
    listings = math.ceil(
        _count(
            "select count(*) as n from listings where status = 'active' and deleted_at is null "
            f"and {_live('listings')}"
        )
        / CHUNK
    )
    parts += [f"listings-{page}" for page in range(1, max(1, listings) + 1)]

    if _rows(
        "select 1 from news_posts where is_published and (published_at is null "
        "or published_at <= now()) limit 1"
    ):
        parts.append("news")

    if _rows(
        "select 1 from tenders where status = 'published' "
        "and (published_at is null or published_at <= now()) limit 1"
    ):
        parts.append("tenders")

    if _rows(f"select 1 from it_tasks where status = 'active' and {_live('it_tasks')} limit 1"):
        parts.append("it-tasks")

    lastmod = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    items = "".join(
        f"    <sitemap>\n        <loc>{php_escape(ctx.url(f'sitemap-{p}.xml'))}</loc>\n"
        f"        <lastmod>{lastmod}</lastmod>\n    </sitemap>\n"
        for p in parts
    )

    return _xml(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}</sitemapindex>\n"
    )


def _static(ctx: Context) -> list[dict[str, Any]]:
    docs = [
        {"loc": ctx.url(r["key"]), "priority": "0.4", "changefreq": "monthly"}
        for r in _rows(
            "select key from pages where key = any(%s) and is_published order by sort",
            [list(DOCS)],
        )
    ]

    def item(path: str, priority: str, changefreq: str) -> dict[str, Any]:
        return {"loc": ctx.url(path), "priority": priority, "changefreq": changefreq}

    return [
        item("/", "1.0", "daily"),
        item("/catalog", "0.9", "hourly"),
        item("/companies", "0.9", "daily"),
        item("/pricing", "0.7", "monthly"),
        item("/about", "0.5", "monthly"),
        item("/news", "0.6", "weekly"),
        {"loc": ctx.url("/catalog") + "?type=tender", "priority": "0.8", "changefreq": "daily"},
        item("/it-services", "0.8", "daily"),
        *[item(f"/services/{slug}", "0.7", "daily") for slug in SERVICE_PAGES],
        item("/countries", "0.5", "monthly"),
        item("/partners", "0.4", "monthly"),
        item("/partners/general", "0.4", "monthly"),
        item("/partners/regular", "0.4", "monthly"),
        item("/partners/multi", "0.4", "monthly"),
        item("/contact", "0.4", "yearly"),
        *docs,
        # Юридические документы — только на русском (как и их canonical)
        *[
            {**item(f"/{doc}", "0.3", "yearly"), "locales": [locales.DEFAULT]}
            for doc in ("terms", "payment", "security", "privacy", "refunds")
        ],
    ]


def _categories(ctx: Context) -> list[dict[str, Any]]:
    """
    Непустые активные категории. Порядка у Laravel нет — запрос тот же
    (withCount), строки в том порядке, в каком их отдаст база.
    """
    return [
        {"loc": ctx.url(f"/catalog?category={r['id']}"), "priority": "0.8", "changefreq": "daily"}
        for r in _rows(
            "select c.id, (select count(*) from listings l where c.id = l.category_id "
            f"and l.status = 'active' and l.deleted_at is null and {_live('l')}) as active "
            "from categories c "
            "where c.is_active = true"
        )
        if r["active"] > 0
    ]


def _dated(
    ctx: Context, path: str, rows: list[dict[str, Any]], priority: str, freq: str
) -> list[dict[str, Any]]:
    return [
        {
            "loc": ctx.url(f"{path}/{r['slug']}"),
            "lastmod": _atom(r["updated_at"]),
            "priority": priority,
            "changefreq": freq,
        }
        for r in rows
    ]


def _listing_locales(row: dict[str, Any]) -> list[str]:
    """Listing::visibleLocales: все языки — и у загруженного из книги."""
    return list(locales.CODES)


def _listings(ctx: Context, page: int) -> list[dict[str, Any]]:
    rows = _rows(
        "select slug, updated_at, source, title_i18n from listings where status = 'active' "
        f"and deleted_at is null and slug is not null and {_live('listings')} "
        "order by id limit %s offset %s",
        [CHUNK, max(0, (page - 1) * CHUNK)],
    )

    return [
        {
            "loc": ctx.url(f"/listing/{r['slug']}"),
            "lastmod": _atom(r["updated_at"]),
            "priority": "0.6",
            "changefreq": "weekly",
            "locales": _listing_locales(r),
        }
        for r in rows
    ]


def _part(ctx: Context, name: str) -> list[dict[str, Any]] | None:
    if name == "static":
        return _static(ctx)

    if name == "categories":
        return _categories(ctx)

    if name == "companies":
        return _dated(
            ctx,
            "/company",
            _rows(
                "select slug, updated_at from companies where status = 'active' "
                "and slug is not null and deleted_at is null"
            ),
            "0.7",
            "weekly",
        )

    if name == "news":
        return _dated(
            ctx,
            "/news",
            _rows(
                "select slug, updated_at from news_posts where is_published and "
                "(published_at is null or published_at <= now())"
            ),
            "0.5",
            "monthly",
        )

    if name == "tenders":
        return _dated(
            ctx,
            "/tenders",
            _rows(
                "select slug, updated_at from tenders where status = 'published' "
                "and (published_at is null or published_at <= now())"
            ),
            "0.6",
            "weekly",
        )

    if name == "it-tasks":
        return _dated(
            ctx,
            "/it-services",
            _rows(
                "select slug, updated_at from it_tasks where status = 'active' "
                f"and {_live('it_tasks')}"
            ),
            "0.6",
            "weekly",
        )

    found = re.fullmatch(r"listings-(\d+)", name)

    if found:
        rows = _listings(ctx, int(found.group(1)))

        # Части дальше последней нет: пустая карта под 200 выглядит как
        # настоящая, и робот возвращается к ней снова и снова. Первая
        # часть есть всегда — её перечисляет список частей
        return rows if rows or found.group(1) == "1" else None

    return None


def _with_locales(ctx: Context, urls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Каждый адрес — на каждом своём языке, со всеми языковыми версиями."""
    out = []

    for url in urls:
        path = url["loc"]
        path = path[len(ctx.root) :] if path.startswith(ctx.root) else path
        path = path or "/"
        codes = url.pop("locales", None) or list(locales.CODES)
        alternates = {
            meta["hreflang"]: locales.url(ctx.root, path, code)
            for code, meta in locales.ALL.items()
            if code in codes
        }
        alternates["x-default"] = locales.url(ctx.root, path, locales.DEFAULT)

        out += [
            {**url, "loc": locales.url(ctx.root, path, code), "alternates": alternates}
            for code in codes
        ]

    return out


def sitemap_part(request: HttpRequest, part: str) -> HttpResponse:
    """SitemapController::part: адреса одной части на всех языках."""
    from savdex.web.views import not_found

    ctx = context(request, redirect=False)

    if isinstance(ctx, HttpResponse):
        return ctx

    urls = _part(ctx, part)

    if urls is None:
        return not_found(ctx)

    body = []

    for url in _with_locales(ctx, urls):
        body.append(f"    <url>\n        <loc>{php_escape(url['loc'])}</loc>\n")

        if url.get("lastmod") is not None:
            body.append(f"        <lastmod>{php_escape(url['lastmod'])}</lastmod>\n")

        body.append(
            f"        <changefreq>{url['changefreq']}</changefreq>\n"
            f"        <priority>{url['priority']}</priority>\n"
            # Строка, оставшаяся от комментария Blade в urlset.blade.php
            "\n"
        )
        body += [
            f'        <xhtml:link rel="alternate" hreflang="{php_escape(lang)}" '
            f'href="{php_escape(href)}"/>\n'
            for lang, href in url["alternates"].items()
        ]
        body.append("    </url>\n")

    return _xml(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "".join(body) + "</urlset>\n"
    )
