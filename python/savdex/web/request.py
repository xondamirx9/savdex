"""
Разбор запроса к странице сайта — то, что у Laravel делают глобальные
посредники до контроллера.

- BlockGreedyCrawlers: коммерческие SEO-роботы — 403 сразу;
- LocalizeUrl: языковой префикс снимается с пути;
- SetLocale: язык — из префикса; без префикса — запомненный (профиль,
  затем сессия), и тогда GET-запрос уводится на адрес с префиксом.

Сессию Laravel страница ведёт сама (savdex/web/session.py): начинает
её здесь, как StartSession, — раньше SetLocale, но после отказа
роботу; SetLocale запоминает язык из префикса в сессии и в профиле;
сохраняет её SessionMiddleware после страницы. ?hl= (смена языка)
Apache сюда не пускает — это делает Laravel.

Канонический хост и мини-сайты сюда тоже не доходят: Apache отдаёт
Django только запросы к основному домену (docker/apache-python.conf).
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex import laravel_session
from savdex.web import locales, phpquery, session
from savdex.web.shared import Context

#: BlockGreedyCrawlers::CRAWLERS
CRAWLERS = (
    "AhrefsBot",
    "SemrushBot",
    "MJ12bot",
    "DotBot",
    "rogerbot",
    "BLEXBot",
    "DataForSeoBot",
    "Barkrowler",
    "serpstatbot",
    "SEOkicks",
    "ZoominfoBot",
    "MegaIndex",
    "linkdexbot",
)


def root_of(request: HttpRequest) -> str:
    """url('/') за прокси: схема и хост из X-Forwarded-* (trustProxies('*'))."""
    proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()
    scheme = proto or ("https" if request.is_secure() else "http")
    host = host or request.META.get("HTTP_HOST") or request.META.get("SERVER_NAME", "localhost")
    port = request.headers.get("X-Forwarded-Port", "").split(",")[0].strip()

    if (
        port
        and ":" not in host
        and not ((scheme == "https" and port == "443") or (scheme == "http" and port == "80"))
    ):
        host = f"{host}:{port}"

    return f"{scheme}://{host}"


def _expects_json(request: HttpRequest) -> bool:
    """Request::expectsJson."""
    accept = request.headers.get("Accept", "")
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    pjax = bool(request.headers.get("X-PJAX"))
    any_type = accept.strip() in ("", "*/*") or "*/*" in accept or accept.startswith("*")
    wants_json = "/json" in accept or "+json" in accept

    return (ajax and not pjax and any_type) or wants_json


def context(request: HttpRequest, redirect: bool = True) -> Context | HttpResponse:
    """
    Контекст страницы или готовый ответ (отказ роботу, переход на язык).

    redirect=False — без перехода на запомненный язык: так контекст
    нужен ограничению частоты, которое у Laravel стоит раньше SetLocale.
    """
    agent = request.headers.get("User-Agent", "")

    if agent and any(c.lower() in agent.lower() for c in CRAWLERS):
        return HttpResponse(
            "Crawling is not allowed for this user agent.\n",
            status=403,
            content_type="text/plain; charset=utf-8",
        )

    url_locale, path = locales.split(request.path)
    query = request.META.get("QUERY_STRING", "")
    root = root_of(request)
    started = session.start(request)

    if started is None:
        visitor = laravel_session.identify(request.COOKIES, connection)
    else:
        store, visitor = started
        store.root = root
        # Request::fullUrl() после LocalizeUrl — путь без префикса
        store.full_url = root + phpquery.full_path(path, query)

    if url_locale is not None:
        locale = url_locale

        if redirect and started is not None:
            session.remember_locale(request, started[0], url_locale)
    else:
        stored = _stored(visitor)
        locale = stored or locales.DEFAULT

        if (
            redirect
            and stored is not None
            and stored != locales.DEFAULT
            and request.method == "GET"
            and not _expects_json(request)
        ):
            target = locales.url(root, path + (f"?{query}" if query else ""), stored)

            return HttpResponseRedirect(target)

    return Context(
        request=request,
        root=root,
        path=path,
        query=query,
        locale=locale,
        visitor=visitor,
        session=visitor.session,
        url_locale=url_locale,
    )


def _stored(visitor: laravel_session.Visitor) -> str | None:
    """SetLocale::stored: язык из профиля, затем из сессии."""
    if visitor.user_id is not None:
        with connection.cursor() as cursor:
            cursor.execute("select locale from users where id = %s", [visitor.user_id])
            row = cursor.fetchone()

        if row and locales.supports(row[0]):
            return str(row[0])

    stored = visitor.session.get("locale")

    return stored if locales.supports(stored) else None
