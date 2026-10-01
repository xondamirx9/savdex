"""
Этап 3, шаг 1: Django узнаёт, кто вошёл на сайт, по сессии Laravel.

Главная проверка этапа (docs/migration-to-python.md, этап 3): «вошёл на
сайте → перешёл на страницу /py/… → остался тем же пользователем».
Вход — формой /login, как в браузере (сессия и кука в формате Laravel:
ими пользуются уже вошедшие посетители); с теми же куками Django
отвечает на /py/whoami.

Плюс то, где читающий сессию легко ошибиться:

- выход — гость и на /py/whoami;
- подменённая кука, чужой ключ — гость;
- просроченная сессия — гость; «запомнить меня» — вошёл и без сессии;
- сменённый токен «запомнить меня», пользователь в корзине — гость.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py и web_site.py.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote, urlencode

import bcrypt
import pytest

from savdex import laravel_session

from .pg_admin import APP_KEY, PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, гостевая, открыть

pytestmark = нужна_база

ПАРОЛЬ = "Pass-12345-word"

#: Как на боевом: сессии в базе, имя куки — от APP_NAME
САЙТ = {
    "SESSION_DRIVER": "database",
    "SESSION_LIFETIME": "120",
    "APP_NAME": "SAVDEX",
    "CACHE_STORE": "array",
    "APP_ENV": "local",
}

КТО = """
import json, sys
import django
django.setup()
from django.test import Client

client = Client()
for name, value in json.loads(sys.argv[1]).items():
    client.cookies[name] = value
r = client.get("/py/whoami")
print(json.dumps({"status": r.status_code, "cache": r.get("Cache-Control"), **r.json()}))
"""


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def _пользователь(email: str) -> int:
    # $2y$, как пишет PHP: тот же bcrypt, но Laravel проверяет метку
    hashed = "$2y$" + bcrypt.hashpw(ПАРОЛЬ.encode(), bcrypt.gensalt(rounds=4)).decode()[4:]
    [(uid,)] = sql(
        "insert into users (name, email, password, status, email_verified_at, created_at, "
        "updated_at) values (%s, %s, %s, 'active', now(), now(), now()) returning id",
        [f"Покупатель {email}", email, hashed],
    )

    return int(uid)


def _куки(было: dict[str, str], ответ: dict[str, Any]) -> dict[str, str]:
    """Куки браузера после ответа: новые поверх прежних, стёртые — прочь."""
    куки = dict(было)

    for имя, кука in ответ["cookies"].items():
        if кука["value"] and str(кука.get("max-age", "1")) != "0":
            куки[имя] = кука["value"]
        else:
            куки.pop(имя, None)

    return куки


def _отправить(сайт: str, path: str, куки: dict[str, str], форма: dict[str, str]) -> dict:
    """Форма, как из браузера: токен — из куки XSRF-TOKEN."""
    return открыть(
        сайт,
        path,
        куки,
        {"X-XSRF-TOKEN": unquote(куки["XSRF-TOKEN"]), "Referer": сайт},
        method="POST",
        body=urlencode(форма),
        content_type="application/x-www-form-urlencoded",
    )


def _вход_формой(сайт: str, email: str, *, remember: bool = False) -> dict[str, str]:
    """Вход формой /login, как в браузере; куки вошедшего."""
    куки = гостевая(сайт)
    форма = {"email": email, "password": ПАРОЛЬ} | ({"remember": "1"} if remember else {})
    ответ = _отправить(сайт, "/login", куки, форма)

    assert ответ["status"] == 302, ответ["body"][:2000]
    assert ответ["headers"]["location"].endswith("/cabinet")

    return _куки(куки, ответ)


def кто(куки: dict[str, str], env: dict[str, str] | None = None) -> dict[str, Any]:
    """Django с этими куками отвечает на /py/whoami."""
    вывод = subprocess.run(
        [sys.executable, "-c", КТО, json.dumps(куки)],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            **САЙТ,
            **(env or {}),
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return dict(json.loads(вывод.stdout))


def test_вошёл_в_laravel_узнан_в_django(сайт):
    uid = _пользователь("buyer1@savdex.uz")
    ответ = кто(_вход_формой(сайт, "buyer1@savdex.uz"))

    assert ответ["status"] == 200
    assert ответ["authenticated"] is True
    assert ответ["user_id"] == uid
    assert ответ["name"] == "Покупатель buyer1@savdex.uz"
    assert ответ["via_remember"] is False
    # Свой ответ у каждого вошедшего — не хранится ни браузером, ни прокси
    assert ответ["cache"] == "no-store, private"


def test_гость_и_подменённая_кука(сайт):
    _пользователь("buyer2@savdex.uz")
    куки = _вход_формой(сайт, "buyer2@savdex.uz")
    # Имя куки — от APP_NAME=SAVDEX, как на боевом
    имя = "savdex-session"
    assert имя in куки

    assert кто({})["authenticated"] is False

    испорченная = куки[имя][:-6] + ("A" if куки[имя][-6] != "A" else "B") + куки[имя][-5:]
    assert кто({**куки, имя: испорченная})["authenticated"] is False

    # Кука сессии под чужим именем не годится: префикс — от имени куки
    assert кто({"other-session": куки[имя]})["authenticated"] is False

    # Чужой ключ — ничего не расшифровать
    чужой = "base64:" + "A" * 43 + "="
    assert кто(куки, env={"APP_KEY": чужой})["authenticated"] is False
    # Прежний ключ после смены — Laravel ещё читает старые куки, Django тоже
    assert кто(куки, env={"APP_KEY": чужой, "APP_PREVIOUS_KEYS": APP_KEY})["authenticated"]


def test_после_выхода_не_узнан(сайт):
    _пользователь("buyer3@savdex.uz")
    до_выхода = _вход_формой(сайт, "buyer3@savdex.uz")
    assert кто(до_выхода)["authenticated"] is True

    ответ = _отправить(сайт, "/logout", до_выхода, {})
    assert ответ["status"] == 302

    # И прежняя кука, и новая — гость: сессия вошедшего стёрта
    assert кто(до_выхода)["authenticated"] is False
    assert кто(_куки(до_выхода, ответ))["authenticated"] is False


def test_просроченная_сессия(сайт):
    _пользователь("buyer4@savdex.uz")
    куки = _вход_формой(сайт, "buyer4@savdex.uz")
    assert кто(куки)["authenticated"] is True
    sql("update sessions set last_activity = %s", [int(time.time()) - 121 * 60])

    assert кто(куки)["authenticated"] is False


def test_запомнить_меня(сайт):
    uid = _пользователь("buyer5@savdex.uz")
    куки = _вход_формой(сайт, "buyer5@savdex.uz", remember=True)
    assert laravel_session.REMEMBER_COOKIE in куки

    # Сессия кончилась — впускает кука «запомнить меня»
    sql("delete from sessions where user_id = %s", [uid])
    ответ = кто(куки)
    assert (ответ["authenticated"], ответ["user_id"], ответ["via_remember"]) == (True, uid, True)

    # Выход на всех устройствах меняет токен — кука больше не годится
    sql("update users set remember_token = 'другой-токен' where id = %s", [uid])
    assert кто(куки)["authenticated"] is False


def test_пользователь_в_корзине(сайт):
    uid = _пользователь("buyer6@savdex.uz")
    куки = _вход_формой(сайт, "buyer6@savdex.uz")
    sql("update users set deleted_at = now() where id = %s", [uid])

    assert кто(куки)["authenticated"] is False


def _зашифровать_как_encrypter(text: str, key: bytes, iv: bytes) -> str:
    """
    Encrypter::encryptString у Laravel, написанный отдельно от сайта:
    AES-256-CBC с PKCS7, base64; mac — HMAC-SHA256 от iv и value; всё —
    JSON в base64.
    """
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    дополнитель = padding.PKCS7(128).padder()
    данные = дополнитель.update(text.encode()) + дополнитель.finalize()
    шифр = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    iv_b64 = base64.b64encode(iv).decode()
    value_b64 = base64.b64encode(шифр.update(данные) + шифр.finalize()).decode()
    mac = hmac.new(key, (iv_b64 + value_b64).encode(), hashlib.sha256).hexdigest()
    тело = json.dumps(
        {"iv": iv_b64, "value": value_b64, "mac": mac, "tag": ""}, separators=(",", ":")
    )

    return base64.b64encode(тело.encode()).decode()


def test_расшифровка_формата_куки():
    """Зашифрованное по-ларавеловски (куки уже вошедших) Python читает; чужой ключ — нет."""
    for text in ("savdex", "Вошёл · 登录 · giriş", "x" * 1000):
        payload = _зашифровать_как_encrypter(text, _key(), bytes(range(16)))

        assert laravel_session.decrypt(payload, [_key()]) == text

    payload = _зашифровать_как_encrypter("secret", _key(), b"\x07" * 16)
    assert laravel_session.decrypt(payload, [b"x" * 32]) is None
    # Испорченная подпись — тоже ничего
    испорченный = json.loads(base64.b64decode(payload))
    испорченный["mac"] = "0" * 64
    assert (
        laravel_session.decrypt(
            base64.b64encode(json.dumps(испорченный).encode()).decode(), [_key()]
        )
        is None
    )


def test_имя_куки_как_в_config_session(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE", raising=False)
    monkeypatch.setenv("APP_NAME", "SAVDEX")
    assert laravel_session.cookie_name() == "savdex-session"

    monkeypatch.setenv("APP_NAME", "Savdex Market 2")
    assert laravel_session.cookie_name() == "savdex-market-2-session"

    monkeypatch.setenv("SESSION_COOKIE", "sid")
    assert laravel_session.cookie_name() == "sid"


def _key() -> bytes:
    import base64

    return base64.b64decode(APP_KEY[7:])
