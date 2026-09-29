"""
Вход в админку Django по пропуску из Laravel: проверка пропуска и куки.

Пропуск здесь собирается так же, как его собирает PHP
(App\\Support\\PythonBridge), — чтобы проверить все отказы по отдельности.
Что подпись от настоящего Laravel сходится, проверяет
tests/test_bridge_parity.py.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from django.test import Client

from savdex import access, adminpanel, bridge
from savdex.dashboard import widgets

APP_KEY = "base64:" + base64.b64encode(b"k" * 32).decode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def пропуск(payload: dict, key: bytes | None = None) -> str:
    raw = base64.b64decode(APP_KEY[7:])
    key = key or hmac.new(raw, b"savdex-django-bridge-v1", hashlib.sha256).digest()
    body = _b64(json.dumps(payload).encode())

    return body + "." + _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


@pytest.fixture(autouse=True)
def ключи(monkeypatch, settings):
    monkeypatch.setenv("APP_KEY", APP_KEY)
    settings.SECRET_KEY = "проверочный-ключ-" + "x" * 40
    settings.SECRET_KEY_IS_REAL = True


def годный(**поправки) -> dict:
    return {
        "uid": 7,
        "next": "/py/admin/geo/",
        "exp": int(time.time()) + 60,
        "nonce": "n",
    } | поправки


class TestПропуск:
    def test_годный_принимается(self):
        passed = bridge.verify(пропуск(годный()))

        assert passed == bridge.Pass(uid=7, next="/py/admin/geo/")

    @pytest.mark.parametrize(
        ("token", "причина"),
        [
            ("", "без подписи"),
            ("abc", "без подписи"),
            ("abc.", "без подписи"),
            ("!!!.???", "не разбирается"),
        ],
    )
    def test_мусор(self, token, причина):
        with pytest.raises(bridge.BridgeError, match=причина):
            bridge.verify(token)

    def test_просроченный(self):
        with pytest.raises(bridge.BridgeError, match="просрочен"):
            bridge.verify(пропуск(годный(exp=int(time.time()) - 1)))

    def test_подписанный_чужим_ключом(self):
        with pytest.raises(bridge.BridgeError, match="подпись"):
            bridge.verify(пропуск(годный(), key=b"x" * 32))

    def test_подменённый_номер(self):
        """Подпись от одного содержимого, содержимое — другое."""
        token = пропуск(годный(uid=7))
        _, _, signature = token.partition(".")
        forged = _b64(json.dumps(годный(uid=1)).encode())

        with pytest.raises(bridge.BridgeError, match="подпись"):
            bridge.verify(forged + "." + signature)

    @pytest.mark.parametrize("uid", ["7", True, None, 7.0])
    def test_номер_не_целое(self, uid):
        with pytest.raises(bridge.BridgeError, match="номера"):
            bridge.verify(пропуск(годный(uid=uid)))

    @pytest.mark.parametrize(
        "next_",
        [
            "https://evil.example/",
            "//evil.example/",
            "/py/admin//x",
            "/admin",
            None,
            5,
            "/py/admin/\n",
        ],
    )
    def test_чужой_адрес_заменяется(self, next_):
        assert bridge.verify(пропуск(годный(next=next_))).next == bridge.HOME

    def test_без_app_key_вход_выключен(self, monkeypatch):
        monkeypatch.delenv("APP_KEY")

        assert not bridge.enabled()

        with pytest.raises(bridge.BridgeError, match="APP_KEY"):
            bridge.verify(пропуск(годный()))

    def test_без_настоящего_secret_key_вход_выключен(self, settings):
        settings.SECRET_KEY_IS_REAL = False

        assert not bridge.enabled()


class TestКука:
    def test_туда_и_обратно(self):
        assert bridge.session_uid(bridge.session_cookie(7)) == 7

    def test_подделанная(self):
        value = bridge.session_cookie(7)

        assert bridge.session_uid(value[:-2] + "xx") is None
        assert bridge.session_uid("") is None
        assert bridge.session_uid(None) is None

    def test_истёкшая(self, monkeypatch):
        value = bridge.session_cookie(7)
        сейчас = time.time()
        monkeypatch.setattr(time, "time", lambda: сейчас + bridge.SESSION_TTL + 5)

        assert bridge.session_uid(value) is None


def сотрудник(**поправки) -> access.Admin:
    return access.Admin(
        **{
            "id": 7,
            "name": "Анна",
            "email": "anna@savdex.uz",
            "is_admin": True,
            "role": "content_manager",
            "status": "active",
        }
        | поправки
    )


class TestСтраницы:
    """Вход, раздел и выход — с подменённым чтением пользователя из базы."""

    @pytest.fixture
    def база(self, monkeypatch):
        люди: dict[int, access.Admin | None] = {7: сотрудник()}
        monkeypatch.setattr(bridge, "load_admin", lambda _conn, uid: люди.get(uid))
        # Базы здесь нет, а виджеты главной её читают; они проверены
        # на PostgreSQL в tests/test_dashboard.py
        monkeypatch.setattr(widgets, "for_request", lambda request: [])

        return люди

    def test_вход_и_раздел(self, база):
        client = Client()

        response = client.post("/py/login", {"token": пропуск(годный())})

        assert response.status_code == 302
        assert response["Location"] == "/py/admin/geo/"

        cookie = response.cookies[bridge.COOKIE]
        assert cookie["httponly"] and cookie["path"] == "/py/" and cookie["samesite"] == "Lax"

        page = client.get("/py/admin/")

        assert page.status_code == 200
        assert "Анна" in page.content.decode()
        # Контент-менеджеру справочники выданы — раздел стран виден
        assert "Страны" in page.content.decode()

    def test_без_входа_за_пропуском_в_laravel(self, база):
        response = Client().get("/py/admin/geo/?page=2")

        assert response.status_code == 302
        assert response["Location"] == "/admin/python?next=/py/admin/geo/%3Fpage%3D2"

    def test_снятые_права_действуют_сразу(self, база):
        client = Client()
        client.post("/py/login", {"token": пропуск(годный())})

        база[7] = None  # заблокировали, удалили или сняли роль

        assert client.get("/py/admin/").status_code == 302

    def test_плохой_пропуск_не_пускает(self, база):
        response = Client().post("/py/login", {"token": пропуск(годный(exp=0))})

        assert response.status_code == 403
        assert bridge.COOKIE not in response.cookies

    def test_пропуск_тому_кому_нельзя(self, база):
        response = Client().post("/py/login", {"token": пропуск(годный(uid=8))})

        assert response.status_code == 403

    def test_вход_только_post(self, база):
        assert Client().get("/py/login").status_code == 405

    def test_выход_защищён_от_подделки_запроса(self, база):
        client = Client(enforce_csrf_checks=True)
        client.post("/py/login", {"token": пропуск(годный())})

        assert client.post("/py/logout").status_code == 403

    def test_выход(self, база):
        client = Client()
        client.post("/py/login", {"token": пропуск(годный())})

        response = client.post("/py/logout")

        assert response.status_code == 302
        assert response.cookies[bridge.COOKIE].value == ""

    def test_без_app_key_раздел_закрыт(self, база, monkeypatch):
        monkeypatch.delenv("APP_KEY")

        assert Client().get("/py/admin/").status_code == 503

    def test_промежуточный_слой_не_трогает_прочие_адреса(self):
        assert Client().get("/py/up").status_code == 200
        assert adminpanel.LARAVEL_BRIDGE == "/admin/python"
