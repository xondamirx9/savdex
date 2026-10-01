"""
Пароль и почта — проверки Django.

- Смена выданного пароля: проверка, «не тот же, что выдан», флаг снят,
  хеш в сессии — новый, администратору — в панель (409 для Inertia).
- «Забыли пароль»: ответ один при любом исходе, письмо со ссылкой
  (оформление — как у Laravel), токен брокера в password_reset_tokens,
  не чаще раза в минуту; гостевой маршрут.
- Сброс по токену: проверка, чужой, просроченный и верный токен.
- Подтверждение почты: код из кэша (попытки, одноразовость), письмо
  ещё раз, подписанная ссылка (подпись, отпечаток почты, срок).

Письма — в своём журнале (MAIL_MAILER=log), кэш — файловый.
Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import json
import re
import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import bcrypt
import pytest

from savdex import laravel_cache

from .pg_admin import APP_KEY, КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .test_web_register_actions import _письма, _разбор
from .web_site import ПАРОЛЬ, адрес

pytestmark = нужна_база

ПОЧТА = "account@savdex.uz"
НОВЫЙ = "Cement2027x"
ТОКЕН_СБРОСА = "a" * 64
#: Свой журнал писем: storage/logs — общий с другими проверками
ЖУРНАЛ = Path(КОРЕНЬ) / "storage/logs/python-mail-test-account.log"
КЭШ = Path(КОРЕНЬ) / "storage/framework/cache/data"
ОКРУЖЕНИЕ_DJANGO = {"MAIL_MAILER": "log", "CACHE_STORE": "file", "MAIL_LOG_PATH": str(ЖУРНАЛ)}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    было = os.environ.get("CACHE_STORE")
    os.environ["CACHE_STORE"] = "file"

    with адрес() as root:
        yield root

    if было is None:
        os.environ.pop("CACHE_STORE", None)
    else:
        os.environ["CACHE_STORE"] = было


def _хеш(значение: str) -> str:
    return "$2y$" + bcrypt.hashpw(значение.encode(), bcrypt.gensalt(4)).decode()[4:]


def _проверка(значение: str, хеш: str) -> bool:
    return bcrypt.checkpw(значение.encode(), ("$2b$" + хеш[4:]).encode())


def пользователь(**поля: Any) -> int:
    uid = учётка(
        ПОЧТА,
        **{"status": "active", "email_verified_at": "2026-01-01 00:00:00", **поля},
    )
    sql("update users set remember_token = 'старый' where id = %s", [uid])

    return uid


def подготовка(*шаги: Callable[[], None]) -> Callable[[], None]:
    """Чистые кэш (и счётчики throttle), журналы писем и токены сброса."""

    def run() -> None:
        shutil.rmtree(КЭШ, ignore_errors=True)
        ЖУРНАЛ.parent.mkdir(parents=True, exist_ok=True)
        ЖУРНАЛ.write_text("")
        sql("delete from password_reset_tokens")
        sql("delete from admin_actions")

        for шаг in шаги:
            шаг()

    return run


def _без_изменчивого(текст: str) -> str:
    текст = re.sub(r"\b\d{6}\b", "<код>", текст)
    текст = re.sub(r"expires=\d+", "expires=<срок>", текст)
    текст = re.sub(r"signature=[0-9a-f]{64}", "signature=<подпись>", текст)
    текст = re.sub(r"/reset-password/[0-9a-f]{64}", "/reset-password/<токен>", текст)

    return re.sub(r"https?://127\.0\.0\.1:\d+", "<сайт>", текст)


def _письма_сайта() -> list[dict[str, Any]]:
    return [_разбор(п) for п in _письма(ЖУРНАЛ.read_text())]


def снимок() -> dict[str, Any]:
    uid_rows = sql("select id from users where email = %s", [ПОЧТА])
    uid = uid_rows[0][0] if uid_rows else 0
    письма = _письма_сайта()
    токены = sql("select email, token, created_at is not null from password_reset_tokens")

    # Токен из письма сходится с хешем брокера
    for письмо in письма:
        найдено = re.search(r"/reset-password/([0-9a-f]{64})\?email=", письмо["text"])

        if найдено:
            assert len(токены) == 1 and _проверка(найдено.group(1), токены[0][1])

    код = laravel_cache.get(f"email_verification_code.{uid}")

    return {
        "users": sql(
            "select email, password like '$2y$12$%%', password like '$2y$04$%%', "
            "remember_token = 'старый', must_change_password, email_verified_at is not null "
            "from users where email = %s",
            [ПОЧТА],
        ),
        "tokens": [(e, t.startswith("$2y$"), c) for e, t, c in токены],
        "code": None if not isinstance(код, dict) else {"attempts": код.get("attempts")},
        "mail": [{k: _без_изменчивого(v) for k, v in п.items()} for п in письма],
        "journal": [
            (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
            for a, s, label, ch in sql(
                "select action, section, subject_label, changes::text from admin_actions "
                "order by id"
            )
        ],
    }


def _без_хеша(payload: str) -> str:
    """Хеш нового пароля в сессии (соль случайная): только «есть»."""
    return re.sub(r'("password_hash_web":)"[^"]*"', r'\1"<хеш>"', payload)


def форма(сайт: str, path: str, шаг: Callable[[], None], **kwargs: Any) -> dict[str, Any]:
    return отправить(сайт, path, подготовка(шаг), снимок, env=ОКРУЖЕНИЕ_DJANGO, **kwargs)


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Строка сессии после ответа — разобранным JSON, без токена и отметки входа."""
    payload = json.loads(_без_хеша(итог["сессия"]["payload"])) if итог["сессия"] else {}

    return {k: v for k, v in payload.items() if k != "_token" and not k.startswith("login_web")}


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]] | None:
    errors = сессия(итог).get("errors")

    return None if errors is None else dict(errors["default"]["messages"])


def куда(сайт: str, итог: dict[str, Any]) -> tuple[int, str | None]:
    """Статус и адрес перехода (без адреса сайта)."""
    ответ = итог["ответ"]
    location = ответ["headers"].get("location") or ответ["headers"].get("x-inertia-location")

    return ответ["status"], None if location is None else location.removeprefix(сайт)


# ── Смена выданного пароля ──────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"password": НОВЫЙ, "password_confirmation": "другой"},
        {"password": "short1", "password_confirmation": "short1"},
        {"password": "onlyletterslong", "password_confirmation": "onlyletterslong"},
        {"password": ["x"], "password_confirmation": ["x"]},
        {"password": ПАРОЛЬ, "password_confirmation": ПАРОЛЬ},
        {"password": НОВЫЙ, "password_confirmation": НОВЫЙ},
    ],
)
def test_смена_пароля(сайт, body):
    uid = пользователь(must_change_password=True)
    итог = форма(
        сайт,
        "/password/change",
        lambda: пользователь(must_change_password=True, password=_хеш(ПАРОЛЬ)),
        uid=uid,
        body=body,
    )

    if body.get("password") == НОВЫЙ and body.get("password_confirmation") == НОВЫЙ:
        assert итог["ответ"]["headers"]["location"].endswith("/cabinet")
        assert итог["база"]["users"][0][4] is False
        assert '"password_hash_web":"<хеш>"' in _без_хеша(итог["сессия"]["payload"])


@pytest.mark.parametrize("заголовки", ["inertia", "form"])
def test_смена_пароля_администратора(сайт, заголовки):
    uid = пользователь(must_change_password=True, is_admin=True)
    headers = (
        inertia()
        if заголовки == "inertia"
        else {"Content-Type": "application/x-www-form-urlencoded"}
    )
    итог = форма(
        сайт,
        "/password/change",
        lambda: пользователь(must_change_password=True, is_admin=True, password=_хеш(ПАРОЛЬ)),
        uid=uid,
        body=f"_token={'t' * 40}&password={НОВЫЙ}&password_confirmation={НОВЫЙ}"
        if заголовки == "form"
        else {"password": НОВЫЙ, "password_confirmation": НОВЫЙ},
        content_type="application/x-www-form-urlencoded"
        if заголовки == "form"
        else "application/json",
        headers=headers,
    )
    assert итог["ответ"]["status"] in (302, 409)


def test_смена_пароля_гостю_нельзя(сайт):
    форма(
        сайт,
        "/password/change",
        lambda: None,
        body={"password": НОВЫЙ, "password_confirmation": НОВЫЙ},
    )


# ── Забыли пароль ───────────────────────────────────────────────────


def _свежий_токен() -> None:
    sql(
        "insert into password_reset_tokens (email, token, created_at) values (%s, %s, now())",
        [ПОЧТА, _хеш("прежний")],
    )


@pytest.mark.parametrize(
    ("body", "шаг"),
    [
        ({}, None),
        ({"email": "нет"}, None),
        ({"email": "nobody@savdex.uz"}, None),
        ({"email": ПОЧТА}, None),
        ({"email": ПОЧТА.upper()}, None),
        ({"email": ПОЧТА, "channel": "telegram"}, None),
        ({"email": ПОЧТА, "channel": "pigeon"}, None),
        ({"email": ПОЧТА}, _свежий_токен),
        ({"email": ПОЧТА, "channel": ["mail"]}, None),
    ],
)
def test_забыли_пароль(сайт, body, шаг):
    пользователь()

    def готово() -> None:
        пользователь()

        if шаг is not None:
            шаг()

    итог = форма(сайт, "/forgot-password", готово, body=body)

    if body == {"email": ПОЧТА}:
        assert len(итог["база"]["mail"]) == (0 if шаг else 1)


def test_забыли_пароль_вошедшему_нельзя(сайт):
    uid = пользователь()
    форма(сайт, "/forgot-password", lambda: None, uid=uid, body={"email": ПОЧТА})


# ── Сброс по токену ─────────────────────────────────────────────────


def _токен(минут_назад: int = 0, token: str = ТОКЕН_СБРОСА) -> Callable[[], None]:
    def run() -> None:
        пользователь(must_change_password=True)
        sql(
            "insert into password_reset_tokens (email, token, created_at) "
            "values (%s, %s, now() - make_interval(mins => %s))",
            [ПОЧТА, _хеш(token), минут_назад],
        )

    return run


ВЕРНЫЙ_СБРОС = {
    "token": ТОКЕН_СБРОСА,
    "email": ПОЧТА,
    "password": НОВЫЙ,
    "password_confirmation": НОВЫЙ,
}


@pytest.mark.parametrize(
    ("body", "шаг"),
    [
        ({}, _токен()),
        ({**ВЕРНЫЙ_СБРОС, "password_confirmation": "другой"}, _токен()),
        ({**ВЕРНЫЙ_СБРОС, "password": "short", "password_confirmation": "short"}, _токен()),
        ({**ВЕРНЫЙ_СБРОС, "email": "плохо"}, _токен()),
        ({**ВЕРНЫЙ_СБРОС, "token": "b" * 64}, _токен()),
        ({**ВЕРНЫЙ_СБРОС, "email": "nobody@savdex.uz"}, _токен()),
        (ВЕРНЫЙ_СБРОС, _токен(минут_назад=61)),
        (ВЕРНЫЙ_СБРОС, lambda: пользователь(must_change_password=True)),
        (ВЕРНЫЙ_СБРОС, _токен()),
    ],
)
def test_сброс_пароля(сайт, body, шаг):
    пользователь()
    итог = форма(сайт, "/reset-password", шаг, body=body)

    # Пароль сменён: токен «запомнить» новый — дальше на вход
    if итог["база"]["users"][0][3] is False:
        assert итог["ответ"]["headers"]["location"].endswith("/login")


# ── Подтверждение почты ─────────────────────────────────────────────


def _код(код: str = "123456", попытки: int = 0) -> Callable[[], None]:
    def run() -> None:
        uid = пользователь(email_verified_at=None)
        laravel_cache.put(
            f"email_verification_code.{uid}", {"hash": _хеш(код), "attempts": попытки}, 900
        )

    return run


@pytest.mark.parametrize(
    ("body", "шаг", "данные"),
    [
        ({}, _код(), None),
        ({"code": "12345"}, _код(), None),
        ({"code": "12345a"}, _код(), None),
        ({"code": 123456.0}, _код(), None),
        ({"code": "000000"}, _код(), None),
        ({"code": "123456"}, _код(), None),
        ({"code": 123456}, _код(), None),
        ({"code": "123456"}, _код(попытки=5), None),
        ({"code": "123456"}, lambda: пользователь(email_verified_at=None), None),
        ({"code": "123456"}, _код(), {"url": {"intended": "http://127.0.0.1/pricing"}}),
        ({"code": "000000"}, lambda: пользователь(), None),
    ],
)
def test_код_подтверждения(сайт, body, шаг, данные):
    uid = пользователь()
    форма(сайт, "/verify-email/code", шаг, uid=uid, body=body, данные=данные)


@pytest.mark.parametrize("проверена", [False, True])
def test_письмо_ещё_раз(сайт, проверена):
    uid = пользователь()
    итог = форма(
        сайт,
        "/email/verification-notification",
        lambda: пользователь(email_verified_at="2026-01-01 00:00:00" if проверена else None),
        uid=uid,
        body={},
    )

    if not проверена:
        assert len(итог["база"]["mail"]) == 1 and итог["база"]["code"] == {"attempts": 0}


def _ссылка(сайт: str, uid: int, *, почта: str = ПОЧТА, срок: int = 3600) -> str:
    отпечаток = hashlib.sha1(почта.encode()).hexdigest()
    путь = f"/verify-email/{uid}/{отпечаток}?expires={int(time.time()) + срок}"
    подпись = hmac.new(APP_KEY.encode(), (сайт + путь).encode(), hashlib.sha256).hexdigest()

    return путь + "&signature=" + подпись


@pytest.mark.parametrize(
    "вариант",
    ["верно", "уже", "подпись", "срок", "чужой", "почта", "без_подписи", "intended"],
)
def test_ссылка_подтверждения(сайт, вариант):
    uid = пользователь()
    путь = {
        "верно": _ссылка(сайт, uid),
        "уже": _ссылка(сайт, uid),
        "подпись": _ссылка(сайт, uid)[:-1] + "0",
        "срок": _ссылка(сайт, uid, срок=-10),
        "чужой": _ссылка(сайт, uid + 1000),
        "почта": _ссылка(сайт, uid, почта="other@savdex.uz"),
        "без_подписи": _ссылка(сайт, uid).split("&signature=")[0],
        "intended": _ссылка(сайт, uid),
    }[вариант]
    форма(
        сайт,
        путь,
        lambda: пользователь(email_verified_at="2026-01-01 00:00:00" if вариант == "уже" else None),
        uid=uid,
        method="GET",
        body="",
        headers={},
        данные={"url": {"intended": сайт + "/pricing"}} if вариант == "intended" else None,
    )
