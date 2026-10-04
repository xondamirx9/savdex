"""
Письма и Telegram по уведомлениям кабинета — то, что человек выбрал
в «Настройки → Уведомления» (notification_preferences).

Уведомление в колокольчике (user_notifications) пишут десятки мест
сайта; рассылка их не трогает. Фоновый проход (manage.py notify, раз
в минуту) берёт уведомления старше DELAY, ещё не прошедшие рассылку
(delivered_at пуст), и по каждому человеку:

- оставляет те, чей вид входит в событие настроек (EVENT_OF_TYPE) и не
  прочитан: увиденное в колокольчике — или чат, уже открытый
  в кабинете, — на почту не дублируется;
- шлёт одно письмо на всё набравшееся — галочка «email» (по умолчанию
  включена), почта подтверждена, учётная запись активна, почтовик задан
  (MAIL_MAILER smtp или log);
- и одно сообщение в Telegram — галочка «Telegram» (по умолчанию
  выключена) и привязанный бот.

Строки сначала занимаются (delivered_at = сейчас, skip locked): два
прохода — старый и новый контейнер во время деплоя — одно письмо не
отправят дважды. Письмо не ушло (почтовик недоступен) — строки
освобождаются и пробуются на следующем проходе; старше STALE — уже нет:
вчерашнее «вам написали» на почте больше путает, чем помогает.

Рассылки администратора (broadcast), напоминания об отзывах и
служебные уведомления в настройках не перечислены и на почту не идут.
"""

from __future__ import annotations

import html
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import connection, transaction

from savdex.guards import allowed_writes
from savdex.web import mail, messaging

log = logging.getLogger("savdex.deliveries")

#: Вид уведомления → событие настроек (web/cabinet.NOTIFICATION_EVENTS)
EVENT_OF_TYPE = {
    "contact_unlocked": "contact_unlocked",
    "review": "new_review",
    "moderation": "moderation",
    "listing_expiring": "listing_expiring",
    "chat": "chat",
    "billing": "billing",
    "payment": "billing",
    "promotion": "billing",
}

#: Сколько уведомление ждёт в колокольчике, прежде чем уйти на почту:
#: прочитанное за это время не дублируется письмом
DELAY = timedelta(minutes=2)

#: Дольше этого письмо не пробуется: почтовик лежал сутки — вчерашнее
#: «вам написали» уже не новость
STALE = timedelta(days=1)

#: Уведомлений за проход
LIMIT = 500

#: Текст уведомления в письме — не длиннее
BODY_LIMIT = 300

_P = (
    "box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Roboto, Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', "
    "'Segoe UI Symbol'; position: relative; font-size: 16px; line-height: 1.5em; "
    "margin-top: 0; text-align: left;"
)
_A = "color: #18181b;"
_CHAT = re.compile(r"^/cabinet/chats/([0-9]{1,18})$")


@dataclass
class Report:
    emails: int = 0
    telegrams: int = 0
    skipped: int = 0
    failed: int = 0
    users: set[int] = field(default_factory=set)

    def __str__(self) -> str:
        return (
            f"писем {self.emails}, Telegram {self.telegrams}, "
            f"без отправки {self.skipped}, не ушло {self.failed}"
        )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0, tzinfo=None)


def _rows(query: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _claim(now: datetime, limit: int) -> list[dict[str, Any]]:
    """Занять неразосланные уведомления старше DELAY (delivered_at = now)."""
    with transaction.atomic(), allowed_writes("user_notifications"):
        rows = _rows(
            "update user_notifications set delivered_at = %s where id in ("
            "  select id from user_notifications"
            "  where delivered_at is null and created_at <= %s"
            "  order by id limit %s for update skip locked"
            ") returning id, user_id, type, title, body, url, read_at, created_at",
            [now, now - DELAY, limit],
        )

    return sorted(rows, key=lambda r: r["id"])


def _release(ids: list[int]) -> None:
    """Письмо не ушло — вернуть строки следующему проходу."""
    with allowed_writes("user_notifications"), connection.cursor() as cursor:
        cursor.execute(
            "update user_notifications set delivered_at = null where id = any(%s)", [ids]
        )


def _chat_seen(row: dict[str, Any], company_id: int | None) -> bool:
    """Переписку уже открыли в кабинете после этого сообщения."""
    found = _CHAT.match(row["url"] or "")

    if found is None or company_id is None:
        return False

    threads = _rows(
        "select buyer_company_id, buyer_read_at, seller_read_at from message_threads where id = %s",
        [int(found.group(1))],
    )

    if not threads:
        return False

    thread = threads[0]
    read_at = (
        thread["buyer_read_at"]
        if thread["buyer_company_id"] == company_id
        else thread["seller_read_at"]
    )

    return read_at is not None and read_at >= row["created_at"]


def _app_url() -> str:
    return (os.environ.get("APP_URL") or "http://localhost").rstrip("/")


def _link(row: dict[str, Any]) -> str:
    return _app_url() + (row["url"] or "/notifications")


def _body(row: dict[str, Any]) -> str:
    text = " ".join(str(row["body"] or "").split())

    return text if len(text) <= BODY_LIMIT else text[: BODY_LIMIT - 1].rstrip() + "…"


def _subject(rows: list[dict[str, Any]]) -> str:
    """Заголовок первого; есть ещё — «(+N)»: без слов, на любом языке."""
    first = " ".join(str(rows[0]["title"]).split())

    return first if len(rows) == 1 else f"{first} (+{len(rows) - 1})"


def _items_html(rows: list[dict[str, Any]]) -> str:
    parts = []

    for row in rows:
        title = html.escape(str(row["title"]))

        # Одно уведомление ведёт кнопка письма; у нескольких — каждое своей ссылкой
        if len(rows) > 1:
            link = html.escape(_link(row), quote=True)
            title = f'<a href="{link}" style="{_A}">{title}</a>'

        body = html.escape(_body(row))
        tail = f"<br>{body}" if body else ""
        parts.append(f'<p style="{_P}"><strong>{title}</strong>{tail}</p>')

    return "\n".join(parts)


def _items_text(rows: list[dict[str, Any]]) -> str:
    parts = []

    for row in rows:
        lines = [f"— {row['title']}"]

        if _body(row):
            lines.append(f"  {_body(row)}")

        if len(rows) > 1:
            lines.append(f"  {_link(row)}")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _email(user: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    url = _link(rows[0]) if len(rows) == 1 else _app_url() + "/notifications"
    subject, body_html, body_text = mail.render(
        "notification",
        url=url,
        app_url=_app_url(),
        lang=user["locale"],
        fields={
            "SUBJECT": _subject(rows),
            "ITEMS": _items_text(rows),
            "SETTINGS_URL": _app_url() + "/cabinet/settings",
        },
        html_fields={"ITEMS": _items_html(rows)},
    )

    return mail.send(str(user["email"]), subject, body_html, body_text)


def _telegram(user: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    text = "\n\n".join(
        "\n".join(line for line in (str(row["title"]), _body(row), _link(row)) if line)
        for row in rows
    )

    return messaging.telegram(str(user["telegram_chat_id"]), text)


def run(now: datetime | None = None, limit: int = LIMIT) -> Report:
    """Один проход рассылки."""
    now = now or _now()
    report = Report()
    claimed = _claim(now, limit)

    if not claimed:
        return report

    by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for row in claimed:
        by_user[row["user_id"]].append(row)

    users = {
        u["id"]: u
        for u in _rows(
            "select id, email, email_verified_at, locale, status, deleted_at, company_id, "
            "telegram_chat_id from users where id = any(%s)",
            [list(by_user)],
        )
    }
    prefs: dict[tuple[int, str], dict[str, Any]] = {
        (p["user_id"], p["event"]): p
        for p in _rows(
            "select user_id, event, email, telegram from notification_preferences "
            "where user_id = any(%s)",
            [list(by_user)],
        )
    }
    telegram_on = messaging.telegram_configured()
    # Почтовик не задан — письма уведомлений не пишутся даже в журнал:
    # иначе без SMTP файл журнала в контейнере растёт с каждым проходом
    email_on = os.environ.get("MAIL_MAILER") in ("smtp", "log")

    for user_id, rows in by_user.items():
        user = users.get(user_id)
        fresh = [
            row
            for row in rows
            if row["type"] in EVENT_OF_TYPE
            and row["read_at"] is None
            and row["created_at"] > now - STALE
        ]

        if user is None or user["deleted_at"] is not None or user["status"] != "active":
            fresh = []

        company_id = user["company_id"] if user else None
        fresh = [row for row in fresh if not _chat_seen(row, company_id)]

        def wanted(row: dict[str, Any], channel: str, default: bool, owner: int = user_id) -> bool:
            pref = prefs.get((owner, EVENT_OF_TYPE[row["type"]]))
            value = pref.get(channel) if pref else None

            return default if value is None else bool(value)

        by_email = [row for row in fresh if wanted(row, "email", True)]
        by_telegram = [row for row in fresh if wanted(row, "telegram", False)]

        if not (email_on and user and user["email"] and user["email_verified_at"]):
            by_email = []

        if not (user and user["telegram_chat_id"] and telegram_on):
            by_telegram = []

        report.skipped += len(rows) - len({r["id"] for r in by_email + by_telegram})

        if by_email:
            assert user is not None

            if not _email(user, by_email):
                report.failed += len(rows)
                _release([row["id"] for row in rows])
                continue

            report.emails += 1
            report.users.add(user_id)

        if by_telegram:
            assert user is not None

            if _telegram(user, by_telegram):
                report.telegrams += 1
                report.users.add(user_id)

    return report
