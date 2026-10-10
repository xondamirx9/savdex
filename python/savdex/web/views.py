"""
Страницы сайта, которые отдаёт Django (этап 3).

Каждая — копия своего метода контроллера Laravel; сверка —
tests/test_web_parity.py. С этапа 8 Apache (docker/apache-python.conf)
передаёт Django все адреса, кроме готовых файлов из public/.
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


def error(ctx: Context, status: int, bare: bool = False, message: str = "") -> HttpResponse:
    """
    Страница ошибки в оформлении сайта — как обработчик исключений в
    bootstrap/app.php: Error с языком, словарём и ссылками языков.
    У ошибки сервера — код обращения, и она пишется в журнал.
    """
    reference = None

    if status >= 500:
        import hashlib
        import logging
        import time

        reference = hashlib.md5(f"{message}{int(time.time())}".encode()).hexdigest()[:8]
        logging.getLogger("savdex").error(
            "Код обращения %s: %s (%s)", reference, message, ctx.request.build_absolute_uri()
        )

    seo = _seo(ctx)
    title = (
        ui.t("errors.not_found", ctx.locale)
        if status == 404
        else ui.t("errors.generic", ctx.locale, status=status)
    )
    seo.title(title).bare()
    props = {
        "status": status,
        "reference": reference,
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

    if bare:
        return inertia.render_bare(ctx, "Error", props, seo, status)

    return inertia.render(ctx, "Error", props, seo, status=status)


def not_found(ctx: Context) -> HttpResponse:
    return error(ctx, 404)


# ── «О компании» и «Контакты» ───────────────────────────────────────


def _count(query: str, params: list[Any] | None = None) -> int:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(query, params or [])

        return int(cursor.fetchone()[0])


def stats(locale: str) -> dict[str, int]:
    """PageController::stats — счётчики витрины, все из базы."""
    # Listing::scopeVisibleIn: на всех языках одно и то же — и загруженное
    # из книги тоже
    listings = "select count(*) from listings where status = 'active' and deleted_at is null"
    params: list[Any] = []

    return {
        "companies": _count(
            "select count(*) from companies where status = 'active' and deleted_at is null"
        ),
        "listings": _count(listings, params),
        "categories": _count(
            "select count(*) from categories where is_active and parent_id is not null"
        ),
        "countries": _count(
            "select count(*) from countries c where c.is_active and exists (select 1 from "
            "companies m where m.country_id = c.id and m.status = 'active' "
            "and m.deleted_at is null)"
        ),
    }


def about(request: HttpRequest) -> HttpResponse:
    """PageController::about."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    pages = {p.key: p for p in Page.objects.filter(key__in=["about", "contacts"])}
    about_page = pages.get("about")
    translations = content.Translations(ctx.locale)
    values = settings_values()
    seo = _seo(ctx)
    meta_title = (about_page.meta_title or "").strip() if about_page else ""
    meta_description = (about_page.meta_description or "").strip() if about_page else ""

    if about_page is not None and meta_title:
        seo.title(
            _meta(about_page, "meta_title", translations)
            or content.localized(about_page, "title", translations)
        )
    else:
        seo.title(ctx.t("seo.about_title"))

    if about_page is not None and meta_description:
        seo.description(
            _meta(about_page, "meta_description", translations)
            or content.localized(about_page, "excerpt", translations)
        )
    else:
        seo.description(ctx.t("seo.about_description"))

    seo.canonical(ctx.url("about"))
    office_ = office(values)

    if office_ is not None:
        details: dict[str, Any] = {
            "legalName": setting(values, "legal_name"),
            "email": setting(values, "support_email"),
            "telephone": setting(values, "support_phone"),
            "address": {
                "@type": "PostalAddress",
                "streetAddress": office_["address"],
                "addressCountry": "UZ",
            }
            if office_["address"] != ""
            else None,
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": office_["lat"],
                "longitude": office_["lng"],
            }
            if office_["lat"] is not None
            else None,
        }
        # array_filter: пустые поля не размечаются
        seo.organization_details = {k: v for k, v in details.items() if v}

    return inertia.render(
        ctx,
        "About",
        {
            "stats": stats(ctx.locale),
            "office": office_,
            "page": _card(about_page, translations) if about_page else None,
            "contacts": _card(pages["contacts"], translations) if "contacts" in pages else None,
            "nav": docs_nav(ctx, office_, translations),
        },
        seo,
    )


def contacts(request: HttpRequest) -> HttpResponse:
    """PageController::contacts — /contact (без «s»)."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    seo = _seo(ctx)
    seo.title(ctx.t("seo.contacts_title")).description(ctx.t("seo.contacts_description"))
    seo.canonical(ctx.url("contact"))

    return inertia.render(ctx, "Contacts", {}, seo)
