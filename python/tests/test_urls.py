"""
Адреса Django за Apache.

Apache передаёт Django путь целиком (docker/apache-python.conf), поэтому
адреса здесь те же, что видит посетитель. /py/up — проверка распределителя:
её дёргает проверка образа в CI через настоящий Apache.
"""

from __future__ import annotations

import pytest
from django.http import HttpRequest
from django.test import Client, RequestFactory


@pytest.mark.parametrize("path", ["/up", "/py/up"])
def test_проверка_живости(path):
    response = Client().get(path)

    assert response.status_code == 200
    assert response.content == b"ok"


def test_чужой_адрес_не_найден():
    assert Client().get("/py/nothing").status_code == 404


@pytest.mark.parametrize(("header", "secure"), [("https", True), ("http", False), (None, False)])
def test_https_узнаётся_за_прокси(header, secure):
    """
    Render снимает HTTPS снаружи, до Django запрос доходит по HTTP.
    Исходный протокол — в X-Forwarded-Proto; без этого Django считал бы
    каждый запрос небезопасным и строил ссылки на http://.
    """
    extra = {"HTTP_X_FORWARDED_PROTO": header} if header else {}
    request: HttpRequest = RequestFactory().get("/py/up", **extra)

    assert request.is_secure() is secure
