"""
Посетитель сайта на каждом запросе к Django (этап 3 переноса).

request.visitor — кто вошёл, по сессии Laravel (savdex/laravel_session.py).
Считается лениво: запросу, которому посетитель не нужен (админка,
проверка /py/up), чтение сессии ничего не стоит.

/py/whoami — проверка на живом сайте, что Django узнаёт того же
человека, что и Laravel: войти на сайте и открыть адрес. Отдаёт только
своё — номер и имя вошедшего, ничего чужого.
"""

from __future__ import annotations

from collections.abc import Callable

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.functional import SimpleLazyObject

from savdex import laravel_session


class VisitorMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.visitor = SimpleLazyObject(  # type: ignore[attr-defined]
            lambda: laravel_session.identify(request.COOKIES, connection)
        )

        return self.get_response(request)


def whoami(request: HttpRequest) -> HttpResponse:
    visitor: laravel_session.Visitor = request.visitor  # type: ignore[attr-defined]
    body: dict[str, object] = {"authenticated": visitor.authenticated}

    if visitor.authenticated:
        with connection.cursor() as cursor:
            cursor.execute("select name from users where id = %s", [visitor.user_id])
            row = cursor.fetchone()

        body |= {
            "user_id": visitor.user_id,
            "name": row[0] if row else None,
            "via_remember": visitor.via_remember,
        }

    response = JsonResponse(body, json_dumps_params={"ensure_ascii": False})
    # Ответ свой у каждого вошедшего: ни браузер, ни прокси не хранят
    response["Cache-Control"] = "no-store, private"

    return response
