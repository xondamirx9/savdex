"""
Письма и Telegram по уведомлениям кабинета (savdex/deliveries.py),
рассылка новых объявлений и тендеров по категориям в Telegram
(savdex/telegram_feed.py), письма рассылки потенциальным клиентам
(savdex/crm/prospects.py) и чтение ящика поддержки в обращения
(savdex/support/mail.py) — фоновый обработчик рядом с расписанием
и переводом.

  manage.py notify --once      один проход
  manage.py notify             бесконечно, проход раз в минуту
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from savdex import deliveries, telegram_feed
from savdex.crm import prospects
from savdex.support import mail as support_mail

log = logging.getLogger("savdex.deliveries")


class Command(BaseCommand):
    help = "Письма и Telegram по уведомлениям; новые объявления и тендеры в Telegram"

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

            # Отдельно: сбой одной рассылки не должен останавливать другую
            try:
                feed = telegram_feed.run()

                if feed.messages or feed.failed or feed.blocked:
                    self.stdout.write(f"Telegram, новинки: {feed}.")
            except Exception:
                log.exception("Проход рассылки новинок в Telegram не удался")

            try:
                sent = prospects.run()

                if sent:
                    self.stdout.write(f"Рассылка по базе: {sent}.")
            except Exception:
                log.exception("Проход рассылки по базе не удался")

            try:
                inbox = support_mail.run()

                if inbox:
                    self.stdout.write(f"Почта поддержки: {inbox}.")
            except Exception:
                log.exception("Проход по ящику поддержки не удался")

            if options["once"]:
                return

            time.sleep(max(5, options["every"]))
