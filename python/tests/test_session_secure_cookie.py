"""
Кука сессии по HTTPS — с Secure и тогда, когда сессию открывают мимо
страницы сайта (вход в админку, капча, колбэки): кука общая с сайтом.
Без базы: гость без куки, вход не проверяется.
"""

from __future__ import annotations

import base64

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from savdex import laravel_session
from savdex.web import session


@pytest.fixture
def ключ(monkeypatch):
    monkeypatch.setenv("APP_KEY", "base64:" + base64.b64encode(b"k" * 32).decode())
    monkeypatch.delenv("SESSION_DRIVER", raising=False)
    monkeypatch.delenv("SESSION_SECURE_COOKIE", raising=False)
    monkeypatch.setenv("APP_URL", "https://savdex.test")
    # Гость: без куки вход не ищется в базе
    monkeypatch.setattr(session, "_authenticate", lambda *a: laravel_session.GUEST)


@pytest.mark.parametrize(("proto", "secure"), [("https", True), ("http", False)])
def test_кука_сессии_мимо_страницы_сайта(ключ, proto, secure):
    request = RequestFactory().get(
        "/py/admin/login/", HTTP_HOST="savdex.test", HTTP_X_FORWARDED_PROTO=proto
    )
    started = session.start(request)
    assert started is not None
    store, _ = started
    response = HttpResponse()

    session._set_cookie(
        response, store, "laravel-session", store.id, b"k" * 32, http_only=True, session_cookie=True
    )

    assert store.root == f"{proto}://savdex.test"
    assert bool(response.cookies["laravel-session"]["secure"]) is secure
