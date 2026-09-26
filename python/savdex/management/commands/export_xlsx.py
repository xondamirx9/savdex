"""
Консольная часть выгрузки.

Содержательная часть — в `savdex.export.workbooks`; здесь каталог,
печать и код возврата.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import connections

from savdex.console import table
from savdex.export.compare import pair
from savdex.export.workbooks import Collected, Exporter, ExportError, books, verify, write

#: Метка строки с итогом для вызывающей стороны (--json). По ней
#: PHP находит итог в выводе, не гадая, какая строка последняя
RESULT = "SAVDEX-RESULT "


class Command(BaseCommand):
    help = "Выгрузить компании и объявления в два файла Excel со сверкой"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dir",
            default=str(Path(settings.BASE_DIR) / "storage" / "exports"),
            help="Каталог для файлов",
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Имя подключения из settings.DATABASES",
        )
        parser.add_argument(
            "--compare-with",
            default="",
            help="Каталог с книгами PHP-версии: сверить свои книги с ними ячейка в ячейку",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Последней строкой напечатать итог для программы (для вызова из PHP)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        directory = Path(str(options["dir"]))
        connection = connections[str(options["database"])]

        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.stderr.write(f"Не удалось создать каталог {directory}")

            raise SystemExit(1) from None

        self.stdout.write(f"База: {connection.alias} ({connection.vendor})")
        self.stdout.write(f"Каталог: {directory}")
        self.stdout.write("")

        exporter = Exporter(connection)
        exporter.prepare()

        written: list[tuple[Any, list[Collected]]] = []

        for book in books(directory):
            try:
                collected = [exporter.collect(sheet) for sheet in book.sheets]
            except ExportError as error:
                self.stderr.write(str(error))

                raise SystemExit(1) from None

            try:
                write(book, collected)
            except OSError as error:
                self.stderr.write(f"Запись {book.file.name}: {error}")

                raise SystemExit(1) from None

            self.stdout.write(f"Записано: {book.file.name}")
            written.append((book, collected))

        self.stdout.write("")
        self.stdout.write("Сверка записанного с базой…")
        self.stdout.write("")

        verdict = verify(exporter, written)

        for line in table(("Файл", "Лист", "Строк", "Сверка"), verdict.report):
            self.stdout.write(line)

        self.stdout.write("")

        if exporter.truncated:
            self.stdout.write(
                f"Значений, обрезанных до предела Excel: {exporter.truncated}. "
                "Они помечены в ячейке."
            )

        if verdict.problems:
            self.stderr.write(f"Расхождения ({len(verdict.problems)}):")

            for problem in verdict.problems[:20]:
                self.stderr.write(f"  {problem}")
        else:
            self.stdout.write(
                "Все листы сошлись: число строк, шапки, наборы идентификаторов и каждая ячейка."
            )

            for book, _ in written:
                self.stdout.write(f"  {book.file}  ({_size(book.file)})")

        against_php = self._compare(str(options["compare_with"]), directory)

        if options["json"]:
            self.stdout.write(
                RESULT
                + json.dumps(
                    {
                        "self_check": not verdict.problems,
                        "self_problems": verdict.problems[:20],
                        "compared": against_php is not None,
                        "differences": sum(len(p) for p in (against_php or {}).values()),
                        "problems": [p for ps in (against_php or {}).values() for p in ps][:20],
                        "truncated": exporter.truncated,
                    },
                    ensure_ascii=False,
                )
            )

        if verdict.problems or any((against_php or {}).values()):
            raise SystemExit(1)

    def _compare(self, php_dir: str, own_dir: Path) -> dict[str, list[str]] | None:
        """
        Сверка своих книг с книгами PHP-версии, если попросили.

        Собственная сверка слепа к ошибке своего же чтения базы (так было
        с полями JSON), поэтому на боевом сервере Python-версия каждый
        раз сверяется ещё и с PHP-версией, выгрузившей те же данные.
        """
        if php_dir == "":
            return None

        result = pair(Path(php_dir), own_dir)

        self.stdout.write("")
        self.stdout.write("Сверка с выгрузкой PHP-версии:")

        for kind, problems in result.items():
            self.stdout.write(
                f"  {kind}: " + ("совпадает" if not problems else f"расхождений {len(problems)}")
            )

            for problem in problems[:10]:
                self.stdout.write(f"    {problem}")

        return result


def _size(file: Path) -> str:
    size = file.stat().st_size

    return f"{round(size / 1048576, 1)} МБ" if size > 1048576 else f"{round(size / 1024)} КБ"
