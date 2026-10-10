"""
Шаг 69: первые шаги регистрации на Django —
почта (POST /register/email), код из письма (/register/code, POST
/register/code/resend) и страница анкеты (/register/details).

Проверяются ответ, сессия после него, запись кода в файловом кэше (адрес
хешем, попытки) и письмо с кодом (код скрыт — он случайный, но сходится
с хешем в кэше).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex.web import register_code

from .factories import категория, узбекистан
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить
from .test_web_register_actions import (
    ЖУРНАЛ_DJANGO,
    КЭШ,
    ОКРУЖЕНИЕ_ПОЧТЫ,
    _без_изменчивого,
    _письма,
    _разбор,
)
from .web_site import адрес, страница

pytestmark = нужна_база

АДРЕС = "aziz@reg.savdex.uz"
КОД = "123456"
ОКРУЖЕНИЕ_DJANGO = {**ОКРУЖЕНИЕ_ПОЧТЫ, "MAIL_LOG_PATH": str(ЖУРНАЛ_DJANGO)}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    категория(slug="cement", parent_id=None)
    категория(slug="off", parent_id=None, is_active=False)
    # Страны первого шага: Китай — с галочкой «Регистрация без кода»
    узбекистан()
    sql(
        "insert into countries (code, phone_code, currency_code, is_active, email_code_optional, "
        "created_at, updated_at) values ('cn', '86', 'CNY', true, true, now(), now())"
    )

    with адрес(**ОКРУЖЕНИЕ_ПОЧТЫ) as root:
        yield root


def _кэш(email: str) -> Any:
    """Запись кода в файловом кэше Laravel — как есть."""
    from savdex.web.currency import unserialize

    ключ = register_code._key(email)
    файл = hashlib.sha1(ключ.encode()).hexdigest()
    путь = КЭШ / файл[:2] / файл[2:4] / файл

    return unserialize(путь.read_bytes()[10:]) if путь.exists() else None


def подготовка(код: str | None = None, попытки: int = 0) -> Callable[[], None]:
    """Кэш с нуля (счётчики частоты тоже), журналы писем пустые, код — заданный."""

    def подготовить() -> None:
        import os

        from savdex import laravel_cache
        from savdex.web import guard

        shutil.rmtree(КЭШ, ignore_errors=True)
        ЖУРНАЛ_DJANGO.parent.mkdir(parents=True, exist_ok=True)
        ЖУРНАЛ_DJANGO.write_text("")

        if код is not None:
            os.environ["CACHE_STORE"] = "file"
            laravel_cache.put(
                register_code._key(АДРЕС), {"hash": guard.make(код), "attempts": попытки}, 900
            )

    return подготовить


def снимок(сайт: str) -> Callable[[], Any]:
    """Письма (код скрыт) и запись кода: попытки и сходится ли код письма с хешем."""

    def снять() -> Any:
        import re

        import bcrypt

        письма = [_разбор(п) for п in _письма(ЖУРНАЛ_DJANGO.read_text())]
        запись = _кэш(АДРЕС)
        код = None

        if письма:
            код = re.search(r"# (\d{6})", письма[0]["text"]).group(1)  # type: ignore[union-attr]

        return {
            "mail": [{k: _без_изменчивого(v, сайт) for k, v in п.items()} for п in письма],
            "entry": None
            if not isinstance(запись, dict)
            else {
                "attempts": запись["attempts"],
                "from_mail": код is not None
                and bcrypt.checkpw(код.encode(), ("$2b$" + запись["hash"][4:]).encode()),
            },
        }

    return снять


def _страна(code: str = "uz") -> int:
    return int(sql("select id from countries where code = %s", [code])[0][0])


def шаг(
    сайт: str,
    path: str,
    *,
    данные: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    method: str = "POST",
    код: str | None = None,
    попытки: int = 0,
) -> dict[str, Any]:
    # Первый шаг — страна и почта: страна нужна всегда
    if method == "POST" and path.endswith("/register/email") and body and "email" in body:
        body = {"country_id": _страна(), **body}

    return отправить(
        сайт,
        path,
        подготовка(код, попытки),
        снимок(сайт),
        данные=данные,
        body=body or {},
        method=method,
        env=ОКРУЖЕНИЕ_DJANGO,
        # Страница — обычным запросом браузера: у Inertia на GET своя
        # проверка версии сборки (409)
        headers=inertia(Referer=сайт + "/register")
        if method == "POST"
        else {"Referer": сайт + "/register", "User-Agent": "savdex-parity"},
    )


def _ждёт(email: str = АДРЕС) -> dict[str, Any]:
    return {"register": {"email": email}}


# ── Шаг 1: почта ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("email", "уходит"),
    [
        (" Aziz@Reg.Savdex.UZ ", True),
        ("aziz.reg.savdex.uz", False),
        ("aziz@reg", False),
        ("aziz(x)@reg.savdex.uz", False),
        ("", False),
        (None, False),
    ],
)
def test_почта(сайт, email, уходит):
    итог = шаг(сайт, "/register/email", body={} if email is None else {"email": email})

    if уходит:
        assert итог["ответ"]["headers"]["location"].endswith("/register/code")
        assert len(итог["база"]["mail"]) == 1 and итог["база"]["entry"] == {
            "attempts": 0,
            "from_mail": True,
        }
        assert json.loads(итог["сессия"]["payload"])["register"] == {
            "email": "aziz@reg.savdex.uz",
            "country_id": _страна(),
        }
        # ТЗ-03: событие GA4 ждёт следующую страницу — в сессии, без почты
        assert '"name":"sign_up_start","params":{"plan_param":"free"}' in итог["сессия"]["payload"]
    else:
        assert итог["база"] == {"mail": [], "entry": None}


@pytest.mark.parametrize(
    ("path", "lang", "тема", "вводная"),
    [
        ("/register/email", "ru", "Код подтверждения <код> — SAVDEX", "Ваш код для регистрации"),
        (
            "/en/register/email",
            "en",
            "Confirmation code <код> — SAVDEX",
            "Your SAVDEX registration",
        ),
        ("/uz/register/email", "uz", "Tasdiqlash kodi <код> — SAVDEX", "SAVDEX’da ro‘yxatdan"),
        ("/zh/register/email", "zh", "验证码 <код> — SAVDEX", "您的 SAVDEX 注册验证码"),
    ],
)
def test_письмо_на_языке_страницы(сайт, path, lang, тема, вводная):
    """Письмо с кодом — на языке страницы регистрации."""
    итог = шаг(сайт, path, body={"email": АДРЕС})

    [m] = итог["база"]["mail"]
    assert (m["subject"], m["to"]) == (тема, АДРЕС)
    assert f"\n\n{вводная}" in m["text"] and "\n\n# <код>\n\n" in m["text"]
    assert f' lang="{lang}">' in m["html"]
    assert итог["база"]["entry"] == {"attempts": 0, "from_mail": True}


@pytest.mark.parametrize("отключена", [False, True])
def test_почта_занята(сайт, отключена):
    sql("delete from users where email = %s", [АДРЕС])
    sql(
        "insert into users (name, email, password, status, deleted_at, created_at, updated_at) "
        "values ('Был', %s, 'x', 'active', %s, now(), now())",
        [АДРЕС, "2026-01-01 00:00:00" if отключена else None],
    )

    try:
        итог = шаг(сайт, "/uz/register/email", body={"email": АДРЕС})
    finally:
        sql("delete from users where email = %s", [АДРЕС])

    # Отключённый аккаунт адрес не держит
    assert (итог["база"]["entry"] is not None) is отключена


def test_почта_снимает_прежнее_подтверждение(сайт):
    итог = шаг(
        сайт,
        "/register/email",
        данные={"register": {"email": "old@reg.savdex.uz", "verified_email": "old@reg.savdex.uz"}},
        body={"email": АДРЕС},
    )

    assert "verified_email" not in итог["сессия"]["payload"]


# ── Шаг 2: код ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("данные", "prefix", "status"),
    [
        ({}, "", None),
        (_ждёт(), "", None),
        (_ждёт(), "/en", None),
        (
            {**_ждёт(), "status": "Письмо отправлено", "_flash": {"old": [], "new": ["status"]}},
            "",
            "Письмо отправлено",
        ),
    ],
)
def test_страница_кода(сайт, данные, prefix, status):
    итог = шаг(сайт, prefix + "/register/code", данные=данные, method="GET")

    if not данные:
        # Почта ещё не указана — к первому шагу
        assert итог["ответ"]["status"] == 302
        assert итог["ответ"]["headers"]["location"] == сайт + "/register"
        return

    стр = страница(итог["ответ"]["body"])

    assert итог["ответ"]["status"] == 200
    assert стр["component"] == "auth/RegisterCode"
    assert стр["props"]["email"] == АДРЕС
    assert стр["props"]["status"] == status
    assert стр["props"]["locale"] == (prefix.strip("/") or "ru")


НЕ_ПОДОШЁЛ = "Код не подошёл или устарел. Отправьте письмо повторно и введите код из него."


@pytest.mark.parametrize(
    ("body", "попытки", "prefix", "ошибка", "осталось"),
    [
        ({"code": КОД}, 0, "", None, None),
        ({"code": КОД}, 0, "/tr", None, None),
        # Неверный код — попытка засчитана
        ({"code": "111111"}, 0, "", НЕ_ПОДОШЁЛ, 1),
        # Попытки кончились — и верный код уже не принимается, запись снята
        ({"code": КОД}, 5, "", НЕ_ПОДОШЁЛ, None),
        # Не шесть цифр или пусто — попытка не тратится
        ({"code": "12ab"}, 0, "", "Код — шесть цифр", 0),
        ({}, 0, "", "Введите код из письма", 0),
    ],
)
def test_код(сайт, body, попытки, prefix, ошибка, осталось):
    итог = шаг(сайт, prefix + "/register/code", данные=_ждёт(), body=body, код=КОД, попытки=попытки)
    payload = итог["сессия"]["payload"]

    assert итог["ответ"]["status"] == 302

    if ошибка is None:
        assert итог["ответ"]["headers"]["location"] == сайт + prefix + "/register/details"
        assert '"verified_email":"aziz@reg.savdex.uz"' in payload
        assert итог["база"]["entry"] is None  # верный код одноразов
    else:
        assert итог["ответ"]["headers"]["location"] == сайт + "/register"
        assert json.loads(payload)["errors"]["default"]["messages"] == {"code": [ошибка]}
        assert "verified_email" not in payload
        assert (
            None if итог["база"]["entry"] is None else итог["база"]["entry"]["attempts"]
        ) == осталось


def test_код_без_почты(сайт):
    итог = шаг(сайт, "/register/code", body={"code": КОД}, код=КОД)

    assert итог["ответ"]["headers"]["location"].endswith("/register")


@pytest.mark.parametrize("ждёт", [True, False])
def test_код_ещё_раз(сайт, ждёт):
    итог = шаг(
        сайт, "/register/code/resend", данные=_ждёт() if ждёт else {}, код=КОД if ждёт else None
    )

    if ждёт:
        assert len(итог["база"]["mail"]) == 1 and итог["база"]["entry"]["from_mail"]
        assert '"status"' in итог["сессия"]["payload"]
    else:
        assert итог["база"]["mail"] == []


# ── Шаг 3: анкета ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "данные",
    [
        {},
        _ждёт(),
        {"register": {"email": АДРЕС, "verified_email": "other@reg.savdex.uz"}},
        {"register": {"email": АДРЕС, "verified_email": АДРЕС}},
    ],
)
def test_анкета(сайт, данные):
    итог = шаг(сайт, "/register/details", данные=данные, method="GET")
    verified = данные.get("register", {}).get("verified_email")

    if verified == АДРЕС:
        assert итог["ответ"]["status"] == 200
    elif данные:
        assert итог["ответ"]["headers"]["location"].endswith("/register/code")
    else:
        assert итог["ответ"]["headers"]["location"].endswith("/register")


def test_вошедшему_шаги_не_нужны(сайт):
    from .test_web_forms import учётка

    uid = учётка("in@reg.savdex.uz")

    for path, method in (("/register/code", "GET"), ("/register/email", "POST")):
        итог = отправить(
            сайт,
            path,
            подготовка(),
            uid=uid,
            body={"email": АДРЕС},
            method=method,
            env=ОКРУЖЕНИЕ_DJANGO,
            headers=inertia(Referer=сайт + "/register")
            if method == "POST"
            else {"Referer": сайт + "/register", "User-Agent": "savdex-parity"},
        )

        assert итог["ответ"]["status"] == 302


def test_письмо_не_ушло(сайт):
    # Почтовик недоступен — не «код отправлен», а ошибка на первом шаге
    # (раньше сайт молча вёл ко второму шагу, а письма не было)
    итог = отправить(
        сайт,
        "/register/email",
        подготовка(),
        снимок(сайт),
        body={"email": АДРЕС, "country_id": _страна()},
        env={**ОКРУЖЕНИЕ_DJANGO, "MAIL_MAILER": "smtp", "MAIL_HOST": "127.0.0.1", "MAIL_PORT": "9"},
        headers=inertia(Referer=сайт + "/register"),
    )

    assert итог["ответ"]["headers"]["location"].endswith("/register")
    ошибки = json.loads(итог["сессия"]["payload"])["errors"]["default"]["messages"]
    assert ошибки["email"][0].startswith("Не удалось отправить письмо")
    assert '"register":{"email"' not in итог["сессия"]["payload"]


@pytest.mark.parametrize(("email", "китайский"), [("wang@qq.com", True), (АДРЕС, False)])
def test_подсказка_китайской_почты(сайт, email, китайский):
    итог = шаг(сайт, "/zh/register/code", данные=_ждёт(email), method="GET")
    props = страница(итог["ответ"]["body"])["props"]

    assert props["chinaMailbox"] is китайский
    assert props["sender"]


# ── Страна на первом шаге и регистрация без кода ────────────────────


def test_почта_без_страны(сайт):
    итог = отправить(
        сайт,
        "/register/email",
        подготовка(),
        снимок(сайт),
        body={"email": АДРЕС},
        env=ОКРУЖЕНИЕ_DJANGO,
        headers=inertia(Referer=сайт + "/register"),
    )
    ошибки = json.loads(итог["сессия"]["payload"])["errors"]["default"]["messages"]

    # Страна обязательна: от неё зависит, можно ли пропустить код
    assert list(ошибки) == ["country_id"]
    assert итог["база"]["mail"] == []


def test_почта_запоминает_страну(сайт):
    итог = шаг(
        сайт,
        "/register/email",
        данные={"register": {"skipped_email": АДРЕС}},
        body={"email": АДРЕС, "country_id": _страна("cn")},
    )
    register = json.loads(итог["сессия"]["payload"])["register"]

    assert register["country_id"] == _страна("cn")
    # Новая почта — прежний пропуск кода не в счёт
    assert "skipped_email" not in register


@pytest.mark.parametrize(("страна", "можно"), [("cn", True), ("uz", False)])
def test_кнопка_без_кода(сайт, страна, можно):
    данные = {"register": {"email": АДРЕС, "country_id": _страна(страна)}}
    стр = страница(шаг(сайт, "/register/code", данные=данные, method="GET")["ответ"]["body"])

    assert стр["props"]["canSkip"] is можно


@pytest.mark.parametrize(
    ("страна", "куда"), [("cn", "/register/details"), ("uz", "/register/code")]
)
def test_без_кода(сайт, страна, куда):
    данные = {"register": {"email": АДРЕС, "country_id": _страна(страна)}}
    итог = шаг(сайт, "/register/code/skip", данные=данные)
    register = json.loads(итог["сессия"]["payload"])["register"]

    assert итог["ответ"]["headers"]["location"] == сайт + куда
    assert (register.get("skipped_email") == АДРЕС) is (страна == "cn")


def test_без_кода_без_почты(сайт):
    итог = шаг(сайт, "/register/code/skip", данные={})

    assert итог["ответ"]["headers"]["location"] == сайт + "/register"


def test_без_кода_страна_выключена(сайт):
    # Галочку «Регистрация без кода» сняли — пропуск больше не открывает анкету
    sql("update countries set email_code_optional = false where code = 'cn'")

    try:
        данные = {"register": {"email": АДРЕС, "country_id": _страна("cn"), "skipped_email": АДРЕС}}
        итог = шаг(сайт, "/register/details", данные=данные, method="GET")
    finally:
        sql("update countries set email_code_optional = true where code = 'cn'")

    assert итог["ответ"]["headers"]["location"].endswith("/register/code")


def test_анкета_без_кода(сайт):
    данные = {"register": {"email": АДРЕС, "country_id": _страна("cn"), "skipped_email": АДРЕС}}
    итог = шаг(сайт, "/register/details", данные=данные, method="GET")
    props = страница(итог["ответ"]["body"])["props"]

    assert итог["ответ"]["status"] == 200
    assert props["skipped"] is True and props["countryId"] == _страна("cn")
