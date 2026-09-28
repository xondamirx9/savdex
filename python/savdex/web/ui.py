"""
Словарь интерфейса и подписи «N минут назад» — из выгрузки Laravel.

Выгружает их команда `php artisan savdex:export-ui`
(app/Console/Commands/ExportUiForPython.php) при старте службы: словарь
— PHP-массив lang/<язык>/ui.php поверх русского, подписи — правила
склонения Carbon. Django читает готовый JSON и перечитывает его, только
если файл сменился.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class UiNotExportedError(RuntimeError):
    """Словарь не выгружен — страницу на Django не собрать."""


def directory() -> Path:
    return Path(settings.LARAVEL_ROOT) / "storage/app/python/ui"


def _load(locale: str) -> dict[str, Any]:
    path = directory() / f"{locale}.json"

    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError as error:
        raise UiNotExportedError(f"Нет {path}: запустите php artisan savdex:export-ui") from error

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
