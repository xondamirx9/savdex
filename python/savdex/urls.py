"""
Адреса Django.

На сервере Django стоит за Apache в той же службе Render: Apache
отдаёт сюда только адреса, перечисленные в docker/apache-python.conf,
а всё остальное — Laravel. Адрес приходит целиком, без обрезки
префикса, поэтому пути здесь те же, что видит посетитель.

/py/up — проверка, что Django жив именно за Apache: её дёргает
проверка образа в CI. /up — то же для прямого запуска.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.urls import path

from savdex import adminpanel


def up(request: HttpRequest) -> HttpResponse:
    """То же, что /up у Laravel."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("up", up),
    path("py/up", up),
    # Вход в админку на Django — по пропуску из Laravel (savdex/bridge.py)
    path("py/login", adminpanel.login),
    path("py/logout", adminpanel.logout),
    path("py/admin/", adminpanel.home),
]
