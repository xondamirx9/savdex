"""
Этап 3, шаг 1: Django узнаёт, кто вошёл на сайт, по сессии Laravel.

Главная проверка этапа (docs/migration-to-python.md, этап 3): «вошёл на
странице Laravel → перешёл на страницу Django → остался тем же
пользователем». Здесь это делается по-настоящему: Laravel запущен
(php artisan serve), вход — формой /login, как в браузере; с теми же
куками Django отвечает на /py/whoami.

Плюс то, где читающий сессию легко ошибиться:

- выход в Laravel — гость и в Django;
- подменённая кука, чужой ключ — гость;
- просроченная сессия — гость; «запомнить меня» — вошёл и без сессии;
- сменённый токен «запомнить меня», пользователь в корзине — гость.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote

import bcrypt
import httpx
import pytest

from savdex import laravel_session

from .pg_admin import APP_KEY, PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

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


def _порт() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))

        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    """Laravel на своём порту — вход настоящей формой."""
    свежая_база()
    port = _порт()
    env = {**ОКРУЖЕНИЕ, **САЙТ, "APP_URL": f"http://127.0.0.1:{port}"}
    сервер = subprocess.Popen(
        ["php", "artisan", "serve", "--host=127.0.0.1", f"--port={port}"],
        cwd=КОРЕНЬ,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/up", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.2)

        yield f"http://127.0.0.1:{port}"
    finally:
        сервер.terminate()
        сервер.wait(timeout=10)


def _пользователь(email: str) -> int:
    # $2y$, как пишет PHP: тот же bcrypt, но Laravel проверяет метку
    hashed = "$2y$" + bcrypt.hashpw(ПАРОЛЬ.encode(), bcrypt.gensalt(rounds=4)).decode()[4:]
    [(uid,)] = sql(
        "insert into users (name, email, password, status, email_verified_at, created_at, "
        "updated_at) values (%s, %s, %s, 'active', now(), now(), now()) returning id",
        [f"Покупатель {email}", email, hashed],
    )

    return int(uid)


def _войти(сайт: str, email: str, *, remember: bool = False) -> httpx.Client:
    """Вход формой /login, как в браузере: с CSRF из куки XSRF-TOKEN."""
    клиент = httpx.Client(base_url=сайт, follow_redirects=False, timeout=30)
    # Переходом Inertia: ответ — JSON без вёрстки, собранный фронт не
    # нужен (в CI его нет). Куки сессии и XSRF ставятся так же
    клиент.get("/login", headers={"X-Inertia": "true"})
    форма = {"email": email, "password": ПАРОЛЬ} | ({"remember": "1"} if remember else {})
    ответ = клиент.post(
        "/login",
        data=форма,
        headers={"X-XSRF-TOKEN": unquote(клиент.cookies["XSRF-TOKEN"]), "Referer": сайт},
    )
    assert ответ.status_code == 302, ответ.text[:2000]
    assert ответ.headers["location"].endswith("/cabinet")

    return клиент


def _куки(клиент: httpx.Client) -> dict[str, str]:
    return {c.name: c.value for c in клиент.cookies.jar}


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
    клиент = _войти(сайт, "buyer1@savdex.uz")

    ответ = кто(_куки(клиент))

    assert ответ["status"] == 200
    assert ответ["authenticated"] is True
    assert ответ["user_id"] == uid
    assert ответ["name"] == "Покупатель buyer1@savdex.uz"
    assert ответ["via_remember"] is False
    # Свой ответ у каждого вошедшего — не хранится ни браузером, ни прокси
    assert ответ["cache"] == "no-store, private"


def test_гость_и_подменённая_кука(сайт):
    _пользователь("buyer2@savdex.uz")
    куки = _куки(_войти(сайт, "buyer2@savdex.uz"))
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


def test_выход_в_laravel_гость_в_django(сайт):
    _пользователь("buyer3@savdex.uz")
    клиент = _войти(сайт, "buyer3@savdex.uz")
    до_выхода = _куки(клиент)

    клиент.post(
        "/logout",
        headers={"X-XSRF-TOKEN": unquote(клиент.cookies["XSRF-TOKEN"]), "Referer": сайт},
    )

    assert кто(до_выхода)["authenticated"] is False
    assert кто(_куки(клиент))["authenticated"] is False


def test_просроченная_сессия(сайт):
    _пользователь("buyer4@savdex.uz")
    куки = _куки(_войти(сайт, "buyer4@savdex.uz"))
    sql("update sessions set last_activity = %s", [int(time.time()) - 121 * 60])

    assert кто(куки)["authenticated"] is False


def test_запомнить_меня(сайт):
    uid = _пользователь("buyer5@savdex.uz")
    куки = _куки(_войти(сайт, "buyer5@savdex.uz", remember=True))
    assert laravel_session.REMEMBER_COOKIE in куки

    # Сессия кончилась — Laravel впускает по куке «запомнить меня»
    sql("delete from sessions where user_id = %s", [uid])
    ответ = кто(куки)
    assert (ответ["authenticated"], ответ["user_id"], ответ["via_remember"]) == (True, uid, True)

    # Выход на всех устройствах меняет токен — кука больше не годится
    sql("update users set remember_token = 'другой-токен' where id = %s", [uid])
    assert кто(куки)["authenticated"] is False


def test_пользователь_в_корзине(сайт):
    uid = _пользователь("buyer6@savdex.uz")
    куки = _куки(_войти(сайт, "buyer6@savdex.uz"))
    sql("update users set deleted_at = now() where id = %s", [uid])

    assert кто(куки)["authenticated"] is False


def test_расшифровка_как_у_laravel():
    """То, что зашифровал Laravel, Python читает; чужой ключ — нет."""
    for text in ("savdex", "Вошёл · 登录 · giriş", "x" * 1000):
        payload = php(f"echo Illuminate\\Support\\Facades\\Crypt::encryptString({text!r});")

        assert laravel_session.decrypt(payload, [_key()]) == text

    payload = php("echo Illuminate\\Support\\Facades\\Crypt::encryptString('secret');")
    assert laravel_session.decrypt(payload, [b"x" * 32]) is None


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
