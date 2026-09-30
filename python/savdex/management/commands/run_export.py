"""
Выгрузка базы в Excel с историей в админке (savdex/system/exports.py).

  manage.py run_export <номер>   выполнить заведённую выгрузку (так её
                                 запускает кнопка «Выгрузить сейчас»)
  manage.py run_export           завести и выполнить новую — из консоли;
                                 файлы появятся в админке, как от кнопки

Код выхода — 1, если выгрузка не удалась или одна уже идёт.
"""

from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from savdex.system import exports


class Command(BaseCommand):
    help = "Выгрузка базы в Excel с историей в админке"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("run_id", nargs="?", default="", help="Номер заведённой выгрузки")

    def handle(self, *args: Any, **options: Any) -> None:
        run_id = str(options["run_id"])

        if run_id == "":
            created = exports.create("консоль", None)

            if created is None:
                self.stderr.write("Выгрузка уже идёт — дождитесь её.")
                sys.exit(1)

            run_id = created
        elif exports.find(run_id) is None:
            self.stderr.write(f"Нет выгрузки {run_id!r}.")
            sys.exit(1)

        self.stdout.write(f"Выгрузка {run_id}…")
        exports.run(run_id)
        run = exports.find(run_id) or {}

        if run.get("status") != exports.DONE:
            self.stderr.write(f"Не удалась: {run.get('note') or 'без подробностей'}")
            sys.exit(1)

        for file in run.get("files") or []:
            self.stdout.write(f"  {exports.root() / run_id / file}")
