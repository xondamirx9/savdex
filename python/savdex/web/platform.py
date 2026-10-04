"""
Заявки площадки — копия App\\Support\\PlatformListings.

Загруженные из Excel без компании заявки лежат у служебной компании
(Anjir Group), пока их не передали настоящему владельцу. На витрине они
подписаны площадкой SavdEx, а не этой компанией: она не продаёт и не
покупает. Отклики приходят в её кабинет. Собственные объявления
служебной компании, написанные в кабинете, — обычные.
"""

from __future__ import annotations

import os
from typing import Any

from django.db import connection

from savdex.text import numeric

#: Как подписана заявка площадки вместо компании
NAME = "SavdEx"

#: Служебная компания по умолчанию — по названию
_DEFAULT_NAME = "anjir group"


def _rows(query: str, params: list[Any]) -> list[dict[str, Any]]:
    # Свой запрос, а не cabinet._rows: модуль нужен главной и карточкам,
    # и импорт кабинета отсюда замкнул бы круг импортов
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        names = [c[0] for c in cursor.description or []]

        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def service_company_id() -> int | None:
    """
    PlatformListings::companyId: SAVDEX_SERVICE_COMPANY (номер, ИНН или
    название как есть), иначе первая компания с «anjir group» в названии.
    Компании в корзине не считаются (SoftDeletes).
    """
    configured = (os.environ.get("SAVDEX_SERVICE_COMPANY") or "").strip()

    if configured:
        rows = _rows(
            "select id from companies where deleted_at is null and "
            "(id = %s or tin = %s or name = %s) order by id limit 1",
            [int(configured) if numeric(configured) else -1, configured, configured],
        )
    else:
        rows = _rows(
            "select id from companies where deleted_at is null and lower(name) like %s "
            "order by id limit 1",
            [f"%{_DEFAULT_NAME}%"],
        )

    return int(rows[0]["id"]) if rows else None


def owns(listing: dict[str, Any], service: int | None) -> bool:
    """PlatformListings::owns: заявка служебной компании, загруженная из Excel."""
    return (
        service is not None
        and listing.get("company_id") == service
        and listing.get("source") == "import"
    )


def exclude_sql(service: int | None, alias: str = "l") -> tuple[str, list[Any]]:
    """PlatformListings::exclude: условие «не заявка площадки» для where."""
    if service is None:
        return "", []

    return (
        f" and ({alias}.company_id <> %s or {alias}.source <> 'import' or {alias}.source is null)",
        [service],
    )
