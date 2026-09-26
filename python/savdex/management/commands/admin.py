"""
Консольная часть выдачи доступа в админку (перенос `savdex:admin`).

Содержательная часть — в `savdex.admins`; здесь разбор параметров,
печать и код возврата. Тексты сообщений — те же, что у PHP-команды:
их читают люди, привыкшие к PHP-версии.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import connections

from savdex import admins
from savdex.console import table


class Command(BaseCommand):
    help = "Создать администратора или выдать роль существующему пользователю"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email", help="Почта администратора")
        parser.add_argument("--name", default="", help="Имя, если пользователя ещё нет")
        parser.add_argument(
            "--moderator",
            action="store_true",
            help="Выдать роль модератора вместо суперадмина",
        )
        parser.add_argument(
            "--role",
            default="",
            help="Любая из ролей: " + ", ".join(admins.ROLES),
        )
        parser.add_argument("--password", default="", help="Свой пароль вместо сгенерированного")
        parser.add_argument(
            "--database", default="default", help="Имя подключения из settings.DATABASES"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email = admins.normalize_email(str(options["email"]))

        if not admins.valid_email(email):
            self.stderr.write(f"«{email}» не похоже на адрес почты.")

            raise SystemExit(1)

        role = self._role(_filled(options["role"]), bool(options["moderator"]))

        # Пустой --password, как и в PHP, значит «сгенерировать»
        password = _filled(options["password"]) or admins.generate_password()

        try:
            granted = admins.grant(
                connections[str(options["database"])],
                email=email,
                role=role,
                name=_filled(options["name"]) or email.split("@", 1)[0],
                password=password,
                rounds=int(os.environ.get("BCRYPT_ROUNDS", "12")),
            )
        except admins.AccountDeletedError as error:
            self.stderr.write(str(error))

            raise SystemExit(1) from None

        self.stdout.write("")
        self.stdout.write(
            "Администратор создан."
            if granted.created
            else "Роль выдана существующему пользователю, пароль заменён."
        )

        for line in table(
            ("Поле", "Значение"),
            [
                ("Адрес", _url("/admin")),
                ("Почта", granted.email),
                ("Пароль", granted.password),
                ("Роль", granted.role_label),
            ],
        ):
            self.stdout.write(line)

        self.stdout.write("Пароль показан один раз. При первом входе система попросит его сменить.")

    def _role(self, role: str, moderator: bool) -> str:
        """
        Какую роль выдать — как chooseRole() в PHP.

        Неизвестное имя — отказ со списком: молча выдать «никаких прав»
        хуже, чем не выдать ничего.
        """
        if role == "":
            return admins.MODERATOR if moderator else admins.SUPERADMIN

        if role not in admins.ROLES:
            self.stderr.write(f"Роли «{role}» нет. Доступны: {', '.join(admins.ROLES)}.")

            raise SystemExit(1)

        return role


def _filled(value: object) -> str:
    """
    Значение параметра так, как его видит `?:` в PHP.

    Для PHP строка «0» — ложь: `--password=0` там значит «сгенерировать»,
    `--role=0` — «роль по умолчанию». Повторено, чтобы одинаковый вызов
    давал одинаковый итог.
    """
    text = str(value)

    return "" if text in ("", "0") else text


def _url(path: str) -> str:
    """Как url() в консоли Laravel: адрес сайта из APP_URL."""
    return os.environ.get("APP_URL", "http://localhost").rstrip("/") + path
