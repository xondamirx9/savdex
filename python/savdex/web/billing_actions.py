"""
Формы кассы кабинета на Django (этап 7, шаг 53): заказ тарифа или
пакета кредитов, промокод, оплата счёта онлайн, отмена и включение
автопродления, отвязка карты, отказ от неоплаченного счёта. Копия
Cabinet\\BillingController (сервисы — savdex/web/orders.py, касса Uzum —
savdex/payments/checkout.py).

Счёт выставляется сразу, доступ — только после оплаты. При включённой
онлайн-кассе покупатель уходит на платёжную страницу Uzum
(Inertia::location); отказ кассы оставляет счёт для оплаты переводом.
Незакрытый счёт на то же самое повторно не выставляется.

Подписка при отмене автопродления не обрывается — оплаченный период
остаётся. Включить автопродление можно только у оплаченной подписки.
Основную карту при включённом автопродлении не отвязать. Отменённый
счёт остаётся строкой со статусом failed, захваченный скидочный
промокод возвращается в оборот — если по счёту нет живой карточной
транзакции. Payment и Subscription у администратора пишутся в журнал
(AuditObserver), PaymentMethod — нет.

Сверка с настоящим Laravel — tests/test_web_billing_actions.py и
tests/test_web_billing_orders.py.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex.guards import allowed_writes
from savdex.payments import checkout as cashier
from savdex.web import eloquent, locales, orders
from savdex.web.actions import form
from savdex.web.billing import _date, amount_label, price_uzs
from savdex.web.cabinet import _rows, active_subscription, company_of
from savdex.web.chat_actions import _unverified
from savdex.web.currency import CurrencyRate
from savdex.web.forms import _store, action, back, flash, input_of, invalid
from savdex.web.listing_actions import _as_id
from savdex.web.shared import Context
from savdex.web.validation import validate, validated
from savdex.web.views import not_found

log = logging.getLogger("savdex.payments")

#: Subscription::SOURCE_PAYMENT
SOURCE_PAYMENT = "payment"

#: Приведения моделей для сравнения «изменилось ли»
SUBSCRIPTION_CASTS = {"auto_renew": "bool"}


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

    orders.cancel(ctx, found[0])
    flash(ctx, "success", ctx.t("messages.billing.cancelled", number=found[0]["number"]))

    return back(ctx)


# ── Заказ, промокод, оплата ─────────────────────────────────────────


def _with_errors(ctx: Context, errors: dict[str, list[str]]) -> HttpResponse:
    """back()->withErrors(): ошибки в сессию, ввод — нет."""
    _store(ctx).flash("errors", {"default": {"format": ":message", "messages": errors}})

    return back(ctx)


def _location(ctx: Context, url: str) -> HttpResponse:
    """Inertia::location: запросу Inertia — 409 с X-Inertia-Location, иначе переход."""
    if ctx.request.headers.get("X-Inertia"):
        response = HttpResponse("", status=409)
        response["X-Inertia-Location"] = url

        return response

    return HttpResponseRedirect(url)


def _checkout(ctx: Context, payment: dict[str, Any]) -> HttpResponse:
    """
    BillingController::checkout: регистрация в Uzum и уход на его форму.
    Отказ кассы не роняет покупку — счёт остаётся для оплаты переводом.
    """
    try:
        config = cashier.gateway()
        # Назад — на тарифы того же домена и языка, а не ко входу
        result = cashier.create_checkout(
            config,
            payment,
            ctx.locale,
            back_url=locales.url(ctx.root, "/cabinet/billing", ctx.locale),
        )
        # Номер заказа Uzum — мост между колбэком и счётом
        eloquent.save(
            ctx,
            "payments",
            payment,
            {"external_id": result["order_id"]},
            section="payments",
            model="Payment",
            casts={"amount": "int"},
        )
        # Провайдер — сразу: колбэк должен понять, чьим форматом разбирать
        eloquent.save(
            ctx,
            "payments",
            payment,
            {"provider": "uzum"},
            section="payments",
            model="Payment",
            casts={"amount": "int"},
        )

        return _location(ctx, result["redirect_url"])
    except cashier.GatewayError as error:
        log.warning(
            "payment.checkout.failed",
            extra={"payment": payment["number"], "error": str(error)},
        )
        flash(
            ctx,
            "warning",
            ctx.t("messages.billing.checkout_down_invoice", number=payment["number"]),
        )

        return back(ctx)


@form()
def order(request: HttpRequest) -> HttpResponse:
    """BillingController::order (verified, throttle:20,60)."""
    ctx = action(request, throttle=20, throttle_minutes=60, throttle_prefix="billing-order")

    if (refused := _unverified(ctx)) is not None:
        return refused

    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        flash(ctx, "error", ctx.t("messages.billing.no_company_invoice"))

        return back(ctx)

    data = input_of(request)
    rules: dict[str, list[Any]] = {
        "kind": ["required", "in:plan,credits"],
        "id": ["required", "integer"],
    }
    errors = validate(data, rules, ctx.locale)

    if errors:
        return invalid(ctx, errors)

    valid = validated(data, rules)
    plan_order = valid["kind"] == "plan"
    target = _as_id(valid["id"])

    # Незакрытый счёт на то же самое — не второй счёт, а «хочу оплатить»
    duplicate = _rows(
        "select * from payments where company_id = %s and status = 'pending' and "
        + ("plan_id" if plan_order else "credit_pack_id")
        + " = %s limit 1",
        [company["id"], target],
    )

    if duplicate:
        if cashier.checkout_enabled():
            return _checkout(ctx, duplicate[0])

        flash(ctx, "warning", ctx.t("messages.billing.duplicate", number=duplicate[0]["number"]))

        return back(ctx)

    found = _rows(
        # Снятый с продажи тариф или пакет не продаётся и по прямой ссылке
        f"select * from {'plans' if plan_order else 'credit_packs'} where id = %s and is_active",
        [target],
    )

    if not found:
        return not_found(ctx)

    # Бесплатное не продаётся: счёт на 0 сум оплатить нечем и незачем
    if price_uzs(found[0], CurrencyRate().usd()) <= 0:
        flash(ctx, "warning", ctx.t("messages.billing.free_plan"))

        return back(ctx)

    payment = (
        orders.order_plan(ctx, company, found[0], ctx.user)
        if plan_order
        else orders.order_credits(ctx, company, found[0], ctx.user)
    )

    if cashier.checkout_enabled():
        return _checkout(ctx, payment)

    flash(
        ctx,
        "success",
        ctx.t(
            "messages.billing.issued",
            number=payment["number"],
            amount=amount_label(payment, ctx.t("catalog.currency_uzs")),
        ),
    )

    return back(ctx)


@form()
def promo(request: HttpRequest) -> HttpResponse:
    """BillingController::promo (verified, throttle:10,60)."""
    ctx = action(request, throttle=10, throttle_minutes=60, throttle_prefix="billing-promo")

    if (refused := _unverified(ctx)) is not None:
        return refused

    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        return _with_errors(ctx, {"promo_code": [ctx.t("messages.billing.no_company_promo")]})

    data = input_of(request)
    rules: dict[str, list[Any]] = {"promo_code": ["required", "string", "max:32"]}
    errors = validate(
        data,
        rules,
        ctx.locale,
        {"promo_code.required": ctx.t("messages.billing.promo_required")},
    )

    if errors:
        return invalid(ctx, errors)

    try:
        kind, result = orders.redeem(ctx, validated(data, rules)["promo_code"], company, ctx.user)
    except orders.PromoCodeRejectedError as rejected:
        # Ошибка на поле — только пока форма остаётся на странице
        if orders.eligible(company["id"]):
            return _with_errors(ctx, {"promo_code": [str(rejected)]})

        flash(ctx, "error", str(rejected))

        return back(ctx)

    if kind == "payment":
        if cashier.checkout_enabled():
            return _checkout(ctx, result)

        codes = _rows(
            "select discount_percent from promo_codes where id = %s", [result["promo_code_id"]]
        )
        flash(
            ctx,
            "success",
            ctx.t(
                "messages.billing.promo_discount",
                percent=codes[0]["discount_percent"] if codes else None,
                number=result["number"],
                amount=amount_label(result, ctx.t("catalog.currency_uzs")),
            ),
        )

        return back(ctx)

    until = _date(result["ends_at"])
    name = result["plan"]["name"]
    flash(
        ctx,
        "success",
        ctx.t("messages.billing.promo_plan", plan=name)
        if until is None
        else ctx.t("messages.billing.promo_free", plan=name, date=until),
    )

    return back(ctx)


@form()
def pay(request: HttpRequest, payment_id: str) -> HttpResponse:
    """BillingController::pay (verified, throttle:20,60): свой неоплаченный счёт."""
    ctx = action(request, throttle=20, throttle_minutes=60, throttle_prefix="billing-pay")

    if (refused := _unverified(ctx)) is not None:
        return refused

    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    found = _rows(
        "select * from payments where company_id = %s and id = %s and status = 'pending' limit 1",
        [company["id"], int(payment_id)],
    )

    if not found:
        return not_found(ctx)

    if not cashier.checkout_enabled():
        flash(ctx, "warning", ctx.t("messages.billing.checkout_down"))

        return back(ctx)

    return _checkout(ctx, found[0])
