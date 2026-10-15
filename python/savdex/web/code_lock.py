"""
Неверные коды подтверждения — одна блокировка для почты и телефона.

Пять неверных кодов подряд на один адрес почты или номер — 15 минут ни
ввести код, ни получить новый. Потом счёт заново. Новый код блокировку
не снимает: иначе перебор шёл бы дальше, просто с новым кодом.

Счёт — на адрес или номер, а не на адрес сети: код «Забыли пароль»
перебирали бы с разных адресов. Хранится в кэше Laravel рядом с кодами.

Где: регистрация (код из письма и из SMS), подтверждение почты в
кабинете, подтверждение телефона в профиле, «Забыли пароль» по SMS.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from savdex import laravel_cache

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


def _key(target: str) -> str:
    return "code_lock." + hashlib.sha1(target.strip().lower().encode()).hexdigest()


def _entry(target: str) -> dict[str, Any]:
    entry = laravel_cache.get(_key(target), any_store=True)

    return entry if isinstance(entry, dict) else {}


def locked_minutes(target: str) -> int:
    """Сколько минут ещё ждать (с округлением вверх); 0 — не заблокирован."""
    until = _entry(target).get("until")

    if not isinstance(until, int):
        return 0

    left = until - int(time.time())

    if left <= 0:
        clear(target)

        return 0

    return max(1, math.ceil(left / 60))


def fail(target: str) -> int:
    """Неверный код: засчитать. Пятый подряд — блокировка; вернёт её минуты (иначе 0)."""
    if (minutes := locked_minutes(target)) > 0:
        return minutes

    failures = int(_entry(target).get("failures") or 0) + 1
    entry: dict[str | int, laravel_cache.Value] = {"failures": failures}

    if failures >= MAX_FAILURES:
        entry["until"] = int(time.time()) + LOCK_SECONDS

    laravel_cache.put(_key(target), entry, LOCK_SECONDS)

    return locked_minutes(target)


def clear(target: str) -> None:
    """Верный код (или блокировка истекла) — счёт заново."""
    laravel_cache.forget_file(_key(target))


def email(address: str) -> str:
    return "email:" + address


def phone(number: str) -> str:
    return "phone:" + number


def failure_message(ctx: Any, target: str, invalid_key: str) -> str:  # noqa: ANN401
    """Текст после неверного кода: заблокирован — «попробуйте через N мин.», иначе свой."""
    if (minutes := locked_minutes(target)) > 0:
        return str(ctx.t("messages.auth.code_locked", minutes=minutes))

    return str(ctx.t(invalid_key))


def locked_message(ctx: Any, target: str) -> str | None:  # noqa: ANN401
    """Заблокирован — текст «попробуйте через N мин.», иначе None."""
    if (minutes := locked_minutes(target)) > 0:
        return str(ctx.t("messages.auth.code_locked", minutes=minutes))

    return None
