"""
Код по SMS (savdex/web/sms.py, Telnyx Verify): номер в международном
виде, отправка и проверка кода, суточный предел на номер.

Telnyx — заглушка (HTTP-сервер): код «12345» верный, номер со словом
в конце …000 — отказ отправки.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from savdex.web import sms

#: Что получила заглушка: путь, ключ, тело
ЗАПРОСЫ: list[dict[str, Any]] = []


class _Telnyx(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        ЗАПРОСЫ.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})

        if self.path == "/verifications/sms":
            ok = not str(body.get("phone_number", "")).endswith("000")
            self._json(200 if ok else 422, {"data": {"id": "v1"}} if ok else {"errors": []})
        else:
            accepted = body.get("code") == "12345"
            self._json(200, {"data": {"response_code": "accepted" if accepted else "rejected"}})

    def _json(self, status: int, data: Any) -> None:
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: Any) -> None:
        pass


@contextmanager
def заглушка_telnyx() -> Iterator[str]:
    """Заглушка Telnyx на свободном порту — её адрес для TELNYX_API_URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Telnyx)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@pytest.fixture(scope="module")
def telnyx() -> Iterator[str]:
    with заглушка_telnyx() as url:
        yield url


@pytest.fixture
def окружение(monkeypatch, telnyx, tmp_path):
    ЗАПРОСЫ.clear()
    счётчики: dict[str, Any] = {}
    monkeypatch.setattr(sms.laravel_cache, "get", lambda key, **_: счётчики.get(key))
    monkeypatch.setattr(
        sms.laravel_cache, "put", lambda key, value, ttl: счётчики.__setitem__(key, value)
    )
    monkeypatch.setenv("TELNYX_API_KEY", "key-1")
    monkeypatch.setenv("TELNYX_VERIFY_PROFILE_ID", "profile-1")
    monkeypatch.setenv("TELNYX_API_URL", telnyx)

    return monkeypatch


@pytest.mark.parametrize(
    ("raw", "dial", "ждём"),
    [
        ("+86 138 1234 5678", "+86", "+8613812345678"),
        ("138 1234 5678", "+86", "+8613812345678"),
        ("8613812345678", "+86", "+8613812345678"),
        ("0086 138 1234 5678", None, "+8613812345678"),
        ("+998 (90) 123-45-67", None, "+998901234567"),
        ("12345", "+86", None),
        ("", "+86", None),
    ],
)
def test_номер(raw, dial, ждём):
    assert sms.normalize(raw, dial) == ждём


def test_без_ключей_выключено(monkeypatch):
    monkeypatch.delenv("TELNYX_API_KEY", raising=False)
    monkeypatch.delenv("TELNYX_VERIFY_PROFILE_ID", raising=False)

    assert sms.configured() is False
    assert sms.send_code("+8613812345678") is False


def test_отправка_и_проверка(окружение):
    assert sms.send_code("+8613812345678") is True
    assert ЗАПРОСЫ[0] == {
        "path": "/verifications/sms",
        "auth": "Bearer key-1",
        "body": {"phone_number": "+8613812345678", "verify_profile_id": "profile-1"},
    }

    assert sms.check_code("+8613812345678", "12345") is True
    assert ЗАПРОСЫ[1]["path"] == "/verifications/by_phone_number/%2B8613812345678/actions/verify"
    assert sms.check_code("+8613812345678", "99999") is False
    # Не цифры — даже не спрашиваем
    assert sms.check_code("+8613812345678", "12a45") is False
    assert len(ЗАПРОСЫ) == 3


def test_отказ_отправки(окружение):
    assert sms.send_code("+8613812345000") is False


def test_суточный_предел(окружение):
    for _ in range(sms.MAX_PER_DAY):
        assert not sms.daily_limit_reached("+8613812345678")
        assert sms.send_code("+8613812345678")

    assert sms.daily_limit_reached("+8613812345678")
    # Другой номер — свой счёт
    assert not sms.daily_limit_reached("+8613812345679")


def test_неверный_код_сгорает_после_пяти(окружение):
    """
    Пять неверных кодов на номер — дальше даже верный не принимается и
    Telnyx не спрашиваем: код перебирали бы с разных адресов сети.
    Новое SMS — счёт заново.
    """
    номер = "+8613812345678"

    for _ in range(sms.MAX_FAILURES):
        assert sms.failed_message_key(номер) == "messages.auth.sms_code_invalid"
        assert sms.check_code(номер, "99999") is False

    запросов = len(ЗАПРОСЫ)
    assert sms.too_many_failures(номер)
    assert sms.failed_message_key(номер) == "messages.auth.sms_code_exhausted"
    assert sms.check_code(номер, "12345") is False
    assert len(ЗАПРОСЫ) == запросов
    # Другой номер — свой счёт
    assert sms.check_code("+8613812345679", "12345") is True

    assert sms.send_code(номер)
    assert not sms.too_many_failures(номер)
    assert sms.check_code(номер, "12345") is True


def test_верный_код_обнуляет_счёт(окружение):
    номер = "+8613812345678"

    for _ in range(sms.MAX_FAILURES - 1):
        sms.check_code(номер, "99999")

    assert sms.check_code(номер, "12345") is True
    assert sms.check_code(номер, "99999") is False
    assert not sms.too_many_failures(номер)
