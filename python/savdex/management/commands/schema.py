"""
Схема базы без PHP (savdex/schema.py).

  manage.py schema            пустая база — создать схему из снимка
  manage.py schema --status   «empty» или «ready»
  manage.py schema --export   снять снимок с базы после migrate:fresh (DB_URL)
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from savdex import schema


class Command(BaseCommand):
    help = "Схема базы из снимка миграций Laravel — на пустой базе"

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
            "Схема создана из снимка." if schema.create() else "База не пустая — схему не трогаю."
        )
