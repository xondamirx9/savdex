"""
Защитные заголовки и HTTPS (savdex/settings.py, savdex/web/headers.py):
http:// — на https://, кроме проверки здоровья Render; HSTS; страницы
площадки нельзя встроить в чужой сайт.
"""

from __future__ import annotations

from django.test import Client, override_settings

БОЕВЫЕ = {
    "SECURE_SSL_REDIRECT": True,
    "SECURE_HSTS_SECONDS": 31_536_000,
}


@override_settings(**БОЕВЫЕ)
def test_http_на_https():
    response = Client().get("/catalog")

    assert response.status_code == 301
    assert response["Location"] == "https://testserver/catalog"


@override_settings(**БОЕВЫЕ)
def test_проверка_здоровья_без_редиректа():
    # Render ходит внутрь по HTTP: редирект он счёл бы падением службы
    assert Client().get("/up").status_code != 301
    assert Client().get("/py/up").status_code != 301


@override_settings(**БОЕВЫЕ)
def test_заголовки_на_https():
    response = Client().get("/up", secure=True)

    assert response["Strict-Transport-Security"] == "max-age=31536000"
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert response["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "camera=()" in response["Permissions-Policy"]
