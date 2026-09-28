"""
Этап 5, шаг 1: страница сайта на Django ведёт сессию Laravel, как он сам.

Одна и та же исходная сессия (строка sessions и куки) — перед каждой
стороной; после ответа сравниваются строка sessions байт в байт (кроме
случайного _token и времени) и куки ответа (расшифрованные значения и
атрибуты):

- гостю без куки заводится сессия, кука сессии и XSRF-TOKEN;
- одноразовое сообщение показывается и стирается (ageFlashData);
- язык из префикса — в сессию и в профиль (SetLocale);
- вход по «запомнить меня» — в сессию, сессия под новым номером,
  старая строка удалена (migrate);
- просроченная сессия — пустая, но с тем же номером;
- XHR-запрос не запоминает адрес (_previous.url).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote, unquote

import pytest

from savdex import laravel_session

from .pg_admin import KEY, sql, нужна_база, свежая_база
from .web_site import laravel, пользователь, сверить, страница

pytestmark = нужна_база

#: Имя куки сессии: APP_NAME=SAVDEX (web_site.САЙТ)
СЕССИЯ = "savdex-session"

АГЕНТ = {"User-Agent": "savdex-parity/1.0"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel() as root:
        yield root


def кука(имя: str, значение: str) -> str:
    """Кука, как её поставил бы Laravel, — в виде, в каком её шлёт браузер."""
    return quote(laravel_session.encrypt_cookie(имя, значение, KEY), safe="")


def расшифровать(имя: str, значение: str) -> str | None:
    return laravel_session.cookie_value(имя, unquote(значение), [KEY])


def строка(sid: str) -> dict[str, Any] | None:
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


def завести(sid: str, payload: dict[str, Any], *, last: int | None = None) -> None:
    """Строка sessions, как её оставил Laravel после прошлого запроса."""
    sql("delete from sessions where id = %s", [sid])
    sql(
        "insert into sessions (id, user_id, ip_address, user_agent, payload, last_activity) "
        "values (%s, null, '127.0.0.1', 'x', %s, %s)",
        [
            sid,
            base64.b64encode(json.dumps(payload).encode()).decode(),
            last if last is not None else int(time.time()),
        ],
    )


def куки_ответа(ответ: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Куки ответа: значение расшифровано, атрибуты — в нижнем регистре."""
    итог = {}

    for имя, кука_ in ответ["cookies"].items():
        атрибуты = {k.lower(): v for k, v in кука_.items() if k.lower() not in ("value", "expires")}
        атрибуты = {
            k: (str(v).lower() if k == "samesite" else v if v is True else str(v))
            for k, v in атрибуты.items()
            # Флаги: у Django — True, у Symfony — присутствие
            if v not in (False, "")
        }
        итог[имя] = {"value": расшифровать(имя, кука_["value"]), **атрибуты}

    return итог


def сессия_из(ответ: dict[str, Any]) -> str:
    sid = куки_ответа(ответ)[СЕССИЯ]["value"]
    assert sid is not None and re.fullmatch(r"[A-Za-z0-9]{40}", sid)

    return sid


def по_сторонам(
    сайт: str,
    path: str,
    подготовить: Any,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, tuple[dict[str, Any], dict[str, Any] | None]]:
    """
    Django, затем Laravel — каждый после подготовить(); страница сверяется
    (web_site.сверить), а после каждой стороны снимается строка сессии.
    """
    снимки: list[dict[str, Any] | None] = []

    def после(ответ: dict[str, Any]) -> None:
        sid = куки_ответа(ответ).get(СЕССИЯ, {}).get("value")
        снимки.append(строка(sid) if sid else None)

    д, л = сверить(
        сайт,
        path,
        cookies,
        {**АГЕНТ, **(headers or {})},
        перед=подготовить,
        после=после,
    )

    return {"django": (д, снимки[0]), "laravel": (л, снимки[1])}


def одинаково(стороны: dict[str, tuple[dict[str, Any], dict[str, Any] | None]]) -> dict[str, Any]:
    (д, строка_д), (л, строка_л) = стороны["django"], стороны["laravel"]
    куки_д, куки_л = куки_ответа(д), куки_ответа(л)

    assert set(куки_д) == set(куки_л) == {СЕССИЯ, "XSRF-TOKEN"}, (куки_д, куки_л)

    for имя in (СЕССИЯ, "XSRF-TOKEN"):
        без_значения = [{k: v for k, v in к[имя].items() if k != "value"} for к in (куки_д, куки_л)]
        assert без_значения[0] == без_значения[1], имя

    assert строка_д is not None and строка_л is not None

    for сторона, строка_, куки in (("django", строка_д, куки_д), ("laravel", строка_л, куки_л)):
        # XSRF-TOKEN — тот же _token, что в сессии
        assert куки["XSRF-TOKEN"]["value"] == строка_["token"], сторона

    for ключ in ("payload", "user_id", "ip", "agent"):
        assert строка_д[ключ] == строка_л[ключ], (ключ, строка_д[ключ], строка_л[ключ])

    return строка_д


def test_гостю_заводится_сессия(сайт):
    стороны = по_сторонам(сайт, "/about", lambda: None)
    итог = одинаково(стороны)

    assert '"_previous":{"url":' in итог["payload"] and '"route":"about"' in итог["payload"]
    assert итог["user_id"] is None

    # Токен формы на странице — тот же, что в сессии
    д, строка_д = стороны["django"]
    assert f'<meta name="csrf-token" content="{строка_д["token"]}">' in д["body"]


def test_переход_xhr_не_запоминает_адрес(сайт):
    итог = одинаково(
        по_сторонам(сайт, "/contact", lambda: None, headers={"X-Requested-With": "XMLHttpRequest"})
    )

    assert "_previous" not in итог["payload"]


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

    стороны = по_сторонам(
        сайт, "/about", lambda: завести(sid, исходная), cookies={СЕССИЯ: кука(СЕССИЯ, sid)}
    )
    итог = одинаково(стороны)

    assert сессия_из(стороны["django"][0]) == sid
    assert страница(стороны["django"][0]["body"])["props"]["flash"]["success"] == "Сохранено"
    assert "Сохранено" not in итог["payload"] and '"old":[]' in итог["payload"]
    assert итог["user_id"] == uid


def test_язык_из_адреса_в_сессию_и_профиль(сайт):
    uid = пользователь("locale@savdex.uz")
    sid = "B" * 40

    def подготовить() -> None:
        sql("update users set locale = 'ru' where id = %s", [uid])
        завести(sid, {"_token": "t" * 40, laravel_session.LOGIN_KEY: uid})

    итог = одинаково(
        по_сторонам(сайт, "/uz/about", подготовить, cookies={СЕССИЯ: кука(СЕССИЯ, sid)})
    )

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

    стороны = по_сторонам(сайт, "/about", lambda: завести(sid, {"_token": "t" * 40}), cookies=куки)
    итог = одинаково(стороны)

    for ответ, _ in стороны.values():
        assert сессия_из(ответ) != sid

    assert sql("select count(*) from sessions where id = %s", [sid]) == [(0,)]
    assert итог["user_id"] == uid
    assert f'"{laravel_session.LOGIN_KEY}":{uid}' in итог["payload"]


def test_просроченная_сессия_пустая_с_тем_же_номером(сайт):
    uid = пользователь("expired@savdex.uz")
    sid = "D" * 40
    старая = {"_token": "t" * 40, laravel_session.LOGIN_KEY: uid, "locale": "en"}

    стороны = по_сторонам(
        сайт,
        "/about",
        lambda: завести(sid, старая, last=int(time.time()) - 3 * 3600),
        cookies={СЕССИЯ: кука(СЕССИЯ, sid)},
    )
    итог = одинаково(стороны)

    for ответ, строка_ in стороны.values():
        assert сессия_из(ответ) == sid
        assert строка_ is not None and строка_["token"] != "t" * 40

    assert итог["user_id"] is None and "locale" not in итог["payload"]


def test_битая_кука_новая_сессия(сайт):
    стороны = по_сторонам(сайт, "/contact", lambda: None, cookies={СЕССИЯ: "garbage"})
    одинаково(стороны)


@pytest.mark.parametrize(
    "path",
    [
        # Адрес без префикса, параметры — в порядке getQueryString
        "/uz/about?b=2&a=1",
        # 404 изнутри маршрута — сессия всё равно пишется
        "/news/nothing-here",
        "/catalog?q=%20x%20&page=2",
    ],
)
def test_адрес_и_ошибка(сайт, path):
    одинаково(по_сторонам(сайт, path, lambda: None))


def test_переход_на_запомненный_язык(сайт):
    """SetLocale уводит на /uz/…: ответ — переход, сессия пишется и тут."""
    sid = "E" * 40
    стороны = по_сторонам(
        сайт,
        "/contact?x=1",
        lambda: завести(sid, {"_token": "t" * 40, "locale": "uz"}),
        cookies={СЕССИЯ: кука(СЕССИЯ, sid)},
    )
    итог = одинаково(стороны)

    assert стороны["django"][0]["status"] == 302
    assert '"url":"http:\\/\\/' in итог["payload"] and 'contact?x=1"' in итог["payload"]
