"""Общее для консольных команд."""

from __future__ import annotations

from collections.abc import Sequence


def table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    """
    Таблица в рамке — строками, готовыми к печати.

    Своя отрисовка: у Django таблиц в консоли нет. Ширина по содержимому,
    как у Laravel: выводы двух реализаций сравнивают глазами, и одинаковая
    рамка это заметно облегчает.
    """
    cells = [[str(value) for value in row] for row in rows]
    columns = len(header)
    widths = [max(len(row[i]) for row in (list(header), *cells)) for i in range(columns)]
    rule = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def line(row: Sequence[str]) -> str:
        return "| " + " | ".join(row[i].ljust(widths[i]) for i in range(columns)) + " |"

    return [rule, line(header), rule, *(line(row) for row in cells), rule]
