"""
Проверка подделки запроса у Django — только для адресов /py/ (админка).

У страниц и форм сайта своя проверка — токен сессии Laravel в
savdex/web/forms.action (419, как PreventRequestForgery): формы шлют
его в _token или заголовке, куки Django у них нет вовсе (CSRF_COOKIE_PATH
= /py/). Стандартная проверка Django отвечала 403 «CSRF cookie not set»
на каждую форму, которую адрес делит со страницей (вход, регистрация,
смена пароля, продвижение, мини-сайт, профиль компании…): такие виды не
помечены csrf_exempt — помечен только вложенный вид формы.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponseForbidden
from django.middleware.csrf import CsrfViewMiddleware

#: Адреса, которые проверяет Django: админка и её выход
PREFIX = "/py/"


class SavdexCsrfMiddleware(CsrfViewMiddleware):
    def process_view(
        self,
        request: HttpRequest,
        callback: Callable[..., Any],
        callback_args: tuple[Any, ...],
        callback_kwargs: dict[str, Any],
    ) -> HttpResponseForbidden | None:
        if not request.path.startswith(PREFIX):
            # Сайт: токен Laravel сверяет forms.action
            return None

        return super().process_view(request, callback, callback_args, callback_kwargs)
