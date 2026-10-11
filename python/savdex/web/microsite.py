"""
Мини-сайты компаний — страница /s/<адрес>, поддомен <адрес>.MICROSITE_DOMAIN
и предпросмотр в кабинете (этап 5, шаг 48). Копия Microsite\\SiteController,
Cabinet\\SiteController::preview, SitePage и SiteTheme (переменные
оформления, шрифты).

Страница одна и для посетителей, и для предпросмотра; корневой шаблон —
свой (resources/views/microsite.blade.php): вывеска компании, а не
площадки. Сайт, которого нет, и выключенный — одинаковые 404.

Сверка с настоящим Laravel — tests/test_web_microsite.py.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
)

from savdex.web import content, inertia, locales, platform
from savdex.web.cabinet import (
    _microsite_domain,
    _rows,
    company_plan,
    site_theme,
    site_url,
    suggest_subdomain,
)
from savdex.web.chat_actions import str_limit
from savdex.web.company import _file_size, business_card, href
from savdex.web.directory import logo_url
from savdex.web.home import _LISTING_COMPANY, Cards, visible_in
from savdex.web.seo import Seo, php_json
from savdex.web.shared import Context, _php_round, initials, settings_values

#: SitePage::LISTINGS: мини-сайт — витрина, а не каталог
LISTINGS = 24

#: SiteTheme::RADII, FONTS, SURFACES
RADII = {"sharp": "2px", "soft": "10px", "round": "22px"}
FONTS = {
    "manrope": ("Manrope", "sans-serif"),
    "inter": ("Inter", "sans-serif"),
    "montserrat": ("Montserrat", "sans-serif"),
    "rubik": ("Rubik", "sans-serif"),
    "nunito": ("Nunito", "sans-serif"),
    "pt-sans": ("PT Sans", "sans-serif"),
    "ibm-plex-sans": ("IBM Plex Sans", "sans-serif"),
    "oswald": ("Oswald", "sans-serif"),
    "playfair-display": ("Playfair Display", "serif"),
    "lora": ("Lora", "serif"),
    "pt-serif": ("PT Serif", "serif"),
    "roboto": ("Roboto", "sans-serif"),
    "open-sans": ("Open Sans", "sans-serif"),
    "raleway": ("Raleway", "sans-serif"),
    "ubuntu": ("Ubuntu", "sans-serif"),
    "exo-2": ("Exo 2", "sans-serif"),
    "comfortaa": ("Comfortaa", "sans-serif"),
    "roboto-slab": ("Roboto Slab", "serif"),
    "merriweather": ("Merriweather", "serif"),
}
SURFACES = {
    "light": {
        "bg": "#ffffff",
        "surface": "#f6f7f9",
        "text": "#0f172a",
        "muted": "#5b6475",
        "line": "#e2e8f0",
    },
    "dark": {
        "bg": "#0b1120",
        "surface": "#141c2f",
        "text": "#e8ecf3",
        "muted": "#9aa4b8",
        "line": "#26314a",
    },
}
MIN_CONTRAST = 4.5
MIN_CTA_CONTRAST = 1.6

# ── Цвет (SiteTheme) ────────────────────────────────────────────────


def _rgb(value: str) -> list[int]:
    value = value.lstrip("#")

    return [int(value[i : i + 2], 16) for i in (0, 2, 4)]


def _luminance(value: str) -> float:
    def channel(c: int) -> float:
        x = c / 255

        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(value))

    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)

    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def mix(start: str, end: str, amount: float) -> str:
    a, b = _rgb(start), _rgb(end)

    return "#" + "".join(
        f"{int(_php_round(x + (y - x) * amount)):02x}" for x, y in zip(a, b, strict=True)
    )


def readable_on(background: str) -> str:
    white, ink = contrast("#ffffff", background), contrast("#0f172a", background)

    return "#ffffff" if white >= ink else "#0f172a"


def legible_on(color: str, background: str, toward: str) -> str:
    for i in range(11):
        candidate = mix(color, toward, i / 10)

        if contrast(candidate, background) >= MIN_CONTRAST:
            return candidate

    return toward


def variables(theme: dict[str, Any]) -> dict[str, str]:
    """SiteTheme::variables: CSS-переменные оформления."""
    s = SURFACES[theme["mode"]]
    heading = FONTS[theme["heading_font"]]
    body = FONTS[theme["body_font"]]
    primary, accent = theme["primary"], theme["accent"]
    cta = contrast(accent, primary) >= MIN_CTA_CONTRAST

    return {
        "--ms-bg": s["bg"],
        "--ms-surface": s["surface"],
        "--ms-text": s["text"],
        "--ms-muted": s["muted"],
        "--ms-line": s["line"],
        "--ms-primary": primary,
        "--ms-on-primary": readable_on(primary),
        "--ms-primary-text": legible_on(primary, s["bg"], s["text"]),
        "--ms-primary-soft": mix(primary, s["bg"], 0.88),
        "--ms-accent": accent,
        "--ms-on-accent": readable_on(accent),
        "--ms-hero-cta": accent if cta else readable_on(primary),
        "--ms-on-hero-cta": readable_on(accent) if cta else primary,
        "--ms-radius": RADII[theme["radius"]],
        "--ms-font-heading": f"'{heading[0]}', {heading[1]}",
        "--ms-font-body": f"'{body[0]}', {body[1]}",
    }


def css(theme: dict[str, Any]) -> str:
    return ";".join(f"{k}:{v}" for k, v in variables(theme).items())


def fonts_url(theme: dict[str, Any]) -> str:
    families = list(dict.fromkeys([theme["heading_font"], theme["body_font"]]))

    return (
        "https://fonts.bunny.net/css?family="
        + "|".join(f"{f}:400,600,700" for f in families)
        + "&display=swap"
    )


# ── Страница (SitePage) ─────────────────────────────────────────────


def _app_url() -> str:
    return (os.environ.get("APP_URL") or "http://localhost").rstrip("/")


def marketplace_url(ctx: Context, path: str) -> str:
    """SitePage::marketplaceUrl: адрес на площадке (APP_URL), на языке посетителя."""
    return _app_url() + locales.prefix(ctx.locale) + path


#: Контакты, которые мини-сайт берёт сам, если их нет в «Моих контактах»
_AUTO_CONTACTS = ("phone", "email", "telegram", "whatsapp")


def _contact(kind: str, value: str) -> dict[str, Any]:
    return {
        "type": kind,
        "label": None,
        "contact_person": None,
        "value": value,
        "href": href(kind, value),
    }


def _contacts(company: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Контакты мини-сайта: сначала «Мои контакты» (company_contacts,
    публичные). Телефона, почты, Telegram или WhatsApp там нет вовсе (даже
    скрытого) — мини-сайт берёт их сам: из профиля компании, а телефон и
    почту — ещё и из учётной записи владельца (то, что вписали при
    регистрации). Так у
    только что зарегистрированной компании на сайте сразу есть как с ней
    связаться; правка в профиле видна на сайте без отдельного шага.
    """
    contacts = [
        {
            "type": c["type"],
            "label": c["label"],
            "contact_person": c["contact_person"],
            "value": c["value"],
            "href": href(c["type"], c["value"]),
        }
        for c in _rows(
            "select type, label, contact_person, value from company_contacts "
            "where company_id = %s and is_public order by is_primary desc, sort_order, id",
            [company["id"]],
        )
    ]
    # Вид контакта, который есть в «Моих контактах» — пусть и скрытый, — сам
    # не подставляется: скрытую почту владелец скрыл нарочно
    have = {
        r["type"]
        for r in _rows(
            "select distinct type from company_contacts where company_id = %s", [company["id"]]
        )
    }
    # Сотрудники — владелец первым: у кого первого есть телефон или почта
    people = _rows(
        "select phone, email from users where company_id = %s and deleted_at is null "
        "and status = 'active' order by (company_role = 'owner') desc, id",
        [company["id"]],
    )

    for kind in _AUTO_CONTACTS:
        if kind in have:
            continue

        candidates = [company.get(kind), *(p.get(kind) for p in people)]
        value = next((str(v).strip() for v in candidates if v and str(v).strip()), "")

        if value:
            contacts.append(_contact(kind, value))

    return contacts


def _products(ctx: Context, company_id: int) -> list[dict[str, Any]]:
    own = [
        {
            "key": f"p{p['id']}",
            "title": p["title"],
            "excerpt": str_limit(_squish(p["description"] or ""), 140),
            "cover": logo_url(ctx, p["thumb_path"] or p["image_path"]),
            "price": float(p["price"]) if p["price"] is not None else None,
            "currency": p["currency"],
            "unit": p["unit"],
            "negotiable": p["price"] is None,
            "category": None,
            "url": None,
        }
        for p in _rows(
            "select * from company_site_products where company_id = %s order by sort, id desc",
            [company_id],
        )
    ]
    visible, params = visible_in(ctx.locale)
    # Заявки площадки у служебной компании — не её товары (PlatformListings)
    hidden, hidden_params = platform.exclude_sql(platform.service_company_id())
    rows = _rows(
        f"select l.*, {_LISTING_COMPANY} from listings l "
        "left join companies c on c.id = l.company_id and c.deleted_at is null "
        "where l.company_id = %s and l.status = 'active' and l.deleted_at is null"
        f"{hidden}{visible} order by l.published_at desc limit %s",
        [company_id, *hidden_params, *params, LISTINGS],
    )
    cards = Cards(ctx, settings_values(), content.Translations(ctx.locale)).present(rows)
    listings = [
        {
            "key": f"l{card['id']}",
            "title": card["title"],
            "excerpt": card["excerpt"],
            "cover": card["cover"],
            "price": card["price"],
            "currency": card["currency"],
            "unit": card["unit"],
            "negotiable": card["negotiable"],
            "category": card["category"],
            "url": marketplace_url(ctx, f"/listing/{row['slug']}")
            if row["slug"] is not None
            else None,
        }
        for card, row in zip(cards, rows, strict=True)
    ]

    return own + listings


def _files(ctx: Context, company_id: int) -> list[dict[str, Any]]:
    """Документы и фото с карточки: непроверенный документ не виден, без файла — тоже."""
    from savdex import laravel_storage
    from savdex.web.company import MATERIAL_TYPES, _extension

    private = laravel_storage.private_root()
    result = []

    for d in _rows(
        "select * from company_documents where company_id = %s and is_public order by id",
        [company_id],
    ):
        if not (d["type"] in MATERIAL_TYPES or d["moderation_status"] == "approved"):
            continue

        if not (private / str(d["file_path"] or "")).is_file():
            continue

        label = ctx.t(f"cabinet.files.types.{d['type']}")
        result.append(
            {
                "id": d["id"],
                "title": d["title"],
                "is_image": _extension(str(d["file_path"] or "")).lower()
                in ("jpg", "jpeg", "png", "webp"),
                "type_label": label
                if label != f"ui.cabinet.files.types.{d['type']}"
                else d["type"],
                "size": _file_size(d["file_size"], ctx.locale),
                # Относительный адрес: скачивание открыто и на домене мини-сайтов
                "url": f"/files/{d['id']}",
            }
        )

    return result


def _reviews(ctx: Context, company: dict[str, Any]) -> dict[str, Any]:
    from savdex.web.home import _utc

    return {
        "rating": float(company["rating"] or 0),
        "count": int(company["reviews_count"] or 0),
        "latest": [
            {
                "id": r["id"],
                "author": r["author_name"]
                if r["author_name"] is not None
                else ctx.t("cabinet.incoming.deleted"),
                "rating": r["rating"],
                "body": r["body"],
                "when": _utc(r["created_at"]).strftime("%d.%m.%Y"),  # type: ignore[union-attr]
            }
            for r in _rows(
                "select r.*, a.name as author_name from reviews r left join companies a "
                "on a.id = r.author_company_id and a.deleted_at is null "
                "where r.company_id = %s and r.status = 'published' "
                "order by r.created_at desc limit 6",
                [company["id"]],
            )
        ],
    }


def _squish(value: str) -> str:
    """Str::squish: края прочь, пробелы подряд — один."""
    value = re.sub(r"^[\s﻿​‎]+|[\s﻿​‎]+$", "", value)

    return re.sub(r"(\s|ㅤ|ᅠ)+", " ", value)


def _html(ctx: Context, page: dict[str, Any], view: dict[str, Any], tags: str) -> str:
    """resources/views/microsite.blade.php."""
    e = inertia.php_escape
    token = ctx.session.get("_token", "")
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<meta name="csrf-token" content="{e(token)}">',
    ]

    if view["icon"]:
        head.append(f'<link rel="icon" href="{e(view["icon"])}">')

    head.append(f"<title inertia>{e(view['title'])}</title>")

    if view["description"] != "":
        head += [
            f'<meta name="description" content="{e(view["description"])}">',
            f'<meta property="og:description" content="{e(view["description"])}">',
        ]

    if view["noindex"]:
        head.append('<meta name="robots" content="noindex, nofollow">')
    else:
        head.append(f'<link rel="canonical" href="{e(view["canonical"])}">')

    head += [
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{e(view["title"])}">',
        f'<meta property="og:title" content="{e(view["title"])}">',
        f'<meta property="og:url" content="{e(view["canonical"])}">',
    ]

    if view["icon"]:
        head.append(f'<meta property="og:image" content="{e(view["icon"])}">')

    head += [
        f"<style>:root{{ {view['css']} }}</style>",
        '<link rel="preconnect" href="https://fonts.bunny.net">',
        '<link rel="preconnect" href="https://fonts.bunny.net" crossorigin>',
        # Шрифт — без ожидания отрисовки (как на сайте, inertia.py)
        f'<link id="ms-fonts" href="{e(view["fonts"])}" rel="stylesheet" media="print" '
        "onload=\"this.media='all'\">",
        tags,
    ]
    lang = e(ctx.locale.replace("_", "-"))
    body = (
        f'<script data-page="app" type="application/json">{php_json(page)}</script>'
        '<div id="app"></div>'
    )

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n    '
        + "\n    ".join(head)
        + f'\n</head>\n<body class="antialiased ms-body">\n    {body}</body>\n</html>\n'
    )


def render(
    ctx: Context,
    site: dict[str, Any],
    company: dict[str, Any],
    theme: dict[str, Any],
    *,
    preview: bool = False,
) -> HttpResponse:
    """SitePage::render: одна страница и для посетителей, и для предпросмотра."""
    translations = content.Translations(ctx.locale)
    url = site_url(site["subdomain"])
    hero = theme.get("hero_image")
    props = {
        "theme": theme,
        "vars": variables(theme),
        "fonts": fonts_url(theme),
        "hero": logo_url(ctx, hero) if isinstance(hero, str) else None,
        "preview": preview,
        "site": {
            "url": url,
            "marketplace": marketplace_url(ctx, f"/company/{company['slug']}"),
        },
        "company": business_card(ctx, company, translations),
        "initials": initials(company["name"]),
        "contacts": _contacts(company),
        "products": _products(ctx, company["id"]),
        "files": _files(ctx, company["id"]),
        "reviews": _reviews(ctx, company),
    }
    view = {
        "css": css(theme),
        "fonts": fonts_url(theme),
        "title": company["name"],
        "description": str_limit(_squish(company["description"] or ""), 160),
        "icon": logo_url(ctx, company["logo_path"]),
        "canonical": url,
        "noindex": preview,
    }

    return inertia.render(
        ctx,
        "site/Show",
        props,
        Seo(ctx.root, ctx.path, ctx.locale),
        html=lambda page, tags: _html(ctx, page, view, tags),
    )


def _live(subdomain: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Опубликован, компания не заблокирована, тариф с мини-сайтом."""
    found = _rows("select * from company_sites where subdomain = %s limit 1", [subdomain.lower()])

    if not found or found[0]["status"] != "published":
        return None

    companies = _rows(
        "select * from companies where id = %s and deleted_at is null", [found[0]["company_id"]]
    )

    if not companies or companies[0]["status"] == "blocked":
        return None

    if not company_plan(companies[0]["id"]).get("has_microsite"):
        return None

    return found[0], companies[0]


def _published(site: dict[str, Any]) -> dict[str, Any]:
    raw = site["published_theme"]

    return site_theme(json.loads(raw) if isinstance(raw, str) else raw)


def page(request: HttpRequest, subdomain: str) -> HttpResponse:
    """SiteController::page — /s/<адрес> (throttle:120,1); с поддоменами — 301 на сам сайт."""
    from savdex.web.throttle import throttled

    return throttled(request, 120, lambda ctx: _page(ctx, subdomain, redirect=True))


def show(request: HttpRequest, subdomain: str) -> HttpResponse:
    """SiteController::show — <адрес>.MICROSITE_DOMAIN (throttle:120,1 домена мини-сайтов)."""
    from savdex.web.throttle import throttled

    return throttled(
        request,
        120,
        lambda ctx: _page(ctx, subdomain, redirect=False),
        domain="{subdomain}." + _microsite_domain(),
    )


def _page(ctx: Context, subdomain: str, *, redirect: bool) -> HttpResponse:
    from savdex.web.views import not_found

    live = _live(subdomain)

    if live is None:
        return not_found(ctx)

    site, company = live

    if redirect and _microsite_domain() != "":
        return HttpResponsePermanentRedirect(site_url(site["subdomain"]))

    return render(ctx, site, company, _published(site))


def root(request: HttpRequest) -> HttpResponse:
    """SiteController::root: сам домен мини-сайтов ведёт в каталог компаний."""
    return HttpResponseRedirect(_app_url() + "/companies")


def preview(request: HttpRequest) -> HttpResponse:
    """Cabinet\\SiteController::preview: оформление из редактора (?theme=…) или черновик."""
    from savdex.web.cabinet import _redirect, company_of
    from savdex.web.cabinet import page as cabinet_page

    ctx = cabinet_page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    company = company_of(ctx)

    if company is None:
        return _redirect(ctx, "/cabinet/company")

    found = _rows(
        "select * from company_sites where company_id = %s order by id limit 1", [company["id"]]
    )
    site = found[0] if found else {"subdomain": suggest_subdomain(company["slug"]), "theme": None}
    raw = request.GET.get("theme", "")

    try:
        from_editor = json.loads(raw) if raw != "" else None
    except ValueError:
        from_editor = None

    if isinstance(from_editor, dict | list):
        theme = site_theme(from_editor if isinstance(from_editor, dict) else {})
    else:
        draft = site["theme"]
        theme = site_theme(json.loads(draft) if isinstance(draft, str) else draft)

    return render(ctx, site, company, theme, preview=True)


def subdomain_of(host: str) -> str | None:
    """SiteHost::subdomain: вложенные поддомены не выдаются никому."""
    domain = _microsite_domain()

    if domain == "":
        return None

    host = host.lower()
    suffix = "." + domain

    if not host.endswith(suffix):
        return None

    sub = host[: -len(suffix)]

    return sub if sub != "" and "." not in sub else None


def matches(host: str) -> bool:
    """SiteHost::matches: сам домен мини-сайтов или его поддомен."""
    domain = _microsite_domain()

    if domain == "":
        return False

    host = host.lower()

    return host == domain or host.endswith("." + domain)


#: RestrictSiteHost::ALLOWED: на домене мини-сайтов открыт только сам сайт
_ALLOWED = re.compile(r"^/(?:robots\.txt|up|files/.*)?$")


class HostMiddleware:
    """
    Домен мини-сайтов (MICROSITE_DOMAIN): «/» поддомена — сам сайт
    (Route::domain), «/» домена — в каталог компаний; прочее, кроме
    robots.txt, up и файлов компании, — 404, как RestrictSiteHost.
    Путь сверяется без языкового префикса, как после LocalizeUrl.
    """

    def __init__(self, get_response: Any) -> None:  # noqa: ANN401
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        host = request.get_host().rsplit(":", 1)[0].lower()

        if not matches(host):
            return self.get_response(request)  # type: ignore[no-any-return]

        path = re.sub(r"^/(?:uz|en|zh|tr)(?=/|$)", "", request.path) or "/"

        if not _ALLOWED.match(path):
            return _not_found(request)

        if path == "/":
            sub = subdomain_of(host)

            if sub is not None:
                return show(request, sub)

            if host == _microsite_domain():
                return root(request)

        return self.get_response(request)  # type: ignore[no-any-return]


def _not_found(request: HttpRequest) -> HttpResponse:
    """abort(404) из глобального посредника: страница ошибки без сессии."""
    from dataclasses import replace

    from savdex.web.request import context
    from savdex.web.views import error

    first = context(request, redirect=False, start_session=False)

    if isinstance(first, HttpResponse):
        return first

    return error(replace(first, locale=first.url_locale or locales.DEFAULT), 404, bare=True)
