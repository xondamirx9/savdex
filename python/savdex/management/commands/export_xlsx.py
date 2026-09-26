"""
Консольная часть выгрузки.

Содержательная часть — в `savdex.export.workbooks`; здесь каталог,
печать и код возврата.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import connections

from savdex.console import table
from savdex.export.workbooks import Collected, Exporter, ExportError, books, verify, write


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

            raise SystemExit(1)

        self.stdout.write(
            "Все листы сошлись: число строк, шапки, наборы идентификаторов и каждая ячейка."
        )

        for book, _ in written:
            self.stdout.write(f"  {book.file}  ({_size(book.file)})")


def _size(file: Path) -> str:
    size = file.stat().st_size

    return f"{round(size / 1048576, 1)} МБ" if size > 1048576 else f"{round(size / 1024)} КБ"
