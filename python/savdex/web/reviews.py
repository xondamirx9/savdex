"""
Лента отзывов и страница «Все отзывы» — копия App\\Support\\ReviewFeed
и ReviewsController::index.

В ленте — опубликованные отзывы компаний о компаниях и отзывы
пользователей о самой площадке. Порядок — тем же запросом UNION, что
у Laravel: свежие сверху, при равной дате — по виду и номеру. Пишет
отзывы только Laravel (форма «Оцените SavdEx» и модерация); Django их
только показывает.
"""

from __future__ import annotations

import math
import re
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.web import content, inertia, ui
from savdex.web.request import context
from savdex.web.seo import Seo
from savdex.web.shared import initials

#: ReviewFeed::TYPES и PER_PAGE, ReviewsController::MAX_PAGE
TYPES = ("all", "platform", "company")
PER_PAGE = 20
MAX_PAGE = 10_000

#: PlatformReview::CRITERIA — поле → ключ подписи
CRITERIA = {
    "rating_usability": "usability",
    "rating_search": "search",
    "rating_support": "support",
}

_COMPANY_ROWS = (
    "select 'company' as kind, r.id, r.created_at from reviews r "
    "join companies c on c.id = r.company_id join companies a on a.id = r.author_company_id "
    "where r.status = 'published' and c.status = 'active' and c.deleted_at is null "
    "and a.deleted_at is null"
)
_PLATFORM_ROWS = (
    "select 'platform' as kind, p.id, p.created_at from platform_reviews p "
    "where p.status = 'published'"
)


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _feed(kind: str) -> str:
    if kind == "platform":
        return _PLATFORM_ROWS

    if kind == "company":
        return _COMPANY_ROWS

    return f"({_COMPANY_ROWS}) union all ({_PLATFORM_ROWS})"


def count(kind: str) -> int:
    return int(_rows(f"select count(*) as n from ({_feed(kind)}) as feed")[0]["n"])


def take(
    kind: str, limit: int, offset: int, translations: content.Translations
) -> list[dict[str, Any]]:
    """ReviewFeed::take: отзывы ленты по порядку, карточками."""
    rows = _rows(
        f"select * from ({_feed(kind)}) as feed "
        "order by created_at desc, kind asc, id desc limit %s offset %s",
        [limit, offset],
    )
    company = {
        r["id"]: r
        for r in _rows(
            "select r.id, r.rating, r.body, r.created_at, a.name as author, "
            "c.name as company_name, c.slug as company_slug from reviews r "
            "join companies c on c.id = r.company_id "
            "join companies a on a.id = r.author_company_id where r.id = any(%s)",
            [[r["id"] for r in rows if r["kind"] == "company"]],
        )
    }
    # Удалённые пользователь и компания не подгружаются — как у Eloquent
    platform = {
        r["id"]: r
        for r in _rows(
            "select p.id, p.rating, p.body, p.created_at, u.name as user_name, "
            "co.name as company_name from platform_reviews p "
            "left join users u on u.id = p.user_id and u.deleted_at is null "
            "left join companies co on co.id = p.company_id and co.deleted_at is null "
            "where p.id = any(%s)",
            [[r["id"] for r in rows if r["kind"] == "platform"]],
        )
    }
    translations.prefetch(r["body"] for r in [*company.values(), *platform.values()])

    return [
        _company_card(company[r["id"]], translations)
        if r["kind"] == "company"
        else _platform_card(platform[r["id"]], translations)
        for r in rows
    ]


def _company_card(r: dict[str, Any], translations: content.Translations) -> dict[str, Any]:
    return {
        "id": r["id"],
        "kind": "company",
        "author": r["author"],
        "initials": initials(r["author"]),
        "rating": int(r["rating"]),
        "body": translations.text(r["body"]),
        "when": r["created_at"].strftime("%d.%m.%Y"),
        "company_name": r["company_name"],
        "company_slug": r["company_slug"],
    }


def platform_author(company_name: str | None, user_name: str | None, locale: str) -> str:
    """ReviewFeed::platformAuthor: компания, иначе имя и буква фамилии."""
    if company_name is not None:
        return company_name

    words = [w for w in re.split(r"\s+", (user_name or "").strip()) if w]

    if not words:
        return ui.t("platform_reviews.anonymous", locale)

    return words[0] if len(words) == 1 else f"{words[0]} {words[1][0].upper()}."


def _platform_card(r: dict[str, Any], translations: content.Translations) -> dict[str, Any]:
    author = platform_author(r["company_name"], r["user_name"], translations.locale)

    return {
        "id": r["id"],
        "kind": "platform",
        "author": author,
        "initials": initials(author),
        "rating": int(r["rating"]),
        "body": translations.text(r["body"]),
        "when": r["created_at"].strftime("%d.%m.%Y"),
        "company_name": None,
        "company_slug": None,
    }


def _number(value: object) -> float | None:
    return None if value is None else float(str(value))


def platform_summary(locale: str) -> dict[str, Any]:
    """ReviewFeed::platformSummary: средняя, число, звёзды, стороны работы."""
    published = "from platform_reviews where status = 'published'"
    [head] = _rows(f"select count(*) as total, round(avg(rating), 1) as average {published}")
    stars = {
        r["rating"]: int(r["total"])
        for r in _rows(f"select rating, count(*) as total {published} group by rating")
    }
    criteria = []

    for field, key in CRITERIA.items():
        [row] = _rows(
            f"select round(avg({field}), 1) as average {published} and {field} is not null"
        )
        criteria.append(
            {
                "key": key,
                "label": ui.t(f"platform_reviews.criteria.{key}", locale),
                "average": _number(row["average"]),
            }
        )

    return {
        "count": int(head["total"]),
        "average": _number(head["average"]),
        "stars": [{"star": star, "count": stars.get(star, 0)} for star in (5, 4, 3, 2, 1)],
        "criteria": criteria,
    }


#: (int) у PHP для строки: ведущие пробелы, знак, цифры, дробь и порядок
_PHP_NUMBER = re.compile(r"^[ \t\n\r\v\f]*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def php_int(value: str | None, default: int) -> int:
    """(int) $request->query(...): не число — 0, «2abc» — 2, «1e2» — 100."""
    if value is None:
        return default

    match = _PHP_NUMBER.match(value)

    if match is None:
        return 0

    number = float(match.group(1))

    return int(number) if math.isfinite(number) and abs(number) < 2**63 else 0


def index(request: HttpRequest) -> HttpResponse:
    """ReviewsController::index."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    kind = request.GET.get("type")
    kind = kind if kind in TYPES else "all"
    page = min(max(1, php_int(request.GET.get("page"), 1)), MAX_PAGE)
    total = count(kind)
    translations = content.Translations(ctx.locale)

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("seo.reviews_title")).description(ctx.t("seo.reviews_description"))
    seo.canonical(ctx.url("reviews"))

    return inertia.render(
        ctx,
        "Reviews",
        {
            "summary": platform_summary(ctx.locale),
            "counts": {t: count(t) for t in TYPES},
            "type": kind,
            "reviews": take(kind, PER_PAGE, (page - 1) * PER_PAGE, translations),
            "page": page,
            "pages": max(1, math.ceil(total / PER_PAGE)),
        },
        seo,
    )
