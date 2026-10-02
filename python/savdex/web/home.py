"""
Главная — копия PageController::home.

Секции: тексты и видимость из админки (LandingBlock::cards), счётчики,
баннер акции, фон первого экрана, популярные категории и услуги, лента
товаров VIP и лента запросов (ListingCard), поставщики, страны и города
для поиска, свежие новости и отзывы. Всё только читается; машинный
перевод, которого ещё нет, встаёт в очередь, как у Laravel.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse
from PIL import Image

from savdex import laravel_storage
from savdex.site.models import Banner, LandingBlock
from savdex.web import content, inertia, locales, news, platform, reviews, ui
from savdex.web.currency import CurrencyRate
from savdex.web.directory import _named, listed_countries, logo_url, type_label, type_options
from savdex.web.request import context
from savdex.web.seo import Seo, _limit
from savdex.web.shared import (
    Context,
    ago,
    initials,
    public_url,
    setting,
    settings_values,
)
from savdex.web.views import stats

# ── Общее ───────────────────────────────────────────────────────────


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def visible_in(locale: str, alias: str = "l") -> tuple[str, list[Any]]:
    """
    Listing::scopeVisibleIn: объявления показываются на всех языках, и
    загруженные из книги тоже — до перевода русским текстом. Условие
    оставлено функцией, чтобы запросы витрины не менялись.
    """
    return "", []


def php_round(value: float, places: int = 0) -> float:
    """round($value, $places) PHP: половина — от нуля, точность и отрицательная."""
    exponent = Decimal(1).scaleb(-places)

    return float(Decimal(repr(value)).quantize(exponent, rounding=ROUND_HALF_UP))


def _utc(moment: datetime | None) -> datetime | None:
    """Столбцы timestamp без пояса: Laravel пишет в них время UTC."""
    if moment is None or moment.tzinfo is not None:
        return moment

    return moment.replace(tzinfo=UTC)


def _filled(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def completeness(company: dict[str, Any], has_documents: bool) -> int:
    """Company::profileCompleteness."""
    checks = [
        _filled(company["name"]),
        _filled(company["type"]) or company["legal_form"] in ("individual", "freelancer"),
        company["city_id"] is not None,
        _filled(company["phone"]),
        _filled(company["email"]),
        _filled(company["tin"]),
        _filled(company["address"]),
        len(company["description"] or "") >= 100,
        _filled(company["logo_path"]),
        has_documents,
    ]

    return int(php_round(sum(checks) / len(checks) * 100))


# ── Цена в валюте языка (PriceDisplay) ──────────────────────────────

#: PriceDisplay::DEFAULTS
DISPLAY_DEFAULTS = {"ru": "UZS", "uz": "UZS", "en": "USD", "zh": "CNY", "tr": "TRY"}

#: Currencies::ALL
CURRENCIES = ("UZS", "USD", "EUR", "CNY", "TRY", "RUB", "KZT")


class PriceDisplay:
    def __init__(self, locale: str, values: dict[str, Any], rate: CurrencyRate) -> None:
        chosen = values.get(f"display_currency_{locale}")
        chosen = chosen.strip(" \t\n\r\0\x0b").upper() if isinstance(chosen, str) else None
        default = DISPLAY_DEFAULTS.get(locale, DISPLAY_DEFAULTS[locales.DEFAULT])
        self.currency = chosen if chosen in CURRENCIES else default
        self.rate = rate

    def convert(self, amount: Decimal | float | None, source: str | None) -> dict[str, Any] | None:
        if amount is None or source is None or source == self.currency:
            return None

        from_rate, to_rate = self.rate.rate(source), self.rate.rate(self.currency)

        if from_rate is None or to_rate is None:
            return None

        rounded = self.round(float(amount) * from_rate / to_rate)

        return None if rounded <= 0.0 else {"price": rounded, "currency": self.currency}

    @staticmethod
    def round(value: float) -> float:
        if value <= 0.0:
            return 0.0

        digits = 2 - math.floor(math.log10(value))

        return php_round(value, min(2, digits))


# ── Карточка объявления (ListingCard) ───────────────────────────────

NEW_DAYS = 7

_LISTING_COMPANY = (
    "c.name as c_name, c.slug as c_slug, c.verification_level as c_verification_level, "
    "c.rating as c_rating, c.response_time_hours as c_response_time_hours, "
    "c.city_id as c_city_id, c.country_id as c_country_id, "
    "c.type as c_type, c.legal_form as c_legal_form, c.phone as c_phone, c.email as c_email, "
    "c.tin as c_tin, c.address as c_address, c.description as c_description, "
    "c.logo_path as c_logo_path, exists (select 1 from company_documents d where "
    "d.company_id = c.id and d.moderation_status = 'approved') as c_has_documents"
)


class Cards:
    """ListingCard::present для пачки объявлений: справочники — одним заходом."""

    def __init__(
        self, ctx: Context, values: dict[str, Any], translations: content.Translations
    ) -> None:
        self.ctx = ctx
        self.locale = ctx.locale
        self.translations = translations
        self.cities = _named("cities", ctx.locale)
        self.countries = _named("countries", ctx.locale)
        self.categories = _named("categories", ctx.locale)
        self.codes = {r["id"]: r["code"] for r in _rows("select id, code from countries")}
        self.prices = PriceDisplay(ctx.locale, values, CurrencyRate())
        self.now = datetime.now(UTC)
        # Служебная компания: её заявки из Excel подписаны площадкой
        self.service = platform.service_company_id()

    def _localized(self, listing: dict[str, Any], field: str) -> str | None:
        """Listing::localized: перевод есть и не пустой — он, иначе оригинал."""
        if self.locale != "ru":
            value = (listing[f"{field}_i18n"] or {}).get(self.locale)

            if str(value or "").strip() != "":
                return str(value)

        original = listing[field]

        return None if original is None else str(original)

    def present(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [r["id"] for r in rows]
        images: dict[int, list[dict[str, Any]]] = {}
        badges: dict[int, list[str | None]] = {}
        promoted: set[int] = set()

        if ids:
            for image in _rows(
                "select listing_id, path, thumb_path from listing_images "
                "where listing_id = any(%s) order by sort",
                [ids],
            ):
                images.setdefault(image["listing_id"], []).append(image)

            promotions = _rows(
                "select p.listing_id, t.badge from promotions p left join promotion_types t "
                "on t.id = p.promotion_type_id where p.listing_id = any(%s) "
                "and p.status = 'active' order by p.id",
                [ids],
            )
            self.translations.prefetch(p["badge"] for p in promotions)

            for promotion in promotions:
                promoted.add(promotion["listing_id"])
                badges.setdefault(promotion["listing_id"], []).append(
                    self.translations.text(promotion["badge"])
                )

        return [
            self._card(r, images.get(r["id"], []), badges.get(r["id"], []), r["id"] in promoted)
            for r in rows
        ]

    def _card(
        self,
        listing: dict[str, Any],
        images: list[dict[str, Any]],
        badges: list[str | None],
        promoted: bool,
    ) -> dict[str, Any]:
        now = self.now
        published = _utc(listing["published_at"])
        cover = images[0] if images else None
        company = {k[2:]: v for k, v in listing.items() if k.startswith("c_")}
        # Заявка площадки (PlatformListings): SavdEx вместо служебной
        # компании, город — самой заявки, страны поставщика нет
        own = platform.owns(listing, self.service)
        city = listing["city_id"] if own else company["city_id"]
        country = None if own else company["country_id"]

        return {
            "id": listing["id"],
            "slug": listing["slug"],
            "title": self._localized(listing, "title") or "",
            "excerpt": _limit(self._localized(listing, "description") or "", 140, "..."),
            "type": listing["type"],
            "category": self.categories.get(listing["category_id"])
            if listing["category_id"]
            else None,
            "price": float(listing["price"]) if listing["price"] is not None else None,
            "currency": listing["currency"],
            "converted": None
            if listing["price_negotiable"]
            else self.prices.convert(listing["price"], listing["currency"]),
            "unit": listing["unit"],
            "negotiable": listing["price_negotiable"],
            "min_order": listing["min_order"],
            "city": self.cities.get(city) if city else None,
            "country": self.codes.get(country) if country else None,
            "country_name": self.countries.get(country) if country else None,
            "published": ago(published, self.locale, now) if published else None,
            "is_new": published is not None and published > now - timedelta(days=NEW_DAYS),
            "views": listing["views_count"],
            "cover": self.ctx.url("storage/" + (cover["thumb_path"] or cover["path"]))
            if cover
            else None,
            "photos": len(images),
            "company": {
                "name": platform.NAME,
                "slug": None,
                "verified": 0,
                "rating": 0.0,
                "trust": 0,
                "response_hours": None,
                "platform": True,
            }
            if own
            else {
                "name": company["name"],
                "slug": company["slug"],
                "verified": int(company["verification_level"] or 0),
                "rating": float(company["rating"] or 0),
                "trust": completeness(company, bool(company["has_documents"])),
                "response_hours": company["response_time_hours"],
                "platform": False,
            },
            "badges": [b for b in badges if b],
            "promoted": promoted,
        }


def _listings(where: str, params: list[Any], order: str, limit: int) -> list[dict[str, Any]]:
    return _rows(
        f"select l.*, {_LISTING_COMPANY} from listings l join companies c on c.id = l.company_id "
        f"where l.status = 'active' and l.deleted_at is null and c.status = 'active' "
        f"and c.deleted_at is null {where} order by {order} limit {int(limit)}",
        params,
    )


def latest_listings(cards: Cards) -> list[dict[str, Any]]:
    """PageController::latestListings: витрина VIP, продвинутые первыми."""
    visible, params = visible_in(cards.locale)

    return cards.present(
        _listings(
            f"{visible} and l.type = 'supply' and exists (select 1 from subscriptions s "
            "join plans p on p.id = s.plan_id where s.company_id = c.id and s.status = 'active' "
            "and (s.ends_at is null or s.ends_at > now()) and p.code = 'vip')",
            params,
            "(select count(*) from promotions p where p.listing_id = l.id "
            "and p.status = 'active') desc, l.published_at desc, l.id desc",
            12,
        )
    )


def latest_products(cards: Cards, shown: list[int]) -> list[dict[str, Any]]:
    """PageController::latestProducts: лента «Товары», без карточек витрины VIP."""
    visible, params = visible_in(cards.locale)
    skip = f" and l.id not in ({', '.join(['%s'] * len(shown))})" if shown else ""

    return cards.present(
        _listings(
            f"{visible} and l.type = 'supply'{skip}",
            [*params, *shown],
            "(select count(*) from promotions p where p.listing_id = l.id "
            "and p.status = 'active') desc, l.published_at desc, l.id desc",
            8,
        )
    )


def latest_requests(cards: Cards) -> list[dict[str, Any]]:
    """PageController::latestRequests: запросы на закупку."""
    visible, params = visible_in(cards.locale)

    return cards.present(
        _listings(f"{visible} and l.type = 'demand'", params, "l.published_at desc, l.id desc", 8)
    )


# ── Секции ──────────────────────────────────────────────────────────

#: LandingBlock::KEYS и WITH_ITEMS
KEYS = (
    "hero",
    "stats",
    "categories",
    "vip",
    "products",
    "requests",
    "suppliers",
    "how",
    "reviews",
    "faq",
    "news",
    "cta",
)
WITH_ITEMS = ("how", "faq")

_BREAKS = re.compile(r"(?:\r\n|\n|\r)\s*(?:\r\n|\n|\r)")
_LINE = re.compile(r"\r\n|\n|\r")
_TRIM = " \t\n\r\0\x0b"


def parse_items(text: str | None) -> list[dict[str, str]]:
    """LandingBlock::parseItems: название первой строкой, пункты через пустую строку."""
    items = []

    for chunk in _BREAKS.split((text or "").strip(_TRIM)):
        lines = [line.strip(_TRIM) for line in _LINE.split(chunk.strip(_TRIM))]
        lines = [line for line in lines if line != ""]

        if lines:
            items.append({"title": lines[0], "text": " ".join(lines[1:])})

    return items


def _items(block: LandingBlock, translations: content.Translations) -> list[dict[str, str]]:
    """LandingBlock::items: свой текст языка или перевод русского по пунктам."""
    locale = translations.locale
    own = content.own(block, "body", locale)

    if own != "" or locale == "ru":
        return parse_items(own)

    items = parse_items(block.body)
    translations.prefetch(t for item in items for t in item.values())

    return [
        {
            "title": str(translations.text(item["title"]) or ""),
            "text": str(translations.text(item["text"]) or ""),
        }
        for item in items
    ]


def landing_cards(translations: content.Translations) -> dict[str, Any]:
    """LandingBlock::cards."""
    cards = {}

    for block in LandingBlock.objects.filter(key__in=KEYS).order_by():
        card: dict[str, Any] = {
            "visible": block.is_visible or block.key == "hero",
            "eyebrow": content.localized(block, "eyebrow", translations),
            "heading": content.localized(block, "heading", translations),
            "subheading": content.localized(block, "subheading", translations),
            "button": content.localized(block, "button", translations),
        }

        if block.key in WITH_ITEMS:
            card["items"] = _items(block, translations)
        else:
            card["note"] = content.localized(block, "body", translations)

        cards[block.key] = card

    return cards


def banner(ctx: Context, placement: str = "home") -> dict[str, Any] | None:
    """BannerCard::forPlacement: главная, каталог."""
    now = datetime.now(UTC)
    found = (
        Banner.objects.filter(is_active=True, placement=placement)
        .exclude(starts_at__gt=now)
        .exclude(ends_at__lte=now)
        .order_by("sort", "-id")
        .first()
    )

    if found is None:
        return None

    own = found.images.filter(locale=ctx.locale).first()
    image = own.image_path if own is not None else found.image_path
    mobile = own.image_mobile_path if own is not None else found.image_mobile_path

    return {
        "key": f"banner-{found.id}",
        "url": found.url,
        "alt": found.alt,
        "image": ctx.url("storage/" + image),
        "imageMobile": ctx.url("storage/" + mobile) if mobile is not None else None,
        "focal": f"{found.focal_x}% {found.focal_y}%",
        "dismissible": found.is_dismissible,
        "dismissDays": 3,
    }


HERO_FALLBACK = "/images/hero-port.svg"


def _absolute(path: str) -> bool:
    return path.startswith(("http://", "https://", "/"))


def hero_image(values: dict[str, Any]) -> str:
    """Appearance::heroImage."""
    path = setting(values, "hero_image", "").strip(_TRIM)

    if path == "":
        return HERO_FALLBACK

    return path if _absolute(path) else public_url(path)


def hero_ratio(values: dict[str, Any]) -> float | None:
    """Appearance::heroImageRatio: ширина / высота загруженного фона."""
    path = setting(values, "hero_image", "").strip(_TRIM)
    file = laravel_storage.public_root() / path

    if path == "" or _absolute(path) or not file.is_file():
        return None

    try:
        with Image.open(file) as image:
            width, height = image.size
    except (OSError, ValueError):
        return None

    return php_round(width / height, 4) if height > 0 else None


#: Объявление действующей компании — как в каталоге: у заблокированной
#: и удалённой объявлений в счётчиках и фильтрах нет
LIVE_COMPANY = (
    " and exists (select 1 from companies co where co.id = l.company_id "
    "and co.status = 'active' and co.deleted_at is null)"
)


def popular_categories(locale: str) -> list[dict[str, Any]]:
    """PageController::popularCategories: с подкатегориями, без пустых."""
    visible, params = visible_in(locale)
    counts = {
        r["category_id"]: int(r["total"])
        for r in _rows(
            "select category_id, count(*) as total from listings l where l.status = 'active' "
            f"and l.deleted_at is null{visible}{LIVE_COMPANY} and l.category_id is not null "
            "group by category_id",
            params,
        )
    }
    names = _named("categories", locale)
    children: dict[int, list[int]] = {}

    for child in _rows("select id, parent_id from categories where parent_id is not null"):
        children.setdefault(child["parent_id"], []).append(child["id"])

    result = []

    for c in _rows(
        "select id, slug, icon from categories where parent_id is null and is_active order by sort"
    ):
        total = counts.get(c["id"], 0) + sum(counts.get(i, 0) for i in children.get(c["id"], []))

        if total > 0:
            result.append(
                {
                    "id": c["id"],
                    "slug": c["slug"],
                    "name": names[c["id"]],
                    "icon": c["icon"],
                    "listings": total,
                }
            )

    return result


#: ItTask::SERVICE_SECTIONS без «Другого» и PageController::DEFAULT_SERVICES
SERVICE_SECTIONS = {
    "it": ("web", "mobile", "erp", "integration", "design", "automation", "support"),
    "hr_services": ("hr",),
    "logistics": (),
    "customs": (),
    "accounting": (),
}
DEFAULT_SERVICES = ("it", "logistics")


def popular_services(locale: str) -> list[dict[str, Any]]:
    """PageController::popularServices: два направления по числу задач."""
    counts = {
        r["service_type"]: int(r["total"])
        for r in _rows(
            "select t.service_type, count(*) as total from it_tasks t join companies c "
            "on c.id = t.company_id where t.status = 'active' and c.status = 'active' "
            "and c.deleted_at is null group by t.service_type"
        )
    }
    sections: list[dict[str, Any]] = [
        {
            "type": section,
            "name": ui.t(f"it_tasks.types.{section}", locale),
            "tasks": sum(counts.get(t, 0) for t in (types or (section,))),
        }
        for section, types in SERVICE_SECTIONS.items()
    ]

    def rank(section: str) -> int:
        return DEFAULT_SERVICES.index(section) if section in DEFAULT_SERVICES else 2

    return sorted(sections, key=lambda s: (-s["tasks"], rank(s["type"])))[:2]


def top_suppliers(ctx: Context) -> list[dict[str, Any]]:
    """PageController::topSuppliers: лучшие по проверке и рейтингу."""
    options = type_options(ctx.locale)
    cities = _named("cities", ctx.locale)

    return [
        {
            "slug": c["slug"],
            "name": c["name"],
            "type_label": type_label(ctx, c, options),
            "city": cities.get(c["city_id"]) if c["city_id"] else None,
            "verification_level": c["verification_level"],
            "rating": float(c["rating"] or 0),
            "reviews_count": c["reviews_count"],
            "listings_count": int(c["listings_count"]),
            "initials": initials(c["name"]),
            "logo": logo_url(ctx, c["logo_path"]),
        }
        for c in _rows(
            "select m.*, (select count(*) from listings l where l.company_id = m.id and "
            "l.status = 'active' and l.deleted_at is null) as listings_count from companies m "
            "where m.status = 'active' and m.deleted_at is null "
            "order by m.verification_level desc, m.rating desc, m.id limit 4"
        )
    ]


def city_options(locale: str) -> list[dict[str, Any]]:
    """PageController::cityOptions: города с живыми объявлениями, по названию."""
    names = _named("cities", locale)
    cities = [
        {"id": r["id"], "name": names[r["id"]]}
        for r in _rows(
            "select id from cities c where is_active and exists (select 1 from listings l "
            "where l.city_id = c.id and l.status = 'active' and l.deleted_at is null"
            f"{LIVE_COMPANY})"
        )
    ]

    return sorted(cities, key=lambda c: c["name"])


# ── Страница ────────────────────────────────────────────────────────


def home(request: HttpRequest) -> HttpResponse:
    """PageController::home."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    values = settings_values()
    translations = content.Translations(ctx.locale)
    counters = stats(ctx.locale)
    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("seo.home_title")).description(ctx.t("seo.home_description"))
    seo.canonical(ctx.url("/"))
    seo.schema(
        {
            "@type": "WebSite",
            "name": "SAVDEX",
            "url": ctx.url("/"),
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": ctx.url("/catalog?q={search_term_string}"),
                },
                "query-input": "required name=search_term_string",
            },
        }
    )
    blocks = landing_cards(translations)
    faq = blocks.get("faq")

    if faq is not None and faq["visible"] and faq["items"]:
        seo.schema(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["title"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["text"]},
                    }
                    for item in faq["items"]
                ],
            }
        )

    cards = Cards(ctx, values, translations)
    latest = latest_listings(cards)

    return inertia.render(
        ctx,
        "Home",
        {
            "blocks": blocks,
            "stats": counters,
            "banner": banner(ctx),
            "heroImage": hero_image(values),
            "heroRatio": hero_ratio(values),
            "categories": popular_categories(ctx.locale),
            "services": popular_services(ctx.locale),
            "latest": latest,
            "products": latest_products(cards, [row["id"] for row in latest]),
            "requests": latest_requests(cards),
            "suppliers": top_suppliers(ctx),
            "countries": [
                {"code": c["code"], "name": c["name"]} for c in listed_countries(ctx.locale)
            ],
            "cities": city_options(ctx.locale),
            "news": [news.present(p, ctx.locale) for p in news.published()[:4]],
            # Три свежих отзыва — о компаниях и о площадке (ReviewFeed)
            "reviews": reviews.take("all", 3, 0, translations),
        },
        seo,
    )
