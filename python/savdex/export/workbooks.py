"""
Выгрузка базы в две книги Excel: компании и объявления.

Перенос `savdex:export-xlsx` из PHP — недели 3–4 этапа 1
(`docs/migration-to-python.md`, раздел 8). Самая содержательная из
безопасных команд: читает почти всю базу и пишет файлы, но в базу
не пишет ничего.

Зачем выгрузка вообще (из PHP-версии): снять с площадки всё живое
перед чисткой тестовых аккаунтов. Поэтому выгружается не витрина,
а содержимое таблиц — с идентификаторами, служебными полями
и удалёнными записями. Читаемые названия стоят рядом с идентификаторами,
а не вместо них: человеку нужны первые, восстановлению — вторые.

Записанное проверяется: файл открывается заново, и каждая ячейка
сверяется с повторным запросом к базе. Молча испорченная выгрузка хуже
отсутствующей — на неё полагаются, когда база уже стёрта.

## Чем отличается от PHP-версии

**Поля JSON забираются текстом.** Драйвер psycopg сам разбирает столбцы
типа `json` в словари, а PHP получает их сырым текстом и так и пишет.
Собрать словарь обратно в тот же текст нельзя — поменяются пробелы
и экранирование кириллицы, — поэтому на время выгрузки драйверу
велено отдавать `json` строкой. `jsonb` Django и так отдаёт строкой.

**Значения приводятся к тому, что увидел бы PHP.** PDO отдаёт
PHP-коду числа и строки, psycopg — Decimal, datetime и bool. Где
тип столбца в описании листа не совпадает с типом в базе (скажем,
логическое поле описано как текст), результат обязан совпасть с тем,
что дало бы (string) в PHP: true → «1», false → пусто.

Остальное — построчно то же, вплоть до ширины столбцов.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from savdex.export.sheets import COMPANY_SHEETS, LISTING_SHEETS, Sheet

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from openpyxl.worksheet._write_only import WriteOnlyWorksheet

#: Предел длины ячейки в формате Excel
CELL_LIMIT = 32000

#: Вычисляемое поле → (справочник, поле записи с идентификатором)
LOOKUPS: dict[str, tuple[str, str]] = {
    "@users_count": ("users_count", "id"),
    "@listings_total": ("listings_total", "id"),
    "@listings_active": ("listings_active", "id"),
    "@unlocks_made": ("unlocks_made", "id"),
    "@country": ("countries", "country_id"),
    "@city": ("cities", "city_id"),
    "@category": ("categories", "category_id"),
    "@company": ("companies", "company_id"),
    "@target_company": ("companies", "target_company_id"),
    "@author_company": ("companies", "author_company_id"),
    "@user": ("users", "user_id"),
    "@verified_by": ("users", "verified_by"),
    "@plan": ("plans", "plan_id"),
    "@listing": ("listings", "listing_id"),
}

#: Справочники-счётчики: отсутствие значения — это ноль, а не пусто
COUNTERS = frozenset({"users_count", "listings_total", "listings_active", "unlocks_made"})

# Оформление — то же, что у PHP-версии
HEAD_FONT = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="2E5C86")
HEAD_ALIGN = Alignment(vertical="center", wrap_text=False)
TITLE_FONT = Font(bold=True, size=16)
MUTED_FONT = Font(color="595959")

Value = str | int | float


class ExportError(RuntimeError):
    """Описание листа не сходится с таблицей — выгружать нельзя."""


@dataclass(frozen=True)
class Book:
    file: Path
    title: str
    about: str
    sheets: tuple[Sheet, ...]


@dataclass
class Collected:
    """Лист с собранными строками."""

    sheet: Sheet
    rows: list[list[Value]]

    @property
    def headers(self) -> list[str]:
        return [header for header, _, _ in self.sheet.columns]


@dataclass
class Verdict:
    """Итог сверки: строки отчёта и найденные расхождения."""

    report: list[tuple[str, str, int, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


# ── Значения ────────────────────────────────────────────────────────


def php_string(value: Any) -> str:  # noqa: ANN401
    """
    То, что дал бы (string) в PHP для значения из PDO.

    Нужно там, где тип столбца в описании листа и тип в базе
    не совпадают: выгрузка обязана совпасть с PHP-версией ячейка
    в ячейку.
    """
    if value is None or value is False:
        return ""

    if value is True:
        return "1"

    if isinstance(value, (dict, list)):
        # Запасной путь: json уже велено отдавать текстом (см. заголовок).
        # PHP-версия кодирует с JSON_UNESCAPED_UNICODE и экранирует «/»
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("/", "\\/")

    return str(value)


def php_int(value: Any) -> int:  # noqa: ANN401
    """(int) в PHP: дробная часть отбрасывается к нулю."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    return int(Decimal(str(value)))


class Exporter:
    """Одна выгрузка: справочники, сбор листов, запись и сверка."""

    def __init__(self, connection: BaseDatabaseWrapper) -> None:
        self.connection = connection
        self.truncated = 0
        self.dictionaries: dict[str, dict[int, Value]] = {}

    # ── База ────────────────────────────────────────────────────────

    def prepare(self) -> None:
        """
        Соединение и справочники.

        Для PostgreSQL драйверу велено отдавать `json` строкой — причина
        в заголовке модуля.
        """
        self.connection.ensure_connection()

        if self.connection.vendor == "postgresql":
            from psycopg.types.string import TextLoader

            raw = self.connection.connection
            raw.adapters.register_loader("json", TextLoader)
            raw.adapters.register_loader("jsonb", TextLoader)

        self.load_dictionaries()

    def _records(self, sql: str) -> Iterator[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            names = [column[0] for column in cursor.description]

            while batch := cursor.fetchmany(500):
                for row in batch:
                    yield dict(zip(names, row, strict=True))

    def _quote(self, name: str) -> str:
        return str(self.connection.ops.quote_name(name))

    def count(self, table: str) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(f"select count(*) from {self._quote(table)}")
            row = cursor.fetchone()

        return int(row[0]) if row else 0

    # ── Справочники ─────────────────────────────────────────────────

    def load_dictionaries(self) -> None:
        self.dictionaries = {
            "countries": self.translations("country_translations", "country_id"),
            "cities": self.translations("city_translations", "city_id"),
            "categories": self.translations("category_translations", "category_id"),
            "companies": self.column("companies", "name"),
            "users": self.column("users", "email"),
            "plans": self.column("plans", "name"),
            "listings": self.column("listings", "title"),
            # Живую компанию от тестовой отличает не карточка, а след:
            # сколько у неё людей, объявлений и оплаченных раскрытий
            "users_count": self.counts("users", "company_id"),
            "listings_total": self.counts("listings", "company_id"),
            "listings_active": self.counts("listings", "company_id", status="active"),
            "unlocks_made": self.counts("contact_unlocks", "company_id"),
        }

    def translations(self, table: str, key: str) -> dict[int, Value]:
        """Названия из таблицы переводов: русский, иначе любой имеющийся."""
        names: dict[int, Value] = {}

        for row in self._records(f"select * from {self._quote(table)} order by id"):
            ident = php_int(row[key])

            if row["locale"] == "ru" or ident not in names:
                names[ident] = php_string(row["name"])

        return names

    def column(self, table: str, name: str) -> dict[int, Value]:
        sql = f"select id, {self._quote(name)} from {self._quote(table)}"

        return {php_int(row["id"]): php_string(row[name]) for row in self._records(sql)}

    def counts(self, table: str, name: str, status: str | None = None) -> dict[int, Value]:
        """
        Сколько строк таблицы приходится на каждое значение колонки.

        Подсчёт в коде, а не GROUP BY, как у PHP-версии: одинаково
        на SQLite и PostgreSQL.
        """
        sql = f"select {self._quote(name)} from {self._quote(table)}"

        if status is not None:
            # Значение — литерал из этого модуля, не ввод пользователя
            sql += f" where status = '{status}'"

        result: dict[int, Value] = {}

        for row in self._records(sql):
            ident = row[name]

            if ident is not None:
                key = php_int(ident)
                result[key] = int(result.get(key, 0)) + 1

        return result

    # ── Сбор листа ──────────────────────────────────────────────────

    def assert_columns_sane(self, sheet: Sheet) -> None:
        """
        Описание листа не должно врать о таблице.

        Повторяющийся заголовок затёр бы соседний столбец, а опечатка
        в имени поля молча дала бы пустой столбец — на выгрузке перед
        чисткой базы это выглядит как «данных нет».
        """
        headers = [header for header, _, _ in sheet.columns]
        duplicates = sorted({h for h in headers if headers.count(h) > 1})

        if duplicates:
            raise ExportError(
                f"Лист «{sheet.name}»: заголовки повторяются — {', '.join(duplicates)}"
            )

        with self.connection.cursor() as cursor:
            existing = {
                column.name
                for column in self.connection.introspection.get_table_description(
                    cursor, sheet.table
                )
            }

        for header, key, _ in sheet.columns:
            if not key.startswith("@") and key not in existing:
                raise ExportError(
                    f"Лист «{sheet.name}»: в таблице {sheet.table} нет поля «{key}» "
                    f"(колонка «{header}»)"
                )

    def fetch(self, sheet: Sheet) -> list[list[Value]]:
        """Строки таблицы, приведённые к значениям ячеек."""
        rows: list[list[Value]] = []
        sql = f"select * from {self._quote(sheet.table)} order by id"

        for record in self._records(sql):
            rows.append(
                [
                    self.lookup(key, record)
                    if key.startswith("@")
                    else self.cell(record.get(key), kind)
                    for _, key, kind in sheet.columns
                ]
            )

        return rows

    def collect(self, sheet: Sheet) -> Collected:
        self.assert_columns_sane(sheet)

        return Collected(sheet=sheet, rows=self.fetch(sheet))

    def lookup(self, key: str, record: dict[str, Any]) -> Value:
        """Читаемое название вместо идентификатора."""
        dictionary, name = LOOKUPS.get(key, ("", ""))
        ident = record.get(name)

        if ident is None or dictionary == "":
            return ""

        value = self.dictionaries[dictionary].get(php_int(ident))

        # Счётчик, которого нет в справочнике, — это ноль, а не пустая
        # ячейка: «объявлений нет» и «не считали» читаются по-разному
        if dictionary in COUNTERS:
            return php_int(value or 0)

        return php_string(value)

    def cell(self, value: Any, kind: str) -> Value:  # noqa: ANN401
        """Значение ячейки: тип задан колонкой, а не угадывается по виду."""
        if value is None or value == "":
            return ""

        if kind == "int":
            return php_int(value)

        if kind == "float":
            return float(value)

        if kind == "bool":
            return "да" if bool(value) and value != "f" else "нет"

        if kind == "date":
            return self.text(value)[:10]

        if kind == "datetime":
            return self.text(value).replace("T", " ")[:19]

        return self.text(value)

    def text(self, value: Any) -> str:  # noqa: ANN401
        """
        Текст ячейки.

        Телефоны, ИНН и адреса страниц остаются строками намеренно:
        Excel превращает «00998…» в число и съедает ведущие нули.
        """
        # Для дат php_string даёт str(datetime) — то же, что текст
        # PostgreSQL для timestamp(0), который и увидел бы PHP
        text = php_string(value)

        if len(text) > CELL_LIMIT:
            self.truncated += 1

            return text[:CELL_LIMIT] + " […обрезано]"

        return text

    # ── Книги ───────────────────────────────────────────────────────


def books(directory: Path, now: datetime | None = None) -> tuple[Book, Book]:
    """Две книги с именами файлов по времени выгрузки."""
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d-%H%M")

    return (
        Book(
            file=directory / f"savdex-companies-{stamp}.xlsx",
            title="SAVDEX — компании",
            about=(
                "Компании площадки и всё, что к ним привязано: сотрудники, контакты, "
                "документы, кошельки, подписки, раскрытия контактов и отзывы."
            ),
            sheets=COMPANY_SHEETS,
        ),
        Book(
            file=directory / f"savdex-listings-{stamp}.xlsx",
            title="SAVDEX — объявления",
            about=(
                "Объявления площадки и всё, что к ним привязано: фотографии, "
                "характеристики, статистика по дням, избранное. Отдельным листом — тендеры."
            ),
            sheets=LISTING_SHEETS,
        ),
    )


def width(header: str, kind: str) -> float:
    """Ширина колонки по её роли: даты и числа узкие, тексты широкие."""
    if header.startswith("ID"):
        return 9

    if kind in ("int", "float", "bool"):
        return 14

    if kind == "date":
        return 12

    if kind == "datetime":
        return 19

    if header in ("Описание", "Текст", "Замечание модератора", "Заметка"):
        return 60

    return 26


def _styled(
    sheet: WriteOnlyWorksheet,
    values: list[Any],
    font: Font | None = None,
    fill: PatternFill | None = None,
    align: Alignment | None = None,
) -> list[Any]:
    cells = []

    for value in values:
        cell = WriteOnlyCell(sheet, value=value)

        # Текст «=…» из базы — строкой, а не формулой, которую Excel выполнит
        if isinstance(value, str) and value.startswith("="):
            cell.data_type = "s"

        if font is not None:
            cell.font = font

        if fill is not None:
            cell.fill = fill

        if align is not None:
            cell.alignment = align

        cells.append(cell)

    return cells


def write(book: Book, collected: list[Collected], now: datetime | None = None) -> None:
    """
    Запись книги.

    Потоком (write_only), как у OpenSpout в PHP-версии: статистика
    по дням на живой базе — десятки тысяч строк, держать их в памяти
    целиком незачем.
    """
    workbook = Workbook(write_only=True)
    workbook.properties.creator = "SAVDEX"

    _write_legend(workbook, book, collected, now or datetime.now(UTC))

    for sheet in collected:
        _write_sheet(workbook, sheet)

    workbook.save(book.file)


def _write_legend(
    workbook: Workbook, book: Book, collected: list[Collected], now: datetime
) -> None:
    """
    Первый лист — путеводитель по книге.

    Без него человек открывает файл на десять вкладок и гадает, чем
    «Контакты» отличаются от «Доп. полей».
    """
    page = workbook.create_sheet("Справка")
    page.column_dimensions["A"].width = 34
    page.column_dimensions["B"].width = 96
    page.column_dimensions["C"].width = 12

    page.append(_styled(page, [book.title], font=TITLE_FONT))
    page.append(_styled(page, [book.about], font=MUTED_FONT))
    page.append([])
    page.append(_styled(page, ["Выгружено", now.strftime("%d.%m.%Y %H:%M")], font=MUTED_FONT))
    page.append(_styled(page, ["Всего листов с данными", len(collected)], font=MUTED_FONT))
    page.append(
        _styled(page, ["Всего строк", sum(len(s.rows) for s in collected)], font=MUTED_FONT)
    )
    page.append([])
    page.append(
        _styled(
            page,
            ["Лист", "Что содержит", "Строк"],
            font=HEAD_FONT,
            fill=HEAD_FILL,
            align=Alignment(vertical="center"),
        )
    )

    for sheet in collected:
        page.append([sheet.sheet.name, sheet.sheet.about, len(sheet.rows)])

    page.append([])
    page.append(
        _styled(
            page,
            [
                "Как читать",
                "Рядом с каждым «ID …» стоит читаемое название. Идентификаторы нужны, "
                "чтобы связать листы между собой и восстановить данные; названия — чтобы "
                "читать глазами. Пустая ячейка означает, что значения в базе нет.",
            ],
            font=MUTED_FONT,
        )
    )
    page.append(
        _styled(
            page,
            [
                "",
                "Столбцы «Удалена» и «Удалено» заполнены у записей, скрытых с сайта, "
                "но не стёртых из базы. В выгрузку они включены намеренно.",
            ],
            font=MUTED_FONT,
        )
    )


def _write_sheet(workbook: Workbook, collected: Collected) -> None:
    page = workbook.create_sheet(collected.sheet.name)
    headers = collected.headers

    # До первой строки: в потоковом режиме размеры и закрепление
    # задаются заранее, потом их уже не поменять
    for index, (header, _, kind) in enumerate(collected.sheet.columns, start=1):
        page.column_dimensions[get_column_letter(index)].width = width(header, kind)

    # Шапка остаётся на экране при прокрутке, а фильтр позволяет
    # отобрать, например, все объявления одной компании
    page.freeze_panes = "A2"

    if collected.rows:
        page.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(collected.rows) + 1}"

    page.append(_styled(page, headers, font=HEAD_FONT, fill=HEAD_FILL, align=HEAD_ALIGN))

    for row in collected.rows:
        page.append(row)


# ── Сверка ──────────────────────────────────────────────────────────


def read(file: Path) -> dict[str, list[list[Any]]]:
    """Содержимое книги: лист → строки значений."""
    workbook = load_workbook(file, read_only=True, data_only=True)

    try:
        return {
            sheet.title: [list(row) for row in sheet.iter_rows(values_only=True)]
            for sheet in workbook.worksheets
        }
    finally:
        workbook.close()


def same(expected: Any, written: Any) -> bool:  # noqa: ANN401
    """
    Совпадают ли значение из базы и прочитанное из файла.

    Excel не хранит пустую ячейку и отдаёт её как пустоту, число
    приходит как float, дата — как объект. Обе стороны приводятся
    к одному виду, иначе сверка тонула бы в ложных тревогах.
    """
    if isinstance(written, datetime):
        written = written.strftime("%Y-%m-%d %H:%M:%S")

    empty_expected = expected in ("", None)
    empty_written = written in ("", None)

    if isinstance(expected, float) or isinstance(written, float):
        if empty_expected != empty_written:
            return False

        if empty_expected:
            return True

        return abs(float(expected) - float(written)) < 0.0000001

    return php_string(expected) == php_string(written)


def compare(
    name: str, headers: list[str], expected: list[list[Value]], actual: list[list[Any]]
) -> list[str]:
    """Построчная сверка листа."""
    problems: list[str] = []

    if "ID" in headers:
        at = headers.index("ID")
        from_database = [php_string(row[at]) for row in expected]
        from_file = [php_string(row[at] if at < len(row) else "") for row in actual]

        missing = [i for i in from_database if i not in set(from_file)]
        extra = [i for i in from_file if i not in set(from_database)]

        if missing:
            problems.append(f"{name}: в файле нет записей с ID {', '.join(missing[:5])}")

        if extra:
            problems.append(f"{name}: в файле лишние ID {', '.join(extra[:5])}")

    for index, row in enumerate(expected):
        line = actual[index] if index < len(actual) else []

        for position, value in enumerate(row):
            written = line[position] if position < len(line) else None

            if same(value, written):
                continue

            problems.append(
                f"{name} строка {index + 2}, «{headers[position]}»: "
                f"в базе [{php_string(value)[:40]}], в файле [{php_string(written)[:40]}]"
            )

            if len(problems) > 40:
                return problems

    return problems


def verify(exporter: Exporter, written: list[tuple[Book, list[Collected]]]) -> Verdict:
    """
    Файл открывается заново и сверяется с базой.

    Сверяется не с тем, из чего писали, а с повторным запросом: иначе
    проверка подтвердила бы сама себя. Отдельно сверяются наборы
    идентификаторов — так видно пропавшую строку, даже если их число
    случайно совпало.
    """
    verdict = Verdict()

    for book, collected in written:
        on_disk = read(book.file)

        for sheet in collected:
            name = sheet.sheet.name
            expected = exporter.fetch(sheet.sheet)
            actual = on_disk.get(name)

            if actual is None:
                verdict.problems.append(f"{name}: листа нет в файле")

                continue

            headers = sheet.headers
            in_database = exporter.count(sheet.sheet.table)

            if [php_string(h) for h in actual[0]] != headers:
                verdict.problems.append(f"{name}: шапка в файле не совпадает с ожидаемой")

            body = actual[1:]

            if not len(body) == len(expected) == in_database:
                verdict.problems.append(
                    f"{name}: строк в базе {in_database}, собрано {len(expected)}, "
                    f"в файле {len(body)}"
                )

                continue

            mismatch = compare(name, headers, expected, body)
            verdict.problems.extend(mismatch)
            verdict.report.append(
                (book.file.name, name, in_database, "сходится" if not mismatch else "РАСХОЖДЕНИЕ")
            )

    return verdict
