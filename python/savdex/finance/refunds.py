"""
Возвраты — копия App\\Services\\Payments\\RefundService (этап 7, шаг 58).

Возврат не редактируют: по нему принимают решение — провести или
отклонить. Журнал — как у Laravel: строка наблюдателя (AuditObserver у
Refund и Payment) и своя строка службы с пометкой — сумма и счёт при
заявке, «статус» до и после при решении.

- заявить можно только по оплаченному счёту и не больше остатка:
  проведённые частичные возвраты складываются;
- провести: полный возврат (остатка не осталось) переводит счёт в
  «Возвращён», частичный оставляет оплаченным;
- отклонить — только с причиной.

Деньги провайдеру здесь не возвращаются: UzumGateway::refund у Laravel —
заглушка, возврат оформляют в кабинете Uzum.
"""

from __future__ import annotations

from typing import Any

from django.db import connection, transaction

from savdex import access, audit
from savdex.web import eloquent, orders
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context

REQUESTED = "requested"
DONE = "done"
REJECTED = "rejected"


class RefundError(Exception):
    """RuntimeException службы: текст видит сотрудник."""


def money(amount: int, currency: str) -> str:
    """Refund::money."""
    return f"{int(amount):,}".replace(",", " ") + f" {currency}"


def refundable(payment: dict[str, Any]) -> int:
    """Payment::refundableAmount: сумма минус проведённые возвраты."""
    done = _rows(
        "select coalesce(sum(amount), 0) as total from refunds where payment_id = %s "
        "and status = 'done'",
        [payment["id"]],
    )[0]["total"]

    return max(0, int(payment["amount"]) - int(done))


def _log(
    actor: access.Admin,
    action: str,
    refund: dict[str, Any],
    changes: dict[str, Any],
    note: str | None,
    request: Any,  # noqa: ANN401
) -> None:
    """AdminLog::record службы (не наблюдателя)."""
    audit.record(
        connection,
        action=action,
        section="refunds",
        actor=actor,
        subject_type="App\\Models\\Refund",
        subject_id=refund["id"],
        subject_label=audit.label(refund, "Refund", refund["id"]),
        changes=changes,
        note=note,
        ip=audit.client_ip(request),
    )


def request_refund(
    ctx: Context,
    actor: access.Admin,
    payment: dict[str, Any],
    amount: int,
    reason: str,
) -> dict[str, Any]:
    """RefundService::request."""
    if payment["status"] != "paid":
        raise RefundError("Вернуть можно только оплаченный счёт.")

    left = refundable(payment)

    if amount <= 0 or amount > left:
        raise RefundError(f"Сумма возврата должна быть от 1 до {money(left, '').strip()}.")

    now = eloquent.now()
    refund = orders._insert(
        "refunds",
        {
            "payment_id": payment["id"],
            "company_id": payment["company_id"],
            "amount": amount,
            "currency": payment["currency"],
            "reason": reason,
            "status": REQUESTED,
            "created_by": actor.id,
            "updated_at": now,
            "created_at": now,
        },
    )
    eloquent.journal(
        ctx,
        "created",
        "refunds",
        "Refund",
        refund,
        {"after": {k: _stamp(v) for k, v in refund.items()}},
    )
    _log(
        actor,
        "created",
        refund,
        {"after": {"сумма": money(amount, payment["currency"]), "счёт": payment["number"]}},
        reason,
        ctx.request,
    )

    return refund


def _decide(
    ctx: Context, actor: access.Admin, refund: dict[str, Any], status: str, note: str | None
) -> None:
    eloquent.save(
        ctx,
        "refunds",
        refund,
        {
            "status": status,
            "decided_by": actor.id,
            "decided_at": eloquent.now(),
            "decision_note": note,
        },
        section="refunds",
        model="Refund",
        casts={"amount": "int"},
    )


def approve(ctx: Context, actor: access.Admin, refund: dict[str, Any], note: str | None) -> None:
    """RefundService::approve: полный возврат — счёт «Возвращён»."""
    if refund["status"] != REQUESTED:
        raise RefundError("Решение по этому возврату уже принято.")

    with transaction.atomic():
        _decide(ctx, actor, refund, DONE, note)
        payments = _rows("select * from payments where id = %s", [refund["payment_id"]])

        if payments and refundable(payments[0]) == 0:
            eloquent.save(
                ctx,
                "payments",
                payments[0],
                {"status": "refunded"},
                section="payments",
                model="Payment",
                casts={"amount": "int"},
            )

    _log(
        actor,
        "refunded",
        refund,
        {
            "before": {"статус": "Заявлен"},
            "after": {"статус": "Проведён", "сумма": money(refund["amount"], refund["currency"])},
        },
        note if note is not None else refund["reason"],
        ctx.request,
    )


def reject(ctx: Context, actor: access.Admin, refund: dict[str, Any], note: str) -> None:
    """RefundService::reject: только с причиной."""
    if refund["status"] != REQUESTED:
        raise RefundError("Решение по этому возврату уже принято.")

    _decide(ctx, actor, refund, REJECTED, note)
    _log(
        actor,
        "rejected",
        refund,
        {"before": {"статус": "Заявлен"}, "after": {"статус": "Отклонён"}},
        note,
        ctx.request,
    )
