"""
Адреса Django.

Пусто до этапа 2: пока прокси не отдаёт сюда ни одного пути.
Проверка живости нужна уже сейчас — по ней Render поймёт, что служба
поднялась.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.urls import path


def up(request: HttpRequest) -> HttpResponse:
    """То же, что /up у Laravel."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("up", up),
]
