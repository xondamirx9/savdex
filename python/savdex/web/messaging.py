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
