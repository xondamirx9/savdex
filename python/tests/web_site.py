"""
Проверки страниц и форм сайта — общая часть.

Django отвечает в отдельном процессе через тестовый клиент (настройки
читают окружение при запуске): адрес, куки и заголовки — как у браузера,
ответ разбирается на статус, объект страницы Inertia и теги <head>.
Сессия и куки — в формате Laravel, как их ведёт сайт (savdex/laravel_session.py).
"""

from __future__ import annotations

import base64
import hashlib
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
method, content_type = sys.argv[4], sys.argv[6]
# Тело — через stdin: большие файлы не помещаются в аргументы процесса
body = sys.stdin.read()
client = Client()
for name, value in cookies.items():
    client.cookies[name] = value
extra = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()}
if method == "GET":
    r = client.get(path, **extra)
else:
    import base64
    data = base64.b64decode(body[7:]) if body.startswith("base64:") else body.encode()
    r = client.generic(method, path, data, content_type, **extra)
print(json.dumps({
    "status": r.status_code,
    "headers": {k.lower(): v for k, v in r.items()},
    "cookies": {
        k: {"value": m.value, **{a: m[a] for a in m.keys() if m[a] not in ("", None)}}
        for k, m in r.cookies.items()
    },
    # Двоичный ответ (скачивание файла) сверяется по отпечатку
    "body": r.content.decode(errors="replace"),
    "sha256": __import__("hashlib").sha256(r.content).hexdigest(),
}))
"""


def _порт() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))

        return int(s.getsockname()[1])


#: Манифест сборки на время сверки, если фронт не собран (так в CI):
#: без него Django не соберёт страницу (ссылки на стили и скрипты)
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
            "",
            content_type or "application/octet-stream",
        ],
        input=body,
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


# ── Адрес, запрос, вход и сессия ────────────────────────────────────

#: Имя куки сессии: APP_NAME=SAVDEX (САЙТ)
СЕССИЯ = "savdex-session"


@contextmanager
def адрес(**_окружение: str) -> Iterator[str]:
    """
    Адрес сайта для проверок: http://127.0.0.1:<свободный порт>. Сервера
    за ним нет — запросы идут тестовым клиентом Django (из_django), адрес
    нужен для ссылок и APP_URL. Манифест сборки — подставной, если фронт
    не собран.
    """
    with _манифест():
        yield f"http://127.0.0.1:{_порт()}"


def открыть(
    сайт: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    **запрос: Any,
) -> dict[str, Any]:
    """Запрос к Django; ошибка сервера (5xx) — сразу провал с телом ответа."""
    ответ = из_django(сайт, path, cookies, headers, env, **запрос)
    assert ответ["status"] < 500, (ответ["status"], ответ["body"][:3000])

    return ответ


def кука(имя: str, значение: str) -> str:
    """Кука, как её ставит сайт (шифр Laravel), — в виде, в каком её шлёт браузер."""
    from urllib.parse import quote

    from savdex import laravel_session

    from .pg_admin import KEY

    return str(quote(laravel_session.encrypt_cookie(имя, значение, KEY), safe=""))


def расшифровать(имя: str, значение: str) -> str | None:
    from savdex import laravel_session

    from .pg_admin import KEY

    return laravel_session.cookie_value(имя, unquote(значение), [KEY])


def завести(
    sid: str, payload: dict[str, Any], *, last: int | None = None, user_id: int | None = None
) -> None:
    """Строка sessions, как её оставил сайт после прошлого запроса."""
    sql("delete from sessions where id = %s", [sid])
    sql(
        "insert into sessions (id, user_id, ip_address, user_agent, payload, last_activity) "
        "values (%s, %s, '127.0.0.1', 'x', %s, %s)",
        [
            sid,
            user_id,
            base64.b64encode(json.dumps(payload).encode()).decode(),
            last if last is not None else int(time.time()),
        ],
    )


def строка(sid: str) -> dict[str, Any] | None:
    """Строка sessions: payload без случайного _token, кто вошёл, адрес, браузер."""
    rows = sql(
        "select payload, user_id, ip_address, user_agent, last_activity "
        "from sessions where id = %s",
        [sid],
    )

    if not rows:
        return None

    payload, user_id, ip, agent, last = rows[0]
    text = base64.b64decode(payload).decode()
    token = json.loads(text).get("_token", "")

    assert abs(int(last) - time.time()) < 60

    return {
        # Порядок ключей и экранирование — как json_encode у PHP
        "payload": text.replace(json.dumps(token), '"<token>"'),
        "token": token,
        "user_id": user_id,
        "ip": ip,
        "agent": agent,
    }


def куки_ответа(ответ: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Куки ответа: значение расшифровано, атрибуты — в нижнем регистре."""
    итог = {}

    for имя, кука_ in ответ["cookies"].items():
        атрибуты = {k.lower(): v for k, v in кука_.items() if k.lower() not in ("value", "expires")}
        атрибуты = {
            k: (str(v).lower() if k == "samesite" else v if v is True else str(v))
            for k, v in атрибуты.items()
            if v not in (False, "")
        }
        итог[имя] = {"value": расшифровать(имя, кука_["value"]), **атрибуты}

    return итог


def сессия_из(ответ: dict[str, Any]) -> str:
    """Номер сессии из куки ответа."""
    sid = куки_ответа(ответ)[СЕССИЯ]["value"]
    assert sid is not None and re.fullmatch(r"[A-Za-z0-9]{40}", sid)

    return sid


#: Токен CSRF в сессиях, заведённых проверками
ТОКЕН_СЕССИИ = "t" * 40


def вход(uid: int, *, sid: str | None = None, **payload: Any) -> dict[str, str]:
    """
    Куки вошедшего пользователя: строка sessions с отметкой входа (ключ
    login_web_…, как у Laravel) — без формы входа. payload — что ещё
    лежит в сессии.
    """
    from savdex import laravel_session

    sid = sid or hashlib.sha1(f"вход-{uid}-{time.time_ns()}".encode()).hexdigest()
    завести(
        sid,
        {"_token": ТОКЕН_СЕССИИ, laravel_session.LOGIN_KEY: uid, **payload},
        user_id=uid,
    )

    return {СЕССИЯ: кука(СЕССИЯ, sid)}


def гостевая(сайт: str) -> dict[str, str]:
    """Куки гостя, которому сайт уже завёл сессию (первый заход на /login)."""
    ответ = открыть(сайт, "/login", headers={"X-Inertia": "true"})

    return {имя: значение["value"] for имя, значение in ответ["cookies"].items()}
