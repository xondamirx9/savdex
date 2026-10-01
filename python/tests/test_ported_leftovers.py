"""
Последнее, что было только в PHP (сверка перед удалением Laravel):
команда telegram:webhook, предупреждение «База отвечает медленно»
и порядок разделов админки, как в меню Filament.
"""

from __future__ import annotations

import logging
from io import StringIO
from typing import Any

import httpx
import pytest
from django.core.management import call_command
from django.test import RequestFactory

from savdex.web import messaging, slowdb

# ── telegram_webhook ─────────────────────────────────────────────────


@pytest.fixture
def бот(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "@savdex_bot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret-12345")
    monkeypatch.setenv("APP_URL", "https://savdex.uz/")
    вызовы: list[tuple[str, str, Any]] = []

    def ответ(method: str, url: str, status: int, body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(status, json=body, request=httpx.Request(method, url))

    состояние: dict[str, Any] = {"status": 200, "body": {"ok": True, "description": "ok"}}

    def post(url: str, json: Any = None, timeout: float = 0) -> httpx.Response:
        вызовы.append(("POST", url, json))

        return ответ("POST", url, состояние["status"], состояние["body"])

    def get(url: str, timeout: float = 0) -> httpx.Response:
        вызовы.append(("GET", url, None))

        return ответ("GET", url, состояние["status"], состояние["body"])

    monkeypatch.setattr(messaging.httpx, "post", post)
    monkeypatch.setattr(messaging.httpx, "get", get)

    return вызовы, состояние


def запуск(*args: str) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()

    try:
        call_command("telegram_webhook", *args, stdout=out, stderr=err)
    except SystemExit as e:
        return int(e.code or 0), out.getvalue(), err.getvalue()

    return 0, out.getvalue(), err.getvalue()


def test_регистрация_адреса(бот):
    вызовы, _ = бот
    код, out, _ = запуск()

    assert код == 0
    assert "https://savdex.uz/telegram/webhook/secret-12345" in out
    assert вызовы == [
        (
            "POST",
            "https://api.telegram.org/bot123:abc/setWebhook",
            {
                "url": "https://savdex.uz/telegram/webhook/secret-12345",
                "drop_pending_updates": True,
            },
        )
    ]


def test_чужой_токен_по_русски(бот):
    _, состояние = бот
    состояние.update(status=404, body={"ok": False, "description": "Not Found"})
    код, _, err = запуск()

    assert код == 1 and "Telegram не знает такого бота" in err


def test_снять_адрес(бот):
    вызовы, _ = бот

    assert запуск("--delete")[0] == 0
    assert вызовы[0][1].endswith("/deleteWebhook")


def test_что_знает_telegram(бот):
    _, состояние = бот
    состояние["body"] = {
        "ok": True,
        "result": {"url": "https://old/x", "pending_update_count": 3, "last_error_message": "boom"},
    }
    код, out, _ = запуск("--info")

    assert код == 0
    assert "Адрес у Telegram: https://old/x" in out and "Ожидает доставки: 3" in out
    assert "Последняя ошибка: boom" in out and "отличается" in out


def test_без_секрета_и_без_бота(бот, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    код, _, err = запуск()
    assert код == 1 and "TELEGRAM_WEBHOOK_SECRET" in err

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    код, _, err = запуск()
    assert код == 1 and "Бот не настроен" in err


# ── «База отвечает медленно» ────────────────────────────────────────


def test_медленная_страница_один_раз(monkeypatch, caplog):
    часы = iter([0.0, 0.1, 1.0, 1.3, 2.0, 2.2, 3.0, 3.1])
    monkeypatch.setattr(slowdb.time, "perf_counter", lambda: next(часы))
    watch = slowdb._Watch(RequestFactory().get("/catalog"))

    def execute(sql: str, *_: Any) -> None:
        return None

    with caplog.at_level(logging.WARNING, logger="savdex"):
        for sql in ("select 1", "select   2\n from x", "select 3", "select 4"):
            watch(execute, sql, None, False, {})

    записи = [r.getMessage() for r in caplog.records if "медленно" in r.getMessage()]

    # 100 + 300 мс — ещё нет; + 200 мс — порог пройден на третьем запросе;
    # четвёртый уже не пишет
    assert len(записи) == 1
    assert '"запросов": 3' in записи[0] and '"всего_мс": 600' in записи[0]
    assert '"на_запросе": "select 3"' in записи[0] and '"этот_мс": 200' in записи[0]
    assert '"страница": "GET catalog"' in записи[0]


# ── Меню админки ────────────────────────────────────────────────────


def test_порядок_разделов_как_в_filament():
    from savdex.adminsite import MENU_ORDER

    # «Возвраты» после «Счетов и оплат» (8e32f2a)
    assert MENU_ORDER["finance.payment"] < MENU_ORDER["finance.refund"]
    assert MENU_ORDER["finance.subscription"] < MENU_ORDER["finance.payment"]
