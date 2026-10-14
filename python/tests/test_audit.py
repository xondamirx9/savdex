"""Журнал действий: правила записи по отдельности."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from savdex import audit


def test_секреты_спрятаны_шум_убран_длинное_обрезано():
    cleaned = audit.clean(
        {
            "before": {"password": "a", "updated_at": "x", "phone_code": "+1"},
            "after": {"api_token": "t", "search_text": "s", "about": "я" * 301, "sort": 3},
        }
    )

    assert cleaned == {
        "before": {"password": "···", "phone_code": "+1"},
        "after": {"api_token": "···", "about": "я" * 300 + "…", "sort": 3},
    }


def test_пусто_остаётся_пустым():
    assert audit.clean({}) == {}
    assert audit.clean({"after": {"updated_at": "x"}}) == {}


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"name": "Анна", "code": "uz"}, "Анна"),
        ({"name": "", "code": "uz"}, "uz"),
        ({"title": "Т" * 250}, "Т" * 200),
        ({"slug": "tashkent"}, "tashkent"),
        ({"sort": 1}, "Country #7"),
    ],
)
def test_название_записи(attributes, expected):
    assert audit.label(attributes, "Country", 7) == expected


@pytest.mark.parametrize(
    ("forwarded", "remote", "expected"),
    [
        ("203.0.113.5, 10.0.0.1", "127.0.0.1", "203.0.113.5"),
        ("", "127.0.0.1", "127.0.0.1"),
        ("мусор, 10.0.0.1", "127.0.0.1", "127.0.0.1"),
        ("2001:db8::1", "127.0.0.1", "2001:db8::1"),
    ],
)
def test_адрес_клиента(forwarded, remote, expected):
    extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
    request = RequestFactory().get("/", REMOTE_ADDR=remote, **extra)

    assert audit.client_ip(request) == expected
    assert audit.client_ip(None) is None


def test_значения_вне_json_не_губят_запись():
    """Число с фиксированной точкой (координаты города) пишется строкой."""
    import json
    from decimal import Decimal

    assert json.dumps(audit.clean({"after": {"lat": Decimal("41.2995000")}}), default=str) == (
        '{"after": {"lat": "41.2995000"}}'
    )


@pytest.mark.parametrize(
    ("headers", "hops", "expected"),
    [
        # Посетитель сам дописал X-Forwarded-For — край сети знает настоящий адрес
        (
            {
                "HTTP_X_FORWARDED_FOR": "1.2.3.4, 203.0.113.5",
                "HTTP_CF_CONNECTING_IP": "203.0.113.5",
            },
            None,
            "203.0.113.5",
        ),
        (
            {"HTTP_X_FORWARDED_FOR": "1.2.3.4", "HTTP_TRUE_CLIENT_IP": "198.51.100.9"},
            None,
            "198.51.100.9",
        ),
        # Мусор в заголовке края — дальше по цепочке
        (
            {"HTTP_X_FORWARDED_FOR": "203.0.113.5", "HTTP_CF_CONNECTING_IP": "мусор"},
            None,
            "203.0.113.5",
        ),
        # Своих прокси справа двое — подделанное слева не берётся
        ({"HTTP_X_FORWARDED_FOR": "1.2.3.4, 203.0.113.5, 10.0.0.1"}, "2", "203.0.113.5"),
        # Цепочка короче, чем прокси, — самый левый
        ({"HTTP_X_FORWARDED_FOR": "203.0.113.5"}, "3", "203.0.113.5"),
        ({"HTTP_X_FORWARDED_FOR": "203.0.113.5"}, "не число", "203.0.113.5"),
    ],
)
def test_адрес_клиента_не_подделать(monkeypatch, headers, hops, expected):
    if hops is None:
        monkeypatch.delenv("SAVDEX_PROXY_HOPS", raising=False)
    else:
        monkeypatch.setenv("SAVDEX_PROXY_HOPS", hops)

    request = RequestFactory().get("/", REMOTE_ADDR="127.0.0.1", **headers)

    assert audit.client_ip(request) == expected


def test_заголовки_края_можно_выключить(monkeypatch):
    monkeypatch.setenv("SAVDEX_CLIENT_IP_HEADERS", "")
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_FORWARDED_FOR="203.0.113.5",
        HTTP_CF_CONNECTING_IP="1.2.3.4",
    )

    assert audit.client_ip(request) == "203.0.113.5"
