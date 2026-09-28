"""
Нормализация текста для поиска — копия App\\Support\\SearchText.

Узбекоязычная аудитория набирает на латинице («sement», «gisht»), а
объявления чаще написаны кириллицей: запрос ищется как набран и в
транслитерации в другую графику.
"""

from __future__ import annotations

import re

#: Кириллица → узбекская латиница (strtr: сначала длинные ключи)
CYR_TO_LAT = {
    "ё": "yo", "ю": "yu", "я": "ya", "ч": "ch", "ш": "sh", "щ": "sh",
    "ж": "j", "ц": "s", "э": "e", "ъ": "", "ь": "",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}  # fmt: skip

#: Латиница → кириллица: диграфы первыми, иначе «sh» станет «сх»
LAT_TO_CYR = {
    "yo": "ё", "yu": "ю", "ya": "я", "ch": "ч", "sh": "ш", "ts": "ц", "kh": "х",
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "ж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "х",
    "y": "й", "z": "з",
}  # fmt: skip

_APOSTROPHES = ("'", "’", "‘", "ʻ", "ʼ", "`")

#: trim() у PHP
_TRIM = " \t\n\r\0\x0b"

#: \s у PCRE с /u: пробельные Юникода
_SPACES = re.compile(r"\s+")


def _strtr(text: str, table: dict[str, str]) -> str:
    """strtr с массивом: в каждой позиции — самый длинный подходящий ключ."""
    longest = max(len(k) for k in table)
    out: list[str] = []
    i = 0

    while i < len(text):
        for size in range(min(longest, len(text) - i), 0, -1):
            piece = text[i : i + size]

            if piece in table:
                out.append(table[piece])
                i += size
                break
        else:
            out.append(text[i])
            i += 1

    return "".join(out)


def normalize(text: str) -> str:
    """Нижний регистр, без узбекских апострофов, с одиночными пробелами."""
    text = text.strip(_TRIM).lower()

    for mark in _APOSTROPHES:
        text = text.replace(mark, "")

    return _SPACES.sub(" ", text)


def variants(term: str) -> list[str]:
    """Как набрано плюс транслитерации, без повторов и пустых."""
    normalized = normalize(term)
    forms = [normalized, _strtr(normalized, CYR_TO_LAT), _strtr(normalized, LAT_TO_CYR)]
    unique = list(dict.fromkeys(forms))

    return [v for v in unique if v != ""]


def index(text: str) -> str:
    """SearchText::index: строка для столбца search_text — обе графики разом."""
    normalized = normalize(text)
    forms = [normalized, _strtr(normalized, CYR_TO_LAT), _strtr(normalized, LAT_TO_CYR)]

    return " ".join(dict.fromkeys(forms))
