"""
Предел размера запроса — до того, как Django начнёт читать тело.

Ограничение размера файла в проверке формы срабатывает, когда файл уже
принят: тело в гигабайт успевало лечь на диск и в память. Здесь запрос
больше предела отклоняется сразу — 413 по заголовку Content-Length.
Предел — с запасом над самой большой законной загрузкой (книга Excel в
админке — 50 МБ, пачка фотографий объявления); SAVDEX_MAX_REQUEST_MB —
свой. Предел перед Django на сервере (Caddy, Apache) — отдельно, в
настройках машин.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

DEFAULT_MB = 128


def limit_bytes() -> int:
    try:
        mb = int(os.environ.get("SAVDEX_MAX_REQUEST_MB", "") or DEFAULT_MB)
    except ValueError:
        mb = DEFAULT_MB

    return max(mb, 1) * 1024 * 1024


class RequestLimitMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.limit = limit_bytes()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0

        if length > self.limit:
            return HttpResponse(
                "Слишком большой запрос.", status=413, content_type="text/plain; charset=utf-8"
            )

        return self.get_response(request)
