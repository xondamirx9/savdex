"""
Чистка витрины по ТЗ-01 — сначала список, потом правка (savdex/data/showcase_cleanup.py).

  manage.py showcase_cleanup report --dir /var/data/cleanup
      три файла CSV: demand.csv, descriptions.csv, companies.csv — команде
      на просмотр; лишние строки из файлов удаляют
  manage.py showcase_cleanup apply --dir /var/data/cleanup [--dry-run]
      применить ровно те номера, что остались в файлах
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from savdex.data import showcase_cleanup


class Command(BaseCommand):
    help = "ТЗ-01: заявки «куплю» → запросы, чистка описаний заявок, скрытие тестовых компаний"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=["report", "apply"])
        parser.add_argument("--dir", required=True, help="Папка с файлами CSV")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Для apply: только посчитать, что изменится, ничего не записывая",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        directory = Path(str(options["dir"]))

        if options["action"] == "report":
            counts = showcase_cleanup.report(directory)

            for name, count in counts.items():
                self.stdout.write(f"{directory / name}: строк {count}")

            self.stdout.write(
                "Отправьте файлы команде. Лишние строки удалите из файла — "
                "apply применит только оставшиеся номера."
            )

            return

        if not directory.is_dir():
            self.stderr.write(f"Нет папки {directory}: сначала report.")

            raise SystemExit(1)

        done = showcase_cleanup.apply(directory, dry_run=bool(options["dry_run"]))
        prefix = "Изменится" if options["dry_run"] else "Изменено"
        self.stdout.write(
            f"{prefix}: в запросы — {done['demand']}, описаний — {done['descriptions']}, "
            f"скрыто компаний — {done['companies']}"
        )
