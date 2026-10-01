"""Чтение куки Laravel без базы: порча и подделка — «гость», а не ошибка."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from savdex import laravel_session

KEY = b"k" * 32


def _laravel_encrypt(text: str, key: bytes = KEY) -> str:
    """Как Encrypter::encrypt($value, false): AES-256-CBC + HMAC-SHA256."""
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(text.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    value = base64.b64encode(encryptor.update(data) + encryptor.finalize()).decode()
    iv_b64 = base64.b64encode(iv).decode()
    mac = hmac.new(key, (iv_b64 + value).encode(), hashlib.sha256).hexdigest()

    return base64.b64encode(
        json.dumps({"iv": iv_b64, "value": value, "mac": mac, "tag": ""}).encode()
    ).decode()


def _cookie(name: str, value: str, key: bytes = KEY) -> str:
    prefix = hmac.new(key, f"{name}v2".encode(), hashlib.sha1).hexdigest()

    return _laravel_encrypt(f"{prefix}|{value}", key)


def test_своя_кука_читается():
    raw = _cookie("savdex-session", "A" * 40)

    assert laravel_session.cookie_value("savdex-session", raw, [KEY]) == "A" * 40


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "не base64 вовсе",
        base64.b64encode(b"{}").decode(),
        base64.b64encode(json.dumps({"iv": "x", "value": "y", "mac": "z"}).encode()).decode(),
        # Подпись с не-ASCII знаками: compare_digest на строках упал бы
        base64.b64encode(
            json.dumps({"iv": "AAAAAAAAAAAAAAAAAAAAAA==", "value": "AAAA", "mac": "ё"}).encode()
        ).decode(),
    ],
)
def test_порча_значит_не_вошёл(raw):
    assert laravel_session.cookie_value("savdex-session", raw, [KEY]) is None


def test_подпись_не_сходится():
    payload = json.loads(base64.b64decode(_cookie("savdex-session", "A" * 40)))
    payload["mac"] = "0" * 64
    raw = base64.b64encode(json.dumps(payload).encode()).decode()

    assert laravel_session.cookie_value("savdex-session", raw, [KEY]) is None


def test_чужое_имя_и_чужой_ключ():
    raw = _cookie("savdex-session", "A" * 40)

    assert laravel_session.cookie_value("other", raw, [KEY]) is None
    assert laravel_session.cookie_value("savdex-session", raw, [b"z" * 32]) is None
    # Прежний ключ после смены ещё читается
    assert laravel_session.cookie_value("savdex-session", raw, [b"z" * 32, KEY]) == "A" * 40


def test_кука_из_заголовка_с_процентами():
    """PHP кодирует куку: «+», «/», «=» приходят как %2B, %2F, %3D."""
    raw = _cookie("savdex-session", "A" * 40)
    encoded = raw.replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")

    assert laravel_session.cookie_value("savdex-session", encoded, [KEY]) == "A" * 40


def test_ключи_из_окружения(monkeypatch):
    good = "base64:" + base64.b64encode(KEY).decode()
    monkeypatch.setenv("APP_KEY", good)
    monkeypatch.setenv("APP_PREVIOUS_KEYS", "base64:" + base64.b64encode(b"p" * 32).decode())

    assert laravel_session.keys() == [KEY, b"p" * 32]

    # Ключ не той длины Laravel не принял бы — и мы не берём
    monkeypatch.setenv("APP_KEY", "short")
    monkeypatch.setenv("APP_PREVIOUS_KEYS", "")
    assert laravel_session.keys() == []
