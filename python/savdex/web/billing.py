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
from savdex.web import content, inertia, locales, ui
from savdex.web.cabinet import _rows, _seo, active_subscription, company_of, company_plan, page
from savdex.web.currency import CurrencyRate, php_round
from savdex.web.home import php_round as round_places
from savdex.web.inertia import php_escape
from savdex.web.phpquery import laravel_input
from savdex.web.shared import Context, setting, settings_values

#: OrderService::EXPIRES_DAYS
EXPIRES_DAYS = 14

#: Payment::STATUSES; подписи — invoice.status.* в словаре
STATUSES = ("pending", "paid", "failed", "refunded")


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


def amount_label(payment: dict[str, Any], sum_label: str = "сум") -> str:
    """Payment::amountLabel; sum_label — «сум» на нужном языке."""
    currency = payment["currency"]

    return (
        number_format(int(payment["amount"])) + " " + (sum_label if currency == "UZS" else currency)
    )


def expires_at(payment: dict[str, Any]) -> datetime | None:
    """Payment::expiresAt: срок оплаты — от даты счёта, только у ожидающего."""
    created = _utc(payment["created_at"])

    if payment["status"] != "pending" or created is None:
        return None

    return created + timedelta(days=EXPIRES_DAYS)


def masked(method: dict[str, Any], card: str = "Карта") -> str:
    """PaymentMethod::masked; card — подпись карты без бренда на языке страницы."""
    return f"{method['brand'] or card} •••• {method['last4']}".strip()


def _ucfirst(value: str) -> str:
    return value[:1].upper() + value[1:]


# ── Настройки ───────────────────────────────────────────────────────


def checkout_enabled() -> bool:
    """BillingController::checkoutEnabled: провайдер включён и касса открыта."""
    return checkout.checkout_enabled()


def requisite_items() -> list[tuple[str, str]]:
    """Реквизиты из настроек: (ключ подписи, значение), пустые — прочь."""
    values = settings_values()
    items = [
        (
            "messages.billing.payee",
            setting(values, "legal_full_name") or setting(values, "legal_name"),
        ),
        ("messages.billing.tin", setting(values, "legal_tin")),
        ("messages.billing.account", setting(values, "legal_account")),
        ("messages.billing.bank", setting(values, "legal_bank")),
        ("messages.billing.mfo", setting(values, "legal_mfo")),
    ]

    return [(key, value) for key, value in items if value != ""]


def requisites(ctx: Context) -> dict[str, str]:
    """BillingController::requisites: подписи на языке страницы."""
    return {ctx.t(key): value for key, value in requisite_items()}


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

        return (
            f"{provider} · {masked(method, ctx.t('cabinet.billing.card'))}"
            if method is not None
            else provider
        )

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
                "masked": masked(m, ctx.t("cabinet.billing.card")),
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
                "amount": amount_label(p, ctx.t("catalog.currency_uzs")),
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
    payment: dict[str, Any],
    company: dict[str, Any] | None,
    items: list[tuple[str, str]],
    locale: str,
    back_url: str,
) -> str:
    """
    Печатный счёт: основной язык — английский, второй — язык страницы
    строкой ниже (с /en — только английский). Реквизиты, плательщик и
    номер — как записаны: они должны совпасть с платёжкой.
    """
    e = php_escape

    def en(key: str, **replace: object) -> str:
        return ui.t(key, "en", **replace)

    def both(key: str, **replace: object) -> str:
        """Подпись на двух языках: английский и, ниже, язык страницы."""
        main = e(en(key, **replace))

        if locale == "en":
            return main

        alt = e(ui.t(key, locale, **replace))

        return f'{main}<span class="alt" lang="{e(locale)}">{alt}</span>'

    created = _date(_utc(payment["created_at"])) or ""
    until = expires_at(payment)
    paid = _utc(payment["paid_at"])
    status_key = f"invoice.status.{payment['status']}"
    status = both(status_key) if payment["status"] in STATUSES else e(payment["status"])

    if until is not None:
        due = f"                            {both('invoice.pay_by', date=_date(until))}\n"
    elif paid is not None:
        due = f"                            {both('invoice.paid_on', date=_date(paid))}\n"
    else:
        due = ""

    requisites_html = " " * 8

    if items:
        rows = "".join(
            f"{' ' * 36}<dt>{both(key)}</dt>\n{' ' * 20}<dd>{e(value)}</dd>\n"
            for key, value in items
        )
        requisites_html += f"            <dl>\n{rows}{' ' * 28}</dl>\n        "

    payer = (company or {}).get("legal_name") or (company or {}).get("name") or ""
    tin = (company or {}).get("tin")
    tin_html = " " * 12

    if tin:
        tin_html += (
            f"                <dt>{both('invoice.payer_tin')}</dt>\n"
            f"                <dd>{e(tin)}</dd>\n" + " " * 12
        )

    note = ""

    if payment["status"] == "pending":
        number = payment["number"]
        note = (
            '            <div class="note">\n'
            f"                <b>{both('invoice.note_title', number=number)}</b>\n"
            f"                {both('invoice.note_text')}\n            </div>\n        "
        )

    # Описание счёта хранится на языке заказа — английский и язык
    # страницы берутся из переводов содержимого, второй — если отличается
    description = str(payment["description"] or "")
    main_description = content.Translations("en").text(description) or description
    alt_description = content.Translations(locale).text(description) or description
    description_html = e(main_description)

    if locale != "en" and alt_description != main_description:
        description_html += f'<span class="alt" lang="{e(locale)}">{e(alt_description)}</span>'

    values = {
        "doc_title": e(en("invoice.doc_title", number=payment["number"])),
        "back_url": e(back_url),
        "back": e(ui.t("invoice.back", locale)),
        "print": e(ui.t("invoice.print", locale)),
        "tagline": both("invoice.tagline"),
        "dated": both("invoice.dated", date=created),
        "number": e(payment["number"]),
        "status": status,
        "heading": both("invoice.heading", number=payment["number"]),
        "due": due,
        "requisites": requisites_html,
        "payer_label": both("invoice.payer"),
        "payer": e(payer),
        "tin": tin_html,
        "no": both("invoice.no"),
        "item": both("invoice.item"),
        "amount_label": both("invoice.amount"),
        "description": description_html,
        "amount": e(amount_label(payment, en("catalog.currency_uzs"))),
        "total": both("invoice.total"),
        "note": note,
        "director": both("invoice.director"),
        "accountant": both("invoice.accountant"),
        "signature": both("invoice.signature"),
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
    html = _invoice_html(
        found[0],
        payer[0] if payer else None,
        requisite_items(),
        ctx.locale,
        locales.url(ctx.root, "/cabinet/billing", ctx.locale),
    )

    return HttpResponse(html, content_type="text/html; charset=utf-8")
