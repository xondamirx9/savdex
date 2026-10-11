"""
Регистрационный номер компании по стране (ТЗ-02 §3).

Раньше номер везде проверялся как узбекский ИНН — «только цифры», и
18-значный китайский код (统一社会信用代码) приходилось обрезать до 9 цифр.
Теперь правило — по стране компании:

- UZ — ИНН (СТИР) ровно 9 цифр; физлицу — ещё ПИНФЛ 14 цифр;
- CN — 18 знаков: цифры и латинские заглавные без I, O, S, V, Z;
- IN — GSTIN 15 знаков (2 цифры + PAN + 3 знака) или PAN 10 знаков
  (5 букв, 4 цифры, буква);
- KZ — БИН/ИИН 12 цифр; RU — ИНН 10 или 12 цифр; TR — 10 или 11 цифр;
- прочие — от 5 до 20 латинских букв и цифр.

Перед проверкой и записью из номера убираются пробелы и дефисы, буквы —
заглавные (normalize): «91510107ma6-xxx» и «91510107MA6XXX» — один номер.
"""

from __future__ import annotations

import re
from typing import Any

#: Номера-заглушки, которые вводят «чтобы пропустило» (Tin::FAKE)
FAKE = ("123456789", "987654321", "123123123")

#: Страна → (шаблон номера, ключ текста ошибки в messages.tin)
RULES: dict[str, tuple[str, str]] = {
    "cn": (r"[0-9A-HJ-NPQRTUWXY]{18}", "cn_format"),
    "in": (r"\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]{3}|[A-Z]{5}\d{4}[A-Z]", "in_format"),
    "kz": (r"\d{12}", "kz_length"),
    "ru": (r"\d{10}|\d{12}", "ru_length"),
    "tr": (r"\d{10,11}", "tr_length"),
}

#: Страна, для которой правил пока нет
OTHER = (r"[0-9A-Z]{5,20}", "other_format")


def normalize(value: Any) -> Any:  # noqa: ANN401
    """Без пробелов и дефисов, буквы заглавные; не строка — как есть (ошибку даст string)."""
    if not isinstance(value, str):
        return value

    return re.sub(r"[\s\-‐‑–—]+", "", value).upper()


def problem(tin: str, country: str | None, *, person: bool = False) -> str | None:
    """Ключ текста ошибки в messages.tin или None, если номер подходит стране."""
    if re.fullmatch(r"(\d)\1+", tin, re.ASCII) or tin in FAKE:
        return "invalid"

    if country in (None, "uz"):
        if re.fullmatch(r"\d+", tin, re.ASCII) is None:
            return "digits_only"

        if person and len(tin) == 14:
            return None

        return None if len(tin) == 9 else ("uz_person_length" if person else "uz_length")

    pattern, key = RULES.get(country, OTHER)

    return None if re.fullmatch(pattern, tin, re.ASCII) else key
