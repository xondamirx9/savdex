"""
Сверка со шлюзом — копия App\\Support\\GatewayReconciliation (этап 7, шаг 60).

Своя сторона — payments: закрыт счёт или нет. Сторона шлюза —
payment_transactions: шлюз заводит транзакцию и отдельными вызовами
проводит или отменяет её. Экран ищет несогласия между двумя записями
одного события и называет каждое своим именем.

Проверки «счёт возвращён, а транзакция не отменена» нет намеренно:
возврат оформляют руками в кабинете Uzum, и она горела бы на каждом
возврате (подробности — в комментарии у Laravel).

Не путать с payments/reconcile.py: тот сверяет оплату с начисленным
(тариф, кредиты) и шлёт письмо, этот — площадку со шлюзом для экрана.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from savdex.web.cabinet import _rows

PAID_WITHOUT_TRANSACTION = "paid_without_transaction"
PERFORMED_WITHOUT_PAID = "performed_without_paid"
AMOUNT_MISMATCH = "amount_mismatch"
DOUBLE_PERFORMED = "double_performed"

#: Порядок — порядок срочности: «деньги взяли и не начислили» стоит первым
KINDS: dict[str, dict[str, str]] = {
    PERFORMED_WITHOUT_PAID: {
        "title": "Деньги взяты, счёт не закрыт",
        "hint": "Шлюз провёл транзакцию, а площадка счёт не закрыла и ничего не начислила. "
        "Клиент заплатил и не получил. Разбирать первым.",
        "severity": "danger",
    },
    DOUBLE_PERFORMED: {
        "title": "Двойное списание",
        "hint": "На одном счёте больше одной проведённой транзакции. Скорее всего с клиента "
        "списали дважды — проверить и вернуть.",
        "severity": "danger",
    },
    AMOUNT_MISMATCH: {
        "title": "Суммы расходятся",
        "hint": "Площадка и шлюз записали разные суммы по одному счёту.",
        "severity": "danger",
    },
    PAID_WITHOUT_TRANSACTION: {
        "title": "Счёт закрыт без транзакции шлюза",
        "hint": "Площадка начислила, подтверждения от шлюза нет. Бывает законно — оплата "
        "заведена вручную администратором; тогда в счёте есть отметка о том, кто подтвердил.",
        "severity": "warning",
    },
}

#: Значок в меню — только срочное
URGENT = (PERFORMED_WITHOUT_PAID, DOUBLE_PERFORMED, AMOUNT_MISMATCH)


def _row(
    kind: str,
    payment: dict[str, Any],
    ours: int | None,
    theirs: int | None,
    note: str | None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "payment_id": payment["id"],
        "number": payment["number"],
        "company": payment["company"],
        "ours": ours,
        "theirs": theirs,
        "currency": payment["currency"] or "UZS",
        "at": payment["created_at"],
        "note": note,
    }


def findings(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """
    GatewayReconciliation::findings: счёт в периоде, если в нём случилось
    хоть что-то денежное — выставлен, оплачен или шлюз тронул транзакцию.
    """
    payments = _rows(
        "select p.id, p.number, p.status, p.amount, p.currency, p.confirmed_by, p.created_at, "
        "c.name as company from payments p "
        "left join companies c on c.id = p.company_id and c.deleted_at is null "
        "where p.created_at between %s and %s or p.paid_at between %s and %s "
        "or exists (select 1 from payment_transactions t where t.payment_id = p.id "
        "and (t.performed_at between %s and %s or t.cancelled_at between %s and %s)) "
        "order by p.id",
        [start, end] * 4,
    )
    performed: dict[int, list[int | None]] = {}

    for tx in _rows(
        "select payment_id, amount_minor from payment_transactions "
        "where state = 'performed' and payment_id = any(%s) order by id",
        [[p["id"] for p in payments]],
    ):
        performed.setdefault(tx["payment_id"], []).append(tx["amount_minor"])

    found: list[dict[str, Any]] = []

    for payment in payments:
        done = performed.get(payment["id"], [])
        amount = payment["amount"]
        total = sum(int(a or 0) for a in done)

        if payment["status"] == "paid" and not done:
            manual = payment["confirmed_by"] is not None
            note = "Подтверждён вручную администратором" if manual else None
            found.append(_row(PAID_WITHOUT_TRANSACTION, payment, amount, None, note))
        elif payment["status"] not in ("paid", "refunded") and done:
            found.append(_row(PERFORMED_WITHOUT_PAID, payment, amount, total, None))
        elif len(done) > 1:
            note = f"{len(done)} проведённых транзакции"
            found.append(_row(DOUBLE_PERFORMED, payment, amount, total, note))
        elif done and int(amount or 0) * 100 != int(done[0] or 0):
            # Своя сторона — в сумах, шлюз — в тийинах
            found.append(_row(AMOUNT_MISMATCH, payment, amount, int(done[0] or 0), None))

    order = list(KINDS)
    found.sort(key=lambda row: order.index(row["kind"]))

    return found


def summary(start: datetime, end: datetime) -> dict[str, int]:
    """GatewayReconciliation::summary: сколько расхождений каждого вида."""
    counts = dict.fromkeys(KINDS, 0)

    for finding in findings(start, end):
        counts[finding["kind"]] += 1

    return counts


def urgent(start: datetime, end: datetime) -> int:
    counts = summary(start, end)

    return sum(counts[kind] for kind in URGENT)
