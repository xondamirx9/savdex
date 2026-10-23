"""
Работа после ответа: сначала ответ уходит человеку, потом — она.

Зачем: «Забыли пароль» отвечает одинаково, есть такая учётка или нет, —
и по времени тоже. Письмо (SMTP), SMS и мессенджеры идут до секунд, и по
задержке ответа было бы видно, нашлась ли учётка. Поэтому отправка — в
закрытии ответа: gunicorn закрывает его, когда ответ уже записан в
сокет; тестовый клиент Django — сразу после вида, так что проверки видят
письмо. База в это время ещё открыта: соединения закрывает
request_finished, он идёт после.

Сбой — в журнал: ответ уже ушёл, сказать человеку нечего.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.http import HttpResponse

log = logging.getLogger(__name__)


def after(response: HttpResponse, job: Callable[[], None]) -> HttpResponse:
    """job — когда ответ уже ушёл (HttpResponse.close)."""

    def run() -> None:
        try:
            job()
        except Exception:
            log.exception("Работа после ответа не выполнена")

    response._resource_closers.append(run)  # type: ignore[attr-defined]

    return response
