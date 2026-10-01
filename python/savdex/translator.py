"""
Машинный перевод — копия App\\Services\\MachineTranslator.

Публичный переводчик Google (gtx, без ключа): текст уходит телом POST,
длинный режется на куски не длиннее CHUNK_LIMIT (абзацы, затем
предложения, затем символы; мелкие склеиваются обратно). Любая ошибка —
None, а не исключение: перевод — украшение. Отказ 429 отмечается:
фоновой задаче незачем списывать на него попытку.

Адрес переводчика — SAVDEX_TRANSLATE_URL (в сверке — заглушка), включён
ли перевод — MACHINE_TRANSLATION_ENABLED, как у Laravel.
"""

from __future__ import annotations

import os
import re

import httpx

#: Языки каталога, на которые переводится русский оригинал
TARGETS = ("en", "uz", "tr", "zh")

#: Коды Google, где они отличаются от кодов площадки
GOOGLE_CODES = {"zh": "zh-CN"}

CHUNK_LIMIT = 4000

URL = "https://translate.googleapis.com/translate_a/single"

#: trim() у PHP
_TRIM = " \t\n\r\0\x0b"


def enabled() -> bool:
    """
    MACHINE_TRANSLATION_ENABLED, по умолчанию да — как
    config('services.machine_translation.enabled') у Laravel.
    PY_MACHINE_TRANSLATION_ENABLED, если задана, важнее: так до этапа 8
    перевод включали Python, выключив его у Laravel.
    """
    raw = os.environ.get("PY_MACHINE_TRANSLATION_ENABLED")

    if raw is None:
        raw = os.environ.get("MACHINE_TRANSLATION_ENABLED")

    if raw is None:
        return True

    value = raw.strip().lower()

    # env(): «false», «(false)», «empty» и «null» — не истина; пустая
    # строка — пустая строка, то есть ложь для if
    return value not in ("false", "(false)", "", "empty", "(empty)", "null", "(null)", "0")


class Translator:
    def __init__(self) -> None:
        self.rate_limited = False
        self.url = os.environ.get("SAVDEX_TRANSLATE_URL") or URL

    def translate(self, text: str, to: str) -> str | None:
        if text.strip(_TRIM) == "" or not enabled():
            return None

        self.rate_limited = False
        parts = []

        for chunk in chunks(text):
            translated = self._request(chunk, to)

            # Недопереведённый текст хуже оригинала
            if translated is None:
                return None

            parts.append(translated)

        return "\n\n".join(parts)

    def _request(self, text: str, to: str) -> str | None:
        try:
            response = httpx.post(
                self.url,
                params={"client": "gtx", "sl": "auto", "tl": GOOGLE_CODES.get(to, to), "dt": "t"},
                data={"q": text},
                timeout=15,
            )
        except httpx.HTTPError:
            return None

        self.rate_limited = response.status_code == 429

        if response.status_code != 200:
            return None

        try:
            pieces = response.json()[0]
        except (ValueError, IndexError, KeyError, TypeError):
            return None

        if not isinstance(pieces, list):
            return None

        translated = "".join(
            str(p[0] if len(p) > 0 and p[0] is not None else "") if isinstance(p, list) else ""
            for p in pieces
        )
        translated = translated.strip(_TRIM)

        return translated if translated != "" else None


def chunks(text: str) -> list[str]:
    """MachineTranslator::chunks."""
    text = text.strip(_TRIM)

    if len(text) <= CHUNK_LIMIT:
        return [text]

    pieces: list[str] = []

    # \R{2,}: два и больше переводов строки любого вида
    for paragraph in re.split(r"(?:\r\n|[\n\x0b\x0c\r\x85  ]){2,}", text):
        paragraph = paragraph.strip(_TRIM)

        if paragraph == "":
            continue

        if len(paragraph) <= CHUNK_LIMIT:
            pieces.append(paragraph)

            continue

        for sentence in re.split(r"(?<=[.!?…])\s+", paragraph):
            pieces += [sentence[i : i + CHUNK_LIMIT] for i in range(0, len(sentence), CHUNK_LIMIT)]

    result: list[str] = []
    current = ""

    for piece in pieces:
        candidate = piece if current == "" else current + "\n\n" + piece

        if len(candidate) > CHUNK_LIMIT and current != "":
            result.append(current)
            current = piece
        else:
            current = candidate

    if current != "":
        result.append(current)

    return result
