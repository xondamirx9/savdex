"""
Консольная часть проверки базы.

Здесь только соединение, рисование таблицы и код возврата: сама
проверка живёт в `savdex.checks`, чтобы её можно было прогнать
без запуска консоли.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import connections
from django.db.utils import OperationalError

from savdex.checks import Report, inspect, reason

# То, чего из SQL не видно. Список тот же, что у PHP-версии: человек
# должен различать «проверено» и «проверить нечем»
PANEL = (
    "регион базы совпадает с регионом сервиса (потом не поменять);",
    "тариф платный, с бэкапами (бесплатная база удаляется через 30 дней);",
    "в Access Control только нужные адреса, без 0.0.0.0/0;",
    "адрес базы у службы Django совпадает с адресом у службы Laravel.",
)


class Command(BaseCommand):
    help = "Проверить базу PostgreSQL: доступность, права, схему и данные"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--database",
            default="default",
            help="Имя подключения из settings.DATABASES",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        name = str(options["database"])

        self.stdout.write(f"Проверка базы, подключение «{name}».")
        self.stdout.write("")

        report = Report()
        connection = connections[name]

        try:
            connection.ensure_connection()
        except OperationalError as error:
            report.problem("Соединение", "не установлено", reason(str(error)))
        else:
            report.ok("Адрес базы", "задан")
            report = inspect(connection)
            report.rows.insert(0, ("✓", "Адрес базы", "задан"))

        self._print(report)

        if report.blocked:
            self.stderr.write("База к работе не готова — сначала устраните отмеченное.")

            raise SystemExit(1)

        self.stdout.write("База доступна, права понятны, схема и данные читаются.")

    def _print(self, report: Report) -> None:
        self._table(report.rows)

        if report.advice:
            self.stdout.write("")

            for line in report.advice:
                self.stdout.write(f"  {line}")

        self.stdout.write("")
        self.stdout.write("Из SQL не видно, это смотрите в панели Render:")

        for line in PANEL:
            self.stdout.write(f"  • {line}")

        self.stdout.write("")

    def _table(self, rows: list[tuple[str, str, str]]) -> None:
        """
        Своя отрисовка: у Django таблиц в консоли нет.

        Ширина по содержимому, как у Laravel, — вывод двух реализаций
        сравнивают глазами, и одинаковая рамка это заметно облегчает.
        """
        header = ("", "Что", "Состояние")
        widths = [max(len(row[i]) for row in (header, *rows)) for i in range(3)]
        rule = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

        def line(row: tuple[str, str, str]) -> str:
            return "| " + " | ".join(row[i].ljust(widths[i]) for i in range(3)) + " |"

        self.stdout.write(rule)
        self.stdout.write(line(header))
        self.stdout.write(rule)

        for row in rows:
            self.stdout.write(line(row))

        self.stdout.write(rule)
