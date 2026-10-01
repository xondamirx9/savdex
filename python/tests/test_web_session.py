"""
Этап 5, шаг 1: страница сайта на Django ведёт сессию так же, как её
вёл Laravel (строка sessions, кука, формат payload).

Исходная сессия (строка sessions и кука) заводится перед запросом;
после ответа проверяются строка sessions (payload — без случайного
_token, как его пишет json_encode PHP) и куки ответа (расшифрованные
значения и атрибуты):

- гостю без куки заводится сессия, кука сессии и XSRF-TOKEN;
- одноразовое сообщение показывается и стирается (ageFlashData);
- язык из префикса — в сессию и в профиль (SetLocale);
- вход по «запомнить меня» — в сессию, сессия под новым номером,
  старая строка удалена (migrate);
- просроченная сессия — пустая, но с тем же номером;
- XHR-запрос не запоминает адрес (_previous.url).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import (  # noqa: F401 — общие помощники сессии берут отсюда и другие проверки
    СЕССИЯ,
    адрес,
    завести,
    кука,
    куки_ответа,
    открыть,
    пользователь,
    расшифровать,
    сессия_из,
    страница,
    строка,
)

pytestmark = нужна_база


АГЕНТ = {"User-Agent": "savdex-parity/1.0"}

#: Срок куки — SESSION_LIFETIME=120 минут (web_site.САЙТ)
СРОК = 7200


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def зайти(
    сайт: str,
    path: str,
    подготовить: Callable[[], object],
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Запрос к странице после подготовить(); ответ и строка sessions, на
    которую указывает кука ответа. Куки ответа — как у Laravel: сессия
    (HttpOnly) и XSRF-TOKEN с тем же _token, оба на SESSION_LIFETIME.
    """
    подготовить()
    ответ = открыть(сайт, path, cookies, {**АГЕНТ, **(headers or {})})
    куки = куки_ответа(ответ)

    assert set(куки) == {СЕССИЯ, "XSRF-TOKEN"}, куки

    for имя, httponly in ((СЕССИЯ, True), ("XSRF-TOKEN", False)):
        атрибуты = {k: v for k, v in куки[имя].items() if k not in ("value", "max-age")}
        ожидание = {"path": "/", "samesite": "lax", **({"httponly": True} if httponly else {})}
        assert атрибуты == ожидание, (имя, атрибуты)
        # Max-Age у Symfony — «срок минус сейчас»: на стыке секунд 7199
        assert abs(int(куки[имя]["max-age"]) - СРОК) <= 1, куки[имя]

    итог = строка(сессия_из(ответ))

    assert итог is not None
    # XSRF-TOKEN — тот же _token, что в сессии
    assert куки["XSRF-TOKEN"]["value"] == итог["token"]
    assert итог["ip"] == "127.0.0.1" and итог["agent"] == АГЕНТ["User-Agent"]

    return ответ, итог


def прежний(сайт: str, path: str, route: str) -> str:
    """_previous в payload: адрес — как его экранирует json_encode PHP."""
    url = (сайт + path).replace("/", "\\/")

    return f'"_previous":{{"url":"{url}","route":"{route}"}}'


ПУСТОЙ_FLASH = '"_flash":{"old":[],"new":[]}'


def test_гостю_заводится_сессия(сайт):
    ответ, итог = зайти(сайт, "/about", lambda: None)

    assert ответ["status"] == 200
    assert итог["payload"] == (
        '{"_token":"<token>",' + прежний(сайт, "/about", "about") + "," + ПУСТОЙ_FLASH + "}"
    )
    assert итог["user_id"] is None

    # Токен формы на странице — тот же, что в сессии
    assert f'<meta name="csrf-token" content="{итог["token"]}">' in ответ["body"]


def test_переход_xhr_не_запоминает_адрес(сайт):
    _, итог = зайти(сайт, "/contact", lambda: None, headers={"X-Requested-With": "XMLHttpRequest"})

    assert итог["payload"] == '{"_token":"<token>",' + ПУСТОЙ_FLASH + "}"


# ── Сессия вошедшего ────────────────────────────────────────────────


def test_сообщение_показывается_и_стирается(сайт):
    uid = пользователь("flash@savdex.uz")
    sid = "A" * 40
    исходная = {
        "_token": "t" * 40,
        laravel_session.LOGIN_KEY: uid,
        "_previous": {"url": сайт + "/cabinet", "route": "cabinet"},
        "success": "Сохранено",
        "_flash": {"old": ["success"], "new": []},
    }

    ответ, итог = зайти(
        сайт, "/about", lambda: завести(sid, исходная), cookies={СЕССИЯ: кука(СЕССИЯ, sid)}
    )

    assert сессия_из(ответ) == sid
    assert итог["token"] == "t" * 40
    assert страница(ответ["body"])["props"]["flash"]["success"] == "Сохранено"
    assert итог["payload"] == (
        f'{{"_token":"<token>","{laravel_session.LOGIN_KEY}":{uid},'
        + прежний(сайт, "/about", "about")
        + ","
        + ПУСТОЙ_FLASH
        + "}"
    )
    assert итог["user_id"] == uid


def test_язык_из_адреса_в_сессию_и_профиль(сайт):
    uid = пользователь("locale@savdex.uz")
    sid = "B" * 40

    def подготовить() -> None:
        sql("update users set locale = 'ru' where id = %s", [uid])
        завести(sid, {"_token": "t" * 40, laravel_session.LOGIN_KEY: uid})

    ответ, итог = зайти(сайт, "/uz/about", подготовить, cookies={СЕССИЯ: кука(СЕССИЯ, sid)})

    assert ответ["status"] == 200
    assert '"locale":"uz"' in итог["payload"]
    assert sql("select locale from users where id = %s", [uid]) == [("uz",)]


def test_запомнить_меня_переносит_сессию(сайт):
    uid = пользователь("remember@savdex.uz")
    sql("update users set remember_token = %s where id = %s", ["r" * 60, uid])
    sid = "C" * 40
    куки = {
        СЕССИЯ: кука(СЕССИЯ, sid),
        laravel_session.REMEMBER_COOKIE: кука(
            laravel_session.REMEMBER_COOKIE, f"{uid}|{'r' * 60}|hash"
        ),
    }

    ответ, итог = зайти(сайт, "/about", lambda: завести(sid, {"_token": "t" * 40}), cookies=куки)

    assert сессия_из(ответ) != sid
    assert sql("select count(*) from sessions where id = %s", [sid]) == [(0,)]
    assert итог["user_id"] == uid
    assert f'"{laravel_session.LOGIN_KEY}":{uid}' in итог["payload"]
    # Токен сессии тот же: migrate переносит её содержимое
    assert итог["token"] == "t" * 40


def test_просроченная_сессия_пустая_с_тем_же_номером(сайт):
    uid = пользователь("expired@savdex.uz")
    sid = "D" * 40
    старая = {"_token": "t" * 40, laravel_session.LOGIN_KEY: uid, "locale": "en"}

    ответ, итог = зайти(
        сайт,
        "/about",
        lambda: завести(sid, старая, last=int(time.time()) - 3 * 3600),
        cookies={СЕССИЯ: кука(СЕССИЯ, sid)},
    )

    assert сессия_из(ответ) == sid
    assert итог["token"] != "t" * 40
    assert итог["user_id"] is None and "locale" not in итог["payload"]
    assert итог["payload"] == (
        '{"_token":"<token>",' + прежний(сайт, "/about", "about") + "," + ПУСТОЙ_FLASH + "}"
    )


def test_битая_кука_новая_сессия(сайт):
    ответ, итог = зайти(сайт, "/contact", lambda: None, cookies={СЕССИЯ: "garbage"})

    assert ответ["status"] == 200
    assert итог["user_id"] is None
    assert итог["payload"] == (
        '{"_token":"<token>",' + прежний(сайт, "/contact", "contacts") + "," + ПУСТОЙ_FLASH + "}"
    )


@pytest.mark.parametrize(
    ("path", "статус", "начало", "прежний_адрес", "маршрут"),
    [
        # Адрес без префикса, параметры — в порядке getQueryString
        ("/uz/about?b=2&a=1", 200, '"locale":"uz",', "/about?a=1&b=2", "about"),
        # 404 изнутри маршрута — сессия всё равно пишется
        ("/news/nothing-here", 404, "", "/news/nothing-here", "news.show"),
        ("/catalog?q=%20x%20&page=2", 200, "", "/catalog?page=2&q=%20x%20", "catalog"),
    ],
)
def test_адрес_и_ошибка(сайт, path, статус, начало, прежний_адрес, маршрут):
    ответ, итог = зайти(сайт, path, lambda: None)

    assert ответ["status"] == статус
    assert итог["payload"] == (
        '{"_token":"<token>",'
        + начало
        + прежний(сайт, прежний_адрес, маршрут)
        + ","
        + ПУСТОЙ_FLASH
        + "}"
    )


def test_переход_на_запомненный_язык(сайт):
    """SetLocale уводит на /uz/…: ответ — переход, сессия пишется и тут."""
    sid = "E" * 40
    ответ, итог = зайти(
        сайт,
        "/contact?x=1",
        lambda: завести(sid, {"_token": "t" * 40, "locale": "uz"}),
        cookies={СЕССИЯ: кука(СЕССИЯ, sid)},
    )

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == сайт + "/uz/contact?x=1"
    assert сессия_из(ответ) == sid
    assert '"locale":"uz"' in итог["payload"]
    assert прежний(сайт, "/contact?x=1", "contacts") in итог["payload"]
