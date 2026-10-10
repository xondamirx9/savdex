"""
Страница объявления /listing/<адрес> — копия CatalogController::show.

Объявление с характеристиками, фото, тегами (ListingTags), продавцом и
его контактами (маской, пока не заплачено), похожие. Неопубликованное
видит только владелец — как предпросмотр, без счёта просмотров.

Пишет, как StatsRecorder::view: +1 к listings.views_count (и строка
журнала, если смотрит администратор), к дневной строке listing_stats
и «Кто мной интересуется» с этим объявлением — не чаще раза в полчаса
на посетителя (ключ stats:view:<посетитель>:<объявление> в общем
файловом кэше). Под throttle:120,1.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web import analytics, content, inertia, platform, specs
from savdex.web.catalog import bump_daily, visitor_key, without_recent
from savdex.web.companies import website_url
from savdex.web.company import PUBLIC_TYPES, href, masked, remember_viewer
from savdex.web.directory import _named, logo_url
from savdex.web.home import _LISTING_COMPANY, Cards, _utc, visible_in
from savdex.web.it_tasks import number_format
from savdex.web.seo import Seo
from savdex.web.shared import Context, initials, settings_values
from savdex.web.tenders import _admin
from savdex.web.throttle import throttled

#: Locales::codes()
LOCALES = ("ru", "uz", "en", "zh", "tr")

# ── ListingTags ─────────────────────────────────────────────────────

MAX_TAGS = 8
TITLE_WORDS = 5
MAX_SUGGESTIONS = 12
STOP_WORDS = frozenset(
    {
        "куплю", "продам", "продаю", "купим", "продаём", "ищем", "ищу",
        "опт", "оптом", "розница", "шт", "штук", "тонн", "тонны", "кг",
        "для", "под", "из", "на", "в", "с", "со", "по", "от", "до", "и",
        "или", "без", "при", "за", "это", "как", "все", "любой", "любые",
        "sotib", "olamiz", "sotamiz", "dona", "uchun",
    }
)  # fmt: skip

_TRIM = " \t\n\r\0\x0b"


def _letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def _keep(char: str) -> bool:
    """[\\p{L}\\p{N}\\s×xх-]: буква, цифра, пробельный или «×», «x», «х», «-»."""
    return (
        _letter(char)
        or unicodedata.category(char).startswith("N")
        or char.isspace()
        or char in "×xх-"
    )


def _attributes(
    attributes: list[dict[str, Any]], fields: dict[str, str], locale: str, text: specs.Text
) -> list[dict[str, Any]]:
    """
    Характеристики карточки: поля категории подписью из справочника,
    за ними детали товара (spec_*) на языке посетителя — ProductSpecs::present.
    """
    rows: list[dict[str, Any]] = []

    for a in sorted(attributes, key=lambda a: specs.owns(str(a["key"]))):
        if specs.owns(str(a["key"])):
            shown = specs.present(str(a["key"]), str(a["value"] or ""), locale, text)

            if shown is not None:
                rows.append(shown)
        else:
            rows.append({"key": text(fields.get(a["key"]) or a["key"]), "value": text(a["value"])})

    return rows


def suggestions(
    listing: dict[str, Any],
    category: str | None,
    parent: str | None,
    attributes: list[str],
    city: str | None,
) -> list[str]:
    """ListingTags::suggestions: разделы, слова заголовка, числа характеристик, город."""
    tags = [name.lower() for name in (category, parent) if name is not None]
    lowered = str(listing["title"] or "").lower()
    clean = "".join(c if _keep(c) else " " for c in lowered)
    words = [
        w
        for w in clean.split()
        if len(w) >= 3 and w not in STOP_WORDS and any(_letter(c) for c in w)
    ][:TITLE_WORDS]
    tags += words

    for value in attributes:
        value = value.strip(_TRIM)

        if value != "" and len(value) <= 20 and re.search(r"[0-9]", value):
            tags.append(value.lower())

    if city not in (None, ""):
        tags.append(city.lower())

    cleaned = [t.strip(_TRIM) for t in tags]

    return list(dict.fromkeys(t for t in cleaned if t != ""))[:MAX_SUGGESTIONS]


def tags(listing: dict[str, Any], suggested: list[str]) -> list[str]:
    """ListingTags::for: выбранные владельцем, если они из подсказок; иначе подсказки."""
    own = listing["tags"]
    own_list = [str(t) for t in (own if isinstance(own, list) else [])]
    chosen = [t for t in own_list if t in suggested]

    return (chosen or suggested)[:MAX_TAGS]


# ── Страница ────────────────────────────────────────────────────────


def _localized(row: dict[str, Any], field: str, locale: str) -> str | None:
    """Listing::localized: перевод есть и не пустой — он, иначе оригинал."""
    if locale != "ru":
        value = (row[f"{field}_i18n"] or {}).get(locale)

        if str(value or "").strip(_TRIM) != "":
            return str(value)

    original = row[field]

    return None if original is None else str(original)


def _visible_locales(row: dict[str, Any]) -> list[str]:
    """Listing::visibleLocales: все языки — и у загруженного из книги."""
    return list(LOCALES)


def _count_view(ctx: Context, row: dict[str, Any], visitor: str | None) -> None:
    """StatsRecorder::view: отсев повтора, +1 к счётчику, дневная строка, «Кто смотрел»."""
    if not without_recent([row["id"]], "view", visitor):
        return

    # updated_at не трогаем: просмотр — не правка (порядок «Моих объявлений», lastmod карты)
    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            "update listings set views_count = views_count + 1 where id = %s", [row["id"]]
        )

    before = row["views_count"]
    row["views_count"] = before + 1
    admin = _admin(ctx)

    if admin is not None:
        audit.record(
            connection,
            action="updated",
            section="listings",
            actor=admin,
            subject_type="App\\Models\\Listing",
            subject_id=row["id"],
            subject_label=audit.label(row, "Listing", row["id"]),
            changes={"before": {"views_count": before}, "after": {"views_count": before + 1}},
            ip=audit.client_ip(ctx.request),
        )

    bump_daily([row["id"]], "views")

    user = ctx.user
    viewer = user["company_id"] if user is not None else None

    if viewer is not None and viewer != row["company_id"]:
        remember_viewer(row["company_id"], viewer, row["id"])


def _price_text(ctx: Context, row: dict[str, Any]) -> str:
    if row["price_negotiable"] or row["price"] is None:
        return ctx.t("cabinet.listings.negotiable")

    unit = ctx.t("catalog.currency_uzs") if row["currency"] == "UZS" else row["currency"]

    return f"{number_format(float(row['price']), 0)} {unit}"


def _seo(
    ctx: Context,
    row: dict[str, Any],
    company_name: str | None,
    city: str | None,
    category: str | None,
    images: list[str],
) -> Seo:
    """SeoBuilders::listing: товар, крошки, превью картинкой /og/…"""
    title = _localized(row, "title", ctx.locale) or ""
    description = _localized(row, "description", ctx.locale)
    url = ctx.url(f"listing/{row['slug']}")

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(title + (f" — {city}" if city is not None else ""))
    seo.description(
        description
        if description not in (None, "", "0")
        else f"{title}. {_price_text(ctx, row)}. "
        + ctx.t("seo.listing_supplier", company=company_name or "")
    )
    seo.canonical(url)
    seo.locales = _visible_locales(row)
    seo.image(ctx.url(f"og/listing/{row['id']}.jpg"))
    seo.image_meta = {"width": 1200, "height": 630, "type": "image/jpeg"}
    seo.type = "product"

    url = seo.link(url)
    # Название и описание — на языке страницы, как в <title>
    product: dict[str, Any] = {
        "@type": "Product",
        "name": title,
        "description": description or "",
        "category": category,
    }

    if images:
        product["image"] = images

    if row["price"] is not None and not row["price_negotiable"]:
        product["offers"] = {
            "@type": "Offer",
            "price": float(row["price"]),
            "priceCurrency": row["currency"],
            "availability": "https://schema.org/InStock",
            "url": url,
            "seller": {"@type": "Organization", "name": company_name},
        }

    seo.schema(product)
    crumbs = [
        (ctx.t("listing.catalog"), seo.link(ctx.url("catalog"))),
        (
            category if category is not None else ctx.t("tabbar.listings"),
            seo.link(ctx.url(f"catalog?category={row['category_id']}"))
            if row["category_id"] is not None
            else seo.link(ctx.url("catalog")),
        ),
        (title, url),
    ]
    # Одинаковые подписи у PHP — один ключ массива: остаётся последний адрес
    merged: dict[str, str] = {}

    for name, link in crumbs:
        merged[name] = link

    seo.schema(
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": name, "item": link}
                for i, (name, link) in enumerate(merged.items(), start=1)
            ],
        }
    )

    return seo


def show(request: HttpRequest, slug: str) -> HttpResponse:
    """CatalogController::show — под throttle:120,1."""
    return throttled(request, 120, lambda ctx: _show(ctx, slug))


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _show(ctx: Context, slug: str) -> HttpResponse:
    from savdex.web.views import not_found

    found = _rows("select * from listings where slug = %s and deleted_at is null limit 1", [slug])

    if not found:
        return not_found(ctx)

    row = found[0]
    user = ctx.user
    viewer = user["company_id"] if user is not None else None
    owner = viewer == row["company_id"]
    preview = row["status"] != "active"

    companies = _rows(
        "select * from companies where id = %s and deleted_at is null", [row["company_id"]]
    )
    company = companies[0] if companies else None

    # Черновик для чужих не существует: 404, а не 403. Объявление
    # заблокированной или удалённой компании — тоже: в каталоге его нет
    hidden = preview or company is None or company["status"] != "active"

    if hidden and not owner:
        return not_found(ctx)

    visitor = visitor_key(ctx)

    # Свои просмотры владельца в статистику не идут: иначе каждое
    # «посмотреть, как выглядит» добавляло объявлению просмотр
    if not preview and not owner:
        _count_view(ctx, row, visitor)

    locale = ctx.locale
    translations = content.Translations(locale)
    categories = _named("categories", locale)
    cities = _named("cities", locale)
    countries = _named("countries", locale)
    city = cities.get(company["city_id"]) if company and company["city_id"] else None
    category = categories.get(row["category_id"]) if row["category_id"] else None
    parent = None
    fields: dict[str, str] = {}

    if row["category_id"]:
        found_parent = _rows("select parent_id from categories where id = %s", [row["category_id"]])

        if found_parent and found_parent[0]["parent_id"] is not None:
            parent = categories.get(found_parent[0]["parent_id"])

        # firstWhere по полям раздела в их порядке: первое с таким ключом
        for f in _rows(
            "select key, label from category_fields where category_id = %s order by sort, id",
            [row["category_id"]],
        ):
            # Подписи полей раздела заводятся по-русски — на языке страницы
            fields.setdefault(f["key"], translations.text(f["label"]) or f["label"])

    attributes = _rows(
        "select key, value from listing_attributes where listing_id = %s order by id", [row["id"]]
    )
    images = _rows(
        "select id, path, thumb_path from listing_images where listing_id = %s order by sort, id",
        [row["id"]],
    )
    badges = _rows(
        "select t.badge from promotions p left join promotion_types t "
        "on t.id = p.promotion_type_id where p.listing_id = %s and p.status = 'active' "
        "order by p.id",
        [row["id"]],
    )

    # Заявка площадки (PlatformListings): продавцом подписан SavdEx,
    # контактов служебной компании нет — отклик приходит в её кабинет
    own = platform.owns(row, platform.service_company_id())

    if not preview and not owner:
        analytics.queue(
            ctx,
            "listing_viewed",
            {"listing_id": row["id"], "type": row["type"], "is_platform": own},
            now=True,
        )

    shown_city = (cities.get(row["city_id"]) if row["city_id"] else None) if own else city

    unlocked = (
        not own
        and viewer is not None
        and company is not None
        and (
            viewer == company["id"]
            or bool(
                _rows(
                    "select 1 from contact_unlocks where target_company_id = %s "
                    "and company_id = %s limit 1",
                    [company["id"], viewer],
                )
            )
        )
    )
    contacts = []

    if company is not None and not own:
        for c in _rows(
            "select type, value from company_contacts where company_id = %s and is_public "
            "order by is_primary desc, sort_order, id",
            [company["id"]],
        ):
            open_ = unlocked or c["type"] in PUBLIC_TYPES
            contacts.append(
                {
                    "type": c["type"],
                    "value": c["value"] if open_ else masked(c["type"], c["value"]),
                    "href": href(c["type"], c["value"]) if open_ else None,
                    "locked": not open_,
                }
            )

    cards = Cards(ctx, settings_values(), translations)
    image_urls = [ctx.url("storage/" + i["path"]) for i in images]
    suggested = suggestions(
        row,
        category,
        parent,
        [str(a["value"] or "") for a in attributes if not specs.owns(str(a["key"]))],
        city,
    )
    published = _utc(row["published_at"])
    expires = _utc(row["expires_at"])
    seo = _seo(
        ctx,
        row,
        platform.NAME if own else (company["name"] if company is not None else None),
        shown_city,
        category,
        image_urls,
    )

    response = inertia.render(
        ctx,
        "catalog/Show",
        {
            "listing": {
                "id": row["id"],
                "title": _localized(row, "title", locale) or "",
                "description": _localized(row, "description", locale),
                "type": row["type"],
                "category": category,
                "price": float(row["price"]) if row["price"] is not None else None,
                "bundle_price": float(row["bundle_price"])
                if row["bundle_price"] is not None
                else None,
                "currency": row["currency"],
                "converted": None
                if row["price_negotiable"]
                else cards.prices.convert(row["price"], row["currency"]),
                "bundle_converted": None
                if row["price_negotiable"]
                else cards.prices.convert(row["bundle_price"], row["currency"]),
                "unit": row["unit"],
                "negotiable": row["price_negotiable"],
                "min_order": row["min_order"],
                "delivery_terms": _localized(row, "delivery_terms", locale),
                "payment_terms": _localized(row, "payment_terms", locale),
                "city": shown_city,
                "published": published.strftime("%d.%m.%Y") if published else None,
                "expires": expires.strftime("%d.%m.%Y") if expires else None,
                "views": row["views_count"],
                "attributes": _attributes(attributes, fields, locale, translations.text),
                "badges": [
                    b
                    for b in (translations.text(p["badge"]) for p in badges)
                    if b not in (None, "", "0")
                ],
                "promoted": bool(badges),
                "tags": tags(row, suggested),
                "images": [
                    {
                        "id": i["id"],
                        "url": ctx.url("storage/" + i["path"]),
                        "thumb": ctx.url("storage/" + (i["thumb_path"] or i["path"])),
                    }
                    for i in images
                ],
            },
            "company": {
                "name": platform.NAME,
                "slug": None,
                "initials": "SX",
                "logo": None,
                "website": None,
                "verification_level": 0,
                "rating": 0.0,
                "reviews_count": 0,
                "city": shown_city,
                "country": None,
                "platform": True,
            }
            if own
            else {
                "name": company["name"] if company else None,
                "slug": company["slug"] if company else None,
                "initials": initials(company["name"]) if company else None,
                "logo": logo_url(ctx, company["logo_path"]) if company else None,
                "website": website_url(company["website"]) if company else None,
                "verification_level": int(company["verification_level"] or 0) if company else 0,
                "rating": float(company["rating"] or 0) if company else 0.0,
                "reviews_count": int(company["reviews_count"] or 0) if company else 0,
                "city": city,
                "country": countries.get(company["country_id"])
                if company and company["country_id"]
                else None,
                "platform": False,
            },
            "contacts": contacts,
            "unlocked": unlocked,
            "preview": preview,
            "respond": {
                "guest": user is None,
                "owner": viewer is not None and company is not None and viewer == company["id"],
            },
            "similar": _similar(ctx, cards, row),
        },
        seo,
    )

    return response


def _similar(ctx: Context, cards: Cards, row: dict[str, Any]) -> list[dict[str, Any]]:
    """CatalogController::similar: живые того же раздела, свежие; хвост по id."""
    visible, params = visible_in(ctx.locale)
    where = f"l.status = 'active'{visible} and l.deleted_at is null and l.id != %s"
    params.append(row["id"])

    if row["category_id"] is not None:
        where += " and l.category_id = %s"
        params.append(row["category_id"])

    rows = _rows(
        f"select l.*, {_LISTING_COMPANY} from listings l join companies c "
        f"on c.id = l.company_id where {where} and c.status = 'active' "
        "and c.deleted_at is null order by l.published_at desc, l.id desc limit 4",
        params,
    )

    return cards.present(rows)
