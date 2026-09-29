"""
Выгрузка списка раздела в Excel — вместо ExportAction Filament (этап 6).

У Filament файл готовился в очереди и приходил уведомлением; здесь книга
собирается сразу и отдаётся скачиванием (openpyxl в режиме потоковой
записи: строки не держатся в памяти целиком). Формат — XLSX или CSV, как
ExportFormat::Xlsx и ::Csv. Выгрузка уносит персональные данные целым
файлом, поэтому право отдельное (<раздел>.export) и каждая выгрузка —
строка журнала «Выгрузка», как ExportAction::before.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from savdex import audit
from savdex.adminsite import _admin_of

#: (подпись столбца, значение из записи)
Column = tuple[str, Callable[[Any], Any]]


def _cell(value: Any) -> Any:  # noqa: ANN401
    """Дата — по часовому поясу админки, без пояса (Excel его не знает); число — числом."""
    if isinstance(value, datetime):
        return timezone.localtime(value).replace(tzinfo=None) if timezone.is_aware(value) else value

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)

    return value


def respond(
    request: HttpRequest,
    *,
    section: str,
    filename: str,
    columns: list[Column],
    records: Iterable[Any],
    file_format: str = "xlsx",
) -> HttpResponse:
    """Книга (или CSV) со столбцами и строками; строка журнала «Выгрузка»."""
    audit.record(
        connection,
        action="exported",
        section=section,
        actor=_admin_of(request),
        ip=audit.client_ip(request),
    )
    stamp = timezone.localtime().strftime("%Y-%m-%d-%H%M")
    headers = [label for label, _ in columns]

    if file_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)

        for record in records:
            writer.writerow(["" if (v := get(record)) is None else _cell(v) for _, get in columns])

        response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}-{stamp}.csv"'

        return response

    from openpyxl import Workbook

    book = Workbook(write_only=True)
    sheet = book.create_sheet()
    sheet.append(headers)

    for record in records:
        sheet.append([_cell(get(record)) for _, get in columns])

    output = io.BytesIO()
    book.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}-{stamp}.xlsx"'

    return response
