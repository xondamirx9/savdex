"""
Словарь интерфейса и подписи «N минут назад» — savdex/locale/ui/<язык>.json.

Когда-то выгружался из Laravel (lang/<язык>/ui.php поверх русского,
подписи — правила склонения Carbon); с удалением PHP эти файлы — сам
словарь: тексты правятся прямо в них. SAVDEX_UI_DIR — другой каталог
(проверки). Django перечитывает файл, только если он сменился.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class UiNotExportedError(RuntimeError):
    """Словарь не выгружен — страницу на Django не собрать."""


def directory() -> Path:
    configured = os.environ.get("SAVDEX_UI_DIR")

    if configured:
        return Path(configured)

    return Path(__file__).resolve().parent.parent / "locale" / "ui"


def _load(locale: str) -> dict[str, Any]:
    path = directory() / f"{locale}.json"

    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError as error:
        raise UiNotExportedError(f"Нет словаря интерфейса {path} (savdex/locale/ui)") from error

    cached = _cache.get(locale)

    if cached is None or cached[0] != mtime:
        cached = (mtime, json.loads(path.read_text(encoding="utf-8")))
        _cache[locale] = cached

    return cached[1]


def translations(locale: str) -> dict[str, Any]:
    """Словарь для пропа translations — как HandleInertiaRequests::translations."""
    data: dict[str, Any] = _load(locale)["translations"]

    return data


def group_node(key: str, locale: str) -> object:
    """trans('<словарь>.<ключ>') как есть — строка, массив или None, если ключа нет."""
    node: Any = _load(locale).get("groups", {})

    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None

        node = node[part]

    return node


def group_t(key: str, locale: str) -> str:
    """
    __('<словарь>.<ключ>') для словарей, кроме ui (company.field.tin):
    выгружены в groups, русский — запасной. Ключа нет — сам ключ.
    """
    node = group_node(key, locale)

    return node if isinstance(node, str) else key


def t(key: str, locale: str, **replace: object) -> str:
    """
    __('ui.<key>'): строка словаря по пути через точку, с подстановкой
    «:имя». Ключа нет — сам ключ, как у Laravel.
    """
    node: Any = translations(locale)

    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return f"ui.{key}"

        node = node[part]

    if not isinstance(node, str):
        return f"ui.{key}"

    text: str = node

    for name, value in sorted(replace.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf":{re.escape(name)}\b", str(value), text)

    return text


def ago_phrase(locale: str, unit: str, count: int) -> str:
    """«5 минут назад» — строка Carbon для единицы и числа."""
    table: dict[str, dict[str, str]] = _load(locale)["ago"]
    phrase: str = table[unit][str(count)]

    return phrase


def date_template(locale: str, name: str, month: int) -> str:
    """Шаблон даты Carbon::isoFormat для месяца: «{d} сентября {y}»."""
    table: dict[str, dict[str, str]] = _load(locale)["dates"]
    template: str = table[name][str(month)]

    return template


def _plural_index(locale: str, number: int) -> int:
    """MessageSelector::getPluralIndex для языков площадки."""
    if locale == "ru":
        if number % 10 == 1 and number % 100 != 11:
            return 0

        return 1 if 2 <= number % 10 <= 4 and (number % 100 < 10 or number % 100 >= 20) else 2

    if locale == "en":
        return 0 if number == 1 else 1

    # tr, zh — одна форма; uz у Laravel в списке нет — тоже 0
    return 0


def choice(key: str, number: int, locale: str, **replace: object) -> str:
    """
    trans_choice('ui.<key>', n): форма по числу (MessageSelector::choose),
    :count подставляется всегда. Явные условия {1} и [2,*] не
    поддерживаются — в словаре их нет.
    """
    line = t(key, locale)
    segments = line.split("|")
    index = _plural_index(locale, number)
    text = segments[index] if len(segments) > 1 and index < len(segments) else segments[0]

    for name, value in sorted({"count": number, **replace}.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf":{re.escape(name)}\b", str(value), text)

    return text
