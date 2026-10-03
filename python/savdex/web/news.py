"""
Новости на сайте — копия NewsController и NewsRepository.

Лента (/news) и новость (/news/<адрес>): опубликованные (снятые с
публикации и будущие не видны), новые сверху, текст — машинным
переводом на язык посетителя, пока его нет — по-русски.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from savdex import laravel_storage
from savdex.site.models import NewsPost
from savdex.web import inertia, ui
from savdex.web.request import context
from savdex.web.seo import Seo
from savdex.web.shared import Context, public_url

#: NewsPost::CATEGORIES и CATEGORY_KEYS — рубрика → ключ словаря
RUBRICS = {
    "Обновления сервиса": "updates",
    "Тарифы и оплата": "pricing",
    "Аналитика рынка": "market",
    "Полезное": "useful",
}

#: DateHelper::MONTHS_GENITIVE
_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

#: str_word_count($text, 0, 'абв…ЯЁ'): слово — буквы, внутри «'» и «-»
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'\-]*")


def published() -> QuerySet[NewsPost]:
    """NewsPost::scopePublished + NewsRepository::newestFirst."""
    from django.db.models import BooleanField, ExpressionWrapper

    return (
        NewsPost.objects.filter(is_published=True)
        .filter(Q(published_at__isnull=True) | Q(published_at__lte=timezone.now()))
        .annotate(
            _undated=ExpressionWrapper(Q(published_at__isnull=True), output_field=BooleanField())
        )
        .order_by("_undated", "-published_at", "-sort", "-id")
    )


def rubric(category: str | None, locale: str) -> str:
    """NewsPost::categoryLabel."""
    key = RUBRICS.get(category or "")

    return ui.t(f"news.rubrics.{key}", locale) if key else (category or "")


def day_month_year(moment: datetime | None, locale: str) -> str:
    """DateHelper::dayMonthYear."""
    if moment is None:
        return ""

    moment = moment.astimezone(UTC) if moment.tzinfo else moment

    if locale == "ru":
        return f"{moment.day} {_GENITIVE[moment.month - 1]} {moment.year}"

    template = ui.date_template(locale, "day_month_year", moment.month)

    return template.replace("{d}", str(moment.day)).replace("{y}", str(moment.year))


def _localized(post: NewsPost, field: str, locale: str) -> str:
    """NewsPost::localized: машинный перевод, пустой — оригинал."""
    original = str(getattr(post, field) or "")

    if locale == "ru":
        return original

    translated = str((getattr(post, f"{field}_i18n") or {}).get(locale) or "")

    return translated if translated.strip() != "" else original


def read_time(post: NewsPost, locale: str) -> str:
    """NewsPost::readTime."""
    if (post.read_time or "").strip():
        return str(post.read_time)

    text = re.sub(r"<[^>]*>", "", post.body or "")
    words = len(_WORD.findall(text))

    return ui.t("news.read_time", locale, count=max(1, math.ceil(words / 180)))


def image_url(post: NewsPost) -> str | None:
    path = (post.image_path or "").strip()

    if path == "":
        return None

    if path.startswith(("http://", "https://", "/")):
        return path

    if not (laravel_storage.public_root() / path).is_file():
        return None

    return public_url(path)


def present(post: NewsPost, locale: str) -> dict[str, Any]:
    """NewsRepository::present."""
    body = _localized(post, "body", locale)

    return {
        "slug": post.slug,
        "category": post.category,
        "category_label": rubric(post.category, locale),
        "date": day_month_year(post.published_at, locale),
        "sort": post.sort,
        "read": read_time(post, locale),
        "image": image_url(post),
        "title": _localized(post, "title", locale),
        "excerpt": _localized(post, "excerpt", locale),
        "body": [p.strip() for p in re.split(r"(?:\r\n|\n|\r){2,}", body) if p.strip()],
    }


def _seo(ctx: Context) -> Seo:
    return Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)


def index(request: HttpRequest) -> HttpResponse:
    """NewsController::index."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    posts = list(published())
    categories = sorted({p.category for p in posts})
    seo = _seo(ctx)
    seo.title(ctx.t("news.title")).description(ctx.t("news.description")).canonical(ctx.url("news"))

    return inertia.render(
        ctx,
        "news/Index",
        {
            "posts": [present(p, ctx.locale) for p in posts],
            "categories": [{"value": c, "label": rubric(c, ctx.locale)} for c in categories],
        },
        seo,
    )


def related(post: NewsPost, locale: str, limit: int = 3) -> list[dict[str, Any]]:
    """NewsRepository::related: сначала та же рубрика, потом остальные."""
    same = list(published().filter(category=post.category).exclude(id=post.id)[:limit])
    rest = list(published().exclude(id=post.id).exclude(id__in=[p.id for p in same])[:limit])

    return [present(p, locale) for p in (same + rest)[:limit]]


def show(request: HttpRequest, slug: str) -> HttpResponse:
    """NewsController::show."""
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    post = published().filter(slug=slug).first()

    if post is None:
        return not_found(ctx)

    card = present(post, ctx.locale)
    seo = _seo(ctx)
    seo.title(card["title"] or ctx.t("news.title"))
    seo.description(card["excerpt"])
    seo.canonical(ctx.url(f"news/{slug}"))
    seo.image(card["image"])
    seo.type = "article"
    article = {
        "@type": "NewsArticle",
        "headline": card["title"],
        "description": card["excerpt"],
        "author": {"@type": "Organization", "name": "SAVDEX"},
        "mainEntityOfPage": seo.get_canonical(),
    }
    seo.schema({k: v for k, v in article.items() if v})

    return inertia.render(
        ctx, "news/Show", {"post": card, "related": related(post, ctx.locale)}, seo
    )
