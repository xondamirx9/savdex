"""
Машинный перевод на Python — фоновый обработчик (этап 5).

Заменяет у Laravel очередь TranslateListing/TranslateResume/
TranslateTender/TranslateNewsPost, ежечасный добор и translations:fill.
Каждый проход: очередь текстов страниц (content_translations), затем
объявления, резюме, закупки и новости, которым не хватает переводов.
Проход раз в --every секунд, поэтому опубликованное через Django
переводится за минуту, а не ждёт часового добора.

Что не сложилось (переводчик вернул ошибку) — пауза растёт от минуты до
часа: бесплатный переводчик нельзя долбить одной и той же записью.
Отказ по частоте (429) прерывает проход до следующего.

  manage.py translate --once            один проход
  manage.py translate                   бесконечно, проход раз в минуту
  manage.py translate --kind listings --id 5   одна запись
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from savdex import translation_jobs as jobs
from savdex.translator import Translator, enabled

log = logging.getLogger("savdex.translate")

#: Самая длинная пауза для записи, перевод которой не складывается
MAX_BACKOFF = 3600


class Command(BaseCommand):
    help = "Машинный перевод: очередь текстов и недостающие переводы записей"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Один проход и выход")
        parser.add_argument("--every", type=int, default=60, help="Секунд между проходами")
        parser.add_argument("--kind", choices=sorted(jobs.CATCHUP), help="Одна запись: вид")
        parser.add_argument("--id", type=int, help="Одна запись: номер")
        parser.add_argument("--limit", type=int, default=20, help="Текстов страниц за проход")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["kind"] and options["id"]:
            jobs.run(options["kind"], options["id"], Translator())

            return

        self.backoff: dict[tuple[str, int], tuple[float, int]] = {}

        while True:
            close_old_connections()

            if enabled():
                try:
                    self.pass_once(options["limit"])
                except Exception:
                    log.exception("Проход перевода не удался")
            else:
                self.stdout.write("Машинный перевод выключен (MACHINE_TRANSLATION_ENABLED).")

            if options["once"]:
                return

            time.sleep(max(5, options["every"]))

    def pass_once(self, limit: int) -> None:
        translator = Translator()
        done, failed = jobs.fill_content(translator, limit)

        if translator.rate_limited:
            return

        now = time.monotonic()

        for kind in jobs.CATCHUP:
            waiting = jobs.lacking(kind)

            for key in waiting:
                due, _ = self.backoff.get((kind, key), (0.0, 0))

                if due > now:
                    continue

                jobs.run(kind, key, translator)

                if translator.rate_limited:
                    return

            # Кому перевода по-прежнему не хватает — пауза растёт
            still = set(jobs.lacking(kind))

            for key in waiting:
                if key in still:
                    _, failures = self.backoff.get((kind, key), (0.0, 0))
                    delay = min(MAX_BACKOFF, 60 * 2**failures)
                    self.backoff[(kind, key)] = (time.monotonic() + delay, failures + 1)
                else:
                    self.backoff.pop((kind, key), None)

        if done or failed:
            self.stdout.write(f"Тексты страниц: переведено {done}, не удалось {failed}.")
