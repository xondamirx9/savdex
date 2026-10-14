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
from savdex.guards import allowed_writes
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


def _revoke(ctx: Context, payment: dict[str, Any], actor: access.Admin) -> None:
    """
    Полный возврат — забрать купленное этим счётом. Раньше счёт только
    становился «Возвращён»: деньги возвращены, а кредиты пакета и тариф
    оставались у компании.

    - пакет: кредиты, выданные по счёту (по истории кошелька), списываются,
      но не ниже нуля — потраченное уже не вернуть; строка в историю;
    - тариф: подписка этого счёта закрывается, компания — на Free.
    """
    now = _stamp(eloquent.now())

    if payment["purpose"] == "credits":
        granted = int(
            _rows(
                "select coalesce(sum(amount), 0) as n from wallet_transactions "
                "where company_id = %s and kind = 'credits' and reason = 'purchase' "
                "and subject_type = 'App\\Models\\Payment' and subject_id = %s",
                [payment["company_id"], payment["id"]],
            )[0]["n"]
        )
        wallets = _rows(
            "select * from wallets where company_id = %s for update", [payment["company_id"]]
        )

        if granted <= 0 or not wallets:
            return

        take = min(granted, int(wallets[0]["credits"] or 0))

        if take <= 0:
            return

        with allowed_writes("wallets", "wallet_transactions"), connection.cursor() as cursor:
            cursor.execute(
                "update wallets set credits = credits - %s, updated_at = %s where id = %s",
                [take, now, wallets[0]["id"]],
            )
            cursor.execute(
                "insert into wallet_transactions (company_id, user_id, kind, amount, "
                "balance_after, reason, subject_type, subject_id, updated_at, created_at) "
                "values (%s, null, 'credits', %s, %s, 'refund', 'App\\Models\\Payment', %s, "
                "%s, %s)",
                [
                    payment["company_id"],
                    -take,
                    int(wallets[0]["credits"]) - take,
                    payment["id"],
                    now,
                    now,
                ],
            )
    elif payment["purpose"] == "subscription" and payment.get("subscription_id"):
        with allowed_writes("subscriptions"), connection.cursor() as cursor:
            cursor.execute(
                "update subscriptions set status = 'cancelled', auto_renew = false, "
                "cancelled_at = %s, ends_at = least(coalesce(ends_at, %s), %s), "
                "updated_at = %s where id = %s and status = 'active'",
                [now, now, now, now, payment["subscription_id"]],
            )


def approve(ctx: Context, actor: access.Admin, refund: dict[str, Any], note: str | None) -> None:
    """RefundService::approve: полный возврат — счёт «Возвращён»."""
    if refund["status"] != REQUESTED:
        raise RefundError("Решение по этому возврату уже принято.")

    with transaction.atomic():
        # Счёт под замком: два возврата по одному счёту одобряются по
        # очереди, и второй видит первый — больше оплаченного не вернуть
        payments = _rows("select * from payments where id = %s for update", [refund["payment_id"]])
        fresh = _rows("select status from refunds where id = %s", [refund["id"]])

        if not fresh or fresh[0]["status"] != REQUESTED:
            raise RefundError("Решение по этому возврату уже принято.")

        if payments and int(refund["amount"]) > refundable(payments[0]):
            left = refundable(payments[0])
            raise RefundError(
                f"По счёту осталось вернуть {money(left, refund['currency']).strip()} — "
                "этот возврат больше остатка. Отклоните его или заявите заново на остаток."
            )

        _decide(ctx, actor, refund, DONE, note)

        if payments and refundable(payments[0]) == 0:
            from savdex.web import transitions

            transitions.check_payment(
                payments[0]["status"], transitions.REFUNDED, payment_id=payments[0]["id"]
            )
            eloquent.save(
                ctx,
                "payments",
                payments[0],
                {"status": "refunded"},
                section="payments",
                model="Payment",
                casts={"amount": "int"},
            )
            _revoke(ctx, payments[0], actor)

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
