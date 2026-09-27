"""Журнал действий: правила записи по отдельности (сверка с PHP — test_audit_parity.py)."""

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
def test_адрес_как_у_laravel(forwarded, remote, expected):
    extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
    request = RequestFactory().get("/", REMOTE_ADDR=remote, **extra)

    assert audit.client_ip(request) == expected
    assert audit.client_ip(None) is None
