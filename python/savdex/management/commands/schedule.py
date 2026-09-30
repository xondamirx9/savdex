"""
Задачи по расписанию Django (savdex/schedule.py) — вместо расписания
Laravel (routes/console.php).

  manage.py schedule              бесконечно: проверка раз в минуту
  manage.py schedule --once ИМЯ   одна задача сейчас (окна — от «сейчас»)
  manage.py schedule --list       задачи, их час и пройденный день (момент)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import close_old_connections

from savdex import schedule
from savdex.web.listing_actions import _now

log = logging.getLogger("savdex.schedule")


class Command(BaseCommand):
    help = "Ежедневные задачи: снятие истёкших объявлений, чистка просмотров и т. п."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", metavar="ИМЯ", help="Одна задача сейчас и выход")
        parser.add_argument("--list", action="store_true", help="Задачи и пройденные дни")
        parser.add_argument("--every", type=int, default=60, help="Секунд между проверками")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list"]:
            state = schedule.load()

            for job in schedule.JOBS:
                when = f"{job.at:%H:%M}" if job.every is None else f"каждые {job.every} ч"
                self.stdout.write(f"{job.name}\t{when}\t{state.get(job.name, '—')}")

            return

        if options["once"]:
            try:
                job = schedule.job(options["once"])
            except KeyError as missing:
                raise CommandError(f"Нет задачи {options['once']}") from missing

            now = _now()
            self.stdout.write(job.run(now, now))

            return

        schedule.adopt(_now())

        while True:
            close_old_connections()
            now = _now()

            for job in schedule.pending(now):
                try:
                    due = job.due(now)
                    self.stdout.write(f"{job.name}: {job.run(now, due)}")
                    schedule.remember(job.name, job.mark(due))
                except Exception:
                    # Сбой задачи — не повод останавливать остальные:
                    # следующая проверка через минуту попробует снова
                    log.exception("Задача %s не удалась", job.name)

            time.sleep(options["every"])
