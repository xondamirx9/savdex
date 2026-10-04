"""
Страницы «Финансовые отчёты» и «Сверка со шлюзом» (этап 7, шаг 60) —
вместо страниц Filament FinanceReports и GatewayReconciliation. Их не
создают и не правят, их читают, поэтому это страницы админки, а не
разделы модели.

Границы периода — в адресе (?from=…&to=…): ссылку на «сентябрь» можно
переслать бухгалтеру. По умолчанию — местный месяц. Видят те, у кого
finreports.view (финансы и суперадмин): администратор финансов не видит.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from savdex.adminsite import _admin_of, site
from savdex.finance import recon, reports


def _day(value: str | None) -> date | None:
    try:
        day = date.fromisoformat(value) if value else None
    except ValueError:
        return None

    # 0001-01-01 и 9999-12-31 при переводе в UTC и по месяцам выходят за
    # пределы календаря (500); отчёту нужны разумные годы
    return day if day is None or 2000 <= day.year <= 2100 else None


def money(amount: int, currency: str) -> str:
    return f"{int(amount):,}".replace(",", " ") + " " + ("сум" if currency == "UZS" else currency)


def number(amount: int) -> str:
    return f"{int(amount):,}".replace(",", " ")


def quick_periods(today: date) -> list[tuple[str, date, date]]:
    """Быстрые периоды: этот месяц, прошлый, квартал, год — по местному календарю."""
    month = today.replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    previous = (month - timedelta(days=1)).replace(day=1)
    quarter = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
    quarter_end = (quarter + timedelta(days=95)).replace(day=1) - timedelta(days=1)

    return [
        ("Этот месяц", month, next_month - timedelta(days=1)),
        ("Прошлый", previous, month - timedelta(days=1)),
        ("Квартал", quarter, quarter_end),
        ("Год", today.replace(month=1, day=1), today.replace(month=12, day=31)),
    ]


def view(request: HttpRequest) -> HttpResponse:
    if not _admin_of(request).can("finreports.view"):
        raise PermissionDenied

    start_day, end_day = _period(request)
    start, end = reports.start_of_day(start_day), reports.end_of_day(end_day)
    revenue = reports.revenue(start, end)
    today = datetime.now(reports.zone()).date()

    context: dict[str, Any] = {
        **site.each_context(request),
        "title": "Финансовые отчёты",
        "lead": "Выручка, тарифы, источники, продления и отток за выбранный период.",
        "from": start_day.isoformat(),
        "to": end_day.isoformat(),
        "periods": [
            {"label": label, "from": a.isoformat(), "to": b.isoformat()}
            for label, a, b in quick_periods(today)
        ],
        "revenue": [
            {
                "gross": money(row["gross"], currency),
                "refunded": money(row["refunded"], currency),
                "net": money(row["net"], currency),
                "count": row["count"],
            }
            for currency, row in revenue.items()
        ],
        "subscriptions": reports.subscriptions(start, end),
        "months": [
            {**row, **{k: number(row[k]) for k in ("gross", "refunded", "net")}}
            for row in reports.by_month(start, end)
        ],
        "plans": [{**row, "gross": number(row["gross"])} for row in reports.by_plan(start, end)],
        "sources": [
            {**row, "gross": number(row["gross"])} for row in reports.by_source(start, end)
        ],
    }

    return TemplateResponse(request, "admin/finance/reports.html", context)


def _period(request: HttpRequest) -> tuple[date, date]:
    first, last = reports.current_month()

    return _day(request.GET.get("from")) or first, _day(request.GET.get("to")) or last


def _theirs(minor: int | None, currency: str) -> str:
    """Сторона шлюза — в тийинах; копейки показываются, только если они есть."""
    if minor is None:
        return "—"

    unit = "сум" if currency == "UZS" else currency
    whole, rest = divmod(int(minor), 100)

    if rest == 0:
        return f"{number(whole)} {unit}"

    return f"{number(whole)},{rest:02d} {unit}"


def reconciliation(request: HttpRequest) -> HttpResponse:
    """«Сверка со шлюзом» — вместо страницы Filament GatewayReconciliation."""
    if not _admin_of(request).can("finreports.view"):
        raise PermissionDenied

    start_day, end_day = _period(request)
    found = recon.findings(reports.start_of_day(start_day), reports.end_of_day(end_day))
    today = datetime.now(reports.zone()).date()
    groups = []

    for kind, meta in recon.KINDS.items():
        rows = [
            {
                "number": row["number"] or "—",
                "company": row["company"] or "—",
                "at": reports.local(row["at"]).strftime("%d.%m.%Y") if row["at"] else "—",
                "ours": money(row["ours"], row["currency"]) if row["ours"] is not None else "—",
                "theirs": _theirs(row["theirs"], row["currency"]),
                "note": row["note"] or "",
            }
            for row in found
            if row["kind"] == kind
        ]

        if rows:
            groups.append({**meta, "rows": rows})

    context: dict[str, Any] = {
        **site.each_context(request),
        "title": "Сверка со шлюзом",
        "lead": "Несогласия между тем, что записала площадка, и тем, что провёл платёжный шлюз.",
        "from": start_day.isoformat(),
        "to": end_day.isoformat(),
        "periods": [
            {"label": label, "from": a.isoformat(), "to": b.isoformat()}
            for label, a, b in quick_periods(today)
        ],
        "groups": groups,
        "total": len(found),
    }

    return TemplateResponse(request, "admin/finance/reconciliation.html", context)
