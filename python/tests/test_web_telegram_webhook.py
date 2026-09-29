"""
Вебхук Telegram-бота на Django неотличим от Laravel: чужой секрет — 404,
не «/start» и пустой чат — 204 без записи, «/start» без токена и с
истёкшим — 204 без записи, верный токен — чат привязан (номер чата,
имя в Telegram, время), токен одноразовый.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_cache

from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import учётка
from .test_web_register_actions import КЭШ
from .web_site import laravel, из_django, из_laravel

pytestmark = нужна_база

СЕКРЕТ = "hook-secret-1"
ОКРУЖЕНИЕ = {"TELEGRAM_WEBHOOK_SECRET": СЕКРЕТ, "CACHE_STORE": "file"}
ПОЧТА = "tg@savdex.uz"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    было = os.environ.get("CACHE_STORE")
    os.environ["CACHE_STORE"] = "file"

    with laravel(**ОКРУЖЕНИЕ) as root:
        yield root

    if было is None:
        os.environ.pop("CACHE_STORE", None)
    else:
        os.environ["CACHE_STORE"] = было


def сброс(токен: str | None = "tok123") -> Callable[[], None]:
    def run() -> None:
        shutil.rmtree(КЭШ, ignore_errors=True)
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
    стороны = {}

    for имя, сторона in (("django", из_django), ("laravel", из_laravel)):
        подготовка()
        kwargs: dict[str, Any] = {
            "method": "POST",
            "body": body if isinstance(body, str) else json.dumps(body),
            "content_type": "application/json",
        }

        if сторона is из_django:
            kwargs["env"] = ОКРУЖЕНИЕ

        ответ = сторона(сайт, path, None, {"Accept": "application/json"}, **kwargs)
        стороны[имя] = {
            "status": ответ["status"],
            "body": ответ["body"] if ответ["status"] != 404 else "",
            "db": снимок(),
        }

    assert стороны["django"] == стороны["laravel"], стороны

    return стороны["django"]


def сообщение(text: Any, chat: Any = 555, username: Any = "aziz") -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat}, "text": text, "from": {"username": username}},
    }


@pytest.mark.parametrize(
    ("body", "токен"),
    [
        (сообщение("/start tok123"), "tok123"),
        (сообщение("  /start   tok123  ", chat="-100200", username="0"), "tok123"),
        (сообщение("/start tok123", username=None), "tok123"),
        (сообщение("/start"), "tok123"),
        (сообщение("/start other"), "tok123"),
        (сообщение("/start tok123"), None),
        (сообщение("привет"), "tok123"),
        (сообщение("/start tok123", chat=None), "tok123"),
        ({"message": "строка"}, "tok123"),
        ({}, "tok123"),
        ("не json", "tok123"),
    ],
)
def test_вебхук(сайт, body, токен):
    итог = вебхук(сайт, f"/telegram/webhook/{СЕКРЕТ}", body, сброс(токен))

    if body == сообщение("/start tok123") and токен:
        assert итог["db"]["user"][0][0] == "555" and итог["db"]["token"] is False


@pytest.mark.parametrize("path", ["/telegram/webhook/wrong-secret", "/telegram/webhook/short"])
def test_чужой_секрет(сайт, path):
    итог = вебхук(сайт, path, сообщение("/start tok123"), сброс())

    assert итог["status"] == 404
