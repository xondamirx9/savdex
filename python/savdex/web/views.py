"""
Страницы сайта, которые отдаёт Django (этап 3).

Каждая — копия своего метода контроллера Laravel; сверка —
tests/test_web_parity.py. Какие адреса вообще доходят до Django, решает
Apache (docker/apache-python.conf) по переменной SAVDEX_PY_PAGES: убрать
группу из переменной — и адреса снова отдаёт Laravel, без выкладки.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse

from savdex.site.models import FaqItem, Page
from savdex.web import content, inertia, locales, ui
from savdex.web.request import context
from savdex.web.seo import Seo
from savdex.web.shared import Context, setting, settings_values

#: Page::DOCS
DOCS = ("help", "guide", "rules")


def _seo(ctx: Context) -> Seo:
    return Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)


# ── Страницы о площадке ─────────────────────────────────────────────


def _card(page: Page, translations: content.Translations) -> dict[str, Any]:
    """Page::card: ключ, заголовок, подзаголовок и блоки текста на языке."""
    locale = translations.locale
    own_body = content.own(page, "body", locale)

    if own_body or locale == "ru":
        body = content.blocks(own_body)
    else:
        body = content.blocks(page.body)
        translations.prefetch(content.strings(body))
        body = content.map_strings(body, lambda s: str(translations.text(s) or ""))

    return {
        "key": page.key,
        "title": content.localized(page, "title", translations),
        "lead": content.localized(page, "excerpt", translations),
        "blocks": body,
    }


def _meta(page: Page, field: str, translations: content.Translations) -> str:
    """Page::translatedMeta: поля для поисковика — русские, прочие языки переводятся."""
    value = (getattr(page, field) or "").strip()

    return "" if value == "" else str(translations.text(value) or "").strip()


def office(values: dict[str, Any]) -> dict[str, Any] | None:
    """OfficeLocation::current."""
    import re

    address = setting(values, "office_address").strip()
    raw = setting(values, "office_coords")
    lat = lng = None

    if re.fullmatch(r"\s*-?\d{1,2}(\.\d+)?\s*,\s*-?\d{1,3}(\.\d+)?\s*", raw):
        a, b = (float(p.strip()) for p in raw.split(",", 1))

        if abs(a) <= 90 and abs(b) <= 180:
            lat, lng = a, b

    if address == "" and lat is None:
        return None

    try:
        zoom = int(float(setting(values, "office_map_zoom", "16") or 0))
    except ValueError:
        zoom = 0

    return {
        "address": address,
        "lat": lat,
        "lng": lng,
        "zoom": 16 if zoom == 0 else max(3, min(19, zoom)),
        "hours": setting(values, "support_hours").strip(),
    }


def docs_nav(
    ctx: Context, office_: dict[str, Any] | None, translations: content.Translations
) -> list[dict[str, str]]:
    """PageController::docsNav."""
    pages = {p.key: p for p in Page.objects.filter(key__in=["contacts", *DOCS])}
    nav = [{"key": "about", "href": "/about", "label": ui.t("about.nav.about", ctx.locale)}]

    if "contacts" in pages:
        nav.append(
            {
                "key": "contacts",
                "href": "/about#contacts",
                "label": content.localized(pages["contacts"], "title", translations),
            }
        )

    if office_ is not None:
        nav.append(
            {
                "key": "office",
                "href": "/about#office",
                "label": ui.t("about.nav.office", ctx.locale),
            }
        )

    for key in DOCS:
        page = pages.get(key)

        if page is not None and page.is_published:
            nav.append(
                {
                    "key": key,
                    "href": f"/{key}",
                    "label": content.localized(page, "title", translations),
                }
            )

    return nav


def doc(request: HttpRequest, key: str) -> HttpResponse:
    """PageController::doc — «Помощь», «Инструкция», «Правила»."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    page = Page.objects.filter(key=key, is_published=True).first()

    if page is None:
        return not_found(ctx)

    translations = content.Translations(ctx.locale)
    faq: list[dict[str, str]] = []

    if key == "help":
        items = FaqItem.objects.filter(page=page, is_published=True).order_by("sort", "id")
        faq = [
            {
                "question": content.localized(item, "question", translations),
                "answer": content.localized(item, "answer", translations),
            }
            for item in items
        ]

    card = _card(page, translations)
    seo = _seo(ctx)
    seo.title(_meta(page, "meta_title", translations) or card["title"])
    seo.description(_meta(page, "meta_description", translations) or card["lead"])
    seo.canonical(ctx.url(key))

    if faq:
        seo.schema(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                    }
                    for item in faq
                ],
            }
        )

    return inertia.render(
        ctx,
        "DocPage",
        {"page": card, "faq": faq, "nav": docs_nav(ctx, office(settings_values()), translations)},
        seo,
    )


# ── Ошибки ──────────────────────────────────────────────────────────


def not_found(ctx: Context) -> HttpResponse:
    """
    Страница 404 в оформлении сайта — как обработчик исключений в
    bootstrap/app.php: Error с языком, словарём и ссылками языков.
    """
    seo = _seo(ctx)
    seo.title(ui.t("errors.not_found", ctx.locale)).bare()
    props = {
        "status": 404,
        "reference": None,
        "locale": ctx.locale,
        "translations": ui.translations(ctx.locale),
        "localeLinks": [
            {
                "code": code,
                "label": meta["label"],
                "short": meta["short"],
                "url": locales.switch_url(ctx.root, ctx.request_uri, code),
            }
            for code, meta in locales.ALL.items()
        ],
    }

    return inertia.render(ctx, "Error", props, seo, status=404)
