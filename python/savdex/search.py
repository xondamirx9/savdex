"""
Поиск в админке без учёта регистра — в любой локали базы.

Обычный поиск Django (icontains) сравнивает UPPER(поле) с UPPER(запрос).
Если база заведена с локалью C, UPPER меняет только латиницу: «мебель»
не находит «Мебель Плюс», а одна строчная буква находит всё подряд —
поиск будто работает «только по первой букве».

Здесь каждая буква запроса ищется сразу в обоих регистрах: «мебель» →
регулярное выражение [мМ][еЕёЁ][бБ][еЕёЁ][лЛ][ьЬ], и база сравнивает
его как есть (оператор ~), не полагаясь на свою локаль. Заодно «е» и
«ё» — одна буква, а узбекские апострофы (ʻ ’ ' `) — один знак: «Oʻzbek»
находится и по «O'zbek».

Запрос делится на слова, как у Django: каждое слово должно найтись
хотя бы в одном поле; «в кавычках» — одной фразой. Число — ещё и номер
записи.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from django.db.models import Q
from django.utils.text import smart_split, unescape_string_literal

#: Буквы, которые считаются одной
_SAME = {"е": "еЕёЁ", "ё": "еЕёЁ"}

#: Апострофы узбекской латиницы — любой вместо любого
_APOSTROPHES = "ʻʼ’'`‘"

#: Знаки, которые в регулярном выражении PostgreSQL надо экранировать
_SPECIAL = set(r"\.^$|?*+()[]{}")


def _char(char: str) -> str:
    if char in _APOSTROPHES:
        return "[" + _APOSTROPHES + "]"

    lower, upper = char.lower(), char.upper()

    if lower in _SAME:
        return "[" + _SAME[lower] + "]"

    if lower != upper and len(lower) == 1 and len(upper) == 1:
        return f"[{lower}{upper}]"

    return "\\" + char if char in _SPECIAL else char


def pattern(term: str) -> str:
    """«Мебель» → [мМ][еЕёЁ][бБ][еЕёЁ][лЛ][ьЬ]: регистр не важен в любой локали."""
    return "".join(_char(char) for char in term)


def terms(search_term: str) -> list[str]:
    """Слова запроса, как у поиска Django: «в кавычках» — одной фразой."""
    words = []

    for bit in smart_split(search_term):
        if bit[:1] in ('"', "'") and bit[-1:] == bit[:1] and len(bit) > 1:
            bit = unescape_string_literal(bit)

        bit = bit.strip()

        if bit:
            words.append(bit)

    return words


def contains(field: str, term: str) -> Q:
    """Поле содержит слово — без учёта регистра."""
    return Q(**{f"{field}__regex": pattern(term)})


def any_field(fields: Iterable[str], term: str) -> Q:
    """Слово нашлось хотя бы в одном поле."""
    found = Q()

    for field in fields:
        found |= contains(field, term)

    return found


def match(fields: Iterable[str], search_term: str, *, by_id: bool = True) -> Q:
    """
    Весь запрос: каждое слово — хотя бы в одном поле. by_id — число в
    запросе находит и запись с таким номером.
    """
    fields = list(fields)
    found = Q()

    for word in terms(search_term):
        one = any_field(fields, word)

        if by_id and re.fullmatch(r"[0-9]{1,18}", word):
            one |= Q(pk=int(word))

        found &= one

    return found
