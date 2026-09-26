"""
Консольная часть выгрузки.

Содержательная часть — в `savdex.export.workbooks`; здесь каталог,
печать и код возврата.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import connections, transaction
from django.db.backends.base.base import BaseDatabaseWrapper

from savdex.console import table
from savdex.export.compare import pair
from savdex.export.workbooks import (
    Book,
    Collected,
    Exporter,
    ExportError,
    Verdict,
    books,
    verify,
    write,
)

#: Метка строки с итогом для вызывающей стороны (--json). По ней
#: PHP находит итог в выводе, не гадая, какая строка последняя
RESULT = "SAVDEX-RESULT "

#: Вид идентификатора снимка, который выдаёт pg_export_snapshot():
#: «00000003-0000001B-1» (до PostgreSQL 13 — «000003A1-1»). SET TRANSACTION SNAPSHOT не принимает
#: параметров запроса, значение вставляется в текст — поэтому только
#: строго такой вид и ничего больше
SNAPSHOT = re.compile(r"[0-9A-F]{8}(?:-[0-9A-F]{8})?-[0-9]{1,10}")


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
            "--snapshot",
            default="",
            help="Снимок базы от pg_export_snapshot(): читать ровно то, что видит вызывающий",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Последней строкой напечатать итог для программы (для вызова из PHP)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        directory = Path(str(options["dir"]))
        connection = connections[str(options["database"])]
        snapshot = str(options["snapshot"])

        if snapshot != "" and (
            connection.vendor != "postgresql" or not SNAPSHOT.fullmatch(snapshot)
        ):
            self.stderr.write(f"Неверный снимок базы: {snapshot!r}")

            raise SystemExit(1)

        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.stderr.write(f"Не удалось создать каталог {directory}")

            raise SystemExit(1) from None

        self.stdout.write(f"База: {connection.alias} ({connection.vendor})")
        self.stdout.write(f"Каталог: {directory}")
        self.stdout.write("")

        with _consistent(connection, snapshot):
            verdict, written, truncated = self._export(connection, directory)

        for line in table(("Файл", "Лист", "Строк", "Сверка"), verdict.report):
            self.stdout.write(line)

        self.stdout.write("")

        if truncated:
            self.stdout.write(
                f"Значений, обрезанных до предела Excel: {truncated}. Они помечены в ячейке."
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
                        "truncated": truncated,
                    },
                    ensure_ascii=False,
                )
            )

        if verdict.problems or any((against_php or {}).values()):
            raise SystemExit(1)

    def _export(
        self, connection: BaseDatabaseWrapper, directory: Path
    ) -> tuple[Verdict, list[tuple[Book, list[Collected]]], int]:
        """Выгрузить книги и сверить их с базой — всё внутри одного снимка."""
        exporter = Exporter(connection)
        exporter.prepare()

        written: list[tuple[Book, list[Collected]]] = []

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

        return verify(exporter, written), written, exporter.truncated

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


@contextmanager
def _consistent(connection: BaseDatabaseWrapper, snapshot: str) -> Iterator[None]:
    """
    Читать базу одним неизменным снимком.

    Сайт живёт, пока идёт выгрузка: счётчики просмотров растут, ставки
    приходят. Без снимка лист тендеров пишется с одним числом
    просмотров, а сверка через секунду читает уже другое — и честная
    выгрузка «расходится». REPEATABLE READ держит одно состояние базы
    на всю транзакцию, READ ONLY заодно запрещает запись.

    С --snapshot транзакция берёт снимок вызывающего (PHP-выгрузки),
    и обе версии читают буква в букву одно и то же. Обе команды
    SET TRANSACTION обязаны идти первыми, до любого чтения.

    Транзакция только читает, поэтому в конце откатывается.
    """
    if connection.vendor != "postgresql":
        yield

        return

    # Подключение и его настройка (часовой пояс и т. п.) — до транзакции,
    # чтобы первым запросом в ней наверняка был SET TRANSACTION
    connection.ensure_connection()

    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")

            if snapshot != "":
                cursor.execute(f"SET TRANSACTION SNAPSHOT '{snapshot}'")

        try:
            yield
        finally:
            transaction.set_rollback(True, using=connection.alias)


def _size(file: Path) -> str:
    size = file.stat().st_size

    return f"{round(size / 1048576, 1)} МБ" if size > 1048576 else f"{round(size / 1024)} КБ"
