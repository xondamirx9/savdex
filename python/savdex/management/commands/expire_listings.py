"""
Снятие истёкших объявлений (этап 4, savdex/web/listing_expiry.py) —
вместо расписания Laravel listings:expire.

  manage.py expire_listings           бесконечно: проход раз в сутки в 06:00 UTC
  manage.py expire_listings --once    один проход сейчас

Какой день уже пройден, помнит файл (LISTINGS_EXPIRE_STATE, иначе
storage/app/listings-expire.json): перезапуск контейнера не повторяет
проход и не шлёт предупреждения второй раз. Контейнер, поднявшийся
после 06:00, свой день догоняет. Самый первый запуск после 06:00 день
пропускает: в этот день проход уже сделало расписание Laravel.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from savdex.web import listing_expiry
from savdex.web.listing_actions import _now

log = logging.getLogger("savdex.listings.expire")


def state_path() -> Path:
    configured = os.environ.get("LISTINGS_EXPIRE_STATE")

    if configured:
        return Path(configured)

    return Path(settings.LARAVEL_ROOT) / "storage/app/listings-expire.json"


def last_day() -> date | None:
    try:
        return date.fromisoformat(state_path().read_text().strip())
    except (OSError, ValueError):
        return None


def remember(day: date) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(day.isoformat())


class Command(BaseCommand):
    help = "Снять истёкшие объявления и предупредить о скором истечении"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Один проход сейчас и выход")
        parser.add_argument("--every", type=int, default=60, help="Секунд между проверками")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["once"]:
            expired, warned = listing_expiry.run()
            self._print(expired, warned)
            return

        now = _now()

        if last_day() is None and now >= listing_expiry.scheduled_for(now):
            remember(now.date())

        while True:
            close_old_connections()
            now = _now()
            due = listing_expiry.scheduled_for(now)

            if now >= due and last_day() != now.date():
                try:
                    expired, warned = listing_expiry.run(now, anchor=due)
                    remember(now.date())
                    self._print(expired, warned)
                except Exception:
                    # Сбой прохода — не повод останавливаться: следующая
                    # проверка через минуту попробует снова
                    log.exception("Снятие истёкших объявлений не удалось")

            time.sleep(options["every"])

    def _print(self, expired: int, warned: int) -> None:
        self.stdout.write(f"Снято с публикации: {expired}. Предупреждений отправлено: {warned}.")
