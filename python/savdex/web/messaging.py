"""
Сообщения в мессенджеры — TelegramGateway::send и WhatsAppGateway::send
со стороны Django: ссылка на смену пароля туда, куда человек смотрит чаще
почты. Сбой — в журнал и False: ответ формы от этого не меняется.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger("savdex.messaging")

#: TelegramGateway::TIMEOUT и WhatsAppGateway::TIMEOUT
TIMEOUT = 8


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def telegram_configured() -> bool:
    return _env("TELEGRAM_BOT_TOKEN") != "" and _env("TELEGRAM_BOT_USERNAME").lstrip("@") != ""


def _logged(payload: dict[str, object]) -> bool:
    """
    TELEGRAM_TRANSPORT=log — сообщения бота пишутся строками JSON в
    TELEGRAM_LOG_PATH, а не уходят в Telegram: для запуска у себя
    и проверок (как MAIL_MAILER=log у почты).
    """
    if _env("TELEGRAM_TRANSPORT") != "log":
        return False

    path = _env("TELEGRAM_LOG_PATH") or "storage/logs/telegram.log"

    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return True


def whatsapp_configured() -> bool:
    return _env("WHATSAPP_TOKEN") != "" and _env("WHATSAPP_PHONE_NUMBER_ID") != ""


def telegram(chat_id: str, text: str) -> bool:
    """sendMessage без разметки и без превью ссылки."""
    if not telegram_configured() or str(chat_id).strip() == "":
        return False

    if _logged({"chat_id": chat_id, "text": text}):
        return True

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{_env('TELEGRAM_BOT_TOKEN')}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        log.warning("telegram.send_error: %s", e)

        return False

    if response.is_success:
        return True

    log.warning("telegram.send_failed: %s %s", response.status_code, response.text[:500])

    return False


@dataclass(frozen=True)
class Sent:
    """Итог sendMessage для рассылки: ушло, человек заблокировал бота, ждать N секунд."""

    ok: bool
    blocked: bool = False
    retry_after: int = 0


@dataclass(frozen=True)
class Button:
    """Кнопка под сообщением: ссылка (url) или действие (data — callback_data)."""

    text: str
    url: str | None = None
    data: str | None = None


def _keyboard(rows: list[list[Button]]) -> dict[str, object]:
    return {
        "inline_keyboard": [
            [
                {"text": b.text, "url": b.url}
                if b.url is not None
                else {"text": b.text, "callback_data": b.data or b.text}
                for b in row
            ]
            for row in rows
        ]
    }


def telegram_send(chat_id: str, text: str, buttons: list[list[Button]] | None = None) -> Sent:
    """
    sendMessage с разметкой HTML и кнопками — сообщения бота и рассылка.

    403 — человек заблокировал бота или удалил чат: писать ему больше
    некуда. 429 — Telegram просит подождать retry_after секунд.
    """
    if not telegram_configured() or str(chat_id).strip() == "":
        return Sent(False)

    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if buttons:
        payload["reply_markup"] = _keyboard(buttons)

    if _logged(payload):
        return Sent(True)

    try:
        response = httpx.post(_api("sendMessage"), json=payload, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        log.warning("telegram.send_error: %s", e)

        return Sent(False)

    if response.is_success:
        return Sent(True)

    try:
        body = response.json()
    except ValueError:
        body = {}

    params = body.get("parameters") if isinstance(body, dict) else None
    retry = params.get("retry_after") if isinstance(params, dict) else None

    if response.status_code == 403:
        return Sent(False, blocked=True)

    log.warning("telegram.send_failed: %s %s", response.status_code, response.text[:500])

    return Sent(False, retry_after=int(retry) if isinstance(retry, int) else 0)


def telegram_answer(callback_id: str) -> None:
    """answerCallbackQuery: убрать часики с нажатой кнопки."""
    if telegram_configured() and callback_id and not _logged({"callback": callback_id}):
        _call("answerCallbackQuery", {"callback_query_id": callback_id})


# ── Адрес бота у Telegram (команда telegram_webhook) ──────────────────


def webhook_secret() -> str:
    return _env("TELEGRAM_WEBHOOK_SECRET")


def webhook_url() -> str | None:
    """TelegramGateway::webhookUrl — адрес, на который Telegram присылает сообщения боту."""
    secret = webhook_secret()

    if secret == "":
        return None

    return _env("APP_URL", "http://localhost").rstrip("/") + "/telegram/webhook/" + secret


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{_env('TELEGRAM_BOT_TOKEN')}/{method}"


def _call(method: str, payload: dict[str, object]) -> tuple[bool, str]:
    """TelegramGateway::call — вызов Bot API с понятным ответом."""
    try:
        response = httpx.post(_api(method), json=payload, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        return False, str(e)

    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.is_success and isinstance(body, dict) and body.get("ok") is True:
        return True, str(body.get("description") or "Готово")

    # 404 от Telegram означает ровно одно: такого бота нет — в адрес
    # уехал не тот токен. Само «Not Found» человек читает как «сайт
    # недоступен»
    if response.status_code == 404:
        return False, "Telegram не знает такого бота — проверьте TELEGRAM_BOT_TOKEN."

    description = body.get("description") if isinstance(body, dict) else None

    return False, str(description or response.text)


def register_webhook() -> tuple[bool, str]:
    """TelegramGateway::registerWebhook."""
    url = webhook_url()

    if not telegram_configured() or url is None:
        return False, (
            "Не заданы TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME или TELEGRAM_WEBHOOK_SECRET."
        )

    return _call("setWebhook", {"url": url, "drop_pending_updates": True})


def delete_webhook() -> tuple[bool, str]:
    """TelegramGateway::deleteWebhook."""
    if not telegram_configured():
        return False, "Не задан TELEGRAM_BOT_TOKEN."

    return _call("deleteWebhook", {})


def webhook_info() -> dict[str, object] | None:
    """TelegramGateway::webhookInfo — адрес, очередь недоставленного, последняя ошибка."""
    if not telegram_configured():
        return None

    try:
        response = httpx.get(_api("getWebhookInfo"), timeout=TIMEOUT)
        result = response.json().get("result") if response.is_success else None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None

    return result if isinstance(result, dict) else None


def whatsapp(phone: str, value: str, locale: str = "ru") -> bool:
    """Шаблон WhatsApp Cloud API с одним параметром — ссылкой."""
    to = re.sub(r"\D+", "", phone)

    if not whatsapp_configured() or len(to) < 9:
        return False

    url = (
        f"https://graph.facebook.com/{_env('WHATSAPP_API_VERSION', 'v21.0')}/"
        f"{_env('WHATSAPP_PHONE_NUMBER_ID')}/messages"
    )

    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {_env('WHATSAPP_TOKEN')}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": _env("WHATSAPP_TEMPLATE", "password_reset"),
                    "language": {"code": locale},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": value}]}
                    ],
                },
            },
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        log.warning("whatsapp.send_error: %s", e)

        return False

    if response.is_success:
        return True

    log.warning("whatsapp.send_failed: %s %s", response.status_code, response.text[:500])

    return False
