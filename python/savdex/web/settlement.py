"""
Деньги пришли — выдаём оплаченное (этап 7, шаг 54). Копия
OrderService::markPaid и ::settle с grantPlan и grantCredits, и
Wallet::grant.

Единственное место на Django, где счёт превращается в доступ.
Отметка об оплате и начисление — одной транзакцией и только если счёт
ещё не оплачен: оплаченный счёт без начисления — претензия, начисление
без отметки — двойная выдача при повторе колбэка.
"""

from __future__ import annotations

from typing import Any

from django.db import connection, transaction

from savdex.guards import allowed_writes
from savdex.web import eloquent, orders
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _notify_company, _stamp
from savdex.web.shared import Context

#: Приведения Payment для сравнения «изменилось ли»
PAYMENT_CASTS = {"amount": "int"}


def grant(
    wallet: dict[str, Any],
    kind: str,
    amount: int,
    reason: str,
    subject: tuple[str, int] | None,
    user_id: int | None,
) -> None:
    """Wallet::grant: increment построителем (с updated_at) и строка истории."""
    assert kind in ("credits", "promo_units")
    now = _stamp(eloquent.now())

    with allowed_writes("wallets", "wallet_transactions"), connection.cursor() as cursor:
        cursor.execute(
            f"update wallets set {kind} = {kind} + %s, updated_at = %s where id = %s",
            [amount, now, wallet["id"]],
        )
        fresh = _rows(f"select {kind} as balance from wallets where id = %s", [wallet["id"]])[0]
        cursor.execute(
            "insert into wallet_transactions (company_id, user_id, kind, amount, "
            "balance_after, reason, subject_type, subject_id, updated_at, created_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                wallet["company_id"],
                user_id,
                kind,
                amount,
                fresh["balance"],
                reason,
                None if subject is None else f"App\\Models\\{subject[0]}",
                None if subject is None else subject[1],
                now,
                now,
            ],
        )


def _wallet(company_id: int) -> dict[str, Any]:
    """Wallet::firstOrCreate(['company_id' => …])."""
    found = _rows("select * from wallets where company_id = %s limit 1", [company_id])

    if found:
        return found[0]

    now = eloquent.now()

    return orders._insert(
        "wallets", {"company_id": company_id, "updated_at": now, "created_at": now}
    )


def _grant_plan(ctx: Context, payment: dict[str, Any], company: dict[str, Any]) -> None:
    """OrderService::grantPlan: подписка по оплате, скидочный код — к ней."""
    plans = _rows("select * from plans where id = %s", [payment["plan_id"]])

    if not plans:
        return

    subscription = orders.assign(
        ctx,
        company,
        plans[0],
        source=orders.SOURCE_PAYMENT,
        reason=f"Оплата счёта {payment['number']}",
    )
    eloquent.save(
        ctx,
        "payments",
        payment,
        {"subscription_id": subscription["id"]},
        section="payments",
        model="Payment",
        casts=PAYMENT_CASTS,
    )

    if payment["promo_code_id"] is not None:
        with allowed_writes("promo_codes"), connection.cursor() as cursor:
            cursor.execute(
                "update promo_codes set subscription_id = %s, updated_at = %s where id = %s "
                "and used_by_company_id = %s and subscription_id is null",
                [
                    subscription["id"],
                    _stamp(eloquent.now()),
                    payment["promo_code_id"],
                    payment["company_id"],
                ],
            )


def _grant_credits(payment: dict[str, Any], company: dict[str, Any]) -> None:
    """OrderService::grantCredits: кредиты пакета — в кошелёк, с историей."""
    packs = _rows("select * from credit_packs where id = %s", [payment["credit_pack_id"]])

    if not packs:
        return

    grant(
        _wallet(company["id"]),
        "credits",
        int(packs[0]["credits"]),
        "purchase",
        ("Payment", payment["id"]),
        None,
    )


def mark_paid(ctx: Context, payment: dict[str, Any], meta: dict[str, Any]) -> tuple[bool, str]:
    """
    OrderService::markPaid: оплату подтвердил провайдер. meta — след
    провайдера (provider, external_id, payment_method_id), пустое — прочь.
    """
    stamp = {k: v for k, v in meta.items() if v is not None}

    if payment["status"] == "paid":
        return False, ctx.t("messages.order.already_paid")

    companies = _rows(
        "select * from companies where id = %s and deleted_at is null", [payment["company_id"]]
    )

    if not companies:
        return False, ctx.t("messages.order.company_gone")

    company = companies[0]

    with transaction.atomic():
        eloquent.save(
            ctx,
            "payments",
            payment,
            {"status": "paid", "paid_at": eloquent.now(), **stamp},
            section="payments",
            model="Payment",
            casts=PAYMENT_CASTS,
        )

        if payment["purpose"] == "subscription":
            _grant_plan(ctx, payment, company)
        elif payment["purpose"] == "credits":
            _grant_credits(payment, company)

    _notify_company(
        ctx,
        company,
        "billing",
        f"Оплата счёта {payment['number']} зачислена",
        "success",
        "/cabinet/billing",
        payment["description"],
    )

    return True, ctx.t("messages.order.credited")
