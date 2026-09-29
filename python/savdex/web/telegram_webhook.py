"""
Вебхук Telegram-бота — копия TelegramWebhookController (этап 5, шаг 49).

Бот присылает «/start <токен>» из ссылки, которую выдал кабинет
(settings_actions.telegram_link): токен одноразовый, в файловом кэше
Laravel на 15 минут. По нему чат привязывается к учётной записи.
Секрет — в самом адресе; чужой секрет — 404. На всё остальное ответ
пустой с кодом 204: Telegram повторяет доставку, пока не получит 2xx.

Сверка с настоящим Laravel — tests/test_web_telegram_webhook.py.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from savdex import laravel_cache
from savdex.web import eloquent, messaging
from savdex.web.cabinet import _rows
from savdex.web.forms import input_of
from savdex.web.request import context
from savdex.web.settings_actions import LINK_PREFIX
from savdex.web.validation import _php_string


def _data_get(value: Any, path: str) -> Any:  # noqa: ANN401
    """data_get: по ключам через точку; нет — None."""
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None

        value = value[key]

    return value


def _string(value: Any) -> str:  # noqa: ANN401
    """(string) у PHP; массив — «Array»."""
    if isinstance(value, dict | list):
        return "Array"

    return _php_string(value)


def _claim(token: str) -> dict[str, Any] | None:
    """TelegramGateway::claim: токен одноразовый — сразу из кэша прочь."""
    key = LINK_PREFIX + token
    user_id = laravel_cache.get(key)

    if user_id is None:
        return None

    laravel_cache.forget(key)
    rows = _rows("select * from users where id = %s and deleted_at is null", [_php_string(user_id)])

    return rows[0] if rows else None


def _no_content() -> HttpResponse:
    return HttpResponse(status=204)


@csrf_exempt
def webhook(request: HttpRequest, secret: str) -> HttpResponse:
    """TelegramWebhookController::__invoke."""
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    expected = (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()

    if expected == "" or not hmac.compare_digest(expected.encode(), secret.encode()):
        return not_found(ctx)

    raw = input_of(request).get("message", [])
    message = raw if isinstance(raw, dict) else {}
    chat_id = _string(_data_get(message, "chat.id"))
    text = _string(_data_get(message, "text")).strip(" \t\n\r\0\x0b")

    if chat_id == "" or not text.startswith("/start"):
        return _no_content()

    token = text[len("/start") :].strip(" \t\n\r\0\x0b")

    if token == "":
        messaging.telegram(chat_id, ctx.t("messages.auth.telegram_start"))

        return _no_content()

    user = _claim(token)

    if user is None:
        messaging.telegram(chat_id, ctx.t("messages.auth.telegram_link_expired"))

        return _no_content()

    username = _string(_data_get(message, "from.username"))
    eloquent.save(
        ctx,
        "users",
        user,
        {
            "telegram_chat_id": chat_id,
            # (string) … ?: null — у PHP «0» тоже пусто
            "telegram_username": None if username in ("", "0") else username,
            "telegram_linked_at": eloquent.now(),
        },
        section="users",
        model="User",
    )
    messaging.telegram(chat_id, ctx.t("messages.auth.telegram_linked", name=user["name"]))

    return _no_content()
