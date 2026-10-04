"""Текст для человека: склонения, числа."""

from __future__ import annotations


def plural(count: int, one: str, few: str, many: str) -> str:
    """
    «1 таблица», «2 таблицы», «5 таблиц».

    Перенесено из App\\Console\\Commands\\CheckPostgres::plural.
    Отчёт, в котором написано «5 таблица», читается как недоделка,
    и дальше ему уже не верят.
    """
    mod100 = count % 100
    mod10 = count % 10

    if 11 <= mod100 <= 14:
        word = many
    elif mod10 == 1:
        word = one
    elif 2 <= mod10 <= 4:
        word = few
    else:
        word = many

    return f"{count} {word}"


def numeric(value: str) -> bool:
    """
    Строка из цифр 0–9, которую int() примет и которая поместится в bigint.
    str.isdigit() пропускает «²» и «٣» — а int() на них падает (500).
    """
    return value.isascii() and value.isdigit() and len(value) <= 18
