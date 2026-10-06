"""
Деньги пришли — выдаём оплаченное (этап 7, шаг 54). Копия
OrderService::markPaid и ::settle с grantPlan и grantCredits, и
Wallet::grant.

Единственное место на Django, где счёт превращается в доступ.
Отметка об оплате и начисление — одной транзакцией и только если счёт
ещё не оплачен: оплаченный счёт без начисления — претензия, начисление
без отметки — двойная выдача при повторе колбэка. После — открытая
сделка компании в CRM выигрывается (savdex/crm/automation.py).
"""

from __future__ import annotations

from typing import Any

from django.db import connection, transaction

from savdex.guards import allowed_writes
from savdex.web import content, eloquent, orders, ui
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


def _grant_plan(
    ctx: Context,
    payment: dict[str, Any],
    company: dict[str, Any],
    admin: dict[str, Any] | None,
) -> None:
    """OrderService::grantPlan: подписка по оплате, скидочный код — к ней."""
    plans = _rows("select * from plans where id = %s", [payment["plan_id"]])

    if not plans:
        return

    subscription = orders.assign(
        ctx,
        company,
        plans[0],
        source=orders.SOURCE_PAYMENT,
        granted_by=admin,
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


def _grant_credits(
    payment: dict[str, Any], company: dict[str, Any], admin: dict[str, Any] | None
) -> None:
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
        admin["id"] if admin is not None else None,
    )


def _t(ctx: Context, key: str) -> str:
    """__() у Laravel: у страницы сайта — её язык, у админки — русский."""
    translate = getattr(ctx, "t", None)

    return translate(key) if callable(translate) else ui.t(key, "ru")


def mark_paid(ctx: Context, payment: dict[str, Any], meta: dict[str, Any]) -> tuple[bool, str]:
    """
    OrderService::markPaid: оплату подтвердил провайдер. meta — след
    провайдера (provider, external_id, payment_method_id), пустое — прочь.
    """
    return settle(ctx, payment, {k: v for k, v in meta.items() if v is not None}, None)


def confirm(
    ctx: Context, payment: dict[str, Any], admin: dict[str, Any], note: str | None
) -> tuple[bool, str]:
    """OrderService::confirm: деньги пришли переводом — отметил администратор."""
    return settle(ctx, payment, {"confirmed_by": admin["id"], "admin_note": note}, admin)


def settle(
    ctx: Context,
    payment: dict[str, Any],
    stamp: dict[str, Any],
    admin: dict[str, Any] | None,
) -> tuple[bool, str]:
    """OrderService::settle: отметка об оплате и начисление — одной транзакцией."""
    if payment["status"] == "paid":
        return False, _t(ctx, "messages.order.already_paid")

    companies = _rows(
        "select * from companies where id = %s and deleted_at is null", [payment["company_id"]]
    )

    if not companies:
        return False, _t(ctx, "messages.order.company_gone")

    company = companies[0]

    with transaction.atomic():
        # Счёт под замком и статус — заново: два подтверждения разом (двойной
        # щелчок, две вкладки, шлюз и администратор) начисляли дважды
        locked = _rows("select status from payments where id = %s for update", [payment["id"]])

        if not locked or locked[0]["status"] == "paid":
            return False, _t(ctx, "messages.order.already_paid")

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
            _grant_plan(ctx, payment, company, admin)
        elif payment["purpose"] == "credits":
            _grant_credits(payment, company, admin)

    _notify_company(
        ctx,
        company,
        "billing",
        lambda locale: ui.t("messages.billing.paid_title", locale, number=payment["number"]),
        "success",
        "/cabinet/billing",
        # Описание счёта записано по-русски (или на языке заказчика) —
        # остальным сотрудникам на их языке
        lambda locale: (
            content.Translations(locale).text(payment["description"]) or payment["description"]
        ),
    )

    # Оплата → сделка: открытая сделка компании в CRM выиграна
    from savdex.crm import automation

    automation.close_deal_on_payment(
        {**payment, "status": "paid"}, actor_id=admin["id"] if admin is not None else None
    )

    return True, _t(ctx, "messages.order.credited")
