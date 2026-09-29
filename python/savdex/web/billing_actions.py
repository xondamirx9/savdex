"""
Формы кассы кабинета на Django (этап 7, шаг 53): отмена и включение
автопродления, отвязка карты, отказ от неоплаченного счёта. Копия
Cabinet\\BillingController::cancel, ::resume, ::removeCard и
::cancelInvoice (OrderService::cancel).

Подписка при отмене автопродления не обрывается — оплаченный период
остаётся. Включить автопродление можно только у оплаченной подписки.
Основную карту при включённом автопродлении не отвязать. Отменённый
счёт остаётся строкой со статусом failed, захваченный скидочный
промокод возвращается в оборот — если по счёту нет живой карточной
транзакции. Payment и Subscription у администратора пишутся в журнал
(AuditObserver), PaymentMethod — нет.

Сверка с настоящим Laravel — tests/test_web_billing_actions.py.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.billing import _date
from savdex.web.cabinet import _rows, active_subscription, company_of
from savdex.web.forms import action, back, flash
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context
from savdex.web.views import not_found

#: Subscription::SOURCE_PAYMENT
SOURCE_PAYMENT = "payment"

#: Приведения моделей для сравнения «изменилось ли»
SUBSCRIPTION_CASTS = {"auto_renew": "bool"}


def _confirm_timeout() -> int:
    """(int) env('PAYMENTS_UZUM_CONFIRM_TIMEOUT', 30): ведущие цифры строки."""
    raw = os.environ.get("PAYMENTS_UZUM_CONFIRM_TIMEOUT")

    if raw is None:
        return 30

    found = re.match(r"\s*[+-]?\d+", raw)

    return int(found.group(0)) if found else 0


@form()
def cancel(request: HttpRequest) -> HttpResponse:
    """BillingController::cancel: автопродление — прочь, период остаётся."""
    ctx = action(request)
    company = company_of(ctx)
    subscription = active_subscription(company["id"]) if company is not None else None

    if subscription is None:
        return not_found(ctx)

    eloquent.save(
        ctx,
        "subscriptions",
        subscription,
        {"auto_renew": False, "cancelled_at": eloquent.now()},
        section="subscriptions",
        model="Subscription",
        casts=SUBSCRIPTION_CASTS,
    )

    until = _date(subscription["ends_at"])
    flash(
        ctx,
        "success",
        ctx.t("messages.billing.auto_off_until", date=until)
        if until is not None
        else ctx.t("messages.billing.auto_off"),
    )

    return back(ctx)


@form()
def resume(request: HttpRequest) -> HttpResponse:
    """BillingController::resume: только у оплаченной подписки."""
    ctx = action(request)
    company = company_of(ctx)
    subscription = active_subscription(company["id"]) if company is not None else None

    if subscription is None:
        return not_found(ctx)

    if subscription["source"] != SOURCE_PAYMENT:
        flash(ctx, "warning", ctx.t("messages.billing.nothing_to_renew"))

        return back(ctx)

    eloquent.save(
        ctx,
        "subscriptions",
        subscription,
        {"auto_renew": True, "cancelled_at": None},
        section="subscriptions",
        model="Subscription",
        casts=SUBSCRIPTION_CASTS,
    )
    flash(ctx, "success", ctx.t("messages.billing.auto_on"))

    return back(ctx)


@form("DELETE")
def remove_card(request: HttpRequest, card_id: str) -> HttpResponse:
    """BillingController::removeCard: основную при автопродлении — нельзя."""
    ctx = action(request)
    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    cards = _rows(
        "select * from payment_methods where company_id = %s and id = %s limit 1",
        [company["id"], int(card_id)],
    )

    if not cards:
        return not_found(ctx)

    card = cards[0]
    subscription = active_subscription(company["id"])

    # Без карты продлевать нечем — предупреждаем до, а не после
    if card["is_default"] and subscription is not None and subscription["auto_renew"]:
        flash(ctx, "error", ctx.t("messages.billing.card_primary"))

        return back(ctx)

    with allowed_writes("payment_methods"), connection.cursor() as cursor:
        cursor.execute("delete from payment_methods where id = %s", [card["id"]])

    flash(ctx, "success", ctx.t("messages.billing.card_unlinked"))

    return back(ctx)


def _live_card_transaction(payment: dict[str, Any]) -> bool:
    """OrderService::hasLiveCardTransaction: созданная, ещё не просроченная."""
    since = eloquent.now() - timedelta(minutes=_confirm_timeout())

    return bool(
        _rows(
            "select 1 from payment_transactions where payment_id = %s and state = 'created' "
            "and created_at > %s limit 1",
            [payment["id"], _stamp(since)],
        )
    )


def cancel_payment(ctx: Context, payment: dict[str, Any]) -> None:
    """OrderService::cancel без администратора: счёт — failed, промокод — в оборот."""
    # Строго «ждёт оплаты»: повтор отмены не освобождает код второй раз
    if payment["status"] != "pending":
        return

    eloquent.save(
        ctx,
        "payments",
        payment,
        {"status": "failed", "confirmed_by": None, "admin_note": None},
        section="payments",
        model="Payment",
        casts={"amount": "int"},
    )

    if payment["promo_code_id"] is not None and not _live_card_transaction(payment):
        with allowed_writes("promo_codes"), connection.cursor() as cursor:
            cursor.execute(
                "update promo_codes set used_at = null, used_by_company_id = null, "
                "used_by_user_id = null, updated_at = %s where id = %s "
                "and used_by_company_id = %s and subscription_id is null",
                [_stamp(eloquent.now()), payment["promo_code_id"], payment["company_id"]],
            )


@form()
def cancel_invoice(request: HttpRequest, payment_id: str) -> HttpResponse:
    """BillingController::cancelInvoice: только свой неоплаченный счёт."""
    ctx = action(request)
    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    found = _rows(
        "select * from payments where company_id = %s and status = 'pending' and id = %s limit 1",
        [company["id"], int(payment_id)],
    )

    if not found:
        return not_found(ctx)

    cancel_payment(ctx, found[0])
    flash(ctx, "success", ctx.t("messages.billing.cancelled", number=found[0]["number"]))

    return back(ctx)
