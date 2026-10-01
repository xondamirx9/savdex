"""
Этап 8: Django отвечает на все адреса — и на те, что раньше отдавал
Laravel сам, без маршрута в правилах Apache.

- 404 и 500 — страница ошибки в оформлении сайта, как обработчик
  исключений в bootstrap/app.php (savdex/web/views.error, «голая»: без
  сессии — посредники группы web на несовпавшем маршруте не работают);
  у разделов Django /py/… — свои страницы Django;
- CanonicalHost — со служебного адреса Render (*.onrender.com) на домен
  из APP_URL, тем же адресом целиком, 301; кроме /up и не GET/HEAD;
- адреса бывшей панели Filament (/admin, /admin/login, /admin/python,
  /admin/…) — в админку Django; служебные адреса Livewire и Filament — 404.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from urllib.parse import urlsplit

from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.http import HttpResponseRedirect as Redirect

log = logging.getLogger("savdex")

#: CanonicalHost::HOSTING_SUFFIX
HOSTING_SUFFIX = ".onrender.com"


# ── Ошибки ───────────────────────────────────────────────────────────


def _bare_error(request: HttpRequest, status: int, message: str = "") -> HttpResponse:
    """Страница ошибки без сессии, язык — из префикса адреса."""
    from dataclasses import replace

    from savdex.web import locales
    from savdex.web.request import context
    from savdex.web.views import error

    first = context(request, redirect=False, start_session=False)

    if isinstance(first, HttpResponse):
        return first

    return error(
        replace(first, locale=first.url_locale or locales.DEFAULT), status, bare=True,
        message=message,
    )  # fmt: skip


def page_not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    """handler404: несовпавший маршрут — как NotFoundHttpException у Laravel."""
    if request.path.startswith("/py/"):
        from django.views.defaults import page_not_found as django_404

        return django_404(request, exception)

    return _bare_error(request, 404)


def server_error(request: HttpRequest) -> HttpResponse:
    """
    handler500: ошибка сервера — страница с кодом обращения, код и
    сообщение — в журнал. Если не собралась и она (база недоступна) —
    простой текст, а не вторая ошибка.
    """
    if request.path.startswith("/py/"):
        from django.views.defaults import server_error as django_500

        return django_500(request)

    try:
        return _bare_error(request, 500, message="Ошибка сервера")
    except Exception:
        log.exception("Страница ошибки 500 не собралась")

        return HttpResponse(
            "Ошибка сервера. Попробуйте обновить страницу через минуту.\n",
            status=500,
            content_type="text/plain; charset=utf-8",
        )


# ── Канонический хост ────────────────────────────────────────────────


def _canonical() -> str:
    return (os.environ.get("APP_URL") or "").rstrip("/")


class CanonicalHostMiddleware:
    """CanonicalHost: служебный адрес хостинга — на свой домен, адрес целиком."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        target = self._target(request)

        if target is not None:
            return HttpResponsePermanentRedirect(target)

        return self.get_response(request)

    def _target(self, request: HttpRequest) -> str | None:
        if request.method not in ("GET", "HEAD") or request.path in ("/up", "/py/up"):
            return None

        host = request.get_host().rsplit(":", 1)[0].lower()

        if not host.endswith(HOSTING_SUFFIX):
            return None

        canonical = _canonical()

        if canonical == "" or urlsplit(canonical).hostname == host:
            return None

        return canonical + request.get_full_path()


# ── Бывшая панель Filament ───────────────────────────────────────────


def admin(request: HttpRequest, rest: str = "") -> HttpResponse:
    """
    /admin… — в админку Django: вход — на её вход, переход /admin/python
    ?next=… (пропуск из Filament) — сразу туда, куда вёл, остальное — на
    её главную. Вход и права админка Django проверяет сама.
    """
    from savdex import bridge
    from savdex.adminlogin import LOGIN

    rest = rest.strip("/")

    if rest == "login":
        return Redirect(LOGIN)

    if rest == "python":
        return Redirect(bridge.safe_next(request.GET.get("next")))

    return Redirect(bridge.HOME)


def gone(request: HttpRequest, rest: str = "") -> HttpResponse:
    """Служебные адреса Livewire и Filament: их больше нет."""
    return page_not_found(request)
