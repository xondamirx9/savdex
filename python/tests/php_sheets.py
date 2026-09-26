"""
Описание листов выгрузки, прочитанное из PHP-исходника.

Нужно для одной проверки: описание листов в Python-версии
(`savdex/export/sheets.py`) обязано совпадать с PHP-версией столбец
в столбец, пока обе живут рядом. Иначе правка в одной половине тихо
разведёт две выгрузки, и сверка «PHP против Python» начнёт ругаться
на то, что никто не менял.

Разбирается не весь PHP, а ровно одна конструкция:
`$this->sheet($db, 'Имя', 'таблица', 'описание', [['Заголовок', 'поле', 'тип'], ...])`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ИСХОДНИК = Path(__file__).resolve().parents[2] / "app/Console/Commands/ExportWorkbooks.php"

# Строка PHP в одинарных кавычках: \' и \\ внутри экранированы
_СТРОКА = r"'((?:[^'\\]|\\.)*)'"


@dataclass(frozen=True)
class PhpSheet:
    book: str
    name: str
    table: str
    about: str
    columns: tuple[tuple[str, str, str], ...]


def _php(s: str) -> str:
    return s.replace("\\'", "'").replace("\\\\", "\\")


def read_php_sheets(source: Path = ИСХОДНИК) -> list[PhpSheet]:
    text = source.read_text(encoding="utf-8")

    # Книга определяется методом, внутри которого стоит лист
    companies = text.index("function companySheets")
    listings = text.index("function listingSheets")
    machinery = text.index("private function sheet(")

    books = {
        "companies": text[companies:listings],
        "listings": text[listings:machinery],
    }

    head = re.compile(
        r"\$this->sheet\(\$db,\s*" + _СТРОКА + r",\s*" + _СТРОКА + r",\s*" + _СТРОКА + r",\s*\[",
        re.S,
    )
    triple = re.compile(r"\[\s*" + _СТРОКА + r"\s*,\s*" + _СТРОКА + r"\s*,\s*" + _СТРОКА + r"\s*\]")

    sheets: list[PhpSheet] = []

    for book, body in books.items():
        for match in head.finditer(body):
            # Столбцы — до закрывающей «]),» этого листа
            end = body.index("]),", match.end())
            columns = tuple(
                (_php(h), _php(k), _php(t)) for h, k, t in triple.findall(body[match.end() : end])
            )
            sheets.append(
                PhpSheet(
                    book=book,
                    name=_php(match.group(1)),
                    table=_php(match.group(2)),
                    about=_php(match.group(3)),
                    columns=columns,
                )
            )

    return sheets
