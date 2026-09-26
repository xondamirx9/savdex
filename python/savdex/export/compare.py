"""
Сравнение двух книг Excel: выгрузки PHP-версии и Python-версии.

Живёт в рабочем коде, а не в тестах: им пользуется и проверка в CI,
и каждая выгрузка на боевом сервере. Пока Python-версия не заменила
PHP-версию, каждая выгрузка из админки делается обеими, и книги
сверяются этим модулем — на настоящих данных, а не на проверочных.

Сравнивается всё, что видит человек, открывший файл: порядок листов,
каждая ячейка вместе с типом (число или текст — «00998…» строкой
и числом это разные вещи), ширина столбцов, закреплённая шапка
и фильтр. Время выгрузки на листе «Справка» не сравнивается —
две выгрузки не делаются в одну и ту же секунду.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell, MergedCell

# Ячейка времени выгрузки: лист «Справка», строка 4, столбец B
ВРЕМЯ = ("Справка", 4, 2)


def _значение(cell: Cell | MergedCell) -> tuple[str, object]:
    value = cell.value

    # Пустая строка и пустая ячейка для человека неразличимы
    if value is None or value == "":
        return ("пусто", None)

    if isinstance(value, bool):
        return ("bool", value)

    if isinstance(value, (int, float)):
        # 5 и 5.0 — одно число; тип различаем только число/текст
        return ("число", float(value))

    return ("текст", str(value))


def diff(php_file: Path, py_file: Path) -> list[str]:
    php = load_workbook(php_file)
    py = load_workbook(py_file)
    problems: list[str] = []

    if php.sheetnames != py.sheetnames:
        return [f"порядок листов: PHP {php.sheetnames}, Python {py.sheetnames}"]

    for name in php.sheetnames:
        a, b = php[name], py[name]
        rows = max(a.max_row, b.max_row)
        cols = max(a.max_column, b.max_column)

        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                if (name, r, c) == ВРЕМЯ:
                    continue

                va, vb = _значение(a.cell(r, c)), _значение(b.cell(r, c))

                if (
                    isinstance(va[1], float)
                    and isinstance(vb[1], float)
                    and abs(va[1] - vb[1]) < 1e-9
                ):
                    continue

                if va != vb:
                    problems.append(f"{name}!{a.cell(r, c).coordinate}: PHP {va}, Python {vb}")

        for letter, dim in a.column_dimensions.items():
            wa = dim.width
            wb = b.column_dimensions[letter].width

            if wa and abs((wa or 0) - (wb or 0)) > 0.01:
                problems.append(f"{name} ширина {letter}: PHP {wa}, Python {wb}")

        if (a.freeze_panes or None) != (b.freeze_panes or None):
            problems.append(f"{name} закрепление: PHP {a.freeze_panes}, Python {b.freeze_panes}")

        if (a.auto_filter.ref or None) != (b.auto_filter.ref or None):
            problems.append(f"{name} фильтр: PHP {a.auto_filter.ref}, Python {b.auto_filter.ref}")

        # Оформление шапки: жирный белый на синем
        for c in range(1, cols + 1):
            ha, hb = a.cell(1, c), b.cell(1, c)

            if name != "Справка" and (
                bool(ha.font.b) != bool(hb.font.b)
                or (ha.fill.fgColor.rgb or "")[-6:] != (hb.fill.fgColor.rgb or "")[-6:]
            ):
                problems.append(f"{name} оформление шапки {ha.coordinate} различается")

                break

    return problems


def pair(php_dir: Path, py_dir: Path) -> dict[str, list[str]]:
    """
    Сравнить книги двух выгрузок по видам: компании и объявления.

    Книга, которой нет в одной из папок, — тоже расхождение: выгрузка,
    потерявшая книгу, не должна сходить за совпавшую.
    """
    result: dict[str, list[str]] = {}

    for kind in ("companies", "listings"):
        php = sorted(php_dir.glob(f"savdex-{kind}-*.xlsx"))
        py = sorted(py_dir.glob(f"savdex-{kind}-*.xlsx"))

        if not php or not py:
            where = "PHP" if not php else "Python"
            result[kind] = [f"нет книги {kind} в выгрузке {where}"]

            continue

        result[kind] = diff(php[-1], py[-1])

    return result
