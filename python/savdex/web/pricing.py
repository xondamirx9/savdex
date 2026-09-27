"""
Тарифы — копия PageController::pricing.

Цены — из базы, как в кабинете: долларовая цена тарифа как задана,
сумовая — своя, если задана, иначе из долларовой по курсу ЦБ,
округлённая до тысяч (Plan::priceUzs).

Промокод (?promo=КОД) Django не проверяет: проверка считает попытки
с адреса (RateLimiter), то есть пишет, и такие адреса Apache оставляет
Laravel (docker/apache-python.conf).
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


def pricing(request: HttpRequest) -> HttpResponse:
    """PageController::pricing без промокода."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("seo.pricing_title")).description(ctx.t("seo.pricing_description"))
    seo.canonical(ctx.url("pricing"))
    rate = CurrencyRate().usd()
    plans = Plan.objects.filter(is_active=True).order_by("sort")

    return inertia.render(
        ctx,
        "Pricing",
        {"promo": None, "promoError": None, "plans": [_plan(p, rate) for p in plans]},
        seo,
    )
