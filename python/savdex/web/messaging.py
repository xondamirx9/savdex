"""
Сообщения в мессенджеры — TelegramGateway::send и WhatsAppGateway::send
со стороны Django: ссылка на смену пароля туда, куда человек смотрит чаще
почты. Сбой — в журнал и False: ответ формы от этого не меняется.
"""

from __future__ import annotations

import logging
import os
import re

import httpx

log = logging.getLogger("savdex.messaging")

#: TelegramGateway::TIMEOUT и WhatsAppGateway::TIMEOUT
TIMEOUT = 8


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def telegram_configured() -> bool:
    return _env("TELEGRAM_BOT_TOKEN") != "" and _env("TELEGRAM_BOT_USERNAME").lstrip("@") != ""


def whatsapp_configured() -> bool:
    return _env("WHATSAPP_TOKEN") != "" and _env("WHATSAPP_PHONE_NUMBER_ID") != ""


def telegram(chat_id: str, text: str) -> bool:
    """sendMessage без разметки и без превью ссылки."""
    if not telegram_configured() or str(chat_id).strip() == "":
        return False

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
