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

from .factories import категория
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
        assert '"register":{"email":"aziz@reg.savdex.uz"}' in итог["сессия"]["payload"]
    else:
        assert итог["база"] == {"mail": [], "entry": None}


@pytest.mark.parametrize(
    ("path", "lang", "тема", "вводная"),
    [
        ("/register/email", "ru", "Код подтверждения <код> — SAVDEX", "Ваш код для регистрации"),
        ("/en/register/email", "en", "Confirmation code <код> — SAVDEX", "Your SAVDEX registration"),
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
