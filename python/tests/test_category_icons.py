"""Значки категорий в админке на Django — те же, что умеет рисовать витрина."""

from __future__ import annotations

import re
from pathlib import Path

from savdex.catalogs.admin import ICONS

HOME = Path(__file__).resolve().parents[2] / "resources/js/pages/Home.tsx"


def test_значки_совпадают_с_витриной():
    """
    Значок — ключ словаря CATEGORY_ICONS на главной. Выбор в админке
    обязан предлагать ровно те ключи, которые витрина умеет рисовать:
    лишний молча превратится в коробку, недостающий нельзя будет выбрать.
    """
    source = HOME.read_text(encoding="utf-8")
    block = re.search(r"const CATEGORY_ICONS[^{]*\{(.*?)\n\};", source, re.S)

    assert block is not None, "CATEGORY_ICONS не найден в Home.tsx"
    assert set(re.findall(r"^\s*(\w+):", block.group(1), re.M)) == set(ICONS)
