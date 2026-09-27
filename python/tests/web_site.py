"""
Сверка страниц сайта Laravel и Django — общая часть (этап 3).

Laravel запущен по-настоящему (php artisan serve), Django отвечает
в отдельном процессе через тестовый клиент — оба на одной базе и с
одним APP_KEY. Один и тот же запрос (адрес, куки, заголовки) уходит
в обе стороны, ответы разбираются одинаково: статус, объект страницы
Inertia, теги <head>.
"""

from __future__ import annotations

import html
import json
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import unquote

import bcrypt
import httpx

from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql

ПАРОЛЬ = "Pass-12345-word"

#: Как на боевом: сессии в базе, имя куки — от APP_NAME
САЙТ = {
    "SESSION_DRIVER": "database",
    "SESSION_LIFETIME": "120",
    "APP_NAME": "SAVDEX",
    "CACHE_STORE": "array",
    "APP_ENV": "local",
    "APP_DEBUG": "false",
}

ЗАПРОС = """
import json, sys
import django
django.setup()
from django.test import Client

path, cookies, headers = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
client = Client()
for name, value in cookies.items():
    client.cookies[name] = value
extra = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()}
r = client.get(path, **extra)
print(json.dumps({
    "status": r.status_code,
    "headers": {k.lower(): v for k, v in r.items()},
    "body": r.content.decode(),
}))
"""


def _порт() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))

        return int(s.getsockname()[1])


#: Манифест сборки на время сверки, если фронт не собран (так в CI):
#: без него страницу не соберёт ни Laravel (@vite), ни Django
ПОДСТАВНОЙ_МАНИФЕСТ = {
    "resources/css/app.css": {
        "file": "assets/app-ci.css",
        "src": "resources/css/app.css",
        "isEntry": True,
    },
    "resources/js/app.tsx": {
        "file": "assets/app-ci.js",
        "src": "resources/js/app.tsx",
        "isEntry": True,
        "imports": ["_vendor-ci.js"],
        "css": ["assets/app-extra-ci.css"],
    },
    "_vendor-ci.js": {"file": "assets/vendor-ci.js"},
}


@contextmanager
def _манифест() -> Iterator[None]:
    path = КОРЕНЬ / "public/build/manifest.json"

    if path.exists():
        yield
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ПОДСТАВНОЙ_МАНИФЕСТ))

    try:
        yield
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def laravel() -> Iterator[str]:
    """Laravel на своём порту; адрес сайта — http://127.0.0.1:<порт>."""
    with _манифест(), _сервер() as root:
        yield root


@contextmanager
def _сервер() -> Iterator[str]:
    port = _порт()
    root = f"http://127.0.0.1:{port}"
    env = {**ОКРУЖЕНИЕ, **САЙТ, "APP_URL": root}
    subprocess.run(
        ["php", "artisan", "savdex:export-ui"], cwd=КОРЕНЬ, env=env, check=True, capture_output=True
    )
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
                httpx.get(f"{root}/up", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.2)

        yield root
    finally:
        сервер.terminate()
        сервер.wait(timeout=10)


def пользователь(email: str, **поля: Any) -> int:
    hashed = "$2y$" + bcrypt.hashpw(ПАРОЛЬ.encode(), bcrypt.gensalt(rounds=4)).decode()[4:]
    columns = {
        "name": f"Покупатель {email}",
        "email": email,
        "password": hashed,
        "status": "active",
        **поля,
    }
    names = ", ".join(columns)
    marks = ", ".join(["%s"] * len(columns))
    [(uid,)] = sql(
        f"insert into users ({names}, email_verified_at, created_at, updated_at) "
        f"values ({marks}, now(), now(), now()) returning id",
        list(columns.values()),
    )

    return int(uid)


def войти(root: str, email: str) -> dict[str, str]:
    """Вход формой /login; куки вошедшего."""
    клиент = httpx.Client(base_url=root, follow_redirects=False, timeout=30)
    клиент.get("/login", headers={"X-Inertia": "true"})
    ответ = клиент.post(
        "/login",
        data={"email": email, "password": ПАРОЛЬ},
        headers={"X-XSRF-TOKEN": unquote(клиент.cookies["XSRF-TOKEN"]), "Referer": root},
    )
    assert ответ.status_code == 302, ответ.text[:2000]

    return {c.name: c.value for c in клиент.cookies.jar}


def гость(root: str) -> dict[str, str]:
    """Куки гостя, которому Laravel уже завёл сессию."""
    клиент = httpx.Client(base_url=root, follow_redirects=False, timeout=30)
    клиент.get("/login", headers={"X-Inertia": "true"})

    return {c.name: c.value for c in клиент.cookies.jar}


def из_laravel(
    root: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    r = httpx.get(root + path, cookies=cookies or {}, headers=headers or {}, timeout=30)

    return {"status": r.status_code, "headers": dict(r.headers), "body": r.text}


def из_django(
    root: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    host = root.removeprefix("http://")
    вывод = subprocess.run(
        [
            sys.executable,
            "-c",
            ЗАПРОС,
            path,
            json.dumps(cookies or {}),
            json.dumps({"Host": host, **(headers or {})}),
        ],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            **САЙТ,
            "APP_URL": root,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return dict(json.loads(вывод.stdout))


# ── Разбор ответа ───────────────────────────────────────────────────


def страница(body: str) -> dict[str, Any]:
    """Объект страницы Inertia из HTML или из ответа JSON."""
    match = re.search(r'<script data-page="app" type="application/json">(.*?)</script>', body, re.S)

    return dict(json.loads(match.group(1) if match else body))


def шапка(body: str) -> list[str]:
    """Теги <head> по одному, без пробелов вокруг и без токена CSRF."""
    head = body[body.index("<head>") + 6 : body.index("</head>")]
    tags = re.findall(r"<(?:meta|link|title|script)[^>]*>(?:[^<]*</(?:title|script)>)?", head)
    cleaned = []

    for tag in tags:
        tag = re.sub(r"\s+", " ", tag).replace(" >", ">")

        if 'name="csrf-token"' in tag:
            tag = re.sub(r'content="[^"]*"', 'content="…"', tag)

        cleaned.append(html.unescape(tag) if "ld+json" not in tag else tag)

    return cleaned
