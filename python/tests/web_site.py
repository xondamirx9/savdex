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
from collections.abc import Callable, Iterator
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
method, body, content_type = sys.argv[4], sys.argv[5], sys.argv[6]
client = Client()
for name, value in cookies.items():
    client.cookies[name] = value
extra = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()}
if method == "GET":
    r = client.get(path, **extra)
else:
    r = client.generic(method, path, body.encode(), content_type, **extra)
print(json.dumps({
    "status": r.status_code,
    "headers": {k.lower(): v for k, v in r.items()},
    "cookies": {
        k: {"value": m.value, **{a: m[a] for a in m.keys() if m[a] not in ("", None)}}
        for k, m in r.cookies.items()
    },
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
def laravel(**окружение: str) -> Iterator[str]:
    """
    Laravel на своём порту; адрес сайта — http://127.0.0.1:<порт>.

    Окружение сверх САЙТ (например, CACHE_STORE=file) — то же надо
    передать и в сверить(), чтобы Django работал с теми же настройками.
    """
    with _манифест(), _сервер(окружение) as root:
        yield root


@contextmanager
def _сервер(окружение: dict[str, str]) -> Iterator[str]:
    port = _порт()
    root = f"http://127.0.0.1:{port}"
    env = {**ОКРУЖЕНИЕ, **САЙТ, **окружение, "APP_URL": root}
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
    method: str = "GET",
    body: str = "",
    content_type: str = "",
) -> dict[str, Any]:
    headers = dict(headers or {})

    if content_type:
        headers["Content-Type"] = content_type

    r = httpx.request(
        method,
        root + path,
        cookies=cookies or {},
        headers=headers,
        content=body.encode() if method != "GET" else None,
        timeout=30,
    )

    return {
        "status": r.status_code,
        "headers": dict(r.headers),
        "cookies": dict(_куки_ответа(r.headers.get_list("set-cookie"))),
        "body": r.text,
    }


def _куки_ответа(заголовки: list[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Set-Cookie от Laravel — в том же виде, что куки ответа Django."""
    for заголовок in заголовки:
        первая, *атрибуты = [часть.strip() for часть in заголовок.split(";")]
        имя, _, значение = первая.partition("=")
        разобранные: dict[str, Any] = {"value": значение}

        for атрибут in атрибуты:
            ключ, есть, знач = атрибут.partition("=")
            разобранные[ключ.lower()] = знач if есть else True

        yield имя, разобранные


def из_django(
    root: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    method: str = "GET",
    body: str = "",
    content_type: str = "",
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
            method,
            body,
            content_type or "application/octet-stream",
        ],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            **САЙТ,
            **(env or {}),
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


def разница(д: Any, л: Any, путь: str = "") -> list[str]:
    """Где расходятся два значения JSON: «путь: Django | Laravel»."""
    числа = (int, float)

    if type(д) is not type(л) and not (isinstance(д, числа) and isinstance(л, числа)):
        return [f"{путь}: {д!r:.200} | {л!r:.200}"]

    if isinstance(д, dict):
        строки = []

        for key in list(л) + [k for k in д if k not in л]:
            if key not in д or key not in л:
                строки.append(f"{путь}/{key}: есть у Django — {key in д}, у Laravel — {key in л}")
            else:
                строки += разница(д[key], л[key], f"{путь}/{key}")

        return строки

    if isinstance(д, list):
        строки = [f"{путь}: длина {len(д)} | {len(л)}"] if len(д) != len(л) else []

        for i, (x, y) in enumerate(zip(д, л, strict=False)):
            строки += разница(x, y, f"{путь}[{i}]")

        return строки

    return [] if д == л else [f"{путь}: {д!r:.200} | {л!r:.200}"]


#: Данные, которые есть только у Django: с 28.09 Laravel не дополняется
#: (docs/migration-to-python.md), и новые возможности появляются только в
#: Python. Сверка с Laravel их не видит — их проверяют свои тесты
ТОЛЬКО_DJANGO = frozenset({"government"})


def без_новых(value: Any) -> Any:
    """Страница Django без ключей ТОЛЬКО_DJANGO — для сверки с Laravel."""
    if isinstance(value, dict):
        return {k: без_новых(v) for k, v in value.items() if k not in ТОЛЬКО_DJANGO}

    if isinstance(value, list):
        return [без_новых(v) for v in value]

    return value


def сверить(
    сайт: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    перед: Callable[[], object] | None = None,
    после: Callable[[dict[str, Any]], object] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Django, затем Laravel; статус, страница и шапка должны совпасть.

    перед — вызывается перед каждой из сторон: страницы, которые пишут
    (счётчик просмотров), иначе видели бы запись друг друга; после —
    сразу после ответа каждой стороны (снять то, что она записала).
    """
    if перед is not None:
        перед()

    д = из_django(сайт, path, cookies, headers, env)

    if после is not None:
        после(д)

    if перед is not None:
        перед()

    л = из_laravel(сайт, path, cookies, headers)

    if после is not None:
        после(л)

    assert д["status"] == л["status"], (д["status"], л["status"], д["body"][:500])

    if л["status"] in (301, 302, 409):
        for header in ("location", "x-inertia-location"):
            assert д["headers"].get(header) == л["headers"].get(header), header

        return д, л

    стр_д, стр_л = страница(д["body"]), страница(л["body"])
    # Словарь интерфейса у сторон общий (lang/*/ui.php) — его не трогаем
    стр_д["props"] = {
        k: v if k == "translations" else без_новых(v) for k, v in стр_д["props"].items()
    }

    for key in ("component", "url", "version", "sharedProps"):
        assert стр_д.get(key) == стр_л.get(key), key

    for prop in стр_л["props"]:
        assert стр_д["props"].get(prop) == стр_л["props"][prop], f"проп {prop}:\n" + "\n".join(
            разница(стр_д["props"].get(prop), стр_л["props"][prop])[:20]
        )

    assert list(стр_д["props"]) == list(стр_л["props"])
    assert set(стр_д) == set(стр_л)

    if "<head>" in л["body"]:
        assert шапка(д["body"]) == шапка(л["body"])
        assert д["headers"].get("link") == л["headers"].get("link")

    assert д["headers"].get("vary") == л["headers"].get("vary")

    return д, л
