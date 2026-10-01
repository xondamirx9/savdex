"""
Вебхук Telegram-бота на Django: чужой секрет — 404,
не «/start» и пустой чат — 204 без записи, «/start» без токена и с
истёкшим — 204 без записи, верный токен — чат привязан (номер чата,
имя в Telegram, время), токен одноразовый.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_cache

from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import учётка
from .web_site import адрес, открыть

pytestmark = нужна_база

СЕКРЕТ = "hook-secret-1"
ОКРУЖЕНИЕ = {"TELEGRAM_WEBHOOK_SECRET": СЕКРЕТ, "CACHE_STORE": "file"}
ПОЧТА = "tg@savdex.uz"

#: Токены привязки, которые проверки кладут в общий файловый кэш
ТОКЕНЫ = ("tok123", "other")


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


def сброс(токен: str | None = "tok123") -> Callable[[], None]:
    def run() -> None:
        # Только свои ключи: файловый кэш storage/ — общий
        for старый in ТОКЕНЫ:
            laravel_cache.file_path(f"telegram.link.{старый}").unlink(missing_ok=True)

        uid = учётка(ПОЧТА)
        sql(
            "update users set telegram_chat_id = null, telegram_username = null, "
            "telegram_linked_at = null where id = %s",
            [uid],
        )

        if токен is not None:
            laravel_cache.put(f"telegram.link.{токен}", uid, 900)

    return run


def снимок() -> Any:
    return {
        "user": sql(
            "select telegram_chat_id, telegram_username, telegram_linked_at is not null "
            "from users where email = %s",
            [ПОЧТА],
        ),
        "token": laravel_cache.get("telegram.link.tok123") is not None,
    }


def вебхук(сайт: str, path: str, body: Any, подготовка: Callable[[], None]) -> dict[str, Any]:
    подготовка()
    ответ = открыть(
        сайт,
        path,
        None,
        {"Accept": "application/json"},
        ОКРУЖЕНИЕ,
        method="POST",
        body=body if isinstance(body, str) else json.dumps(body),
        content_type="application/json",
    )

    return {
        "status": ответ["status"],
        "body": ответ["body"] if ответ["status"] != 404 else "",
        "db": снимок(),
    }


def сообщение(text: Any, chat: Any = 555, username: Any = "aziz") -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat}, "text": text, "from": {"username": username}},
    }


НЕ_ПРИВЯЗАН = (None, None, False)


@pytest.mark.parametrize(
    ("body", "токен", "чат", "токен_остался"),
    [
        # Верный токен — чат привязан, токен одноразовый
        (сообщение("/start tok123"), "tok123", ("555", "aziz", True), False),
        # Пробелы вокруг — не помеха; имя «0» — пустое, как у PHP
        (
            сообщение("  /start   tok123  ", chat="-100200", username="0"),
            "tok123",
            ("-100200", None, True),
            False,
        ),
        (сообщение("/start tok123", username=None), "tok123", ("555", None, True), False),
        # Без токена, с чужим и с истёкшим — без записи
        (сообщение("/start"), "tok123", НЕ_ПРИВЯЗАН, True),
        (сообщение("/start other"), "tok123", НЕ_ПРИВЯЗАН, True),
        (сообщение("/start tok123"), None, НЕ_ПРИВЯЗАН, False),
        # Не «/start», пустой чат, не сообщение, не JSON — тоже
        (сообщение("привет"), "tok123", НЕ_ПРИВЯЗАН, True),
        (сообщение("/start tok123", chat=None), "tok123", НЕ_ПРИВЯЗАН, True),
        ({"message": "строка"}, "tok123", НЕ_ПРИВЯЗАН, True),
        ({}, "tok123", НЕ_ПРИВЯЗАН, True),
        ("не json", "tok123", НЕ_ПРИВЯЗАН, True),
    ],
)
def test_вебхук(сайт, body, токен, чат, токен_остался):
    итог = вебхук(сайт, f"/telegram/webhook/{СЕКРЕТ}", body, сброс(токен))

    # Telegram ответ не читает: всегда 204 без тела
    assert итог["status"] == 204 and итог["body"] == ""
    assert итог["db"] == {"user": [чат], "token": токен_остался}


@pytest.mark.parametrize("path", ["/telegram/webhook/wrong-secret", "/telegram/webhook/short"])
def test_чужой_секрет(сайт, path):
    итог = вебхук(сайт, path, сообщение("/start tok123"), сброс())

    assert итог["status"] == 404
    assert итог["db"] == {"user": [НЕ_ПРИВЯЗАН], "token": True}
