"""
Схема базы без PHP (savdex/schema.py).

  manage.py schema            пустая база — создать схему из снимка;
                              затем новые миграции SQL (этап 8)
  manage.py schema --status   «empty» или «ready»
  manage.py schema --export   снять снимок с базы после migrate:fresh (DB_URL)
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from savdex import schema


class Command(BaseCommand):
    help = "Схема базы: снимок миграций Laravel на пустой базе, затем новые миграции SQL"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--status", action="store_true", help="empty или ready")
        parser.add_argument("--export", action="store_true", help="Снять снимок (DB_URL)")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["export"]:
            schema.export()
            self.stdout.write(f"Снимок: {schema.BASELINE}, {schema.GRANTS}")

            return

        if options["status"]:
            self.stdout.write("empty" if schema.empty() else "ready")

            return

        self.stdout.write(
            "Схема создана из снимка." if schema.create() else "База не пустая — снимок не нужен."
        )

        for name in schema.migrate():
            self.stdout.write(f"Миграция: {name}")
