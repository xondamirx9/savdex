"""
Вход и выход на Django: проверка ввода, единое
сообщение с остатком попыток, блокировка после пяти неудач, запрет для
заблокированного, пересчёт хеша пароля, «запомнить меня» (токен и кука),
метка последнего входа, url.intended, выданный пароль — на смену; выход —
сессия заново, токен «запомнить» — новый, кука — забыта. После входа у
сессии новый номер: он берётся из куки ответа.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
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
from .web_site import ПАРОЛЬ, адрес, открыть

pytestmark = нужна_база

ПОЧТА = "login@savdex.uz"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
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
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Форма Django: ответ, новая сессия из куки ответа, кука «запомнить» и база."""
    подготовка()
    завести(SID, {"_token": ТОКЕН, **(payload or {})})
    ответ = открыть(
        сайт,
        path,
        {СЕССИЯ: кука(СЕССИЯ, SID), **(cookies or {})},
        {**inertia(), "Referer": сайт + "/login", "User-Agent": "savdex-parity"},
        method="POST",
        env=env,
        body=json.dumps(body),
        content_type="application/json",
    )
    сессия = _сессия_из_ответа(ответ)

    return {
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

        # Полторы минуты назад, а не минуту: до разблокировки 13,5 минуты,
        # и «через 14 мин.» не зависит от того, как быстро пришёл запрос.
        # Ровно минута давала 840 с плюс доли секунды (база округляет
        # время до секунды, сайт — отбрасывает) — на быстром CI «15 мин.»
        for _ in range(неудач):
            sql(
                "insert into login_attempts (email, ip, successful, created_at) "
                "values (%s, '127.0.0.1', false, now() - interval '90 seconds')",
                [ПОЧТА],
            )

    return run


ВЕРНО = {"email": ПОЧТА, "password": ПАРОЛЬ}
НЕВЕРНО = "Неверная почта или пароль. Осталось попыток: "
МНОГО = "Слишком много попыток входа. Попробуйте через "


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    """Ошибки проверки в сессии после ответа."""
    payload = json.loads(итог["session"]["payload"])

    return dict(payload.get("errors", {}).get("default", {}).get("messages", {}))


def вошёл(итог: dict[str, Any], uid: int) -> bool:
    """Сессия после ответа — новая (номер из куки ответа) и с отметкой входа."""
    payload = json.loads(итог["session"]["payload"])

    return (
        итог["session"]["user_id"] == uid
        and payload.get(laravel_session.LOGIN_KEY) == uid
        and not итог["same_sid"]
    )


@pytest.mark.parametrize(
    ("body", "подготовка", "ожидание"),
    [
        (ВЕРНО, {}, {"куда": "/cabinet"}),
        # Почта — без пробелов вокруг и без учёта регистра
        ({**ВЕРНО, "email": "  Login@SAVDEX.uz "}, {}, {"куда": "/cabinet"}),
        ({**ВЕРНО, "remember": True}, {}, {"куда": "/cabinet", "запомнить": True}),
        (
            {**ВЕРНО, "remember": "on"},
            {"is_admin": True},
            {"куда": "/cabinet", "запомнить": True, "журнал": 2},
        ),
        # Выданный пароль — сразу на смену
        (ВЕРНО, {"must_change_password": True}, {"куда": "/password/change"}),
        (ВЕРНО, {"status": "blocked"}, {"email": "Учётная запись заблокирована"}),
        ({**ВЕРНО, "password": "wrong"}, {}, {"email": НЕВЕРНО + "4 из 5"}),
        ({**ВЕРНО, "password": "wrong"}, {"неудач": 3}, {"email": НЕВЕРНО + "1 из 5"}),
        ({**ВЕРНО, "password": "wrong"}, {"неудач": 4}, {"email": МНОГО + "15 мин."}),
        # Пять неудач за 15 минут — и верный пароль не пускает
        (ВЕРНО, {"неудач": 5}, {"email": МНОГО + "14 мин."}),
        ({"email": "nobody@savdex.uz", "password": "x"}, {}, {"email": НЕВЕРНО + "4 из 5"}),
        (
            {"email": "не почта", "password": ""},
            {},
            {"email": "Введите почту или номер телефона", "password": "Введите пароль"},
        ),
        ({}, {}, {"email": "Введите почту или телефон", "password": "Введите пароль"}),
    ],
)
def test_вход(сайт, body, подготовка, ожидание):
    итог = вход(сайт, "/login", сброс(**подготовка), body=body)
    [(uid,)] = sql("select id from users where email = %s", [ПОЧТА])
    [(_, _, remember, last_login, ip)] = итог["db"]["users"]
    попытки = итог["db"]["attempts"]

    assert итог["status"] == 302

    if "куда" in ожидание:
        assert итог["location"] == f"{сайт}{ожидание['куда']}"
        assert вошёл(итог, uid) and not ошибки(итог)
        # Хеш пароля пересчитан со стоимостью 12, вход отмечен
        assert итог["db"]["users"][0][1] is True
        assert (last_login, ip) == (True, "127.0.0.1")
        assert попытки == [(ПОЧТА, "127.0.0.1", True, True)]
        запомнить = ожидание.get("запомнить", False)
        assert remember is запомнить
        assert итог["remember_value"] == (f"{uid}|True|True" if запомнить else None)
        assert len(итог["db"]["journal"]) == ожидание.get("журнал", 0)
    else:
        assert итог["location"] == f"{сайт}/login"
        assert итог["session"]["user_id"] is None
        assert (last_login, ip, remember) == (False, None, False)
        assert итог["db"]["journal"] == []

        найдено = ошибки(итог)
        assert sorted(найдено) == sorted(k for k in ожидание if k in ("email", "password"))
        for поле in найдено:
            assert найдено[поле][0].startswith(ожидание[поле]), найдено[поле]

        неудач = подготовка.get("неудач", 0)
        if body.get("password") == "wrong" or body.get("email") == "nobody@savdex.uz":
            # Неверная пара записана — с тем адресом, что ввели
            assert len(попытки) == неудач + 1
            assert попытки[-1] == (body["email"], "127.0.0.1", False, True)
        else:
            # Заблокированный, ошибка ввода и перебор — без новой попытки
            assert len(попытки) == неудач

        if подготовка.get("status") == "blocked":
            # Сессия заблокированного — заново, без входа
            assert not итог["same_sid"]


ПО_ТЕЛЕФОНУ = {"phone": "+998 90 111-22-33", "phone_verified_at": "2026-09-01 10:00:00"}


@pytest.mark.parametrize(
    ("номер", "поля", "пускает", "попытка"),
    [
        # Подтверждённый номер — вместо почты: целиком, в любом виде
        ("+998901112233", ПО_ТЕЛЕФОНУ, True, ПОЧТА),
        ("+998 (90) 111 22 33", ПО_ТЕЛЕФОНУ, True, ПОЧТА),
        # Без кода страны — по концу номера, если такая учётка одна
        ("90 111 22 33", ПО_ТЕЛЕФОНУ, True, ПОЧТА),
        # Номер не подтверждён — вписать можно любой, не пускает
        ("+998901112233", {**ПО_ТЕЛЕФОНУ, "phone_verified_at": None}, False, "phone:998901112233"),
        ("+998901110000", ПО_ТЕЛЕФОНУ, False, "phone:998901110000"),
    ],
)
def test_вход_по_телефону(сайт, номер, поля, пускает, попытка):
    итог = вход(сайт, "/login", сброс(**поля), body={"email": номер, "password": ПАРОЛЬ})
    [(uid,)] = sql("select id from users where email = %s", [ПОЧТА])

    assert итог["status"] == 302
    # Попытка записана на учётку номера, иначе — на сам номер
    assert итог["db"]["attempts"] == [(попытка, "127.0.0.1", пускает, True)]

    if пускает:
        assert итог["location"] == f"{сайт}/cabinet"
        assert вошёл(итог, uid)
    else:
        assert итог["location"] == f"{сайт}/login"
        assert ошибки(итог)["email"][0].startswith(НЕВЕРНО)


@pytest.mark.parametrize(
    ("сохранено", "ожидание"),
    [
        ("<сайт>/cabinet/listings?status=active", "<сайт>/en/cabinet/listings?status=active"),
        ("/cabinet/listings", "<сайт>/en/cabinet/listings"),
        # Чужой адрес (url.intended пишется и из Referer) — в кабинет
        ("https://evil.example/cabinet", "<сайт>/en/cabinet"),
        ("//evil.example/cabinet", "<сайт>/en/cabinet"),
        ("/\\evil.example", "<сайт>/en/cabinet"),
        ("<сайт>.evil.example/cabinet", "<сайт>/en/cabinet"),
        ("<сайт>@evil.example/cabinet", "<сайт>/en/cabinet"),
        ("javascript:alert(1)", "<сайт>/en/cabinet"),
    ],
)
def test_вход_туда_куда_шёл(сайт, сохранено, ожидание):
    итог = вход(
        сайт,
        "/en/login",
        сброс(),
        body=ВЕРНО,
        payload={"url.intended": сохранено.replace("<сайт>", сайт)},
    )

    assert итог["location"] == ожидание.replace("<сайт>", сайт)
    [(uid,)] = sql("select id from users where email = %s", [ПОЧТА])
    assert вошёл(итог, uid)
    # Язык адреса формы остаётся в сессии
    assert json.loads(итог["session"]["payload"])["locale"] == "en"


def test_вошедшему_форма_не_нужна(сайт):
    uid = пользователь()
    итог = вход(сайт, "/login", сброс(), body=ВЕРНО, payload={laravel_session.LOGIN_KEY: uid})

    # Сразу на главную: та же сессия, вход не повторяется и не записывается
    assert (итог["status"], итог["location"]) == (302, сайт)
    assert итог["same_sid"] and итог["session"]["user_id"] == uid
    assert итог["db"]["attempts"] == [] and итог["db"]["users"][0][3] is False


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
    payload = json.loads(итог["session"]["payload"])

    # На главную с новой сессией без входа
    assert (итог["status"], итог["location"]) == (302, сайт)
    assert not итог["same_sid"] and итог["session"]["user_id"] is None
    assert laravel_session.LOGIN_KEY not in payload and payload["_token"] == "<token>"
    # Вход в админку Django — та же учётка: его кука тоже стёрта
    assert "savdex_py_admin" in итог["cookies"]

    if remember:
        # Кука «запомнить» забыта, токен в базе — новый
        assert итог["remember_value"] == "<пусто>"
        [(token,)] = sql("select remember_token from users where id = %s", [uid])
        assert token and token != "r" * 60
    else:
        assert итог["remember_value"] is None
        assert итог["db"]["users"][0][2] is False

    # Новый токен «запомнить» у администратора — в журнале
    assert len(итог["db"]["journal"]) == (1 if admin and remember else 0)


#: Вход по капче: в тестах она выключена (pg_admin.ОКРУЖЕНИЕ)
КАПЧА = {"CAPTCHA_ENABLED": "true"}
КАПЧУ = "К этой учётной записи было много неудачных попыток входа. "


def перебор(неудач: int = 20, *, своих: int = 0) -> Callable[[], None]:
    """Неудачи по учётке с чужих адресов (у каждого меньше пяти) и со своего."""

    def run() -> None:
        сброс(неудач=своих)()

        for n in range(неудач):
            sql(
                "insert into login_attempts (email, ip, successful, created_at) "
                "values (%s, %s, false, now() - interval '1 minute')",
                [ПОЧТА, f"198.51.100.{n + 1}"],
            )

    return run


def пропуск(token: str = "pass-1") -> dict[str, Any]:
    """Пройденное окно «Я не робот» в сессии (captcha.check)."""
    import time

    return {"captcha_pass": {"login": {"token": token, "expires": int(time.time()) + 600}}}


@pytest.mark.parametrize("captcha", ["", "чужой"])
def test_перебор_с_разных_адресов_просит_капчу(сайт, captcha):
    """
    Двадцать неудач по учётке со всех адресов не запирают её, а требуют
    капчу: без пропуска не пускает даже с верным паролем, пароль не
    проверяется, попытка не засчитывается.
    """
    итог = вход(
        сайт,
        "/login",
        перебор(),
        body={**ВЕРНО, "captcha": captcha},
        payload=пропуск(),
        env=КАПЧА,
    )

    assert итог["location"] == f"{сайт}/login"
    assert итог["session"]["user_id"] is None
    assert list(ошибки(итог)) == ["captcha"]
    assert ошибки(итог)["captcha"][0].startswith(КАПЧУ if captcha == "" else "Проверка")
    assert len(итог["db"]["attempts"]) == 20


def test_хозяин_входит_через_капчу(сайт):
    итог = вход(
        сайт,
        "/login",
        перебор(),
        body={**ВЕРНО, "captcha": "pass-1"},
        payload=пропуск(),
        env=КАПЧА,
    )

    assert итог["location"] == f"{сайт}/cabinet"
    assert вошёл(итог, sql("select id from users where email = %s", [ПОЧТА])[0][0])
    # Пропуск разовый
    assert not json.loads(итог["session"]["payload"]).get("captcha_pass")


def test_неверный_пароль_через_капчу_засчитан(сайт):
    итог = вход(
        сайт,
        "/login",
        перебор(),
        body={**ВЕРНО, "password": "wrong", "captcha": "pass-1"},
        payload=пропуск(),
        env=КАПЧА,
    )

    assert ошибки(итог)["email"][0].startswith(НЕВЕРНО)
    assert ошибки(итог)["captcha"][0].startswith(КАПЧУ)
    assert len(итог["db"]["attempts"]) == 21


def test_двадцатая_неудача_показывает_капчу(сайт):
    итог = вход(сайт, "/login", перебор(19), body={**ВЕРНО, "password": "wrong"}, env=КАПЧА)

    assert ошибки(итог)["email"][0].startswith(НЕВЕРНО)
    assert ошибки(итог)["captcha"][0].startswith(КАПЧУ)


def test_капча_выключена_учётку_не_запирает(сайт):
    итог = вход(сайт, "/login", перебор(), body=ВЕРНО)

    assert итог["location"] == f"{сайт}/cabinet"


def test_адрес_перебора_заперт_и_с_капчей(сайт):
    """Свои пять неудач с этого адреса — замок, капча его не снимает."""

    итог = вход(
        сайт,
        "/login",
        перебор(своих=5),
        body={**ВЕРНО, "captcha": "pass-1"},
        payload=пропуск(),
        env=КАПЧА,
    )

    assert итог["session"]["user_id"] is None
    assert ошибки(итог)["email"][0].startswith(МНОГО)


def test_неудачи_с_разных_адресов_ниже_порога_не_мешают(сайт):
    def подготовка() -> None:
        сброс()()

        for n in range(19):
            sql(
                "insert into login_attempts (email, ip, successful, created_at) "
                "values (%s, %s, false, now() - interval '1 minute')",
                [ПОЧТА, f"198.51.100.{n + 1}"],
            )

    итог = вход(сайт, "/login", подготовка, body=ВЕРНО)

    assert итог["location"] == f"{сайт}/cabinet"
