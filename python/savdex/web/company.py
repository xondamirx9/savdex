"""
Визитка компании /company/<адрес> — копия CompanyController::show.

Шапка визитки (Company::businessCard), контакты — открытые своей
компании и тем, кто заплатил за раскрытие, остальным — маской; файлы
и документы, отзывы и право их оставить (ReviewService::blockedReason),
остаток на счету смотрящего для окна раскрытия.

Пишет одно: «Кто мной интересуется» (StatsRecorder::companyView) —
вошедший с компанией оставляет строку в audience_views, не чаще раза
в 30 минут: повтор отсеивается ключом в кэше Laravel (сессия и
компания) и проверкой по самой таблице. Под throttle:120,1.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex import laravel_cache, laravel_storage
from savdex.guards import allowed_writes
from savdex.web import cabinet, content, inertia, locales, platform, ui
from savdex.web.companies import website_url
from savdex.web.directory import _named, logo_url, type_label, type_options
from savdex.web.home import _utc, php_round, visible_in
from savdex.web.it_tasks import SERVICE_TYPES, _decimal, number_format
from savdex.web.seo import Seo
from savdex.web.shared import Context, initials
from savdex.web.throttle import throttled

#: StatsRecorder::DEDUP_MINUTES
DEDUP_MINUTES = 30

#: CompanyContact::PUBLIC_TYPES — сайт не прячется никогда
PUBLIC_TYPES = ("website",)

#: CompanyDocument::MATERIAL_TYPES
MATERIAL_TYPES = ("presentation", "price_list", "catalog", "other")

#: Company::LEGAL_FORMS
LEGAL_FORMS = ("legal", "individual", "freelancer")

#: PHP_INT_MAX — «безлимит» раскрытий в окне
PHP_INT_MAX = 2**63 - 1

_TRIM = " \t\n\r\0\x0b"


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _falsy(value: object) -> bool:
    """Ложь у PHP для строк и null: '', '0', null."""
    return value is None or value == "" or value == "0"


# ── «Кто мной интересуется» ─────────────────────────────────────────


def company_view(ctx: Context, company_id: int) -> None:
    """StatsRecorder::companyView."""
    user = ctx.user
    viewer = user["company_id"] if user is not None else None

    if viewer is None or viewer == company_id:
        return

    # withoutRecent: ключ из сессии — add() ставит, только если ключа нет
    session = ctx.visitor.session_id

    if session is not None and laravel_cache.is_file_store():
        key = f"stats:cview:{session}:{company_id}"

        if not laravel_cache.add(key, True, DEDUP_MINUTES * 60):
            return

    remember_viewer(company_id, viewer)


def remember_viewer(target: int, viewer: int, listing_id: int | None = None) -> None:
    """StatsRecorder::rememberViewer: повтор отсеивается и по таблице; сбой — молча."""
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    try:
        recent = _rows(
            "select 1 from audience_views where viewer_company_id = %s and "
            "target_company_id = %s and listing_id is not distinct from %s::bigint "
            "and created_at >= %s limit 1",
            [viewer, target, listing_id, now - timedelta(minutes=DEDUP_MINUTES)],
        )

        if recent:
            return

        # Своя точка сохранения: сбой вставки не губит чужую транзакцию
        with (
            allowed_writes("audience_views"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "insert into audience_views (target_company_id, viewer_company_id, "
                "listing_id, created_at, updated_at) values (%s, %s, %s, %s, %s)",
                [target, viewer, listing_id, now, now],
            )
    except Exception:
        # rescue(): статистика дешевле показа страницы
        import logging

        logging.getLogger(__name__).exception("Не записан просмотр визитки %s", target)


# ── Контакты ────────────────────────────────────────────────────────


def _mask_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value)

    if len(digits) < 7:
        return "••• ••• •• ••"

    # mb_substr(…, 0, len - 9): при 7–8 цифрах длина отрицательная — без хвоста
    country = digits[: len(digits) - 9]
    operator = digits[-9:][:2]

    return ((f"+{country} " if country != "" else "") + operator + " ••• •• ••").strip(_TRIM)


def _mask_email(value: str) -> str:
    name, _, domain = value.partition("@")

    if domain == "":
        return "••••••@••••.••"

    return name[:1] + "•" * max(len(name) - 1, 3) + "@" + domain


def masked(kind: str, value: str) -> str:
    """CompanyContact::masked."""
    if kind == "phone":
        return _mask_phone(value)

    if kind == "email":
        return _mask_email(value)

    if kind == "website":
        return value

    return "••••••••"


def href(kind: str, value: str) -> str | None:
    """CompanyContact::href."""
    if kind == "phone":
        return "tel:" + re.sub(r"[^\d+]", "", value)

    if kind == "email":
        return "mailto:" + value

    if kind == "telegram":
        return "https://t.me/" + value.lstrip("@")

    if kind == "whatsapp":
        return "https://wa.me/" + re.sub(r"\D+", "", value)

    if kind == "website":
        return value if value.startswith("http") else "https://" + value

    return None


def _contacts(company_id: int, unlocked: bool) -> list[dict[str, Any]]:
    rows = _rows(
        "select type, label, contact_person, value from company_contacts "
        "where company_id = %s and is_public order by is_primary desc, sort_order, id",
        [company_id],
    )
    result = []

    for c in rows:
        is_open = unlocked or c["type"] in PUBLIC_TYPES
        result.append(
            {
                "type": c["type"],
                "label": c["label"],
                "contact_person": c["contact_person"],
                "value": c["value"] if is_open else masked(c["type"], c["value"]),
                "href": href(c["type"], c["value"]) if is_open else None,
                "locked": not is_open,
            }
        )

    return result


# ── Файлы ───────────────────────────────────────────────────────────


def _extension(path: str) -> str:
    name = path.rstrip("/").rsplit("/", 1)[-1]

    return name.rsplit(".", 1)[1] if "." in name else ""


def _file_size(size: int | None, locale: str) -> str | None:
    """CompanyDocument::sizeLabel на языке страницы."""
    if size is None:
        return None

    if size >= 1048576:
        return ui.t(
            "common.size_mb", locale, size=_decimal(number_format(size / 1048576, 1), locale)
        )

    return ui.t("common.size_kb", locale, size=number_format(size / 1024, 0))


def _files(ctx: Context, company_id: int) -> list[dict[str, Any]]:
    today = datetime.now(UTC).replace(tzinfo=None)
    private = laravel_storage.private_root()
    result = []

    for d in _rows(
        "select * from company_documents where company_id = %s and is_public order by id",
        [company_id],
    ):
        material = d["type"] in MATERIAL_TYPES

        # isVisibleOnCard: материалы — сразу, документы — после одобрения;
        # запись без файла на диске не показывается
        if not (material or d["moderation_status"] == "approved"):
            continue

        if not (private / str(d["file_path"] or "")).exists():
            continue

        label = ctx.t(f"cabinet.files.types.{d['type']}")
        valid: date | None = d["valid_until"]
        result.append(
            {
                "id": d["id"],
                "title": d["title"],
                "type": d["type"],
                "is_image": _extension(str(d["file_path"] or "")).lower()
                in ("jpg", "jpeg", "png", "webp"),
                "type_label": label
                if label != f"ui.cabinet.files.types.{d['type']}"
                else d["type"],
                "size": _file_size(d["file_size"], ctx.locale),
                "is_material": material,
                # isPast: срок — полночь даты, то есть сегодняшний уже прошёл
                "expired": valid is not None
                and datetime(valid.year, valid.month, valid.day) < today,
                "valid_until": valid.strftime("%d.%m.%Y") if valid is not None else None,
            }
        )

    return result


# ── Отзывы ──────────────────────────────────────────────────────────


def _reviews(ctx: Context, company_id: int) -> list[dict[str, Any]]:
    translations = content.Translations(ctx.locale)

    return [
        {
            "id": r["id"],
            "author": r["author_name"]
            if r["author_name"] is not None
            else ctx.t("cabinet.incoming.deleted"),
            "initials": initials(r["author_name"]) if r["author_name"] is not None else "?",
            "rating": r["rating"],
            "body": translations.text(r["body"]),
            "deal_confirmed": r["deal_confirmed"],
            "reply": translations.text(r["reply"]),
            "when": _utc(r["created_at"]).strftime("%d.%m.%Y"),  # type: ignore[union-attr]
        }
        for r in _rows(
            "select r.*, a.name as author_name from reviews r left join companies a "
            "on a.id = r.author_company_id and a.deleted_at is null "
            "where r.company_id = %s and r.status = 'published' "
            "order by r.created_at desc limit 20",
            [company_id],
        )
    ]


def review_blocked(ctx: Context, target: int) -> str | None:
    """ReviewService::blockedReason."""
    user = ctx.user
    author = None

    if user is not None and user["company_id"] is not None:
        found = _rows(
            "select id, status from companies where id = %s and deleted_at is null",
            [user["company_id"]],
        )
        author = found[0] if found else None

    if user is None or author is None:
        return ctx.t("messages.review.no_company")

    if author["id"] == target:
        return ctx.t("messages.review.own_company")

    if user["email_verified_at"] is None:
        return ctx.t("messages.review.verify_email")

    status = _rows("select status from users where id = %s", [user["id"]])[0]["status"]

    if author["status"] == "blocked" or status != "active":
        return ctx.t("messages.review.blocked")

    if not _rows(
        "select 1 from contact_unlocks where company_id = %s and target_company_id = %s limit 1",
        [author["id"], target],
    ):
        return ctx.t("messages.review.unlock_first")

    existing = _rows(
        "select status from reviews where company_id = %s and author_company_id = %s "
        "and listing_id is null limit 1",
        [target, author["id"]],
    )

    if existing:
        return {
            "moderation": ctx.t("messages.review.yours_pending"),
            "hidden": ctx.t("messages.review.yours_hidden"),
        }.get(existing[0]["status"], ctx.t("messages.review.already_left"))

    return None


# ── Кошелёк смотрящего ──────────────────────────────────────────────


def _wallet(viewer_company: int | None, company_id: int) -> dict[str, int] | None:
    """CompanyController::viewerWallet: гостю и своей компании — null."""
    if viewer_company is None or viewer_company == company_id:
        return None

    if not _rows("select 1 from companies where id = %s and deleted_at is null", [viewer_company]):
        return None

    plans = _rows(
        "select p.contacts_limit from subscriptions s join plans p on p.id = s.plan_id "
        "where s.id = (select max(id) from subscriptions where company_id = %s "
        "and status = 'active' and (ends_at is null or ends_at > now()))",
        [viewer_company],
    ) or _rows("select contacts_limit from plans where code = 'free' limit 1")
    # Company::plan: нет ни подписки, ни бесплатного тарифа в базе — 3
    limit = plans[0]["contacts_limit"] if plans else 3
    wallets = _rows(
        "select credits, contacts_used_this_period from wallets where company_id = %s limit 1",
        [viewer_company],
    )
    wallet = wallets[0] if wallets else {}

    return {
        "contacts_left": PHP_INT_MAX
        if limit is None
        else max(0, limit - (wallet.get("contacts_used_this_period") or 0)),
        "credits": wallet.get("credits") or 0,
    }


# ── Визитка ─────────────────────────────────────────────────────────


def business_card(
    ctx: Context, c: dict[str, Any], translations: content.Translations
) -> dict[str, Any]:
    """Company::businessCard."""
    cities = _named("cities", ctx.locale)
    countries = _named("countries", ctx.locale)
    form = c["legal_form"] if c["legal_form"] in LEGAL_FORMS else "legal"
    specializations = (
        [
            ctx.t(f"it_tasks.types.{s}")
            for s in (c["it_specializations"] or [])
            if s in SERVICE_TYPES
        ]
        if c["is_it_provider"]
        else []
    )

    return {
        "name": c["name"],
        "legal_name": c["legal_name"],
        "tin": c["tin"],
        "type": c["type"],
        "type_label": type_label(ctx, c, type_options(ctx.locale)),
        "legal_form": c["legal_form"] if c["legal_form"] is not None else "legal",
        "legal_form_label": ctx.t(f"legal_form.{form}"),
        "custom_category": translations.text(c["custom_category"]),
        "country": countries.get(c["country_id"]) if c["country_id"] is not None else None,
        "city": cities.get(c["city_id"]) if c["city_id"] is not None else None,
        "address": c["address"],
        # decimal:7 — строка «0.0000000» у PHP истинна, пусто только null
        "coords": {"lat": float(c["lat"]), "lng": float(c["lng"])}
        if c["lat"] is not None and c["lng"] is not None
        else None,
        "description": translations.text(c["description"]),
        "source_note": translations.text(c["source_note"]),
        "website": website_url(c["website"]),
        # Кнопка «Мини-сайт компании» — только когда мини-сайт открывается
        "microsite": microsite_url(c),
        "founded_year": c["founded_year"],
        "employees_range": c["employees_range"],
        "verification_level": c["verification_level"],
        "is_it_provider": bool(c["is_it_provider"]),
        "it_specializations": specializations,
        "rating": float(c["rating"] or 0),
        "reviews_count": c["reviews_count"],
        "logo": logo_url(ctx, c["logo_path"]),
        "cover": logo_url(ctx, c["cover_path"]),
        "slug": c["slug"],
        # Ссылкой делятся — на том же языке, что и страница
        "url": locales.url(ctx.root, f"/company/{c['slug']}", ctx.locale),
    }


def _seo(ctx: Context, c: dict[str, Any], card: dict[str, Any]) -> Seo:
    """SeoBuilders::company: заголовок, описание, разметка организации и крошки."""
    city = card["city"]
    tin = f"{ctx.t('companies_page.tin')} {c['tin']}" if c["tin"] is not None else None
    parts = [card["type_label"], city, tin]
    fallback = ", ".join(p for p in parts if not _falsy(p)).strip(_TRIM)
    url = ctx.url(f"company/{c['slug']}")

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(c["name"] + (f" — {city}" if city is not None else ""))
    seo.description(
        c["description"]
        if not _falsy(c["description"])
        else fallback + ". " + ctx.t("seo.company_tail")
    )
    seo.canonical(url)
    seo.image(card["logo"])
    # og:type profile — страница человека; у компании — website
    seo.type = "website"
    url = seo.link(url)

    schema: dict[str, Any] = {
        "@type": "Organization",
        "name": c["name"],
        "legalName": c["legal_name"],
        "url": url,
        "logo": card["logo"],
        "description": c["description"],
        "taxID": c["tin"],
        "foundingDate": str(c["founded_year"]) if c["founded_year"] is not None else None,
    }

    if card["city"] is not None or c["address"] is not None:
        codes = _rows("select code from countries where id = %s", [c["country_id"]])
        address = {
            "@type": "PostalAddress",
            "addressLocality": card["city"],
            "addressCountry": codes[0]["code"].upper() if codes else None,
            "streetAddress": c["address"],
        }
        schema["address"] = {k: v for k, v in address.items() if not _falsy(v)}

    if c["reviews_count"] > 0:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": php_round(float(c["rating"] or 0), 1),
            "reviewCount": c["reviews_count"],
            "bestRating": 5,
            "worstRating": 1,
        }

    seo.schema({k: v for k, v in schema.items() if v is not None and v != ""})
    seo.schema(
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": ctx.t("companies_page.title"),
                    "item": seo.link(ctx.url("companies")),
                },
                {"@type": "ListItem", "position": 2, "name": c["name"], "item": url},
            ],
        }
    )

    return seo


def microsite_url(company: dict[str, Any]) -> str | None:
    """
    Адрес мини-сайта компании — если посетитель его увидит: сайт
    опубликован, компания не заблокирована, в тарифе есть мини-сайт (как
    microsite._live). Иначе None, и кнопки в профиле нет.
    """
    if company.get("status") == "blocked" or company.get("deleted_at") is not None:
        return None

    sites = _rows(
        "select subdomain from company_sites where company_id = %s and status = 'published' "
        "order by id limit 1",
        [company["id"]],
    )

    if not sites or not cabinet.company_plan(company["id"]).get("has_microsite"):
        return None

    return cabinet.site_url(sites[0]["subdomain"])


def show(request: HttpRequest, slug: str) -> HttpResponse:
    """CompanyController::show — под throttle:120,1."""
    return throttled(request, 120, lambda ctx: _show(ctx, slug))


def _show(ctx: Context, slug: str) -> HttpResponse:
    from savdex.web.views import not_found

    found = _rows("select * from companies where slug = %s and deleted_at is null limit 1", [slug])

    if not found:
        return not_found(ctx)

    c = found[0]
    user = ctx.user
    viewer = user["company_id"] if user is not None else None

    # Заблокированной компании нет ни в каталоге, ни на мини-сайте — нет и
    # визитки; себя компания видит (причина блокировки — в кабинете)
    if c["status"] != "active" and viewer != c["id"]:
        return not_found(ctx)

    company_view(ctx, c["id"])
    unlocked = viewer is not None and (
        viewer == c["id"]
        or bool(
            _rows(
                "select 1 from contact_unlocks where target_company_id = %s "
                "and company_id = %s limit 1",
                [c["id"], viewer],
            )
        )
    )
    contacts = _contacts(c["id"], unlocked)
    translations = content.Translations(ctx.locale)
    card = business_card(ctx, c, translations)
    seo = _seo(ctx, c, card)
    visible, params = visible_in(ctx.locale)
    # Заявки площадки у служебной компании — не её объявления (PlatformListings)
    hidden, hidden_params = platform.exclude_sql(platform.service_company_id())
    listings = _rows(
        "select count(*) as n from listings l where l.company_id = %s and l.status = 'active' "
        f"and l.deleted_at is null{hidden}{visible}",
        [c["id"], *hidden_params, *params],
    )[0]["n"]

    return inertia.render(
        ctx,
        "companies/Show",
        {
            "company": card,
            "initials": initials(c["name"]),
            "contacts": contacts,
            "files": _files(ctx, c["id"]),
            "unlocked": unlocked,
            "is_own": viewer == c["id"],
            "reviews": _reviews(ctx, c["id"]),
            "review_blocked": review_blocked(ctx, c["id"]),
            "criteria": cabinet.review_criteria(ctx.locale),
            "listings_count": listings,
            "wallet": _wallet(viewer, c["id"]),
            "locked_count": sum(1 for x in contacts if x["locked"]),
        },
        seo,
    )
