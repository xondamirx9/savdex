"""
Касса кабинета — страница /cabinet/billing и печатная форма счёта
(этап 7, шаг 52). Копия Cabinet\\BillingController::index и ::invoice
(resources/views/invoice.blade.php).

Только чтение: тариф и подписка, кошелёк, карты, история платежей,
тарифы и пакеты кредитов с ценами в сумах и долларах, неоплаченные
счета, реквизиты площадки. Формы кассы — следующим шагом.

Сверка с настоящим Laravel — tests/test_web_billing.py.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from django.http import HttpRequest, HttpResponse

from savdex.payments import checkout
from savdex.web import content, inertia
from savdex.web.cabinet import _rows, _seo, active_subscription, company_of, company_plan, page
from savdex.web.currency import CurrencyRate, php_round
from savdex.web.home import php_round as round_places
from savdex.web.inertia import php_escape
from savdex.web.phpquery import laravel_input
from savdex.web.shared import Context, setting, settings_values

#: OrderService::EXPIRES_DAYS
EXPIRES_DAYS = 14

#: Payment::STATUSES
STATUSES = {
    "pending": "Ожидает оплаты",
    "paid": "Оплачен",
    "failed": "Отменён",
    "refunded": "Возвращён",
}


# ── Цены (Plan, CreditPack, PriceDisplay) ───────────────────────────


def price_round(value: float) -> float:
    """PriceDisplay::round: три значащие цифры, не больше двух знаков после запятой."""
    if value <= 0.0:
        return 0.0

    digits = 2 - math.floor(math.log10(value))

    return round_places(value, min(2, digits))


def price_uzs(row: dict[str, Any], rate: float) -> int:
    """Plan::priceUzs и CreditPack::priceUzs: своя сумовая цена или из долларов по курсу."""
    if row["price_uzs"] is not None:
        return int(row["price_uzs"])

    return int(php_round(float(row["price_usd"]) * rate / 1000) * 1000)


def price_usd(row: dict[str, Any], rate: float) -> float:
    """Plan::priceUsd: при зафиксированной сумовой — обратным пересчётом."""
    if row["price_uzs"] is not None:
        return price_round(int(row["price_uzs"]) / rate) if rate > 0 else 0.0

    return float(row["price_usd"])


def per_credit(pack: dict[str, Any], rate: float) -> int:
    """CreditPack::perCredit."""
    credits = int(pack["credits"] or 0)

    return int(php_round(price_uzs(pack, rate) / credits)) if credits > 0 else 0


# ── Платёж ──────────────────────────────────────────────────────────


def _utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _date(moment: datetime | None) -> str | None:
    """translatedFormat('d.m.Y'): одни цифры."""
    return None if moment is None else moment.strftime("%d.%m.%Y")


def number_format(value: int) -> str:
    """number_format($x, 0, ',', ' ')."""
    return f"{value:,}".replace(",", " ")


def amount_label(payment: dict[str, Any]) -> str:
    """Payment::amountLabel."""
    currency = payment["currency"]

    return number_format(int(payment["amount"])) + " " + ("сум" if currency == "UZS" else currency)


def expires_at(payment: dict[str, Any]) -> datetime | None:
    """Payment::expiresAt: срок оплаты — от даты счёта, только у ожидающего."""
    created = _utc(payment["created_at"])

    if payment["status"] != "pending" or created is None:
        return None

    return created + timedelta(days=EXPIRES_DAYS)


def masked(method: dict[str, Any]) -> str:
    """PaymentMethod::masked."""
    return f"{method['brand'] or 'Карта'} •••• {method['last4']}".strip()


def _ucfirst(value: str) -> str:
    return value[:1].upper() + value[1:]


# ── Настройки ───────────────────────────────────────────────────────


def checkout_enabled() -> bool:
    """BillingController::checkoutEnabled: провайдер включён и касса открыта."""
    return checkout.checkout_enabled()


def requisites(ctx: Context) -> dict[str, str]:
    """BillingController::requisites: реквизиты из настроек, пустые — прочь."""
    values = settings_values()
    items = {
        ctx.t("messages.billing.payee"): setting(values, "legal_full_name")
        or setting(values, "legal_name"),
        ctx.t("messages.billing.tin"): setting(values, "legal_tin"),
        ctx.t("messages.billing.account"): setting(values, "legal_account"),
        ctx.t("messages.billing.bank"): setting(values, "legal_bank"),
        ctx.t("messages.billing.mfo"): setting(values, "legal_mfo"),
    }

    return {k: v for k, v in items.items() if v != ""}


def promo_allowed(company_id: int) -> bool:
    """PromoCodeService::eligible: захваченный скидочный код или ни одного погашенного."""
    if _rows(
        "select 1 from promo_codes where used_by_company_id = %s and discount_percent is not null "
        "and subscription_id is null limit 1",
        [company_id],
    ):
        return True

    return not _rows(
        "select 1 from promo_codes where used_by_company_id = %s limit 1", [company_id]
    )


# ── Страница ────────────────────────────────────────────────────────


def _empty() -> dict[str, Any]:
    return {
        "plan": None,
        "subscription": None,
        "wallet": None,
        "cards": [],
        "payments": [],
        "plans": [],
        "packs": [],
        "invoices": [],
        "requisites": [],
        "checkout": False,
        "promoAllowed": False,
        "selected": None,
    }


def _days_left(ends_at: datetime | None) -> float | None:
    """ends_at->diffInDays(now()) у Carbon 3: со знаком и дробью — прошло от ends_at до сейчас."""
    ends = _utc(ends_at)

    if ends is None:
        return None

    return (datetime.now(UTC) - ends).total_seconds() / 86400


def props(ctx: Context) -> dict[str, Any]:
    company = company_of(ctx)

    if company is None:
        return _empty()

    cid = company["id"]
    plan = company_plan(cid)
    subscription = active_subscription(cid)
    wallets = _rows("select * from wallets where company_id = %s limit 1", [cid])
    wallet = wallets[0] if wallets else None
    rate = CurrencyRate().usd()
    translations = content.Translations(ctx.locale)
    methods = {
        m["id"]: m for m in _rows("select * from payment_methods where company_id = %s", [cid])
    }
    # Payment::HISTORY_STATUSES: в истории только оплаченное и возвраты —
    # брошенная форма Uzum не платёж
    payments = _rows(
        "select * from payments where company_id = %s and status in ('paid', 'refunded') "
        "order by created_at desc limit 20",
        [cid],
    )
    pending = _rows(
        "select * from payments where company_id = %s and status = 'pending' "
        "order by created_at desc",
        [cid],
    )
    query = laravel_input(ctx.query)
    selected = query.get("plan")

    # $p->method: карта платежа — любая, не только из списка компании
    linked = {
        m["id"]: m
        for m in _rows(
            "select * from payment_methods where id = any(%s)",
            [[p["payment_method_id"] for p in payments if p["payment_method_id"] is not None]],
        )
    }

    def method_label(payment: dict[str, Any]) -> str:
        provider = _ucfirst(str(payment["provider"] or ""))
        method = linked.get(payment["payment_method_id"])

        return f"{provider} · {masked(method)}" if method is not None else provider

    return {
        "plan": {
            "name": plan["name"],
            "code": plan["code"],
            "price_uzs": price_uzs(plan, rate) if "price_usd" in plan else 0,
            "price_usd": price_usd(plan, rate) if "price_usd" in plan else 0.0,
            "listings_limit": plan["listings_limit"],
            "contacts_limit": plan["contacts_limit"],
            "promo_units": plan["promo_units"],
        },
        "subscription": None
        if subscription is None
        else {
            "id": subscription["id"],
            "status": subscription["status"],
            "auto_renew": bool(subscription["auto_renew"]),
            "ends_at": _date(subscription["ends_at"]),
            "days_left": _days_left(subscription["ends_at"]),
        },
        "wallet": {
            "credits": wallet["credits"] if wallet else 0,
            "contacts_used": wallet["contacts_used_this_period"] if wallet else 0,
            "contacts_limit": plan["contacts_limit"],
            "promo_units": wallet["promo_units"] if wallet else 0,
            "promo_limit": plan["promo_units"],
            "resets_at": _date(wallet["period_resets_at"]) if wallet else None,
        },
        "cards": [
            {
                "id": m["id"],
                "masked": masked(m),
                "expires": m["expires"],
                "provider": m["provider"],
                "is_default": bool(m["is_default"]),
            }
            for m in methods.values()
        ],
        "payments": [
            {
                "id": p["id"],
                "date": _date(p["paid_at"] or p["created_at"]),
                "description": translations.text(p["description"]),
                "method": method_label(p),
                "amount": int(p["amount"]),
                "currency": p["currency"],
                "status": p["status"],
            }
            for p in payments
        ],
        "plans": [
            {
                "id": p["id"],
                "code": p["code"],
                "name": p["name"],
                "price_uzs": price_uzs(p, rate),
                "price_usd": price_usd(p, rate),
                "listings_limit": p["listings_limit"],
                "contacts_limit": p["contacts_limit"],
                "responses_limit": p["responses_limit"],
                "current": p["code"] == plan["code"],
                # Бесплатный тариф не покупают
                "orderable": p["code"] != "free" and p["code"] != plan["code"],
            }
            for p in _rows("select * from plans where is_active = true order by sort")
        ],
        "packs": [
            {
                "id": p["id"],
                "name": translations.text(p["name"]),
                "credits": p["credits"],
                "price_uzs": price_uzs(p, rate),
                "price_usd": price_usd(p, rate),
                "per_credit": per_credit(p, rate),
            }
            for p in _rows("select * from credit_packs where is_active = true order by sort")
        ],
        "invoices": [
            {
                "id": p["id"],
                "number": p["number"],
                "description": translations.text(p["description"]),
                "amount": amount_label(p),
                "created_at": _date(p["created_at"]),
                "expires_at": _date(expires_at(p)),
            }
            for p in pending
        ],
        "requisites": requisites(ctx) or [],
        # Тариф со страницы тарифов (?plan=business) — сразу к оплате
        "selected": selected if isinstance(selected, str) and selected != "" else None,
        "checkout": checkout_enabled(),
        "promoAllowed": promo_allowed(cid),
    }


def billing_page(request: HttpRequest) -> HttpResponse:
    """BillingController::index."""
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Billing", props(ctx), _seo(ctx))


# ── Печатная форма счёта ────────────────────────────────────────────


def _invoice_html(
    payment: dict[str, Any], company: dict[str, Any] | None, req: dict[str, str]
) -> str:
    """resources/views/invoice.blade.php."""
    e = php_escape
    created = _utc(payment["created_at"])
    until = expires_at(payment)
    paid = _utc(payment["paid_at"])
    status = STATUSES.get(payment["status"], payment["status"])

    # Пробелы — как их оставляет Blade вокруг @if и @foreach: счёт
    # сверяется с Laravel побайтно
    if until is not None:
        due = f"                            Оплатить до {_date(until)}\n"
    elif paid is not None:
        due = f"                            Оплачен {_date(paid)}\n"
    else:
        due = ""

    requisites_html = " " * 8

    if req:
        rows = "".join(
            f"{' ' * 36}<dt>{e(k)}</dt>\n{' ' * 20}<dd>{e(v)}</dd>\n" for k, v in req.items()
        )
        requisites_html += f"            <dl>\n{rows}{' ' * 28}</dl>\n        "

    payer = (company or {}).get("legal_name") or (company or {}).get("name") or ""
    tin = (company or {}).get("tin")
    tin_html = " " * 12

    if tin:
        tin_html += (
            f"                <dt>ИНН плательщика</dt>\n                <dd>{e(tin)}</dd>\n"
            + " " * 12
        )

    note = ""

    if payment["status"] == "pending":
        note = (
            '            <div class="note">\n'
            "                <b>В назначении платежа укажите номер счёта "
            f"{e(payment['number'])}.</b>\n"
            "                По нему поступление находят и зачисляют — без него оплата ищется"
            " вручную\n                и доступ открывается позже.\n            </div>\n        "
        )

    values = {
        "number": e(payment["number"]),
        "created": e(_date(created) or ""),
        "status": e(status),
        "due": e(due),
        "requisites": requisites_html,
        "payer": e(payer),
        "tin": tin_html,
        "description": e(payment["description"] or ""),
        "amount": e(amount_label(payment)),
        "note": note,
    }

    # Одним проходом: подставленный текст не разбирается повторно
    template = (Path(__file__).with_name("page_templates") / "invoice.html").read_text()

    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


def invoice(request: HttpRequest, payment_id: str) -> HttpResponse:
    """BillingController::invoice: свой счёт компании, иначе 404."""
    from savdex.web.views import not_found

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    found = _rows(
        "select * from payments where company_id = %s and id = %s", [company["id"], int(payment_id)]
    )

    if not found:
        return not_found(ctx)

    payer = _rows(
        "select * from companies where id = %s and deleted_at is null", [found[0]["company_id"]]
    )
    html = _invoice_html(found[0], payer[0] if payer else None, requisites(ctx))

    return HttpResponse(html, content_type="text/html; charset=utf-8")
