"""
Рассылка новых объявлений и тендеров в Telegram (savdex/telegram_feed.py,
manage.py notify): кому, что и сколько раз.

Проход — в отдельном процессе Django, sendMessage подменён записью.
Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from .factories import Выражение, категория, компания, объявление, пользователь, тендер
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

APP = "https://savdex.uz"
СЕЙЧАС = Выражение("now() at time zone 'utc'")

#: Проход рассылки: сообщения записываются; чат «blocked» — заблокировал бота
ПРОХОД = """
import json, sys
import django
django.setup()
from savdex import telegram_feed
from savdex.web import messaging
sent = []
messaging.telegram_configured = lambda: True
telegram_feed.PAUSE = 0
def send(chat_id, text, buttons=None):
    if chat_id == "blocked":
        return messaging.Sent(False, blocked=True)
    sent.append({"chat": chat_id, "text": text,
                 "buttons": [[b.text, b.url] for row in buttons or [] for b in row]})
    return messaging.Sent(True)
messaging.telegram_send = send
report = telegram_feed.run()
print(json.dumps({"items": report.items, "messages": report.messages, "people": report.people,
                  "blocked": report.blocked, "sent": sent}))
"""


@pytest.fixture(scope="module", autouse=True)
def база() -> None:
    свежая_база()


def проход(**env: str) -> dict[str, Any]:
    out = subprocess.run(
        [sys.executable, "-c", ПРОХОД],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
            "APP_URL": APP,
            **env,
        },
        capture_output=True,
        text=True,
        check=True,
    )

    return dict(json.loads(out.stdout.strip().splitlines()[-1]))


@pytest.fixture
def мир() -> dict[str, Any]:
    """
    Мебель (раздел) и Диваны (подраздел), Текстиль. Три компании:
    мебельщик (подписан на «Мебель»), текстильщик, продавец без бота.
    Всё прежнее — разобрано.
    """
    sql(
        "insert into telegram_feed_items (kind, item_id, processed_at) "
        "select 'listing', id, now() from listings on conflict do nothing"
    )
    sql(
        "insert into telegram_feed_items (kind, item_id, processed_at) "
        "select 'tender', id, now() from tenders on conflict do nothing"
    )
    sql("update users set telegram_chat_id = null")
    sql("delete from notification_preferences")

    мебель = категория("Мебель")
    диваны = категория("Диваны", parent_id=мебель)
    текстиль = категория("Текстиль")

    def фирма(chat: str | None, *разделы: int, locale: str = "ru") -> dict[str, int]:
        cid = компания()
        uid = пользователь(company_id=cid, telegram_chat_id=chat, locale=locale)

        for r in разделы:
            sql("insert into company_category (company_id, category_id) values (%s, %s)", [cid, r])

        return {"cid": cid, "uid": uid}

    return {
        "мебель": мебель,
        "диваны": диваны,
        "текстиль": текстиль,
        "мебельщик": фирма("101", мебель),
        "текстильщик": фирма("202", текстиль, locale="uz"),
        "продавец": фирма(None, мебель),
        "фирма": фирма,
    }


def кому(итог: dict[str, Any]) -> list[str]:
    return sorted(m["chat"] for m in итог["sent"])


def test_объявление_в_подразделе(мир):
    lid = объявление(
        company_id=мир["продавец"]["cid"],
        category_id=мир["диваны"],
        title="Диван угловой",
        price=4_500_000,
        published_at=СЕЙЧАС,
    )
    итог = проход()

    # «Диваны» — подраздел «Мебели»: мебельщику да, текстильщику нет
    assert кому(итог) == ["101"]
    [сообщение] = итог["sent"]
    assert сообщение["text"].splitlines()[:4] == [
        "<b>Новое объявление · Продажа</b>",
        "Диваны",
        "",
        "<b>Диван угловой</b>",
    ]
    assert "Цена: 4 500 000 UZS" in сообщение["text"]
    slug = sql("select slug from listings where id = %s", [lid])[0][0]
    assert сообщение["buttons"] == [["Открыть на SAVDEX", f"{APP}/listing/{slug}"]]

    # Второй проход — ничего: объявление уже разобрано
    assert проход()["sent"] == []


def test_тендер_на_языке_получателя(мир):
    тендер(
        category_id=мир["текстиль"],
        title="Ткань для униформы",
        budget=90_000_000,
        customer="АО «Узбекнефтегаз»",
        deadline_at="2026-10-20 10:00:00",
        published_at=СЕЙЧАС,
    )
    итог = проход()

    assert кому(итог) == ["202"]
    текст = итог["sent"][0]["text"]
    assert текст.startswith("<b>Yangi tender</b>")
    assert "Byudjet: 90 000 000 UZS" in текст
    assert "Buyurtmachi: АО «Узбекнефтегаз»" in текст
    assert "20.10.2026" in текст
    assert итог["sent"][0]["buttons"][0][1].startswith(f"{APP}/uz/tenders/")


def test_кому_не_шлётся(мир):
    # Своё объявление — не новость
    объявление(company_id=мир["мебельщик"]["cid"], category_id=мир["мебель"], published_at=СЕЙЧАС)
    # Черновик, вчерашнее и старше суток, чужой раздел
    объявление(company_id=мир["продавец"]["cid"], category_id=мир["мебель"], draft=True)
    объявление(
        company_id=мир["продавец"]["cid"],
        category_id=мир["мебель"],
        published_at=Выражение("now() - interval '2 days'"),
    )
    итог = проход()

    assert итог["sent"] == []
    # Всё разобрано, кроме черновика: его опубликуют — и он станет новостью
    assert итог["items"] == 2


def test_опубликовали_после_проверки(мир):
    lid = объявление(company_id=мир["продавец"]["cid"], category_id=мир["мебель"], draft=True)
    assert проход()["sent"] == []

    sql("update listings set status = 'active', published_at = now() where id = %s", [lid])
    assert кому(проход()) == ["101"]


def test_пауза_и_заблокированные(мир):
    sql(
        "insert into notification_preferences (user_id, event, email, telegram) "
        "values (%s, 'category_feed', false, false)",
        [мир["мебельщик"]["uid"]],
    )
    заблокировал = мир["фирма"]("blocked", мир["мебель"])
    объявление(company_id=мир["продавец"]["cid"], category_id=мир["мебель"], published_at=СЕЙЧАС)
    итог = проход()

    assert итог["sent"] == [] and итог["blocked"] == 1
    # Заблокировал бота — чат у учётной записи снят
    assert sql("select telegram_chat_id from users where id = %s", [заблокировал["uid"]]) == [
        (None,)
    ]


def test_много_новинок_одним_списком(мир):
    for i in range(12):
        объявление(
            company_id=мир["продавец"]["cid"],
            category_id=мир["мебель"],
            title=f"Стол {i}",
            published_at=СЕЙЧАС,
        )

    итог = проход()

    [список] = итог["sent"]
    assert список["chat"] == "101"
    строки = список["text"].splitlines()
    assert строки[0] == "<b>Новое в ваших категориях: 12</b>"
    assert sum(1 for s in строки if s.startswith("• <a href=")) == 10
    assert строки[-1] == "…и ещё 2"
    assert список["buttons"] == [["Смотреть все", f"{APP}/catalog"]]


def test_бот_не_настроен(мир):
    объявление(company_id=мир["продавец"]["cid"], category_id=мир["мебель"], published_at=СЕЙЧАС)
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django, json; django.setup(); from savdex import telegram_feed; "
            "r = telegram_feed.run(); print(json.dumps([r.items, r.messages]))",
        ],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    )

    # Без бота ничего не разбирается: когда его настроят, свежее ещё уйдёт
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [0, 0]
    assert кому(проход()) == ["101"]
