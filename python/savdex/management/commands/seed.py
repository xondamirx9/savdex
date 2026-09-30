"""
Справочники площадки (savdex/seeds.py) — вместо сидеров Laravel при деплое.

  manage.py seed            недостающие тарифы, категории, страны, города
                            и настройки (как PlanSeeder, CategorySeeder,
                            GeoSeeder, SettingSeeder на каждом деплое)
  manage.py seed --fresh    свежая база: ещё типы продвижения и новости
                            (как db:seed)
  manage.py seed --export   снять снимок справочников текущей базы в
                            savdex/bootstrap/seeds.json (после сидеров Laravel
                            на пустой базе)
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from savdex import seeds


class Command(BaseCommand):
    help = "Справочники площадки: досоздать недостающее"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--fresh", action="store_true", help="Свежая база: как db:seed")
        parser.add_argument("--export", action="store_true", help="Снять снимок справочников")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["export"]:
            data = seeds.export()
            self.stdout.write(
                "Снимок: " + ", ".join(f"{table} {len(rows)}" for table, rows in data.items())
            )

            return

        created = seeds.seed(fresh=bool(options["fresh"]))
        made = {table: count for table, count in created.items() if count}
        self.stdout.write(
            "Заведено: " + (", ".join(f"{t} {c}" for t, c in made.items()) or "ничего нового")
        )
