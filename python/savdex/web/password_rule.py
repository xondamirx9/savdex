"""
Правило пароля площадки — Password::defaults() из AppServiceProvider:
от 8 до 20 знаков, хотя бы одна буква и одна цифра; на развёрнутом
сайте (APP_ENV не local и не testing) — ещё и не из утечек
(Have I Been Pwned, диапазон по первым пяти знакам SHA-1).

Как Illuminate\\Validation\\Rules\\Password::passes: свой валидатор
(string, min и max), затем буквы и цифры — все сообщения разом; проверка по
утечкам — только если остальное прошло. Сбой сети — пароль принимается
(NotPwnedVerifier так же не мешает регистрации, когда сервис молчит).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any

import httpx
import regex

from savdex.web import ui
from savdex.web.validation import _displayable, validate

MIN = 8
MAX = 20

_LETTER = regex.compile(r"\p{L}")
_NUMBER = regex.compile(r"\p{N}")


def _deployed() -> bool:
    """Runtime::isDeployed: не машина разработчика."""
    return (os.environ.get("APP_ENV") or "production") not in ("local", "testing")


def _pwned(value: str) -> bool:
    """NotPwnedVerifier::verify наоборот: True — пароль нашёлся в утечках."""
    digest = hashlib.sha1(value.encode()).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]

    try:
        response = httpx.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            headers={"Add-Padding": "true"},
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return False

    for line in response.text.splitlines():
        found, _, count = line.strip().partition(":")

        if found == suffix and int(count or 0) > 0:
            return True

    return False


def _message(key: str, attribute: str, locale: str, custom: Mapping[str, str]) -> str:
    """Своё сообщение «<поле>.<правило>» или «<правило>», иначе validation.<правило>."""
    rule = key.removeprefix("password.")
    text = custom.get(f"{attribute}.{key}") or custom.get(f"{attribute}.{rule}") or custom.get(key)

    if text is None:
        line = ui.group_node(f"validation.{key}", locale)
        text = line if isinstance(line, str) else f"validation.{key}"

    return text.replace(":attribute", _displayable(attribute, False))


def messages(
    attribute: str,
    value: Any,  # noqa: ANN401
    locale: str,
    custom: Mapping[str, str],
) -> list[str]:
    """Ошибки правила Password::defaults() для значения поля."""
    inner = {attribute: ["string", f"min:{MIN}", f"max:{MAX}"]}
    found = validate({attribute: value}, inner, locale, custom)
    result = list(found.get(attribute, []))

    if isinstance(value, str):
        if not _LETTER.search(value):
            result.append(_message("password.letters", attribute, locale, custom))

        if not _NUMBER.search(value):
            result.append(_message("password.numbers", attribute, locale, custom))

    if not result and _deployed() and isinstance(value, str) and _pwned(value):
        result.append(_message("password.uncompromised", attribute, locale, custom))

    return result


def custom_messages(t: Any) -> dict[str, str]:  # noqa: ANN401
    """PasswordMessages::all: подписи к правилам пароля, общие для всех форм."""
    return {
        "password.min": t("messages.register.password_min"),
        "password.max": t("messages.register.password_max"),
        "password.letters": t("messages.register.password_letters"),
        "password.numbers": t("messages.register.password_numbers"),
        "password.uncompromised": t("messages.register.password_leaked"),
    }
