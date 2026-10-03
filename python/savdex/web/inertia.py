"""
Ответ страницы сайта — как Inertia\\Response у Laravel.

Полная загрузка — HTML-каркас resources/views/app.blade.php с объектом
страницы в <script data-page="app">; переход Inertia (заголовок
X-Inertia) — тот же объект JSON-ом. Версия сборки разошлась — 409 с
X-Inertia-Location, браузер перезагрузит страницу целиком. Частичная
перезагрузка (X-Inertia-Partial-Data / -Except) отдаёт только
запрошенные пропсы; errors — всегда (Inertia::always).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.http import HttpResponse, JsonResponse

from savdex.web import locales, phpquery, vite
from savdex.web.seo import Seo, php_json
from savdex.web.shared import Context, appearance_logo, settings_values, shared


def php_escape(text: object) -> str:
    """{{ }} Blade — htmlspecialchars с ENT_QUOTES."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def full_url(ctx: Context) -> str:
    """
    Адрес, который просил браузер: строка запроса разобрана и собрана
    заново (phpquery), языковой префикс — на месте. Без префикса
    перезагрузка после 409 уводила бы /en/… на русскую страницу.
    """
    prefix = locales.prefix(ctx.url_locale) if ctx.url_locale else ""

    return ctx.root + prefix + phpquery.full_path(ctx.path, ctx.query)


def page_url(ctx: Context) -> str:
    """HandleInertiaRequests::urlResolver — fullUrl без хоста, с языковым префиксом."""
    prefix = locales.prefix(ctx.locale)
    uri = phpquery.full_path(ctx.path, ctx.query) or "/"

    return prefix if uri == "/" and prefix else prefix + uri


def _partial(ctx: Context, component: str, props: dict[str, Any]) -> dict[str, Any]:
    headers = ctx.request.headers

    if not ctx.inertia or headers.get("X-Inertia-Partial-Component") != component:
        return props

    only = [k for k in (headers.get("X-Inertia-Partial-Data") or "").split(",") if k]
    exclude = [k for k in (headers.get("X-Inertia-Partial-Except") or "").split(",") if k]

    if only:
        props = {k: v for k, v in props.items() if k in only or k == "errors"}

    if exclude:
        props = {k: v for k, v in props.items() if k not in exclude or k == "errors"}

    return props


def render(
    ctx: Context,
    component: str,
    props: dict[str, Any],
    seo: Seo,
    status: int = 200,
    html: Callable[[dict[str, Any], str], str] | None = None,
) -> HttpResponse:
    """
    html — свой корневой шаблон (->rootView(...) у Inertia): страница и
    теги сборки на входе, документ на выходе.
    """
    version = vite.version()

    if (
        ctx.inertia
        and ctx.request.method == "GET"
        and ctx.request.headers.get("X-Inertia-Version", "") != version
    ):
        # Inertia\\Middleware::onVersionChange: полная перезагрузка
        conflict = HttpResponse(status=409)
        conflict["X-Inertia-Location"] = full_url(ctx)

        return conflict

    common = shared(ctx)
    page = {
        "component": component,
        "props": _partial(ctx, component, {**common, **props}),
        "url": page_url(ctx),
        "version": version,
        "sharedProps": list(common),
    }

    if ctx.inertia:
        response: HttpResponse = JsonResponse(
            page, status=status, json_dumps_params={"separators": (",", ":")}
        )
        response.content = php_json(page).encode()
        response["X-Inertia"] = "true"
    else:
        tags, preloads = vite.assets(ctx.root)
        document = html(page, tags) if html is not None else _html(ctx, seo, page, tags)
        response = HttpResponse(document, status=status, content_type="text/html; charset=utf-8")

        if preloads:
            response["Link"] = vite.link_header(preloads)

    response["Vary"] = "X-Inertia"
    response["Cache-Control"] = "no-cache, private"

    return response


def render_bare(
    ctx: Context, component: str, props: dict[str, Any], seo: Seo, status: int
) -> HttpResponse:
    """
    Страница, собранная без HandleInertiaRequests, — как ответ на
    исключение, брошенное раньше него (404 несовпавшего адреса, 429):
    без версии сборки и без её проверки, заголовков Vary и Link нет.
    Общие пропсы (поддержка, шапка) — есть: без них страница ошибки
    оставалась пустой; адрес — с языковым префиксом, как у браузера.
    """
    url = page_url(ctx)

    if ctx.path.endswith("/") and ctx.path != "/" and not url.split("?")[0].endswith("/"):
        path, sep, query = url.partition("?")
        url = path + "/" + sep + query

    try:
        common = shared(ctx)
    except Exception:  # страница ошибки должна собраться всегда
        common = {}

    page = {"component": component, "props": {**common, **props}, "url": url, "version": ""}

    if ctx.inertia:
        response = HttpResponse(php_json(page), status=status, content_type="application/json")
        response["X-Inertia"] = "true"
    else:
        tags, _ = vite.assets(ctx.root)
        response = HttpResponse(
            _html(ctx, seo, page, tags), status=status, content_type="text/html; charset=utf-8"
        )

    response["Cache-Control"] = "no-cache, private"

    return response


def _html(ctx: Context, seo: Seo, page: dict[str, Any], vite_tags: str) -> str:
    """resources/views/app.blade.php."""
    values = settings_values()
    logo = appearance_logo(values)
    logo_type = ' type="image/svg+xml" ' if logo.lower().endswith(".svg") else " "
    touch = logo if logo.lower().endswith((".png", ".jpg", ".jpeg")) else "/images/logo-touch.png"
    description = seo.description_text
    title = php_escape(seo.get_title())
    token = ctx.session.get("_token", "")

    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<meta name="csrf-token" content="{php_escape(token)}">',
        '<link rel="icon" href="/favicon.ico" sizes="32x32">',
        f'<link rel="icon" {logo_type} href="{php_escape(logo)}">'.replace("  ", " "),
        f'<link rel="apple-touch-icon" href="{php_escape(touch)}">',
        f"<title inertia>{title}</title>",
    ]

    if description:
        head.append(f'<meta name="description" content="{php_escape(description)}">')

    if not seo.bare_page:
        head.append(f'<link rel="canonical" href="{php_escape(seo.get_canonical())}">')
        head += [
            f'<link rel="alternate" hreflang="{php_escape(lang)}" href="{php_escape(href)}">'
            for lang, href in seo.get_alternates().items()
        ]

    if seo.noindex:
        head.append('<meta name="robots" content="noindex, follow">')

    head += [
        f'<meta property="og:type" content="{php_escape(seo.type)}">',
        '<meta property="og:site_name" content="SAVDEX">',
        f'<meta property="og:locale" content="{php_escape(ctx.locale.replace("-", "_"))}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:url" content="{php_escape(seo.get_canonical())}">',
    ]

    if description:
        head.append(f'<meta property="og:description" content="{php_escape(description)}">')

    head.append(f'<meta property="og:image" content="{php_escape(seo.get_image())}">')

    if seo.image_meta:
        head += [
            f'<meta property="og:image:width" content="{seo.image_meta["width"]}">',
            f'<meta property="og:image:height" content="{seo.image_meta["height"]}">',
            f'<meta property="og:image:type" content="{php_escape(seo.image_meta["type"])}">',
        ]

    head += [
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{title}">',
    ]

    if description:
        head.append(f'<meta name="twitter:description" content="{php_escape(description)}">')

    head += [
        f'<meta name="twitter:image" content="{php_escape(seo.get_image())}">',
        f'<script type="application/ld+json">{seo.get_json_ld()}</script>',
        '<link rel="preconnect" href="https://fonts.bunny.net">',
        '<link rel="preconnect" href="https://fonts.bunny.net" crossorigin>',
        '<link href="https://fonts.bunny.net/css?family=manrope:400,500,600,700,800&display=swap"'
        ' rel="stylesheet">',
        vite_tags,
    ]

    lang = php_escape(ctx.locale.replace("_", "-"))
    body = (
        f'<script data-page="app" type="application/json">{php_json(page)}</script>'
        '<div id="app"></div>'
    )

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n    '
        + "\n    ".join(head)
        + f'\n</head>\n<body class="antialiased">\n    {body}</body>\n</html>\n'
    )
