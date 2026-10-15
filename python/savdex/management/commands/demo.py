"""
Демо-наполнение тестового сервера (savdex/demo.py).

  manage.py demo    придуманные компании, владельцы, объявления и отзывы;
                    уже заведены — ничего. На боевом (APP_ENV=production)
                    отказывается.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from savdex import demo


class Command(BaseCommand):
    help = "Демо-данные тестового сервера: придуманные компании и объявления"

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            made = demo.seed()
        except demo.DemoRefusedError as error:
            raise CommandError(str(error)) from error

        if not made["companies"]:
            self.stdout.write("Демо-данные уже есть — ничего нового")

            return

        self.stdout.write(
            f"Демо-данные: компаний {made['companies']}, владельцев {made['users']}, "
            f"объявлений {made['listings']}, отзывов {made['reviews']}"
        )
