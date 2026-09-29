"""
Заголовки книги закупок с пометками узнаются, как ImportLanguage::matches
у Laravel (PR #235): «Название*», «Описание:», «Цена (сум)», «Цена, UZS».
Синоним со скобками узнаётся и без снятия пометок.
"""

from __future__ import annotations

import pytest

from savdex.tenders.importer import column_map, matches


@pytest.mark.parametrize(
    ("header", "aliases", "found"),
    [
        ("Название*", {"название"}, True),
        ("Описание:", {"описание"}, True),
        ("Цена (сум)", {"цена"}, True),
        ("Цена, UZS", {"цена"}, True),
        (" Name [en] * ", {"name"}, True),
        ("Начальная (максимальная) цена", {"начальная (максимальная) цена"}, True),
        ("Ценник", {"цена"}, False),
    ],
)
def test_пометки_в_заголовке(header, aliases, found):
    assert matches(header, aliases) is found


def test_шапка_с_пометками_узнаётся_целиком():
    mapping = column_map(["Заголовок*", "Описание:"])

    assert set(mapping.values()) <= {"Заголовок*", "Описание:"}
