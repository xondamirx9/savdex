"""
Автоматическая проверка отзыва перед публикацией — копия
App\\Support\\ReviewScreening. Ищет контакты в тексте (обход платного
раскрытия), брань и крик заглавными; найденное отправляет отзыв
модератору.

Шаблоны — как у PHP с флагом u (PCRE2_UTF и PCRE2_UCP: \\d, \\w и \\s —
по Юникоду); модуль regex понимает \\p{L} и \\p{Lu}.
"""

from __future__ import annotations

import regex

#: ReviewScreening::PROFANITY — корни, а не слова целиком
PROFANITY = (
    "хуй", "хуе", "хуё", "пизд", "ебал", "ебан", "ебат", "ёбан", "бляд",
    "муда", "сука", "гандон", "долбоёб", "долбоеб", "пидор", "пидар",
)  # fmt: skip

#: Латиница, похожая на кириллицу: «cyka» пишут именно так
_LOOKALIKE = str.maketrans("aeopcyxkmb", "аеорсухкмб")

_EMAIL = regex.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", regex.IGNORECASE)
_LINK = regex.compile(r"(https?://|www\.|t\.me/|@[a-z0-9_]{4,})", regex.IGNORECASE)
_PHONE_PLUS = regex.compile(r"\+\s*(?:\d[\s()-]*){7,}")
_PHONE_DIGITS = regex.compile(r"\d{9,}")
_PHONE_GROUPS = regex.compile(r"\d+(?:[\s()-]+\d+){3,}")
_NOT_ALNUM = regex.compile(r"[^\p{L}\p{N}]+")
_NOT_LETTER = regex.compile(r"[^\p{L}]+")
_NOT_UPPER = regex.compile(r"[^\p{Lu}]+")


def reasons(text: str) -> list[str]:
    """ReviewScreening::reasons: пустой список — можно публиковать."""
    found = []

    if _has_contacts(text):
        found.append("В тексте есть контакты: телефон, почта или ссылка")

    if _has_profanity(_normalize(text)):
        found.append("В тексте есть брань")

    if _is_shouting(text):
        found.append("Текст набран заглавными буквами")

    return found


def _normalize(text: str) -> str:
    """«с-у-к-а» и «с у к а» становятся одним словом."""
    return _NOT_ALNUM.sub("", text.lower().translate(_LOOKALIKE))


def _has_profanity(normalized: str) -> bool:
    return any(root in normalized for root in PROFANITY)


def _has_contacts(text: str) -> bool:
    if _EMAIL.search(text) or _LINK.search(text):
        return True

    return _has_phone(text)


def _has_phone(text: str) -> bool:
    """Плюс и 7+ цифр, 9+ цифр подряд или четыре и более групп цифр."""
    return bool(
        _PHONE_PLUS.search(text) or _PHONE_DIGITS.search(text) or _PHONE_GROUPS.search(text)
    )


def _is_shouting(text: str) -> bool:
    letters = _NOT_LETTER.sub("", text)

    if len(letters) < 20:
        return False

    return len(_NOT_UPPER.sub("", letters)) / len(letters) > 0.7
