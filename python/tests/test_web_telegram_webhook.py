"""
Telegram-бот на Django: привязка по ИНН и меню уведомлений.

- чужой секрет — 404; бот не настроен — 204 и тишина;
- человек открыл бота сам: ИНН → почта его учётной записи в компании →
  код из письма → чат привязан к его учётной записи (не к владельцу);
- кнопка кабинета: ИНН сверяется с его компанией, кода нет; чужой ИНН —
  «неверный», незнакомый — «зарегистрируйтесь»;
- три неверных кода — пауза; привязанный чат — меню и пауза рассылки.

Сообщения бота — TELEGRAM_TRANSPORT=log в файл, письма — MAIL_MAILER=log.
Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from savdex import laravel_cache

from .factories import категория, компания, пользователь
from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть

pytestmark = нужна_база

СЕКРЕТ = "hook-secret-1"

#: Токены привязки, которые проверки кладут в общий файловый кэш
ТОКЕНЫ = ("tok123", "tok456", "other")


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    было = os.environ.get("CACHE_STORE")
    os.environ["CACHE_STORE"] = "file"

    try:
        with адрес() as root:
            yield root
    finally:
        for токен in ТОКЕНЫ:
            laravel_cache.file_path(f"telegram.link.{токен}").unlink(missing_ok=True)

        if было is None:
            os.environ.pop("CACHE_STORE", None)
        else:
            os.environ["CACHE_STORE"] = было


class Бот:
    """Переписка с ботом: что ему пишут и что он отвечает."""

    def __init__(self, сайт: str, папка: Path, chat: int = 555) -> None:
        self.сайт = сайт
        self.chat = chat
        self.журнал = папка / "telegram.log"
        self.почта = папка / "mail.log"
        self.прочитано = 0

    def окружение(self, **extra: str) -> dict[str, str]:
        return {
            "TELEGRAM_WEBHOOK_SECRET": СЕКРЕТ,
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_BOT_USERNAME": "savdex_test_bot",
            "TELEGRAM_TRANSPORT": "log",
            "TELEGRAM_LOG_PATH": str(self.журнал),
            "CACHE_STORE": "file",
            "MAIL_MAILER": "log",
            "MAIL_LOG_PATH": str(self.почта),
            **extra,
        }

    def прислать(self, update: Any, path: str | None = None, **env: str) -> int:
        ответ = открыть(
            self.сайт,
            path or f"/telegram/webhook/{СЕКРЕТ}",
            None,
            {"Accept": "application/json"},
            self.окружение(**env),
            method="POST",
            body=update if isinstance(update, str) else json.dumps(update),
            content_type="application/json",
        )

        return int(ответ["status"])

    def написать(self, text: str, username: str = "aziz", **env: str) -> list[dict[str, Any]]:
        status = self.прислать(
            {
                "update_id": 1,
                "message": {
                    "chat": {"id": self.chat},
                    "text": text,
                    "from": {"username": username, "language_code": "ru"},
                },
            },
            **env,
        )
        assert status == 204

        return self.новые()

    def нажать(self, data: str) -> list[dict[str, Any]]:
        status = self.прислать(
            {
                "update_id": 2,
                "callback_query": {
                    "id": "cb1",
                    "data": data,
                    "from": {"language_code": "ru"},
                    "message": {"chat": {"id": self.chat}},
                },
            }
        )
        assert status == 204

        return [m for m in self.новые() if "callback" not in m]

    def новые(self) -> list[dict[str, Any]]:
        if not self.журнал.exists():
            return []

        строки = self.журнал.read_text(encoding="utf-8").splitlines()
        новые = [json.loads(s) for s in строки[self.прочитано :]]
        self.прочитано = len(строки)

        return новые

    def код(self) -> tuple[str, str]:
        """Последнее письмо: кому и код из него."""
        from .test_deliveries import письма, части

        письмо = письма(self.почта)[-1]
        тело, _ = части(письмо)
        найдено = re.search(r"^# (\d{6})$", тело, re.M)
        assert найдено, тело

        return str(письмо["To"]), найдено.group(1)


def кнопки(сообщение: dict[str, Any]) -> list[dict[str, Any]]:
    markup = сообщение.get("reply_markup") or {}

    return [b for row in markup.get("inline_keyboard", []) for b in row]


def чат_у(uid: int) -> str | None:
    rows = sql("select telegram_chat_id from users where id = %s", [uid])

    return rows[0][0]


@pytest.fixture
def фирма() -> dict[str, Any]:
    """Компания с ИНН, владельцем, сотрудником и двумя категориями."""
    sql("delete from telegram_bot_chats")
    sql("update users set telegram_chat_id = null")
    n = sql("select count(*) from companies")[0][0]
    tin = str(300_000_000 + n)
    cid = компания(name=f"ООО «Мебель Плюс {n}»", tin=f"{tin[:3]} {tin[3:6]} {tin[6:]}")
    owner = пользователь(company_id=cid, email=f"owner{n}@mebel.uz", name="Алишер")
    staff = пользователь(
        company_id=cid, email=f"Dilnoza{n}@mebel.uz", name="Дилноза", company_role="manager"
    )
    for name in ("Мебель", "Текстиль"):
        sql(
            "insert into company_category (company_id, category_id) values (%s, %s)",
            [cid, категория(name)],
        )

    return {"cid": cid, "tin": tin, "owner": owner, "staff": staff, "n": n}


def test_чужой_секрет(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path)

    assert (
        бот.прислать({"message": {"chat": {"id": 1}, "text": "/start"}}, "/telegram/webhook/x")
        == 404
    )
    assert бот.новые() == []


def test_бот_не_настроен(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path)

    assert бот.написать("/start", TELEGRAM_BOT_TOKEN="") == []
    assert sql("select count(*) from telegram_bot_chats")[0][0] == 0


@pytest.mark.parametrize(
    "body", ["не json", {}, {"message": "строка"}, {"message": {"text": "/start"}}]
)
def test_мусор(сайт, tmp_path, фирма, body):
    бот = Бот(сайт, tmp_path)

    assert бот.прислать(body) == 204
    assert бот.новые() == []


def test_сам_открыл_бота(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path)

    [привет] = бот.написать("/start")
    assert "введите ИНН" in привет["text"]

    # Не ИНН, незнакомый ИНН — «зарегистрируйтесь» со ссылкой
    assert "9 цифр" in бот.написать("12345")[0]["text"]
    [нет] = бот.написать("999999999")
    assert "не зарегистрирована" in нет["text"]
    assert кнопки(нет) == [{"text": "Зарегистрироваться", "url": f"{сайт}/register"}]

    # ИНН с пробелами — компания найдена, спрашивают почту
    [почта] = бот.написать(f"{фирма['tin'][:3]} {фирма['tin'][3:]}")
    assert "Мебель Плюс" in почта["text"] and "почту" in почта["text"]

    # Почта не из этой компании — отказ, кода нет
    чужой = пользователь(company_id=компания(), email=f"other{фирма['n']}@x.uz")
    assert "не относится" in бот.написать(f"other{фирма['n']}@x.uz")[0]["text"]
    assert not бот.почта.exists()
    assert чат_у(чужой) is None

    # Почта сотрудника (регистр не важен) — код уходит ему
    [отправлен] = бот.написать(f"dilnoza{фирма['n']}@MEBEL.uz")
    assert "Di***@mebel.uz" in отправлен["text"]
    кому, код = бот.код()
    assert кому == f"Dilnoza{фирма['n']}@mebel.uz"

    # Неверный код — попытки считаются
    assert (
        "Осталось попыток: 2" in бот.написать("000000" if код != "000000" else "111111")[0]["text"]
    )

    [готово] = бот.написать(код, username="dilnoza_tg")
    assert "Дилноза, готово" in готово["text"]
    assert "• Мебель" in готово["text"] and "• Текстиль" in готово["text"]
    assert [b.get("url") or b.get("callback_data") for b in кнопки(готово)] == [
        f"{сайт}/cabinet/settings#categories",
        "pause",
    ]

    # Привязан сотрудник, а не владелец
    assert sql(
        "select telegram_chat_id, telegram_username, telegram_linked_at is not null "
        "from users where id = %s",
        [фирма["staff"]],
    ) == [("555", "dilnoza_tg", True)]
    assert чат_у(фирма["owner"]) is None

    # Дальше — меню
    [меню] = бот.написать("привет")
    assert "включены" in меню["text"] and "• Мебель" in меню["text"]
    [меню] = бот.написать("/start")
    assert "включены" in меню["text"]


def test_три_неверных_кода(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path)
    бот.написать("/start")
    бот.написать(фирма["tin"])
    бот.написать(f"owner{фирма['n']}@mebel.uz")
    _, код = бот.код()
    неверный = "000000" if код != "000000" else "111111"

    assert "Осталось попыток: 2" in бот.написать(неверный)[0]["text"]
    assert "Осталось попыток: 1" in бот.написать(неверный)[0]["text"]
    assert "Попробуйте через 15 мин" in бот.написать(неверный)[0]["text"]

    # Пауза: даже верный код уже не принимается
    assert "Попробуйте через" in бот.написать(код)[0]["text"]
    assert чат_у(фирма["owner"]) is None


def test_код_устарел(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path)
    бот.написать("/start")
    бот.написать(фирма["tin"])
    бот.написать(f"owner{фирма['n']}@mebel.uz")
    _, код = бот.код()
    sql("update telegram_bot_chats set code_expires_at = now() - interval '1 day'")

    assert "Код устарел" in бот.написать(код)[0]["text"]
    assert чат_у(фирма["owner"]) is None


def test_кнопка_кабинета(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path, chat=777)
    laravel_cache.put("telegram.link.tok123", фирма["staff"], 900)

    [просьба] = бот.написать("/start tok123")
    assert "Дилноза, чтобы подключить" in просьба["text"]
    # Токен одноразовый
    assert laravel_cache.get("telegram.link.tok123") is None

    # ИНН другой компании — «неверный», незнакомый — «зарегистрируйтесь»
    другая = компания(tin="222333444")
    assert "не принадлежит вашей компании" in бот.написать("222333444")[0]["text"]
    assert "не зарегистрирована" in бот.написать("888777666")[0]["text"]
    assert чат_у(фирма["staff"]) is None
    assert другая

    # Свой ИНН — сразу привязка, без почты и кода
    [готово] = бот.написать(фирма["tin"])
    assert "Дилноза, готово" in готово["text"]
    assert чат_у(фирма["staff"]) == "777"
    assert not бот.почта.exists()


def test_кнопка_кабинета_без_компании(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path, chat=778)
    одиночка = пользователь(company_id=None, name="Без компании")
    laravel_cache.put("telegram.link.tok456", одиночка, 900)
    бот.написать("/start tok456")

    assert "ещё нет компании" in бот.написать(фирма["tin"])[0]["text"]
    assert чат_у(одиночка) is None


def test_истёкшая_ссылка(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path)

    assert "недействительна" in бот.написать("/start other")[0]["text"]


def test_чат_переходит_к_другому(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path, chat=900)
    laravel_cache.put("telegram.link.tok123", фирма["owner"], 900)
    бот.написать("/start tok123")
    бот.написать(фирма["tin"])
    assert чат_у(фирма["owner"]) == "900"

    # Тот же Telegram привязывает сотрудник — у владельца чат снимается
    laravel_cache.put("telegram.link.tok456", фирма["staff"], 900)
    бот.написать("/start tok456")
    бот.написать(фирма["tin"])
    assert (чат_у(фирма["owner"]), чат_у(фирма["staff"])) == (None, "900")


def test_пауза_рассылки(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path, chat=901)
    laravel_cache.put("telegram.link.tok123", фирма["owner"], 900)
    бот.написать("/start tok123")
    бот.написать(фирма["tin"])

    [пауза] = бот.нажать("pause")
    assert "на паузе" in пауза["text"]
    assert [b.get("callback_data") for b in кнопки(пауза)][-1] == "resume"
    assert sql(
        "select telegram from notification_preferences where user_id = %s and event = %s",
        [фирма["owner"], "category_feed"],
    ) == [(False,)]
    assert "на паузе" in бот.написать("меню")[0]["text"]

    [снова] = бот.нажать("resume")
    assert "снова включены" in снова["text"]
    assert sql(
        "select telegram from notification_preferences where user_id = %s and event = %s",
        [фирма["owner"], "category_feed"],
    ) == [(True,)]


def test_кнопка_без_привязки(сайт, tmp_path, фирма):
    бот = Бот(сайт, tmp_path, chat=902)

    assert "введите ИНН" in бот.нажать("pause")[0]["text"]
