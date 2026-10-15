"""
Адрес сайта для ссылок (request.root_of) — только свой хост.

- X-Forwarded-Host: evil.tld — не берётся: ссылка сброса пароля с токеном
  ушла бы на чужой домен; вместо него — APP_URL;
- свой хост из заголовка (APP_URL, DJANGO_ALLOWED_HOSTS, «.домен»,
  мини-сайты на MICROSITE_DOMAIN) — как пришёл, с портом и схемой;
- без APP_URL (разработка) — как раньше, из заголовков.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from savdex.web.request import root_of


def _адрес(**headers: str) -> str:
    return root_of(RequestFactory().get("/", **headers))


@pytest.fixture(autouse=True)
def _окружение(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_URL", "https://savdex.uz")
    monkeypatch.delenv("DJANGO_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MICROSITE_DOMAIN", raising=False)


def test_чужой_хост_из_заголовка_заменяется_app_url() -> None:
    чужой = _адрес(HTTP_X_FORWARDED_HOST="evil.tld", HTTP_X_FORWARDED_PROTO="https")
    assert чужой == "https://savdex.uz"
    assert _адрес(HTTP_X_FORWARDED_HOST="evil.tld, savdex.uz") == "https://savdex.uz"
    assert _адрес(HTTP_HOST="evil.tld") == "https://savdex.uz"
    assert _адрес(HTTP_X_FORWARDED_HOST="savdex.uz.evil.tld") == "https://savdex.uz"
    assert _адрес(HTTP_X_FORWARDED_HOST="evil.tld/savdex.uz") == "https://savdex.uz"
    # Python видит хост savdex.uz, браузер — evil.tld
    assert _адрес(HTTP_X_FORWARDED_HOST="evil.tld\\@savdex.uz") == "https://savdex.uz"
    assert _адрес(HTTP_X_FORWARDED_HOST="evil.tld@savdex.uz") == "https://savdex.uz"


def test_свой_хост_остаётся() -> None:
    свой = _адрес(HTTP_X_FORWARDED_HOST="savdex.uz", HTTP_X_FORWARDED_PROTO="https")
    assert свой == "https://savdex.uz"
    assert _адрес(HTTP_HOST="SAVDEX.UZ") == "http://SAVDEX.UZ"


def test_хосты_из_allowed_hosts_и_мини_сайтов(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "www.savdex.uz,.savdex.app,*")
    monkeypatch.setenv("MICROSITE_DOMAIN", "savdex.site")

    assert _адрес(HTTP_HOST="www.savdex.uz") == "http://www.savdex.uz"
    assert _адрес(HTTP_HOST="savdex.app") == "http://savdex.app"
    assert _адрес(HTTP_HOST="a.savdex.app") == "http://a.savdex.app"
    assert _адрес(HTTP_HOST="shop.savdex.site") == "http://shop.savdex.site"
    # «*» в DJANGO_ALLOWED_HOSTS не открывает любой хост
    assert _адрес(HTTP_HOST="evil.tld") == "https://savdex.uz"


def test_без_app_url_как_раньше(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_URL")

    assert _адрес(HTTP_X_FORWARDED_HOST="localhost:8000") == "http://localhost:8000"
