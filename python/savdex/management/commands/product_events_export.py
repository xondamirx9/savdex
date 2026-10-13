"""
События продукта в CSV для аналитика (ТЗ-03, шаг 3; savdex/product_events.py).

  manage.py product_events_export --out /var/data/events.csv
      за последние 7 дней
  manage.py product_events_export --since 2026-10-01 --until 2026-10-08 --out events.csv
      за период; --until — не включая этот день

Персональных данных в таблице нет — файл можно пересылать как есть.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection


class Command(BaseCommand):
    help = "Выгрузить product_events в CSV (по умолчанию — за последние 7 дней)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--out", required=True, help="Куда записать CSV")
        parser.add_argument("--since", default="", help="С какого дня, ГГГГ-ММ-ДД (UTC)")
        parser.add_argument("--until", default="", help="По какой день, не включая")

    def handle(self, *args: Any, **options: Any) -> None:
        today = datetime.now(UTC).date()

        try:
            until = (
                date.fromisoformat(options["until"]) if options["until"] else today + timedelta(1)
            )
            since = (
                date.fromisoformat(options["since"]) if options["since"] else until - timedelta(7)
            )
        except ValueError as e:
            raise CommandError("Даты — в виде ГГГГ-ММ-ДД") from e

        with connection.cursor() as cursor:
            cursor.execute(
                "select id, occurred_at, event, company_id, user_id, plan, locale, props "
                "from product_events where occurred_at >= %s and occurred_at < %s order by id",
                [since, until],
            )
            rows = cursor.fetchall()

        out = Path(str(options["out"]))
        out.parent.mkdir(parents=True, exist_ok=True)

        # utf-8-sig: Excel открывает файл без «кракозябр»
        with out.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "id",
                    "occurred_at_utc",
                    "event",
                    "company_id",
                    "user_id",
                    "plan",
                    "locale",
                    "props",
                ]
            )

            for row in rows:
                props = (
                    row[7] if isinstance(row[7], str) else json.dumps(row[7], ensure_ascii=False)
                )
                writer.writerow([*row[:7], props])

        self.stdout.write(f"{out}: событий {len(rows)} за {since} — {until - timedelta(1)}")
