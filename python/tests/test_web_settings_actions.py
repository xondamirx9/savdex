"""
Профиль в настройках на Django неотличим от Laravel: имя, телефон
(шаблон PHP, смена номера сбрасывает подтверждение), язык (в профиль и
в сессию), проверка ввода; у администратора — строка журнала.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, inertia, отправить, учётка
from .test_web_session import СЕССИЯ, завести, кука
from .web_site import laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel() as root:
        yield root


def человек(admin: bool = False) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions where section = 'users'")
        учётка(
            "person@savdex.uz",
            name="Азиз",
            phone="+998 90 111-22-33",
            phone_verified_at="2026-09-01 10:00:00",
            is_admin=admin,
        )
        sql(
            "update users set updated_at = now() - interval '1 day' "
            "where email = 'person@savdex.uz'"
        )

    return run


def снимок() -> Any:
    журнал = [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions "
            "where section = 'users' order by id"
        )
    ]

    return {
        "user": sql(
            "select name, phone, phone_verified_at is not null, locale, "
            "updated_at > now() - interval '1 hour' from users where email = 'person@savdex.uz'"
        ),
        "journal": журнал,
    }


ВЕРНО = {"name": "Азиз Каримов", "phone": "+998 90 111-22-33", "locale": "uz"}


@pytest.mark.parametrize(
    "body",
    [
        ВЕРНО,
        {**ВЕРНО, "phone": "+998 (91) 222 33 44"},
        {**ВЕРНО, "locale": "ru", "name": "Азиз"},
        {**ВЕРНО, "phone": "998"},
        {**ВЕРНО, "phone": "+998 90 111-22-33 доб. 5"},
        {**ВЕРНО, "name": "А"},
        {**ВЕРНО, "name": ""},
        {**ВЕРНО, "locale": "de"},
        {**ВЕРНО, "phone": 998901112233},
        {},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_профиль(сайт, body, admin):
    uid = учётка("person@savdex.uz")
    отправить(
        сайт,
        "/cabinet/settings/profile",
        человек(admin),
        снимок,
        uid=uid,
        body=body,
        method="PATCH",
        headers=inertia(),
    )


@pytest.mark.parametrize("prefix", ["/en", "/zh"])
def test_профиль_на_языке(сайт, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/settings/profile",
        человек(),
        снимок,
        uid=учётка("person@savdex.uz"),
        body={**ВЕРНО, "locale": "tr"},
        method="PATCH",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303


# ── Telegram ────────────────────────────────────────────────────────

БОТ = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_BOT_USERNAME": "@savdex_bot"}


def привязан() -> None:
    человек()()
    sql(
        "update users set telegram_chat_id = '555', telegram_username = 'aziz', "
        "telegram_linked_at = '2026-09-01 10:00:00' where email = 'person@savdex.uz'"
    )


def снимок_telegram() -> Any:
    return sql(
        "select telegram_chat_id, telegram_username, telegram_linked_at is not null, "
        "updated_at > now() - interval '1 hour' from users where email = 'person@savdex.uz'"
    )


def test_привязка_без_бота(сайт):
    итог = отправить(
        сайт,
        "/cabinet/settings/telegram",
        человек(),
        снимок_telegram,
        uid=учётка("person@savdex.uz"),
        headers=inertia(),
        env={"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_BOT_USERNAME": ""},
    )

    assert '"telegram"' in итог["сессия"]["payload"]


@pytest.mark.parametrize("admin", [False, True])
def test_отвязка(сайт, admin):
    uid = учётка("person@savdex.uz")
    итог = отправить(
        сайт,
        "/cabinet/settings/telegram",
        lambda: (привязан(), sql("update users set is_admin = %s where id = %s", [admin, uid])),
        снимок_telegram,
        uid=uid,
        method="DELETE",
        headers=inertia(),
    )

    assert итог["база"] == [(None, None, False, True)]


def test_привязка_уводит_к_боту(сайт):
    """Токен случайный: сверяются ответ 409 и начало адреса бота у обеих сторон."""
    from .web_site import из_django, из_laravel

    with laravel(**БОТ) as root:
        ответы = []

        for сторона in (из_django, из_laravel):
            человек()()
            завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: учётка("person@savdex.uz")})
            kwargs: dict[str, Any] = {"method": "POST", "body": "{}"}

            if сторона is из_django:
                kwargs["env"] = БОТ

            ответы.append(
                сторона(
                    root,
                    "/cabinet/settings/telegram",
                    {СЕССИЯ: кука(СЕССИЯ, SID)},
                    inertia(),
                    **kwargs,
                )
            )

    for ответ in ответы:
        assert ответ["status"] == 409
        assert re.fullmatch(
            r"https://t\.me/savdex_bot\?start=[A-Za-z0-9]{32}",
            ответ["headers"]["x-inertia-location"],
        )
