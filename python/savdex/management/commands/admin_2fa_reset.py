"""
Снять второй фактор входа в админку (savdex/twofactor.py): сотрудник
потерял телефон или сменил приложение. После этого вход — по паролю,
код подключается заново в админке («Вход по коду»).

    manage.py admin_2fa_reset anna@savdex.uz
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection

from savdex import twofactor


class Command(BaseCommand):
    help = "Снять вход по коду у сотрудника админки (потерян телефон)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email", help="Почта сотрудника")

    def handle(self, *args: Any, **options: Any) -> None:
        email = str(options["email"]).strip().lower()

        with connection.cursor() as cursor:
            cursor.execute(
                "select id from users where lower(email) = %s and deleted_at is null", [email]
            )
            row = cursor.fetchone()

        if row is None:
            raise CommandError(f"Пользователь {email} не найден")

        if twofactor.reset(int(row[0])):
            self.stdout.write(f"Вход по коду у {email} снят: подключить заново в админке.")
        else:
            self.stdout.write(f"У {email} вход по коду не был подключён.")
