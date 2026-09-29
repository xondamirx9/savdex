"""
Вход и выход на Django неотличимы от Laravel: проверка ввода, единое
сообщение с остатком попыток, блокировка после пяти неудач, запрет для
заблокированного, пересчёт хеша пароля, «запомнить меня» (токен и кука),
метка последнего входа, url.intended, выданный пароль — на смену; выход —
сессия заново, токен «запомнить» — новый, кука — забыта. После входа у
сессии новый номер: он берётся из куки ответа.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import unquote

import pytest

from savdex import laravel_session

from .pg_admin import KEY, sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, inertia, учётка
from .test_web_session import СЕССИЯ, завести, кука, строка
from .web_site import ПАРОЛЬ, laravel, из_django, из_laravel

pytestmark = нужна_база

ПОЧТА = "login@savdex.uz"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel() as root:
        yield root


def пользователь(**поля: Any) -> int:
    uid = учётка(ПОЧТА, **{"status": "active", **поля})
    # Хеш стоимостью 4, как у тестовых учёток: вход пересчитает его в 12
    sql(
        "update users set remember_token = null, last_login_at = null, last_login_ip = null "
        "where id = %s",
        [uid],
    )

    return uid


def снимок() -> Any:
    return {
        "users": sql(
            "select email, password like '$2y$12$%%', remember_token is not null, "
            "last_login_at is not null, last_login_ip from users where email = %s",
            [ПОЧТА],
        ),
        "attempts": sql(
            "select email, ip, successful, user_agent_hash is not null "
            "from login_attempts order by id"
        ),
        "journal": [
            (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
            for a, s, label, ch in sql(
                "select action, section, subject_label, changes::text from admin_actions "
                "order by id"
            )
        ],
    }


def _сессия_из_ответа(ответ: dict[str, Any]) -> dict[str, Any] | None:
    """Номер сессии из куки ответа (расшифрованной) — и её строка."""
    кука_сессии = ответ["cookies"].get(СЕССИЯ)

    if кука_сессии is None:
        return None

    sid = laravel_session.cookie_value(СЕССИЯ, unquote(кука_сессии["value"]), [KEY])

    return строка(sid) if sid else None


def вход(
    сайт: str,
    path: str,
    подготовка: Callable[[], None],
    *,
    body: dict[str, Any],
    payload: dict[str, Any] | None = None,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Одна и та же форма — Django и Laravel; ответы, сессии и база совпадают."""
    стороны = {}

    for имя, сторона in (("django", из_django), ("laravel", из_laravel)):
        подготовка()
        завести(SID, {"_token": ТОКЕН, **(payload or {})})
        ответ = сторона(
            сайт,
            path,
            {СЕССИЯ: кука(СЕССИЯ, SID), **(cookies or {})},
            {**inertia(), "Referer": сайт + "/login", "User-Agent": "savdex-parity"},
            method="POST",
            body=json.dumps(body),
            content_type="application/json",
        )
        сессия = _сессия_из_ответа(ответ)
        стороны[имя] = {
            "status": ответ["status"],
            "location": ответ["headers"].get("location"),
            "cookies": sorted(ответ["cookies"]),
            "remember_value": _remember(ответ),
            "session": None
            if сессия is None
            else {"payload": сессия["payload"], "user_id": сессия["user_id"]},
            "same_sid": сессия is not None and строка(SID) is not None,
            "db": снимок(),
        }

    assert стороны["django"] == стороны["laravel"], json.dumps(
        стороны, ensure_ascii=False, default=str
    )

    return стороны["django"]


def _remember(ответ: dict[str, Any]) -> str | None:
    """Кука «запомнить меня»: номер|токен|хеш — без самих токена и хеша."""
    имя = laravel_session.REMEMBER_COOKIE
    raw = ответ["cookies"].get(имя)

    if raw is None:
        return None

    value = laravel_session.cookie_value(имя, unquote(raw["value"]), [KEY])

    if not value:
        return "<пусто>"

    uid, token, hashed = value.split("|", 2)
    row = sql("select remember_token, password from users where id = %s", [int(uid)])[0]

    import hashlib
    import hmac

    from .pg_admin import APP_KEY

    ожидание = hmac.new(APP_KEY.encode(), row[1].encode(), hashlib.sha256).hexdigest()

    return f"{uid}|{token == row[0]}|{hashed == ожидание}"


def сброс(*, неудач: int = 0, **поля: Any) -> Callable[[], None]:
    def run() -> None:
        sql("delete from login_attempts")
        sql("delete from admin_actions")
        пользователь(**поля)

        for _ in range(неудач):
            sql(
                "insert into login_attempts (email, ip, successful, created_at) "
                "values (%s, '127.0.0.1', false, now() - interval '1 minute')",
                [ПОЧТА],
            )

    return run


ВЕРНО = {"email": ПОЧТА, "password": ПАРОЛЬ}


@pytest.mark.parametrize(
    ("body", "подготовка"),
    [
        (ВЕРНО, {}),
        ({**ВЕРНО, "email": "  Login@SAVDEX.uz "}, {}),
        ({**ВЕРНО, "remember": True}, {}),
        ({**ВЕРНО, "remember": "on"}, {"is_admin": True}),
        (ВЕРНО, {"must_change_password": True}),
        (ВЕРНО, {"status": "blocked"}),
        ({**ВЕРНО, "password": "wrong"}, {}),
        ({**ВЕРНО, "password": "wrong"}, {"неудач": 3}),
        ({**ВЕРНО, "password": "wrong"}, {"неудач": 4}),
        (ВЕРНО, {"неудач": 5}),
        ({"email": "nobody@savdex.uz", "password": "x"}, {}),
        ({"email": "не почта", "password": ""}, {}),
        ({}, {}),
    ],
)
def test_вход(сайт, body, подготовка):
    итог = вход(сайт, "/login", сброс(**подготовка), body=body)

    if body == ВЕРНО and not подготовка:
        assert итог["status"] == 302 and итог["location"].endswith("/cabinet")


def test_вход_туда_куда_шёл(сайт):
    итог = вход(
        сайт,
        "/en/login",
        сброс(),
        body=ВЕРНО,
        payload={"url.intended": "http://savdex.test/cabinet/listings?status=active"},
    )

    assert итог["location"] == "http://savdex.test/cabinet/listings?status=active"


def test_вошедшему_форма_не_нужна(сайт):
    uid = пользователь()
    вход(сайт, "/login", сброс(), body=ВЕРНО, payload={laravel_session.LOGIN_KEY: uid})


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("remember", [False, True])
def test_выход(сайт, admin, remember):
    uid = пользователь()

    def подготовка() -> None:
        сброс(is_admin=admin)()
        sql(
            "update users set remember_token = %s where id = %s",
            ["r" * 60 if remember else None, uid],
        )

    cookies = {}

    if remember:
        cookies[laravel_session.REMEMBER_COOKIE] = кука(
            laravel_session.REMEMBER_COOKIE, f"{uid}|{'r' * 60}|x"
        )

    итог = вход(
        сайт,
        "/logout",
        подготовка,
        body={},
        payload={laravel_session.LOGIN_KEY: uid},
        cookies=cookies,
    )

    assert итог["status"] == 302
