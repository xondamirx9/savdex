"""
Админка на Django: «кто открыл раздел», вход по пропуску и выход.

Сами разделы и сайт админки — в savdex/adminsite.py. Здесь — то, без
чего не обойдётся ни один раздел: кто этот человек. С шага 67 вход —
своя страница (savdex/adminlogin.py) или уже открытая сессия сайта;
пропуск из Laravel (savdex/bridge.py) ещё принимается — им ведут
пункты меню оставшейся админки Filament.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
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

#: Страница входа (savdex/adminlogin.py)
LOGIN = "/py/admin/login/"


def _to_login(path: str) -> HttpResponseRedirect:
    """На страницу входа — с адресом, куда вернуться."""
    return HttpResponseRedirect(f"{LOGIN}?next={quote(path, safe='/')}")


class AdminMiddleware:
    """
    Кто открыл раздел Django-админки.

    На каждом запросе заново: подпись куки → номер → пользователь из
    базы с его ролью и правами. Куки нет или она истекла — сессия сайта
    (Laravel): вошедший на сайт сотрудник проходит без повторного входа,
    кука выдаётся заново. Не вошёл — на страницу входа; с выданным
    паролем — на его смену (RequirePasswordChange).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        request.admin = None  # type: ignore[attr-defined]

        if not request.path.startswith(bridge.HOME) or request.path.startswith(LOGIN):
            return self.get_response(request)

        if not bridge.enabled():
            return HttpResponse(
                "Админка на Python отключена: на сервере не задан APP_KEY.",
                status=503,
                content_type="text/plain; charset=utf-8",
            )

        uid = bridge.session_uid(request.COOKIES.get(bridge.COOKIE))
        admin = bridge.load_admin(connections["default"], uid) if uid is not None else None
        fresh = False

        if admin is None:
            # Сессия сайта — только чтение: страница админки не должна
            # продлевать её, старить флеш-сообщения сайта и т. п.
            from savdex import laravel_session

            visitor = laravel_session.identify(request.COOKIES, connections["default"])

            if visitor.user_id is None:
                return _to_login(request.get_full_path())

            admin = bridge.load_admin(connections["default"], visitor.user_id)

            if admin is None:
                return _refused(connections["default"], visitor.user_id)

            fresh = True

        request.admin = admin  # type: ignore[attr-defined]
        # Админка Django спрашивает права у request.user
        from savdex.adminsite import StaffUser

        request.user = StaffUser(admin)  # type: ignore[assignment]

        response = self.get_response(request)

        if fresh:
            response.set_cookie(
                bridge.COOKIE,
                bridge.session_cookie(admin.id),
                max_age=bridge.SESSION_TTL,
                path=bridge.COOKIE_PATH,
                secure=request.is_secure(),
                httponly=True,
                samesite="Lax",
            )

        return response


def _refused(connection: Any, user_id: int) -> HttpResponseBase:  # noqa: ANN401
    """Вошёл на сайт, но в админку нельзя: выданный пароль — сменить, иначе — 403."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select is_admin, status, must_change_password from users where id = %s", [user_id]
        )
        row = cursor.fetchone()

    if row is not None and row[0] and row[1] == "active" and row[2]:
        return HttpResponseRedirect("/password/change")

    return HttpResponseForbidden(
        format_html(
            '<!doctype html><meta charset="utf-8"><title>Нет доступа</title>'
            "<p>У этой учётной записи нет доступа к админке. "
            '<a href="{}">На сайт</a> · <a href="{}">Войти другим пользователем</a></p>',
            "/",
            LOGIN,
        )
    )


def _forbidden(reason: str) -> HttpResponseForbidden:
    log.warning("Вход в админку на Python отклонён: %s", reason)

    return HttpResponseForbidden(
        format_html(
            '<!doctype html><meta charset="utf-8"><title>Нет доступа</title>'
            '<p>Не удалось войти. <a href="{}">Вернуться в админку</a></p>',
            LOGIN,
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


def logout(request: HttpRequest) -> HttpResponseBase:
    """/py/logout — старый адрес выхода: теперь выход из админки и с сайта."""
    from savdex import adminlogin

    return adminlogin.logout(request)
