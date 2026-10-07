"""
Почта поддержки в обращения (savdex/support/mail.py) вручную.

  manage.py support_mail                один проход по ящику (SUPPORT_IMAP_*)
  manage.py support_mail --eml a.eml    письмо из файла — например,
                                        пересланное вложением
Обычно ящик читает фоновый обработчик (manage.py notify) раз в минуту.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from savdex.support import mail


class Command(BaseCommand):
    help = "Письма на ящик поддержки — в обращения"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--eml", nargs="*", default=[], help="Письма из файлов .eml")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["eml"]:
            for name in options["eml"]:
                path = Path(name)

                if not path.is_file():
                    raise CommandError(f"Нет файла {name}")

                outcome = mail.accept(path.read_bytes())
                suffix = f": {outcome.reason}" if outcome.reason else ""
                self.stdout.write(f"{name}: {outcome.kind} {outcome.ticket_id or ''}{suffix}")

            return

        if mail.imap() is None:
            raise CommandError("Ящик поддержки не задан: SUPPORT_IMAP_HOST, _USERNAME, _PASSWORD")

        self.stdout.write(f"Почта поддержки: {mail.run()}.")
