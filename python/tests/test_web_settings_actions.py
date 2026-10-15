"""
Профиль в настройках на Django: имя, телефон
(шаблон PHP, смена номера сбрасывает подтверждение), язык (в профиль и
в сессию), проверка ввода; у администратора — строка журнала.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, inertia, отправить, учётка
from .web_site import СЕССИЯ, адрес, завести, кука, открыть

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
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


#: Профиль до формы: (имя, телефон, подтверждён ли, язык, тронут ли сейчас)
БЫЛО = ("Азиз", "+998 90 111-22-33", True, "ru", False)


@pytest.mark.parametrize(
    ("body", "стало"),
    [
        (ВЕРНО, ("Азиз Каримов", "+998 90 111-22-33", True, "uz", True)),
        # Другой номер — подтверждение сброшено
        (
            {**ВЕРНО, "phone": "+998 (91) 222 33 44"},
            ("Азиз Каримов", "+998 (91) 222 33 44", False, "uz", True),
        ),
        # Ничего не изменилось — строку не трогают
        ({**ВЕРНО, "locale": "ru", "name": "Азиз"}, БЫЛО),
        ({**ВЕРНО, "phone": "998"}, {"phone"}),
        ({**ВЕРНО, "phone": "+998 90 111-22-33 доб. 5"}, {"phone"}),
        ({**ВЕРНО, "name": "А"}, {"name"}),
        ({**ВЕРНО, "name": ""}, {"name"}),
        ({**ВЕРНО, "locale": "de"}, {"locale"}),
        ({**ВЕРНО, "phone": 998901112233}, {"phone"}),
        ({}, {"name", "phone", "locale"}),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_профиль(сайт, body, стало, admin):
    uid = учётка("person@savdex.uz")
    итог = отправить(
        сайт,
        "/cabinet/settings/profile",
        человек(admin),
        снимок,
        uid=uid,
        body=body,
        method="PATCH",
        headers=inertia(),
    )
    сессия = json.loads(итог["сессия"]["payload"])

    assert итог["ответ"]["status"] == 303
    assert итог["ответ"]["headers"]["location"].endswith("/cabinet/settings")

    if isinstance(стало, set):
        # Ошибки проверки: назад с вводом, профиль прежний
        assert set(сессия["errors"]["default"]["messages"]) == стало
        assert "_old_input" in сессия and "success" not in сессия
        assert итог["база"] == {"user": [БЫЛО], "journal": []}

        return

    # Сменили язык — на ту же страницу уже на нём, с сообщением на нём же
    assert сессия["success"] == {"ru": "Профиль обновлён", "uz": "Profil yangilandi"}[стало[3]]
    assert итог["ответ"]["headers"]["location"].endswith(
        "/uz/cabinet/settings" if стало[3] == "uz" else f"{сайт}/cabinet/settings"
    )
    # Язык — и в профиль, и в сессию
    assert сессия["locale"] == стало[3]
    assert итог["база"]["user"] == [стало]
    журнал = итог["база"]["journal"]

    if admin and стало != БЫЛО:
        [(action, section, label, changes)] = журнал
        assert (action, section, label) == ("updated", "users", "Азиз Каримов")
        assert ("phone_verified_at" in changes) is (not стало[2])
    else:
        assert журнал == []


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

    сессия = json.loads(итог["сессия"]["payload"])

    assert итог["ответ"]["status"] == 303
    # Новый язык — новый адрес: старый префикс перезаписал бы выбор
    assert итог["ответ"]["headers"]["location"].endswith("/tr/cabinet/settings")
    assert сессия["success"] == "Profil güncellendi"
    assert сессия["locale"] == "tr"
    assert итог["база"]["user"] == [("Азиз Каримов", "+998 90 111-22-33", True, "tr", True)]


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

    сессия = json.loads(итог["сессия"]["payload"])

    assert итог["ответ"]["status"] == 302
    assert сессия["errors"]["default"]["messages"] == {
        "telegram": ["Привязка Telegram пока не настроена площадкой."]
    }
    assert итог["база"] == [(None, None, False, False)]


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


def test_привязка_уводит_к_боту(сайт, monkeypatch):
    """Токен случайный: ответ 409 и адрес бота с токеном; токен — в кэше."""
    человек()()
    uid = учётка("person@savdex.uz")
    завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})
    ответ = открыть(
        сайт,
        "/cabinet/settings/telegram",
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        inertia(),
        env={**БОТ, "CACHE_STORE": "file"},
        method="POST",
        body="{}",
        content_type="application/json",
    )

    assert ответ["status"] == 409
    адрес_бота = ответ["headers"]["x-inertia-location"]
    assert re.fullmatch(r"https://t\.me/savdex_bot\?start=[A-Za-z0-9]{32}", адрес_бота)

    # Токен привязки живёт в кэше и ведёт к пользователю (его читает вебхук бота)
    from savdex import laravel_cache

    ключ = f"telegram.link.{адрес_бота.rsplit('=', 1)[1]}"

    monkeypatch.setenv("CACHE_STORE", "file")

    try:
        assert laravel_cache.get(ключ) == uid
    finally:
        laravel_cache.file_path(ключ).unlink(missing_ok=True)


# ── Подтверждение телефона по SMS (Telnyx, заглушка из test_sms) ────


@pytest.fixture(scope="module")
def telnyx() -> Iterator[str]:
    from .test_sms import заглушка_telnyx

    with заглушка_telnyx() as url:
        yield url


def _смс(telnyx: str) -> dict[str, str]:
    return {
        "TELNYX_API_KEY": "key-1",
        "TELNYX_VERIFY_PROFILE_ID": "profile-1",
        "TELNYX_API_URL": telnyx,
    }


def неподтверждённый(пропустил: bool = True) -> Callable[[], None]:
    """Номер не подтверждён; код из письма пропускали при регистрации."""

    def run() -> None:
        человек()()
        sql(
            "update users set phone_verified_at = null, email_verified_at = null, "
            "email_code_skipped = %s where email = 'person@savdex.uz'",
            [пропустил],
        )
        sql("delete from users where email = 'other@savdex.uz'")

    return run


def _телефон() -> Any:
    return sql(
        "select phone, phone_verified_at is not null, email_code_skipped from users "
        "where email = 'person@savdex.uz'"
    )


def test_смс_на_номер_профиля(сайт, telnyx):
    uid = учётка("person@savdex.uz")
    итог = отправить(
        сайт,
        "/cabinet/settings/phone/send",
        неподтверждённый(),
        _телефон,
        uid=uid,
        env=_смс(telnyx),
    )
    сессия = json.loads(итог["сессия"]["payload"])

    assert сессия["settings"]["sms_phone"] == "+998901112233"
    assert сессия["success"] == "Код отправлен в SMS на +998901112233."
    # Пока кода не ввели — не подтверждён
    assert итог["база"] == [("+998 90 111-22-33", False, True)]


def test_смс_номер_занят(сайт, telnyx):
    uid = учётка("person@savdex.uz")

    def занять() -> None:
        неподтверждённый()()
        учётка("other@savdex.uz", phone="998901112233", phone_verified_at="2026-09-01 10:00:00")

    try:
        итог = отправить(сайт, "/cabinet/settings/phone/send", занять, uid=uid, env=_смс(telnyx))
    finally:
        sql("delete from users where email = 'other@savdex.uz'")

    сессия = json.loads(итог["сессия"]["payload"])

    assert list(сессия["errors"]["default"]["messages"]) == ["phone"]
    assert "settings" not in сессия


@pytest.mark.parametrize(
    ("отправлен", "код", "стало"),
    [
        # Верный код: номер подтверждён (в международном виде), метка снята
        ("+998901112233", "12345", ("+998901112233", True, False)),
        ("+998901112233", "99999", ("+998 90 111-22-33", False, True)),
        # Код уходил на прежний номер — не в счёт
        ("+998901110000", "12345", ("+998 90 111-22-33", False, True)),
    ],
)
def test_код_из_смс_в_профиле(сайт, telnyx, отправлен, код, стало):
    uid = учётка("person@savdex.uz")
    итог = отправить(
        сайт,
        "/cabinet/settings/phone/confirm",
        неподтверждённый(),
        _телефон,
        uid=uid,
        данные={"settings": {"sms_phone": отправлен}},
        body={"sms_code": код},
        env=_смс(telnyx),
    )
    сессия = json.loads(итог["сессия"]["payload"])

    assert итог["база"] == [стало]

    if стало[1]:
        assert сессия["success"] == "Телефон подтверждён."
        assert "sms_phone" not in сессия.get("settings", {})
    else:
        assert list(сессия["errors"]["default"]["messages"]) == ["sms_code"]
