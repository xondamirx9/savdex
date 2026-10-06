"""
Вебхук Telegram-бота: сюда Telegram присылает сообщения и нажатия кнопок.

Секрет — в самом адресе; чужой секрет — 404. Разговор (привязка по ИНН,
меню уведомлений) — savdex/telegram_bot.py. Ответ всегда пустой с кодом
204: Telegram повторяет доставку, пока не получит 2xx, — ошибка в разборе
одного сообщения не должна превращаться в бесконечный повтор.

Проверки — tests/test_web_telegram_webhook.py.
"""

from __future__ import annotations

import hmac
import logging
import os

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from savdex import telegram_bot
from savdex.web.forms import input_of
from savdex.web.request import context

log = logging.getLogger("savdex.telegram")


def _no_content() -> HttpResponse:
    return HttpResponse(status=204)


@csrf_exempt
def webhook(request: HttpRequest, secret: str) -> HttpResponse:
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    expected = (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()

    if expected == "" or not hmac.compare_digest(expected.encode(), secret.encode()):
        return not_found(ctx)

    update = input_of(request)

    try:
        telegram_bot.handle(ctx, update if isinstance(update, dict) else {})
    except Exception:
        log.exception("Сообщение боту не разобрано")

    return _no_content()
