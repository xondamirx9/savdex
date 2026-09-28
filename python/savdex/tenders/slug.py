"""
Адрес закупки — как Tender::makeSlug: Str::slug(Str::transliterate(заголовок)),
не длиннее 60 знаков, и номер через дефис.

Транслитерация — по таблицам voku/portable-ascii, которыми пользуется
Laravel (кириллица: ё → io, й → i, ю → iu, я → ia; узбекские и турецкие
буквы), остальное латинское — без диакритики. Знаков, которых таблица
не знает (иероглифы), в адресе нет: заголовок из одних иероглифов даёт
«tender-<номер>», как у Laravel пустая основа.
"""

from __future__ import annotations

import re
import unicodedata

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "io", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "iu",
    "я": "ia", "ў": "u", "қ": "k", "ғ": "g", "ҳ": "kh", "і": "i", "ї": "yi", "є": "ye",
    "ґ": "g",
}  # fmt: skip

#: Знаки, которые Str::transliterate превращает в слова или дефис
_SIGNS = {"—": "-", "–": "-", "−": "-", "№": "No.", "@": "-at-", "ı": "i", "ß": "ss"}


def _ascii(text: str) -> str:
    out = []

    for char in text:
        lower = char.lower()

        if lower in _CYRILLIC:
            value = _CYRILLIC[lower]
            out.append(value.capitalize() if char != lower and value else value)
        elif char in _SIGNS:
            out.append(_SIGNS[char])
        else:
            decomposed = unicodedata.normalize("NFKD", char)
            out.append("".join(c for c in decomposed if ord(c) < 128))

    return "".join(out)


def slugify(title: str) -> str:
    """Str::slug(Str::transliterate(…)): латиница, цифры, дефисы."""
    text = _ascii(title).lower()
    text = re.sub(r"[^-\w\s]+", "", text, flags=re.ASCII)
    text = re.sub(r"[-\s_]+", "-", text)

    return text.strip("-")


def make_slug(title: str, key: int) -> str:
    """Tender::makeSlug."""
    base = slugify(title) or "tender"

    return base[:60].rstrip() + f"-{key}"
