"""
Админка на Django: вход по пропуску, выход и «кто открыл раздел».

Разделы переезжают сюда по одному (этап 2 переноса); сами разделы и
сайт админки — в savdex/adminsite.py. Здесь — то, без чего не обойдётся
ни один раздел: кто этот человек. Вход — через Laravel, пропуском
(savdex/bridge.py).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import quote

from django.db import connections
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.utils.html import format_html
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from savdex import bridge

log = logging.getLogger(__name__)

#: Адрес Laravel, который выдаёт пропуск (App\Http\Controllers\Admin\PythonBridgeController)
LARAVEL_BRIDGE = "/admin/python"


def _to_laravel(path: str) -> HttpResponseRedirect:
    """За пропуском в Laravel — с адресом, куда вернуться."""
    return HttpResponseRedirect(f"{LARAVEL_BRIDGE}?next={quote(path, safe='/')}")


class AdminMiddleware:
    """
    Кто открыл раздел Django-админки.

    На каждом запросе заново: подпись куки → номер → пользователь из
    базы с его ролью и правами. Нет входа или больше нельзя — обратно
    в Laravel за пропуском; для вошедшего в Laravel это незаметный круг,
    для остальных — обычная страница входа.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        request.admin = None  # type: ignore[attr-defined]

        if not request.path.startswith(bridge.HOME):
            return self.get_response(request)

        if not bridge.enabled():
            return HttpResponse(
                "Админка на Python отключена: на сервере не задан APP_KEY.",
                status=503,
                content_type="text/plain; charset=utf-8",
            )

        uid = bridge.session_uid(request.COOKIES.get(bridge.COOKIE))
        admin = bridge.load_admin(connections["default"], uid) if uid is not None else None

        if admin is None:
            return _to_laravel(request.get_full_path())

        request.admin = admin  # type: ignore[attr-defined]
        # Админка Django спрашивает права у request.user
        from savdex.adminsite import StaffUser

        request.user = StaffUser(admin)  # type: ignore[assignment]

        return self.get_response(request)


def _forbidden(reason: str) -> HttpResponseForbidden:
    log.warning("Вход в админку на Python отклонён: %s", reason)

    return HttpResponseForbidden(
        format_html(
            '<!doctype html><meta charset="utf-8"><title>Нет доступа</title>'
            '<p>Не удалось войти. <a href="{}">Вернуться в админку</a></p>',
            "/admin",
        )
    )


@csrf_exempt
@require_POST
def login(request: HttpRequest) -> HttpResponseBase:
    """
    Принять пропуск из Laravel.

    Без проверки CSRF-токена Django: её роль здесь играет подпись
    пропуска — подделать запрос без ключа нельзя.
    """
    if not bridge.enabled():
        return _forbidden("нет APP_KEY")

    try:
        passed = bridge.verify(str(request.POST.get("token", "")))
    except bridge.BridgeError as error:
        return _forbidden(str(error))

    if bridge.load_admin(connections["default"], passed.uid) is None:
        return _forbidden(f"пользователю {passed.uid} в админку нельзя")

    response = HttpResponseRedirect(passed.next)
    response.set_cookie(
        bridge.COOKIE,
        bridge.session_cookie(passed.uid),
        max_age=bridge.SESSION_TTL,
        path=bridge.COOKIE_PATH,
        secure=request.is_secure(),
        httponly=True,
        samesite="Lax",
    )

    return response


@require_POST
def logout(request: HttpRequest) -> HttpResponseBase:
    """Выйти из разделов на Python; из самой админки Laravel — отдельно."""
    response = HttpResponseRedirect("/admin")
    response.delete_cookie(bridge.COOKIE, path=bridge.COOKIE_PATH)

    return response
