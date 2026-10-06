"""
Письма и Telegram по уведомлениям кабинета (savdex/deliveries.py) —
фоновый обработчик рядом с расписанием и переводом. Тем же проходом
уходят письма рассылки потенциальным клиентам (savdex/crm/prospects.py).

  manage.py notify --once      один проход
  manage.py notify             бесконечно, проход раз в минуту
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from savdex import deliveries
from savdex.crm import prospects

log = logging.getLogger("savdex.deliveries")


class Command(BaseCommand):
    help = "Письма и Telegram по уведомлениям — по настройкам каждого человека"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Один проход и выход")
        parser.add_argument("--every", type=int, default=60, help="Секунд между проходами")

    def handle(self, *args: Any, **options: Any) -> None:
        while True:
            close_old_connections()

            try:
                report = deliveries.run()

                if report.emails or report.telegrams or report.failed:
                    self.stdout.write(f"Уведомления: {report}.")
            except Exception:
                log.exception("Проход рассылки уведомлений не удался")

            try:
                sent = prospects.run()

                if sent:
                    self.stdout.write(f"Рассылка по базе: {sent}.")
            except Exception:
                log.exception("Проход рассылки по базе не удался")

            if options["once"]:
                return

            time.sleep(max(5, options["every"]))
