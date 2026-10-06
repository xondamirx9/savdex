"""
Разговор с Telegram-ботом: привязка к учётной записи по ИНН компании
и меню уведомлений о новых объявлениях и тендерах (рассылка —
savdex/telegram_feed.py).

Два входа, оба через ИНН:

- человек открыл бота сам (/start без токена): ИНН → компания найдена →
  почта, с которой он входит на сайт (учётная запись этой компании) →
  код из письма на эту почту → чат привязан к его учётной записи. Так
  каждый сотрудник компании привязывает свой аккаунт, а не владельца;
- кнопка «Привязать Telegram» в кабинете (/start <токен>): человек уже
  вошёл на сайт, кода нет — ИНН только сверяется с его компанией.

ИНН нет на сайте — «зарегистрируйтесь» и ссылка. Неверных ИНН и почт
подряд MAX_MISTAKES, кодов — CODE_TRIES: пауза LOCK. Писем с кодом —
не больше CODES_PER_HOUR в час на чат.

Состояние разговора — telegram_bot_chats (шаг, ИНН, кому ушёл код,
хеш кода, счётчики). Категории в боте не выбираются: они общие на
компанию и меняются на сайте («Настройки → Категории»), бот даёт кнопку
туда и паузу рассылки (notification_preferences, событие category_feed).
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import connection

from savdex import laravel_cache
from savdex.guards import allowed_writes
from savdex.web import eloquent, locales, mail, messaging, ui
from savdex.web.listing_actions import _now
from savdex.web.messaging import Button
from savdex.web.settings_actions import LINK_PREFIX

#: Событие настроек уведомлений: рассылка по категориям (галочка «Telegram»)
FEED_EVENT = "category_feed"

MAX_MISTAKES = 10
CODE_TRIES = 3
LOCK = timedelta(minutes=15)
CODE_TTL = timedelta(minutes=10)
CODES_PER_HOUR = 5

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── База ─────────────────────────────────────────────────────────────


def _rows(query: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _execute(query: str, params: list[Any]) -> None:
    with allowed_writes("telegram_bot_chats"), connection.cursor() as cursor:
        cursor.execute(query, params)


def _chat(chat_id: str, language: str) -> dict[str, Any]:
    """Строка разговора; новая — на языке Telegram, уже привязанный чат — сразу «done»."""
    found = _rows("select * from telegram_bot_chats where chat_id = %s", [chat_id])

    if found:
        return found[0]

    linked = _linked_user(chat_id)
    locale = linked["locale"] if linked else (language if locales.supports(language) else "ru")
    now = _now()
    _execute(
        "insert into telegram_bot_chats (chat_id, state, locale, created_at, updated_at) "
        "values (%s, %s, %s, %s, %s) on conflict (chat_id) do nothing",
        [chat_id, "done" if linked else "inn", locale, now, now],
    )

    return _rows("select * from telegram_bot_chats where chat_id = %s", [chat_id])[0]


def _update(chat: dict[str, Any], **changes: Any) -> None:
    changes["updated_at"] = _now()
    columns = ", ".join(f"{name} = %s" for name in changes)
    _execute(
        f"update telegram_bot_chats set {columns} where chat_id = %s",
        [*changes.values(), chat["chat_id"]],
    )
    chat.update(changes)


def _linked_user(chat_id: str) -> dict[str, Any] | None:
    rows = _rows(
        "select * from users where telegram_chat_id = %s and deleted_at is null "
        "and status = 'active' order by telegram_linked_at desc nulls last, id desc limit 1",
        [chat_id],
    )

    return rows[0] if rows else None


def _active_user(user_id: object) -> dict[str, Any] | None:
    rows = _rows(
        "select * from users where id = %s and deleted_at is null and status = 'active'",
        [user_id],
    )

    return rows[0] if rows else None


def _companies(tin: str) -> list[dict[str, Any]]:
    """Действующие компании с этим ИНН (в базе ИНН бывает с пробелами)."""
    return _rows(
        "select id, name from companies where deleted_at is null and status = 'active' "
        "and regexp_replace(coalesce(tin, ''), '[^0-9]', '', 'g') = %s order by id",
        [tin],
    )


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _is_tin(text: str) -> bool:
    """9 цифр — ИНН юрлица, 14 — ПИНФЛ у ИП; пробелы и дефисы не мешают."""
    return re.fullmatch(r"[\d\s-]+", text) is not None and len(_digits(text)) in (9, 14)


# ── Ответы ───────────────────────────────────────────────────────────


def _t(chat: dict[str, Any], key: str, **replace: object) -> str:
    return ui.t(f"messages.bot.{key}", chat["locale"], **replace)


def _app_url(chat: dict[str, Any], path: str) -> str:
    root = (os.environ.get("APP_URL") or "http://localhost").rstrip("/")

    return root + locales.prefix(chat["locale"]) + path


def _say(chat: dict[str, Any], text: str, buttons: list[list[Button]] | None = None) -> None:
    messaging.telegram_send(chat["chat_id"], text, buttons)


def _e(value: object) -> str:
    return html.escape(str(value), quote=False)


def _register_button(chat: dict[str, Any]) -> list[list[Button]]:
    return [[Button(_t(chat, "btn_register"), _app_url(chat, "/register"))]]


def _locked(chat: dict[str, Any], now: datetime) -> bool:
    until = chat["locked_until"]

    if until is None or until <= now:
        return False

    minutes = max(1, -(-int((until - now).total_seconds()) // 60))
    _say(chat, _t(chat, "locked", minutes=minutes))

    return True


def _mistake(chat: dict[str, Any], limit: int = MAX_MISTAKES) -> int:
    """Ещё одна ошибка; на пороге — пауза. Вернуть, сколько попыток осталось."""
    mistakes = int(chat["mistakes"]) + 1

    if mistakes >= limit:
        _update(chat, mistakes=0, locked_until=_now() + LOCK)

        return 0

    _update(chat, mistakes=mistakes)

    return limit - mistakes


# ── Категории и пауза ────────────────────────────────────────────────


def categories_of(company_id: object, locale: str) -> list[str]:
    from savdex.web.directory import _named

    ids = [
        r["category_id"]
        for r in _rows(
            "select category_id from company_category where company_id = %s order by id",
            [company_id],
        )
    ]

    if not ids:
        return []

    names = _named("categories", locale)

    return [names.get(i, str(i)) for i in ids]


def feed_on(user_id: object) -> bool:
    """Галочка рассылки по категориям: по умолчанию включена."""
    rows = _rows(
        "select telegram from notification_preferences where user_id = %s and event = %s",
        [user_id, FEED_EVENT],
    )

    return not rows or rows[0]["telegram"] is None or bool(rows[0]["telegram"])


def _set_feed(user_id: int, on: bool) -> None:
    from savdex.web.actions import _save_preference

    _save_preference(user_id, FEED_EVENT, False, on)


def _menu_buttons(chat: dict[str, Any], on: bool) -> list[list[Button]]:
    toggle = (
        Button(_t(chat, "btn_pause"), data="pause")
        if on
        else (Button(_t(chat, "btn_resume"), data="resume"))
    )

    return [
        [Button(_t(chat, "btn_categories"), _app_url(chat, "/cabinet/settings#categories"))],
        [toggle],
    ]


def _categories_text(chat: dict[str, Any], user: dict[str, Any]) -> str:
    names = categories_of(user["company_id"], chat["locale"])

    if not names:
        return _t(chat, "no_categories")

    return "\n".join(f"• {_e(name)}" for name in names)


def _menu(chat: dict[str, Any], user: dict[str, Any]) -> None:
    on = feed_on(user["id"])
    state = _t(chat, "state_on" if on else "state_off")
    _say(
        chat,
        _t(chat, "menu", state=state, categories=_categories_text(chat, user)),
        _menu_buttons(chat, on),
    )


# ── Привязка ─────────────────────────────────────────────────────────


def _link(ctx: Any, chat: dict[str, Any], user: dict[str, Any], username: str) -> None:  # noqa: ANN401
    """Чат — этому человеку: у прежнего владельца чата он снимается."""
    others = _rows(
        "select * from users where telegram_chat_id = %s and id <> %s",
        [chat["chat_id"], user["id"]],
    )

    for other in others:
        eloquent.save(
            ctx,
            "users",
            other,
            {"telegram_chat_id": None, "telegram_username": None, "telegram_linked_at": None},
            section="users",
            model="User",
        )

    eloquent.save(
        ctx,
        "users",
        user,
        {
            "telegram_chat_id": chat["chat_id"],
            # У PHP «0» тоже пусто — как в прежней привязке
            "telegram_username": None if username in ("", "0") else username,
            "telegram_linked_at": eloquent.now(),
        },
        section="users",
        model="User",
    )
    locale = user["locale"] if locales.supports(user["locale"]) else chat["locale"]
    _update(
        chat,
        state="done",
        locale=locale,
        link_user_id=None,
        tin=None,
        user_id=None,
        code_hash=None,
        code_expires_at=None,
        mistakes=0,
        locked_until=None,
    )
    on = feed_on(user["id"])
    _say(
        chat,
        _t(chat, "linked", name=_e(user["name"]), categories=_categories_text(chat, user)),
        _menu_buttons(chat, on),
    )


def _claim(token: str) -> dict[str, Any] | None:
    """Токен кнопки кабинета одноразовый — сразу из кэша прочь."""
    key = LINK_PREFIX + token
    user_id = laravel_cache.get(key)

    if user_id is None:
        return None

    laravel_cache.forget(key)

    return _active_user(user_id)


def _start(chat: dict[str, Any], token: str) -> None:
    if token == "":
        user = _linked_user(chat["chat_id"])

        if user is not None and chat["link_user_id"] is None:
            _update(chat, state="done")
            _menu(chat, user)

            return

        _update(chat, state="inn", tin=None, user_id=None, code_hash=None)
        _say(chat, _t(chat, "ask_inn"))

        return

    user = _claim(token)

    if user is None:
        _say(chat, ui.t("messages.auth.telegram_link_expired", chat["locale"]))

        return

    locale = user["locale"] if locales.supports(user["locale"]) else chat["locale"]
    _update(
        chat,
        state="inn",
        locale=locale,
        link_user_id=user["id"],
        tin=None,
        user_id=None,
        code_hash=None,
        mistakes=0,
    )
    _say(chat, _t(chat, "link_ask_inn", name=_e(user["name"])))


def _inn(ctx: Any, chat: dict[str, Any], text: str, username: str) -> None:  # noqa: ANN401
    if not _is_tin(text):
        _mistake(chat)
        _say(chat, _t(chat, "inn_invalid"))

        return

    tin = _digits(text)
    companies = _companies(tin)

    # Пришёл кнопкой из кабинета: ИНН сверяется с его компанией, кода нет
    if chat["link_user_id"] is not None:
        user = _active_user(chat["link_user_id"])

        if user is None:
            _update(chat, link_user_id=None)
            _say(chat, ui.t("messages.auth.telegram_link_expired", chat["locale"]))

            return

        if user["company_id"] is None:
            _say(chat, _t(chat, "no_company"))

            return

        if any(c["id"] == user["company_id"] for c in companies):
            _link(ctx, chat, user, username)

            return

        _mistake(chat)

        if companies:
            _say(chat, _t(chat, "inn_wrong"))
        else:
            _say(chat, _t(chat, "inn_not_found", tin=tin), _register_button(chat))

        return

    if not companies:
        _mistake(chat)
        _say(chat, _t(chat, "inn_not_found", tin=tin), _register_button(chat))

        return

    _update(chat, state="email", tin=tin, user_id=None, code_hash=None)
    _say(chat, _t(chat, "ask_email", company=_e(companies[0]["name"])))


def _mask(email: str) -> str:
    """sa***@gmail.com: человек узнаёт свою почту, посторонний — нет."""
    name, _, domain = email.partition("@")

    return f"{name[:2]}***@{domain}"


def _hash(chat_id: str, code: str) -> str:
    return hmac.new(
        str(settings.SECRET_KEY).encode(), f"{chat_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _send_code(chat: dict[str, Any], user: dict[str, Any], now: datetime) -> bool:
    window = chat["codes_window_at"]
    sent = chat["codes_sent"] if window is not None and window > now - timedelta(hours=1) else 0

    if sent >= CODES_PER_HOUR:
        _say(chat, _t(chat, "too_many_codes"))

        return False

    code = f"{secrets.randbelow(1_000_000):06d}"
    subject, body_html, body_text = mail.render(
        "telegram_code",
        url="",
        app_url=(os.environ.get("APP_URL") or "http://localhost").rstrip("/"),
        lang=user["locale"] if locales.supports(user["locale"]) else chat["locale"],
        code=code,
    )

    if not mail.send(str(user["email"]), subject, body_html, body_text):
        _say(chat, _t(chat, "mail_failed"))

        return False

    _update(
        chat,
        state="code",
        user_id=user["id"],
        code_hash=_hash(chat["chat_id"], code),
        code_expires_at=now + CODE_TTL,
        mistakes=0,
        codes_sent=sent + 1,
        codes_window_at=window if sent else now,
    )
    _say(chat, _t(chat, "code_sent", email=_e(_mask(str(user["email"])))))

    return True


def _email(chat: dict[str, Any], text: str, now: datetime) -> None:
    email = text.strip()

    if not _EMAIL.match(email):
        _say(chat, _t(chat, "email_invalid"))

        return

    users = _rows(
        "select u.* from users u join companies c on c.id = u.company_id "
        "where lower(u.email) = lower(%s) and u.deleted_at is null and u.status = 'active' "
        "and c.deleted_at is null and c.status = 'active' "
        "and regexp_replace(coalesce(c.tin, ''), '[^0-9]', '', 'g') = %s "
        "order by u.id limit 1",
        [email, chat["tin"] or ""],
    )

    if not users:
        _mistake(chat)
        _say(chat, _t(chat, "email_wrong"))

        return

    _send_code(chat, users[0], now)


def _code(ctx: Any, chat: dict[str, Any], text: str, username: str, now: datetime) -> None:  # noqa: ANN401
    code = _digits(text)

    if chat["code_expires_at"] is None or chat["code_expires_at"] <= now:
        _update(chat, state="email", code_hash=None, code_expires_at=None)
        _say(chat, _t(chat, "code_expired"))

        return

    if len(code) == 6 and hmac.compare_digest(
        _hash(chat["chat_id"], code), chat["code_hash"] or ""
    ):
        user = _active_user(chat["user_id"])

        if user is None:
            _update(chat, state="inn", user_id=None, code_hash=None)
            _say(chat, _t(chat, "ask_inn"))

            return

        _link(ctx, chat, user, username)

        return

    left = _mistake(chat, CODE_TRIES)

    if left == 0:
        # Пауза уже стоит; новый код — заново с почты
        _update(chat, state="email", code_hash=None, code_expires_at=None)
        _locked(chat, _now())

        return

    _say(chat, _t(chat, "code_wrong", left=left))


# ── Вход из вебхука ──────────────────────────────────────────────────


def _string(value: object) -> str:
    if value is None or isinstance(value, dict | list):
        return ""

    if isinstance(value, bool):
        return "1" if value else ""

    return str(value)


def handle(ctx: Any, update: dict[str, Any]) -> None:  # noqa: ANN401
    """Одно обновление Telegram: сообщение или нажатие кнопки."""
    callback = update.get("callback_query")

    if isinstance(callback, dict):
        _callback(callback)

        return

    message = update.get("message")

    if not isinstance(message, dict):
        return

    chat_info = message.get("chat")
    raw_sender = message.get("from")
    sender: dict[str, Any] = raw_sender if isinstance(raw_sender, dict) else {}
    chat_id = _string(chat_info.get("id")) if isinstance(chat_info, dict) else ""
    text = _string(message.get("text")).strip()

    if chat_id == "" or text == "" or not messaging.telegram_configured():
        return

    username = _string(sender.get("username"))
    chat = _chat(chat_id, _string(sender.get("language_code"))[:2])
    now = _now()

    if text.startswith("/start"):
        token = text[len("/start") :].strip()

        # Кнопка кабинета — новый вход: прежняя пауза ей не помеха
        if token == "" and _locked(chat, now):
            return

        _start(chat, token)

        return

    if _locked(chat, now):
        return

    user = _linked_user(chat_id)

    if chat["state"] == "done":
        if user is None:
            _update(chat, state="inn")
            _say(chat, _t(chat, "ask_inn"))
        else:
            _menu(chat, user)

        return

    # Новый ИНН можно ввести на любом шаге: 9 или 14 цифр — не почта и не код
    if chat["state"] == "inn" or _is_tin(text):
        if chat["state"] != "inn":
            _update(chat, state="inn", user_id=None, code_hash=None)

        _inn(ctx, chat, text, username)
    elif chat["state"] == "email" or _EMAIL.match(text):
        _email(chat, text, now)
    else:
        _code(ctx, chat, text, username, now)


def _callback(callback: dict[str, Any]) -> None:
    """Кнопки «Поставить на паузу» и «Включить уведомления»."""
    callback_id = _string(callback.get("id"))
    message = callback.get("message")
    chat_info = message.get("chat") if isinstance(message, dict) else None
    chat_id = _string(chat_info.get("id")) if isinstance(chat_info, dict) else ""
    data = _string(callback.get("data"))
    messaging.telegram_answer(callback_id)

    if chat_id == "" or data not in ("pause", "resume") or not messaging.telegram_configured():
        return

    raw_sender = callback.get("from")
    sender: dict[str, Any] = raw_sender if isinstance(raw_sender, dict) else {}
    chat = _chat(chat_id, _string(sender.get("language_code"))[:2])
    user = _linked_user(chat_id)

    if user is None:
        _say(chat, _t(chat, "ask_inn"))

        return

    on = data == "resume"
    _set_feed(int(user["id"]), on)
    _say(chat, _t(chat, "resumed" if on else "paused"), _menu_buttons(chat, on))
