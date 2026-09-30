"""
Шаг 71: курсы ЦБ обновляет расписание Django (savdex/web/currency.refresh)
вместо cbu-rates:refresh у Laravel.

Разбор ответа ЦБ как у CurrencyRate::fetch (номинал, пустые и нулевые
строки), запись — в файловый кэш Laravel тем же форматом: таблица на
сутки и последняя удачная на месяц. Сбой ЦБ кэш не трогает. Что записал
Django, читает сам Laravel (Cache::get) — нужен PHP.
"""

from __future__ import annotations

import json

import httpx
import pytest

from savdex.web import currency

ОТВЕТ = [
    {"Ccy": "USD", "Rate": "12650.50", "Nominal": "1"},
    {"Ccy": " eur ", "Rate": "13790.25", "Nominal": "1"},
    {"Ccy": "JPY", "Rate": "8500", "Nominal": "100"},
    {"Ccy": "", "Rate": "1"},
    {"Ccy": "XXX", "Rate": "0"},
    "мусор",
]


def клиент(status: int = 200, body: object = ОТВЕТ) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == currency.URL
        return httpx.Response(status, content=json.dumps(body).encode())

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def кэш(monkeypatch, settings, tmp_path):
    settings.LARAVEL_ROOT = tmp_path
    monkeypatch.setenv("CACHE_STORE", "file")

    return tmp_path


def test_разбор_как_у_laravel():
    assert currency.fetch(клиент()) == {"USD": 12650.5, "EUR": 13790.25, "JPY": 85.0}


def test_обновление_в_кэш(кэш):
    assert currency.refresh(клиент())

    assert currency.cached(currency.CACHE_KEY) == {"USD": 12650.5, "EUR": 13790.25, "JPY": 85.0}
    assert currency.cached(currency.FALLBACK_KEY) == currency.cached(currency.CACHE_KEY)
    assert currency.CurrencyRate().usd() == 12650.5


@pytest.mark.parametrize(("status", "body"), [(500, ОТВЕТ), (200, []), (200, {"a": 1})])
def test_сбой_цб_кэш_не_трогает(кэш, status, body):
    assert not currency.refresh(клиент(status, body))
    assert currency.cached(currency.CACHE_KEY) is None


def test_laravel_читает_записанное():
    """Запись Django в настоящем кэше Laravel — Cache::get видит ту же таблицу."""
    from .pg_admin import php

    assert currency.refresh(клиент())

    прочитано = php("echo json_encode(Cache::get('cbu.rates'));", {"CACHE_STORE": "file"})

    assert json.loads(прочитано.splitlines()[-1]) == {"USD": 12650.5, "EUR": 13790.25, "JPY": 85}
