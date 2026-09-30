"""
Финансовые отчёты — копия App\\Support\\FinanceReport (этап 7, шаг 60).

Выручка по периодам, по тарифам, по источникам, продления и отток.
Поступившее — «получено» (Payment::received: оплачен или возвращён, с
датой оплаты): полный возврат не стирает деньги из месяца, когда они
пришли. Возвраты вычитаются по дате возврата. Границы периода — местный,
ташкентский день (Support\\Business): хранится всё в UTC, а месяц
закрывают по своему календарю.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings

from savdex.web.cabinet import _rows

#: FinanceReport::PURPOSES
PURPOSES = {"subscription": "Подписка", "credits": "Пакет контактов", "promo_units": "Продвижение"}

#: Payment::scopeReceived
RECEIVED = "status in ('paid', 'refunded') and paid_at is not null"

MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)  # fmt: skip


def zone() -> ZoneInfo:
    return ZoneInfo(settings.TIME_ZONE)


def start_of_day(day: date) -> datetime:
    """Business::startOfDay: полночь по Ташкенту — в UTC, без пояса (как в базе)."""
    local = datetime.combine(day, time.min, tzinfo=zone())

    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def end_of_day(day: date) -> datetime:
    """Business::endOfDay: конец дня по Ташкенту — в UTC."""
    local = datetime.combine(day, time.max, tzinfo=zone())

    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def local(moment: datetime) -> datetime:
    """Business::local: момент из базы (UTC) — в ташкентском времени."""
    return moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone())


def current_month() -> tuple[date, date]:
    """Business::currentMonth: первый и последний день местного месяца."""
    today = datetime.now(zone()).date()
    first = today.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)

    return first, following - timedelta(days=1)


def _received(start: datetime, end: datetime, columns: str) -> list[dict[str, Any]]:
    return _rows(
        f"select {columns} from payments where {RECEIVED} and paid_at between %s and %s",
        [start, end],
    )


def _refunds(start: datetime, end: datetime, columns: str) -> list[dict[str, Any]]:
    return _rows(
        f"select {columns} from refunds where status = 'done' and decided_at between %s and %s",
        [start, end],
    )


def revenue(start: datetime, end: datetime) -> dict[str, dict[str, int]]:
    """FinanceReport::revenue: по валютам — поступило, возвращено, осталось, оплат."""
    rows: dict[str, dict[str, int]] = {}

    for payment in _received(start, end, "currency, amount"):
        row = rows.setdefault(
            payment["currency"], {"gross": 0, "refunded": 0, "net": 0, "count": 0}
        )
        row["gross"] += int(payment["amount"])
        row["net"] += int(payment["amount"])
        row["count"] += 1

    for refund in _refunds(start, end, "currency, amount"):
        row = rows.setdefault(
            refund["currency"] or "UZS", {"gross": 0, "refunded": 0, "net": 0, "count": 0}
        )
        row["refunded"] += int(refund["amount"])
        row["net"] -= int(refund["amount"])

    return rows


def _month_key(moment: datetime) -> str:
    return local(moment).strftime("%Y-%m")


def by_month(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """FinanceReport::byMonth: каждый месяц диапазона по местному календарю, и пустые."""
    paid: dict[str, list[int]] = defaultdict(list)
    back: dict[str, int] = defaultdict(int)

    for payment in _received(start, end, "paid_at, amount"):
        paid[_month_key(payment["paid_at"])].append(int(payment["amount"]))

    for refund in _refunds(start, end, "decided_at, amount"):
        back[_month_key(refund["decided_at"])] += int(refund["amount"])

    cursor = local(start).date().replace(day=1)
    last = local(end).date().replace(day=1)
    rows: list[dict[str, Any]] = []

    while cursor <= last:
        key = cursor.strftime("%Y-%m")
        gross = sum(paid.get(key, []))
        rows.append(
            {
                "month": key,
                "label": f"{MONTHS[cursor.month - 1]} {cursor.year}",
                "gross": gross,
                "refunded": back.get(key, 0),
                "net": gross - back.get(key, 0),
                "count": len(paid.get(key, [])),
            }
        )
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    return rows


def _sorted(groups: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
    """sortByDesc('gross'): при равных — порядок первого появления (устойчиво)."""
    return sorted(groups.values(), key=lambda row: -row["gross"])


def by_plan(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """FinanceReport::byPlan: по названию тарифа; без тарифа — «Без тарифа»."""
    payments = _received(start, end, "plan_id, amount")
    names = {
        r["id"]: r["name"]
        for r in _rows(
            "select id, name from plans where id = any(%s)",
            [sorted({p["plan_id"] for p in payments if p["plan_id"] is not None})],
        )
    }
    groups: dict[str, dict[str, Any]] = {}

    for payment in payments:
        name = names.get(payment["plan_id"]) or "Без тарифа"
        row = groups.setdefault(name, {"name": name, "count": 0, "gross": 0})
        row["count"] += 1
        row["gross"] += int(payment["amount"])

    return _sorted(groups)


def by_source(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """FinanceReport::bySource: за что × шлюз."""
    groups: dict[str, dict[str, Any]] = {}

    for payment in _received(start, end, "purpose, provider, amount"):
        provider = payment["provider"] or ""
        key = f"{payment['purpose']}|{provider}"
        row = groups.setdefault(
            key,
            {
                "purpose": PURPOSES.get(payment["purpose"], payment["purpose"]),
                "provider": provider if provider != "" else "не указан",
                "count": 0,
                "gross": 0,
            },
        )
        row["count"] += 1
        row["gross"] += int(payment["amount"])

    return _sorted(groups)


def subscriptions(start: datetime, end: datetime) -> dict[str, int]:
    """FinanceReport::subscriptions: новые, продлили, отказались, истекли молча, действуют."""
    started = _rows(
        "select id, company_id, started_at from subscriptions where started_at between %s and %s",
        [start, end],
    )
    companies = sorted({s["company_id"] for s in started})
    first_ever = {
        r["company_id"]: r["first"]
        for r in _rows(
            "select company_id, min(started_at) as first from subscriptions "
            "where company_id = any(%s) group by company_id",
            [companies],
        )
    }
    new = renewed = 0

    for subscription in started:
        first = first_ever.get(subscription["company_id"])

        if first is not None and first < subscription["started_at"]:
            renewed += 1
        else:
            new += 1

    cancelled = _rows(
        "select count(*) as n from subscriptions where cancelled_at between %s and %s",
        [start, end],
    )[0]["n"]
    ended = _rows(
        "select company_id, ends_at from subscriptions where status = 'expired' "
        "and ends_at between %s and %s",
        [start, end],
    )
    last_ever = {
        r["company_id"]: r["last"]
        for r in _rows(
            "select company_id, max(started_at) as last from subscriptions "
            "where company_id = any(%s) group by company_id",
            [sorted({e["company_id"] for e in ended})],
        )
    }
    # Завела новую после того, как истекла старая, — не ушла
    expired = sum(
        1
        for e in ended
        if not (
            last_ever.get(e["company_id"]) is not None
            and last_ever[e["company_id"]] >= e["ends_at"]
        )
    )
    active = _rows(
        "select count(*) as n from subscriptions where status = 'active' and started_at <= %s "
        "and (ends_at is null or ends_at >= %s)",
        [end, end],
    )[0]["n"]

    return {
        "new": new,
        "renewed": renewed,
        "cancelled": int(cancelled),
        "expired": expired,
        "active": int(active),
    }
