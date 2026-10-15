"""
Проверка формы регистрации в ILMORA — главная, на сервере.

Браузер повторяет те же правила (resources/js/pages/ilmora/rules.ts),
чтобы показать ошибку сразу, но решает сервер: обойти его нельзя.

- телефон — +998 и ровно 9 цифр (маска «99 222 33 44»);
- ФИО — не меньше трёх слов: буквы латиницы и кириллицы (с узбекскими
  ў ғ қ ҳ, oʻ gʻ), апострофы ʻ ' ‘ ’ ʼ и дефис внутри слова;
- физлицо — ПИНФЛ (14 цифр, правило регистрации Savdex:
  web/auth_actions._pinfl), юрлицо — ИНН (9 цифр);
- обе галочки из раздела 4.1 оферты: ознакомлен с офертой (с согласием
  на обработку персональных данных) и отметка — подпись под заявлением.

Под каждым полем — одна понятная причина: «ИНН должен содержать 9 цифр —
введено 7».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from savdex.web.shared import Context

PERSON_TYPES = ("individual", "legal")

#: Буквы ФИО: латиница (с расширенной — ö, ç, ş), кириллица (с ў ғ қ ҳ)
_LETTER = "A-Za-zÀ-ɏЀ-ӿ"
#: Апострофы узбекской латиницы: ʻ ʼ ' ‘ ’
_APOSTROPHES = "'ʻʼ‘’"
#: Слово: с буквы; апостроф где угодно после неё, дефис — только перед буквой
_WORD = re.compile(rf"[{_LETTER}](?:[{_LETTER}{_APOSTROPHES}]|-(?=[{_LETTER}]))*")
MAX_NAME = 150
MIN_WORDS = 3

PHONE_PREFIX = "+998"
PHONE_DIGITS = 9
PINFL_DIGITS = 14
TIN_DIGITS = 9


@dataclass(frozen=True)
class Application:
    """Проверенная заявка — то, что ляжет в ilmora_registrations."""

    person_type: str
    phone: str
    full_name: str
    pinfl: str | None
    tin: str | None


def _text(value: Any) -> str:  # noqa: ANN401
    """Строка из ввода: не строка (массив, число из JSON) — как строка, None — пусто."""
    if value is None or isinstance(value, bool | dict | list):
        return ""

    return str(value)


def phone_digits(value: Any) -> str:  # noqa: ANN401
    """
    Номер без +998, пробелов, скобок и дефисов. Браузер шлёт 9 цифр
    после префикса, но вставленный целиком «+998 99 222 33 44» тоже годится.
    """
    raw = re.sub(r"[\s\-()]", "", _text(value))

    if raw.startswith(PHONE_PREFIX):
        return raw[len(PHONE_PREFIX) :]

    if raw.startswith("998") and len(raw) == 3 + PHONE_DIGITS:
        return raw[3:]

    return raw


def full_name(value: Any) -> str:  # noqa: ANN401
    """ФИО: пробелы по краям обрезаны, между словами — по одному."""
    return " ".join(unicodedata.normalize("NFC", _text(value)).split())


def number(value: Any) -> str:  # noqa: ANN401
    """ПИНФЛ или ИНН: пробелы и дефисы вставленного номера убраны."""
    return re.sub(r"[\s\-]", "", _text(value))


def accepted(value: Any) -> bool:  # noqa: ANN401
    """Галочка отмечена: true, 1, «on», «yes» — как правило accepted."""
    return value is True or _text(value).strip().lower() in ("1", "true", "on", "yes")


def _digits_error(ctx: Context, field: str, value: str, length: int) -> str | None:
    """Пусто, не цифры, не та длина — текст ошибки; верно — None."""
    if value == "":
        return ctx.t(f"ilmora.errors.{field}_required")

    if re.fullmatch(r"\d+", value, re.ASCII) is None:
        return ctx.t(f"ilmora.errors.{field}_digits")

    if len(value) != length:
        return ctx.t(f"ilmora.errors.{field}_length", count=len(value))

    return None


def _name_error(ctx: Context, name: str) -> str | None:
    if name == "":
        return ctx.t("ilmora.errors.name_required")

    if len(name) > MAX_NAME:
        return ctx.t("ilmora.errors.name_long", max=MAX_NAME)

    words = name.split(" ")

    if any(_WORD.fullmatch(word) is None for word in words):
        return ctx.t("ilmora.errors.name_letters")

    if len(words) < MIN_WORDS:
        return ctx.t("ilmora.errors.name_words")

    return None


def _pinfl_error(ctx: Context, pinfl: str) -> str | None:
    """14 цифр — здесь (с числом введённых), повтор одной цифры — правило регистрации Savdex."""
    from savdex.web.auth_actions import _pinfl

    if (problem := _digits_error(ctx, "pinfl", pinfl, PINFL_DIGITS)) is not None:
        return problem

    messages: list[str] = []

    if not _pinfl(ctx, messages).passes(pinfl):
        return messages[0] if messages else ctx.t("messages.register.pinfl_invalid")

    return None


def validate(ctx: Context, data: dict[str, Any]) -> tuple[Application | None, dict[str, list[str]]]:
    """Заявка — или ошибки по полям в порядке формы."""
    errors: dict[str, list[str]] = {}
    phone = phone_digits(data.get("phone"))
    name = full_name(data.get("full_name"))
    kind = _text(data.get("person_type"))
    pinfl = tin = None

    if (problem := _digits_error(ctx, "phone", phone, PHONE_DIGITS)) is not None:
        errors["phone"] = [problem]

    if (problem := _name_error(ctx, name)) is not None:
        errors["full_name"] = [problem]

    if kind not in PERSON_TYPES:
        errors["person_type"] = [ctx.t("ilmora.errors.person_type")]
    elif kind == "individual":
        pinfl = number(data.get("pinfl"))

        if (problem := _pinfl_error(ctx, pinfl)) is not None:
            errors["pinfl"] = [problem]
    else:
        tin = number(data.get("tin"))

        if (problem := _digits_error(ctx, "tin", tin, TIN_DIGITS)) is not None:
            errors["tin"] = [problem]

    if not accepted(data.get("offer_read")):
        errors["offer_read"] = [ctx.t("ilmora.errors.offer_read")]

    if not accepted(data.get("offer_sign")):
        errors["offer_sign"] = [ctx.t("ilmora.errors.offer_sign")]

    if errors:
        return None, errors

    return Application(
        person_type=kind,
        phone=PHONE_PREFIX + phone,
        full_name=name,
        pinfl=pinfl,
        tin=tin,
    ), {}
