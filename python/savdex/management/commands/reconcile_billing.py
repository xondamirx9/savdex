"""
Сверка денег (этап 7, шаг 55, savdex/payments/reconcile.py).

  manage.py reconcile_billing            бесконечно, проход раз в час
  manage.py reconcile_billing --once     один проход (счета за 2 дня)
  manage.py reconcile_billing --all      один проход по всем счетам, без писем

Код выхода одного прохода — 1, если нашлись расхождения.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from savdex.payments import reconcile

log = logging.getLogger("savdex.payments.reconcile")


class Command(BaseCommand):
    help = "Сверка денег: что должна была выдать оплата — и что лежит в базе"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Один проход и выход")
        parser.add_argument("--all", action="store_true", help="Все счета, только вывод")
        parser.add_argument("--days", type=int, default=2, help="Окно свежих счетов, дней")
        parser.add_argument("--every", type=int, default=3600, help="Секунд между проходами")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["all"]:
            found = reconcile.run(days=0)
            self._print(found)
            sys.exit(1 if found else 0)

        while True:
            close_old_connections()

            try:
                found = reconcile.run(days=options["days"])
                reconcile.report(found)
            except Exception:
                # Сбой прохода — не повод останавливать сверку насовсем
                log.exception("Проход сверки денег не удался")
                found = []

            if options["once"]:
                self._print(found)
                sys.exit(1 if found else 0)

            time.sleep(options["every"])

    def _print(self, found: list[reconcile.Discrepancy]) -> None:
        for item in found:
            self.stdout.write(f"{item.number}\t{item.code}\t{item.message}")

        self.stdout.write(f"Расхождений: {len(found)}")
