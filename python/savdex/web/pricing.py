"""
Тарифы — копия PageController::pricing.

Цены — из базы, как в кабинете: долларовая цена тарифа как задана,
сумовая — своя, если задана, иначе из долларовой по курсу ЦБ,
округлённая до тысяч (Plan::priceUzs).

Промокод (?promo=КОД, шаг 70) только проверяется, а не гасится (гасит
активация в кабинете): десять проверок в час с адреса — счётчик
pricing-promo:<IP> общий с Laravel, в его файловом кэше.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse

from savdex.billing.models import Plan
from savdex.web import inertia
from savdex.web.currency import CurrencyRate, php_round
from savdex.web.request import context
from savdex.web.seo import Seo


def price_uzs(plan: Plan, rate: float) -> int:
    """Plan::priceUzs."""
    if plan.price_uzs is not None:
        return int(plan.price_uzs)

    return int(php_round(float(plan.price_usd) * rate / 1000) * 1000)


def _plan(plan: Plan, rate: float) -> dict[str, Any]:
    return {
        "code": plan.code,
        "name": plan.name,
        "price_uzs": price_uzs(plan, rate),
        "price_usd": float(plan.price_usd),
        "listings_limit": plan.listings_limit,
        "contacts_limit": plan.contacts_limit,
        "responses_limit": plan.responses_limit,
        "promo_units": plan.promo_units,
        "listing_days": plan.listing_days,
        "verification_days": plan.verification_days,
        "sees_interested_names": plan.sees_interested_names,
        "has_microsite": plan.has_microsite,
        "advanced_analytics": plan.advanced_analytics,
        "promo_price": None,
    }


#: Проверок промокода с одного адреса в час
PROMO_ATTEMPTS = 10


def _promo(ctx: Any, raw: str) -> tuple[dict[str, Any] | None, str | None]:  # noqa: ANN401
    """PageController::pricingPromo: код и цена по нему — или причина отказа."""
    from savdex import laravel_cache
    from savdex.audit import client_ip
    from savdex.web import orders, throttle

    code = raw.strip(" \t\n\r\0\x0b")

    if code == "":
        return None, None

    key = "pricing-promo:" + (client_ip(ctx.request) or "")
    counted = laravel_cache.is_file_store()

    if counted and throttle.too_many(key, PROMO_ATTEMPTS):
        return None, ctx.t("pricing.promo_throttled")

    if counted:
        throttle.hit(key, 3600)

    try:
        return orders.preview(ctx, code), None
    except orders.PromoCodeRejectedError as rejected:
        return None, str(rejected)


def _promo_price(plan: Plan, promo: dict[str, Any], rate: float) -> dict[str, Any]:
    """PageController::promoPrice: тем же расчётом, что счёт (OrderService::discounted)."""
    from savdex.dashboard.metrics import php_round as round_to
    from savdex.web.orders import discounted

    percent = promo["discount_percent"]

    return {
        "price_usd": 0.0
        if percent is None
        else round_to(float(plan.price_usd) * (100 - percent) / 100, 2),
        "price_uzs": 0 if percent is None else discounted(price_uzs(plan, rate), percent),
        "discount_percent": percent,
        "days": promo["days"],
    }


def pricing(request: HttpRequest) -> HttpResponse:
    """PageController::pricing."""
    from savdex.web.auth import _query

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("seo.pricing_title")).description(ctx.t("seo.pricing_description"))
    seo.canonical(ctx.url("pricing"))
    # ?promo[]=… — как без кода (у Laravel была страница 500)
    raw = _query(ctx, "promo")
    rate = CurrencyRate().usd()
    promo, promo_error = _promo(ctx, raw)
    plans = Plan.objects.filter(is_active=True).order_by("sort")

    return inertia.render(
        ctx,
        "Pricing",
        {
            "promo": None
            if promo is None
            else {k: promo[k] for k in ("code", "plan_code", "discount_percent", "days")},
            "promoError": promo_error,
            "plans": [
                {
                    **_plan(p, rate),
                    "promo_price": _promo_price(p, promo, rate)
                    if promo is not None and promo["plan_id"] == p.id
                    else None,
                }
                for p in plans
            ],
        },
        seo,
    )
