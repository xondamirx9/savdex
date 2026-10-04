"""
Письма и Telegram по уведомлениям кабинета (savdex/deliveries.py,
manage.py notify): что уходит, что нет и сколько раз.

Почта — почтовиком log в файл, Telegram — подменой messaging.telegram
в отдельном процессе Django. Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import email
import json
import subprocess
import sys
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from .factories import компания, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

APP = "https://savdex.uz"

#: Проход рассылки в отдельном процессе: Telegram записывается, а не шлётся
ПРОХОД = """
import json, sys
import django
django.setup()
from savdex import deliveries
from savdex.web import messaging
sent = []
messaging.telegram_configured = lambda: True
def telegram(chat_id, text):
    sent.append({"chat_id": chat_id, "text": text})
    return True
messaging.telegram = telegram
report = deliveries.run()
print(json.dumps({"emails": report.emails, "telegrams": report.telegrams,
                  "skipped": report.skipped, "failed": report.failed, "sent": sent}))
"""


@pytest.fixture(scope="module", autouse=True)
def база() -> None:
    свежая_база()


@pytest.fixture
def почта(tmp_path: Path) -> Path:
    sql("update user_notifications set delivered_at = now()")

    return tmp_path / "mail.log"


def проход(почта: Path, **env: str) -> dict[str, Any]:
    out = subprocess.run(
        [sys.executable, "-c", ПРОХОД],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
            "APP_URL": APP,
            "MAIL_MAILER": "log",
            "MAIL_LOG_PATH": str(почта),
            **env,
        },
        capture_output=True,
        text=True,
        check=True,
    )

    return dict(json.loads(out.stdout.strip().splitlines()[-1]))


def письма(почта: Path) -> list[Message]:
    if not почта.exists():
        return []

    сырьё = почта.read_text(encoding="utf-8")
    куски = [к for к in сырьё.split("\nContent-Type: multipart/alternative") if к.strip()]

    return [
        email.message_from_string(("Content-Type: multipart/alternative" + к) if i else к)
        for i, к in enumerate(куски)
    ]


def части(письмо: Message) -> tuple[str, str]:
    """Текст и HTML; 8bit в журнале — уже строкой, base64 и QP — раскодировать."""
    тела = {}

    for часть in письмо.walk():
        if часть.get_content_type() not in ("text/plain", "text/html"):
            continue

        if часть["Content-Transfer-Encoding"] in ("base64", "quoted-printable"):
            сырое = часть.get_payload(decode=True)
            assert isinstance(сырое, bytes)
            тела[часть.get_content_type()] = сырое.decode()
        else:
            тела[часть.get_content_type()] = str(часть.get_payload())

    return тела.get("text/plain", ""), тела.get("text/html", "")


def тема(письмо: Message) -> str:
    return str(email.header.make_header(email.header.decode_header(письмо["Subject"])))


def человек(**поля: Any) -> int:
    return пользователь(company_id=компания(), **поля)


def уведомление(uid: int, type_: str = "contact_unlocked", **поля: Any) -> int:
    данные = {
        "title": "Ваш контакт открыла ООО «Ромашка»",
        "body": "По объявлению «Цемент М500»",
        "url": "/cabinet/incoming",
        "tone": "success",
        "минут": 5,
        **поля,
    }
    минут = данные.pop("минут")
    [(nid,)] = sql(
        "insert into user_notifications (user_id, company_id, type, title, body, tone, url, "
        "read_at, created_at, updated_at) values (%s, (select company_id from users "
        "where id = %s), %s, %s, %s, %s, %s, %s, now() at time zone 'utc' - make_interval("
        "mins => %s), now()) returning id",
        [
            uid,
            uid,
            type_,
            данные["title"],
            данные["body"],
            данные["tone"],
            данные["url"],
            данные.get("read_at"),
            минут,
        ],
    )

    return int(nid)


def настройка(uid: int, event: str, email_: bool, telegram: bool) -> None:
    sql(
        "insert into notification_preferences (user_id, event, email, telegram, created_at, "
        "updated_at) values (%s, %s, %s, %s, now(), now())",
        [uid, event, email_, telegram],
    )


def разослано(nid: int) -> bool:
    return sql("select delivered_at is not null from user_notifications where id = %s", [nid]) == [
        (True,)
    ]


def test_одно_уведомление_одно_письмо_на_языке_человека(почта):
    uid = человек(email="owner-uz@savdex.uz", locale="uz")
    nid = уведомление(uid)

    итог = проход(почта)

    assert (итог["emails"], итог["telegrams"]) == (1, 0)
    [письмо] = письма(почта)
    текст, html = части(письмо)

    assert письмо["To"] == "owner-uz@savdex.uz"
    assert тема(письмо) == "Ваш контакт открыла ООО «Ромашка» — SAVDEX"
    assert "SAVDEX kabinetingizda yangiliklar:" in текст
    assert "— Ваш контакт открыла ООО «Ромашка»\n  По объявлению «Цемент М500»" in текст
    assert f"Ochish: {APP}/cabinet/incoming" in текст
    assert f"{APP}/cabinet/settings" in текст
    assert "<strong>Ваш контакт открыла ООО «Ромашка»</strong>" in html
    assert f'href="{APP}/cabinet/incoming"' in html
    assert f'href="{APP}/cabinet/settings"' in html
    assert ' lang="uz">' in html
    assert разослано(nid)

    # Второй проход ничего не повторяет
    assert проход(почта)["emails"] == 0
    assert len(письма(почта)) == 1


def test_несколько_уведомлений_одним_письмом(почта):
    uid = человек()
    уведомление(uid, "review", title="Новый отзыв ★5", url="/cabinet/reviews")
    уведомление(uid, "billing", title="Оплата получена", url="/cabinet/billing", минут=4)

    итог = проход(почта)

    assert итог["emails"] == 1
    [письмо] = письма(почта)
    текст, html = части(письмо)

    assert тема(письмо) == "Новый отзыв ★5 (+1) — SAVDEX"
    # Кнопка — на все уведомления, у каждого своя ссылка
    assert f"Открыть: {APP}/notifications" in текст
    assert f'<a href="{APP}/cabinet/reviews"' in html and f'<a href="{APP}/cabinet/billing"' in html


@pytest.mark.parametrize(
    ("поля", "уведомления"),
    [
        # Прочитано в колокольчике — на почту не дублируется
        ({}, [{"read_at": "2026-01-01 00:00:00"}]),
        # Совсем свежее — ждёт, вдруг человек увидит его на сайте
        ({}, [{"минут": 1}]),
        # Рассылка администратора и напоминание об отзыве — не из настроек
        ({}, [{"type_": "broadcast"}, {"type_": "platform_review_ask"}]),
        # Почта не подтверждена; учётная запись заблокирована или удалена
        ({"email_verified_at": None}, [{}]),
        ({"status": "blocked"}, [{}]),
        ({"deleted_at": "2026-01-01 00:00:00"}, [{}]),
        # Уведомление старше суток — уже не новость
        ({}, [{"минут": 60 * 25}]),
    ],
)
def test_что_не_уходит(почта, поля, уведомления):
    uid = человек(**поля)
    ids = [уведомление(uid, **у) for у in уведомления]

    итог = проход(почта)

    assert итог["emails"] == 0 and письма(почта) == []
    # Кроме совсем свежего, всё помечено пройденным и не пересматривается
    assert [разослано(nid) for nid in ids] == [у.get("минут") != 1 for у in уведомления]


def test_галочки_настроек(почта):
    uid = человек(telegram_chat_id="555")
    настройка(uid, "contact_unlocked", False, True)
    настройка(uid, "new_review", True, False)
    уведомление(uid, "contact_unlocked")
    уведомление(uid, "review", title="Новый отзыв", url="/cabinet/reviews")
    # Без строки настроек: почта — да, Telegram — нет
    уведомление(uid, "chat", title="Новое сообщение", url="/cabinet/chats/999999")

    итог = проход(почта)

    assert (итог["emails"], итог["telegrams"]) == (1, 1)
    текст, _ = части(письма(почта)[0])
    assert "Новый отзыв" in текст and "Новое сообщение" in текст
    assert "Ваш контакт открыла" not in текст
    [сообщение] = итог["sent"]
    assert сообщение["chat_id"] == "555"
    assert сообщение["text"] == (
        f"Ваш контакт открыла ООО «Ромашка»\nПо объявлению «Цемент М500»\n{APP}/cabinet/incoming"
    )


def test_telegram_без_привязки_не_шлётся(почта):
    uid = человек()
    настройка(uid, "moderation", False, True)
    nid = уведомление(uid, "moderation", title="Объявление опубликовано")

    итог = проход(почта)

    assert (итог["emails"], итог["telegrams"]) == (0, 0) and разослано(nid)


def test_прочитанная_переписка_не_приходит_письмом(почта):
    uid = человек()
    [(company,)] = sql("select company_id from users where id = %s", [uid])
    другая = компания()
    [(thread,)] = sql(
        "insert into message_threads (buyer_company_id, seller_company_id, buyer_read_at, "
        "created_at, updated_at) values (%s, %s, now() at time zone 'utc', now(), now()) "
        "returning id",
        [company, другая],
    )
    уведомление(uid, "chat", title="Новое сообщение", url=f"/cabinet/chats/{thread}")

    assert проход(почта)["emails"] == 0


def test_почтовик_недоступен_повтор_на_следующем_проходе(почта):
    uid = человек()
    nid = уведомление(uid)

    итог = проход(почта, MAIL_MAILER="smtp", MAIL_HOST="127.0.0.1", MAIL_PORT="1", MAIL_TIMEOUT="2")

    assert (итог["emails"], итог["failed"]) == (0, 1)
    assert not разослано(nid)

    assert проход(почта)["emails"] == 1 and разослано(nid)


def test_текст_уведомления_с_метками_и_разметкой(почта):
    """Отзыв с «__URL__» и <b> — текстом, без подстановки и без разметки."""
    uid = человек()
    уведомление(uid, "review", title="Отзыв <b>x</b>", body="см. __URL__ " + "я" * 400)

    проход(почта)
    текст, html = части(письма(почта)[0])

    assert "Отзыв &lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert "см. __URL__ " in текст and "см. __URL__ " in html
    assert "я" * 280 in текст and "я" * 300 not in текст and "я…" in текст


def test_без_почтовика_писем_нет(почта):
    uid = человек()
    nid = уведомление(uid)

    assert проход(почта, MAIL_MAILER="")["emails"] == 0
    assert письма(почта) == [] and разослано(nid)
