"""
Сигнал о медленной странице — копия AppServiceProvider::configureDatabase
(DB::whenQueryingForLongerThan(500)).

Когда запросы к базе за одну страницу набирают полсекунды, в журнал —
одно предупреждение «База отвечает медленно» с подробностями: сколько
всего миллисекунд, сколько запросов (один тяжёлый или четыреста мелких
чинятся совершенно по-разному), запрос, на котором счётчик перевалил
за порог, и сама страница. Работает и на боевом сайте намеренно: медленно
отвечающая страница — то, что замечают на живом сайте и не замечают
на машине разработчика с базой под боком.

Только страницы, не команды: посредник работает лишь в запросе, а
сидер или перевод в консоли обязаны тратить это время, и предупреждение,
которое звучит всегда, перестают читать.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

log = logging.getLogger("savdex")

#: Порог: «посетитель ждёт слишком долго»
THRESHOLD_MS = 500

_SPACES = re.compile(r"\s+")


class _Watch:
    def __init__(self, request: HttpRequest) -> None:
        self.request = request
        self.total_ms = 0.0
        self.queries = 0
        self.reported = False

    def __call__(
        self,
        execute: Callable[[str, Any, bool, dict[str, Any]], Any],
        sql: str,
        params: Any,  # noqa: ANN401
        many: bool,
        context: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        started = time.perf_counter()

        try:
            return execute(sql, params, many, context)
        finally:
            took = (time.perf_counter() - started) * 1000
            self.queries += 1
            self.total_ms += took

            # Как whenQueryingForLongerThan: один раз за страницу, на
            # запросе, где сумма перевалила за порог
            if not self.reported and self.total_ms > THRESHOLD_MS:
                self.reported = True
                self._report(sql, took)

    def _report(self, sql: str, took: float) -> None:
        text = _SPACES.sub(" ", sql)

        # Подробности — в самой строке, как контекст у Laravel: у журнала
        # (settings.LOGGING) нет форматтера, extra он бы не показал
        details = {
            "всего_мс": round(self.total_ms),
            "запросов": self.queries,
            "на_запросе": text if len(text) <= 400 else text[:400] + "...",
            "этот_мс": round(took),
            "страница": f"{self.request.method} {self.request.path.lstrip('/') or '/'}",
        }
        log.warning("База отвечает медленно %s", json.dumps(details, ensure_ascii=False))


class SlowDatabaseMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        with connection.execute_wrapper(_Watch(request)):
            return self.get_response(request)
