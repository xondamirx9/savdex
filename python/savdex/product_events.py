"""
События продукта, которые не посчитать в браузере (ТЗ-03, шаг 3): деньги,
модерация, ответы, сроки тарифов. Таблица product_events (миграция
2026_10_21_100000); читает её аналитик — выгрузкой CSV
(manage.py product_events_export).

  record(event, ...)      — строка события; ошибка записи не роняет
                            оплату или модерацию: событие теряется, а
                            действие человека — нет
  send_purchases()        — задача расписания: payment_succeeded уходят в
                            GA4 как purchase через Measurement Protocol
                            (GA4_API_SECRET из окружения, не из кода)

Персональных данных нет: компания и пользователь — номерами, в props —
коды, суммы, номера счетов и объявлений.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from django.db import connection, transaction

from savdex.guards import allowed_writes

log = logging.getLogger(__name__)

#: Адрес Measurement Protocol; GA4_MP_URL — только для проверок
MP_URL = "https://www.google-analytics.com/mp/collect"
#: Как у остальных внешних вызовов (savdex/web/messaging.py)
TIMEOUT = 8
#: Сколько покупок отправлять за один проход задачи
BATCH = 50


def _plain(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def record(
    event: str,
    *,
    company_id: int | None = None,
    user_id: int | None = None,
    plan: str | None = None,
    locale: str | None = None,
    props: dict[str, Any] | None = None,
) -> None:
    """Записать событие. Сбой записи — в журнал, не наверх."""
    clean = {k: _plain(v) for k, v in (props or {}).items()}

    try:
        # Своя точка сохранения: сбой вставки внутри чужой транзакции
        # (оплата, модерация) откатывает только эту строку
        with transaction.atomic(), allowed_writes("product_events"), connection.cursor() as cursor:
            cursor.execute(
                "insert into product_events (occurred_at, event, company_id, user_id, plan, "
                "locale, props) values (%s, %s, %s, %s, %s, %s, %s)",
                [
                    datetime.now(UTC).replace(microsecond=0, tzinfo=None),
                    event,
                    company_id,
                    user_id,
                    plan,
                    locale,
                    json.dumps(clean, ensure_ascii=False),
                ],
            )
    except Exception:  # аналитика не должна ломать оплату
        log.exception("product_events.record_failed: %s", event)


def plan_code(company_id: int | None) -> str | None:
    """Тариф компании на момент события."""
    if company_id is None:
        return None

    from savdex.web.cabinet import company_plan

    try:
        return str(company_plan(company_id).get("code") or "") or None
    except Exception:  # тариф — подпись к событию, не повод падать
        return None


# ── Покупки в GA4 ───────────────────────────────────────────────────


def _usd(amount: float, currency: str) -> float:
    """Сумма в долларах: GA4 сводит выручку в одной валюте (ТЗ-03 — USD)."""
    from savdex.web.currency import CurrencyRate

    if currency == "USD":
        return round(amount, 2)

    rates = CurrencyRate()
    rate = rates.rate(currency)

    return round(amount * (rate or 1.0) / rates.usd(), 2)


def send_purchases(now: datetime | None = None, due: datetime | None = None) -> str:
    """
    Неотправленные payment_succeeded → GA4 purchase. Без GA4_API_SECRET
    ничего не делает. client_id — номер компании: браузера, с которого
    платили, у колбэка банка нет.
    """
    from savdex.web.analytics import DEFAULT_ID

    secret = (os.environ.get("GA4_API_SECRET") or "").strip()
    measurement = (os.environ.get("GA4_MEASUREMENT_ID") or "").strip() or DEFAULT_ID

    if not secret:
        return "GA4: нет GA4_API_SECRET — покупки не отправляются"

    with connection.cursor() as cursor:
        cursor.execute(
            "select id, company_id, plan, props from product_events "
            "where event = 'payment_succeeded' and ga_sent_at is null order by id limit %s",
            [BATCH],
        )
        rows = cursor.fetchall()

    sent = 0

    for event_id, company_id, plan, props in rows:
        data = props if isinstance(props, dict) else json.loads(props or "{}")
        body = {
            "client_id": f"company.{company_id or 0}",
            "events": [
                {
                    "name": "purchase",
                    "params": {
                        "transaction_id": str(data.get("number") or event_id),
                        "currency": "USD",
                        "value": _usd(
                            float(data.get("amount") or 0), str(data.get("currency") or "UZS")
                        ),
                        "items": [
                            {
                                "item_id": str(plan or data.get("purpose") or "payment"),
                                "item_category": str(data.get("purpose") or ""),
                            }
                        ],
                    },
                }
            ],
        }

        try:
            response = httpx.post(
                os.environ.get("GA4_MP_URL") or MP_URL,
                params={"measurement_id": measurement, "api_secret": secret},
                json=body,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("product_events.ga4_failed: %s", e)

            break

        with allowed_writes("product_events"), connection.cursor() as cursor:
            cursor.execute(
                "update product_events set ga_sent_at = %s where id = %s",
                [datetime.now(UTC).replace(microsecond=0, tzinfo=None), event_id],
            )

        sent += 1

    return f"GA4: покупок отправлено {sent} из {len(rows)}"
