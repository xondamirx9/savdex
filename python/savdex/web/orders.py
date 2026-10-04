"""
Заказ и выдача на стороне Django (этап 7, шаг 53): копии OrderService
(счёт на тариф, на тариф со скидкой, на пакет кредитов, отмена счёта),
PromoCodeService (активация кода: бесплатный период или счёт со
скидкой) и SubscriptionService::assign (новая подписка, прежние —
истекли, кошелёк на период).

Строки — как их пишет Eloquent: у только что созданной модели в
«оригинале» лишь заданное при create, поэтому номер счёта и номер
заказа Uzum в журнале администратора идут без «до». Журнал — только у
Payment и Subscription (AuditObserver); у PromoCode правка идёт мимо
модели, запросом, и в журнал не пишется — как у Laravel.

Деньги сюда не приходят: доступ открывается только оплатой (колбэк
кассы или администратор) — шаг 54.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import IntegrityError, connection, transaction

from savdex.guards import allowed_writes
from savdex.web import content, eloquent, ui
from savdex.web.billing import _date, price_uzs
from savdex.web.cabinet import _rows, active_subscription
from savdex.web.currency import CurrencyRate, php_round
from savdex.web.listing_actions import _notify_company, _stamp, relative_url
from savdex.web.shared import Context

#: OrderService::EXPIRES_DAYS
EXPIRES_DAYS = 14

#: Subscription::SOURCE_*
SOURCE_PAYMENT = "payment"
SOURCE_MANUAL = "manual"
SOURCE_PROMO = "promo"


class PromoCodeRejectedError(Exception):
    """PromoCodeRejected: причина отказа — в тексте, её видит человек."""


# ── Запись строк ────────────────────────────────────────────────────


def _insert(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Model::create: вставка заданного, id — последним атрибутом."""
    columns = list(row)

    with allowed_writes(table), connection.cursor() as cursor:
        cursor.execute(
            f"insert into {table} ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [_stamp(v) for v in row.values()],
        )
        row["id"] = cursor.fetchone()[0]

    return row


def _notify_user(user: dict[str, Any], title: str, body: str, url: str) -> None:
    """Notifier::user: уведомление без тона — его ставит база."""
    now = _stamp(eloquent.now())

    with allowed_writes("user_notifications"), connection.cursor() as cursor:
        cursor.execute(
            "insert into user_notifications (user_id, company_id, type, title, body, url, "
            "updated_at, created_at) values (%s, %s, 'billing', %s, %s, %s, %s, %s)",
            [user["id"], user["company_id"], title, body, relative_url(url), now, now],
        )


def make_number(payment_id: int) -> str:
    """OrderService::makeNumber: SVD-000123."""
    return f"SVD-{payment_id:06d}"


def discounted(price: int, percent: int) -> int:
    """OrderService::discounted: цена после скидки в целых сумах."""
    return int(php_round(price * (100 - percent) / 100))


# ── Счета ───────────────────────────────────────────────────────────


def _create(
    ctx: Context, company: dict[str, Any], user: dict[str, Any], attributes: dict[str, Any]
) -> dict[str, Any]:
    """OrderService::create: счёт «ждёт оплаты», номер из id, уведомление заказчику."""
    now = eloquent.now()
    payment = _insert(
        "payments",
        {
            "company_id": company["id"],
            "currency": "UZS",
            "provider": "invoice",
            "status": "pending",
            **attributes,
            "updated_at": now,
            "created_at": now,
        },
    )
    eloquent.journal(ctx, "created", "payments", "Payment", payment, {"after": dict(payment)})
    eloquent.save(
        ctx,
        "payments",
        payment,
        {"number": make_number(payment["id"])},
        section="payments",
        model="Payment",
    )
    # Описание может само кончаться точкой («на 30 дн.») — вторую не ставим
    description = str(payment["description"]).removesuffix(".")
    # На языке заказчика: счёт продления выставляет фоновая задача (русский
    # контекст), а читает его англо- или узбекоязычный сотрудник
    locale = str(user.get("locale") or ctx.locale)

    if locale != ctx.locale and ctx.locale == "ru":
        description = content.Translations(locale).text(description) or description

    _notify_user(
        user,
        ui.t("messages.order.issued_title", locale, number=payment["number"]),
        ui.t("messages.order.issued_body", locale, description=description, days=EXPIRES_DAYS),
        "/cabinet/billing",
    )

    return payment


def _plan_description(ctx: Context, plan: dict[str, Any]) -> str:
    return ctx.t("messages.order.plan", plan=plan["name"], days=plan["period_days"])


def order_plan(
    ctx: Context, company: dict[str, Any], plan: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """OrderService::orderPlan."""
    return _create(
        ctx,
        company,
        user,
        {
            "purpose": "subscription",
            "plan_id": plan["id"],
            "description": ctx.t(
                "messages.order.plan", plan=plan["name"], days=plan["period_days"]
            ),
            "amount": price_uzs(plan, CurrencyRate().usd()),
        },
    )


def order_credits(
    ctx: Context, company: dict[str, Any], pack: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """OrderService::orderCredits."""
    return _create(
        ctx,
        company,
        user,
        {
            "purpose": "credits",
            "credit_pack_id": pack["id"],
            "description": ctx.t("messages.order.pack", pack=pack["name"], credits=pack["credits"]),
            "amount": price_uzs(pack, CurrencyRate().usd()),
        },
    )


def order_plan_with_promo(
    ctx: Context,
    company: dict[str, Any],
    plan: dict[str, Any],
    user: dict[str, Any],
    promo: dict[str, Any],
) -> dict[str, Any]:
    """OrderService::orderPlanWithPromo: полный счёт на тот же тариф — отменить."""
    percent = int(promo["discount_percent"])
    amount = discounted(price_uzs(plan, CurrencyRate().usd()), percent)

    if amount < 1:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.plan_not_sold"))

    for stale in _rows(
        "select * from payments where company_id = %s and status = 'pending' "
        "and purpose = 'subscription' and plan_id = %s",
        [company["id"], plan["id"]],
    ):
        cancel(
            ctx,
            stale,
            note=f"Заменён счётом со скидкой по промокоду {promo['code']}",
        )

    description = (
        _plan_description(ctx, plan)
        + " · "
        + ctx.t("messages.order.with_promo", code=promo["code"], percent=percent)
    )

    return _create(
        ctx,
        company,
        user,
        {
            "purpose": "subscription",
            "plan_id": plan["id"],
            "promo_code_id": promo["id"],
            "description": description,
            "amount": amount,
        },
    )


def _confirm_timeout() -> int:
    """(int) env('PAYMENTS_UZUM_CONFIRM_TIMEOUT', 30)."""
    import os

    from savdex.payments.uzum import _php_int

    raw = os.environ.get("PAYMENTS_UZUM_CONFIRM_TIMEOUT")

    return 30 if raw is None else _php_int(raw)


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


def cancel(
    ctx: Context,
    payment: dict[str, Any],
    note: str | None = None,
    admin: dict[str, Any] | None = None,
) -> None:
    """OrderService::cancel: счёт — failed (кто отменил — confirmed_by), промокод — в оборот."""
    # Строго «ждёт оплаты»: повтор отмены не освобождает код второй раз
    if payment["status"] != "pending":
        return

    eloquent.save(
        ctx,
        "payments",
        payment,
        {
            "status": "failed",
            "confirmed_by": admin["id"] if admin is not None else None,
            "admin_note": note,
        },
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


# ── Подписка ────────────────────────────────────────────────────────


def _naive(moment: datetime) -> datetime:
    """Время из базы — в UTC без пояса, как eloquent.now()."""
    return moment.astimezone(UTC).replace(tzinfo=None) if moment.tzinfo is not None else moment


def assign(
    ctx: Context,
    company: dict[str, Any],
    plan: dict[str, Any],
    *,
    days: int | None = None,
    source: str = SOURCE_PAYMENT,
    granted_by: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """SubscriptionService::assign: прежние — истекли, новая — с кошельком на период."""
    now = eloquent.now()

    with allowed_writes("subscriptions"), connection.cursor() as cursor:
        cursor.execute(
            "select id, plan_id, ends_at from subscriptions where company_id = %s "
            "and status = 'active' for update",
            [company["id"]],
        )
        current = cursor.fetchall()
        # Построителем Eloquent: updated_at ставит он сам, событий и журнала нет
        cursor.execute(
            "update subscriptions set status = 'expired', cancelled_at = %s, updated_at = %s "
            "where company_id = %s and status = 'active'",
            [_stamp(now), _stamp(now), company["id"]],
        )

    days = plan["period_days"] if days is None else days

    # Оплата продления того же тарифа до конца периода (счёт приходит за
    # неделю) — продление, а не перезапуск: новый срок отсчитывается от
    # конца оплаченного, иначе оставшиеся дни сгорали. Счётчики периода
    # при этом не обнуляются раньше времени — их сбросит смена периода
    still_paid = [
        _naive(row[2])
        for row in current
        if row[1] == plan["id"] and row[2] is not None and _naive(row[2]) > now
    ]
    extends = source == SOURCE_PAYMENT and bool(still_paid) and days > 0
    starts = max(still_paid) if extends else now

    subscription = _insert(
        "subscriptions",
        {
            "company_id": company["id"],
            "plan_id": plan["id"],
            "status": "active",
            "started_at": now,
            # Бессрочная подписка — только вручную
            "ends_at": starts + timedelta(days=days) if days > 0 else None,
            # Автопродление у подарочной подписки — обещание, которого не давали
            "auto_renew": source == SOURCE_PAYMENT,
            "source": source,
            "granted_by": granted_by["id"] if granted_by is not None else None,
            "grant_reason": reason,
            "updated_at": now,
            "created_at": now,
        },
    )
    eloquent.journal(
        ctx,
        "created",
        "subscriptions",
        "Subscription",
        subscription,
        {"after": {k: _stamp(v) for k, v in subscription.items()}},
    )

    wallets = _rows("select * from wallets where company_id = %s limit 1", [company["id"]])

    if wallets:
        wallet = wallets[0]
    else:
        wallet = _insert(
            "wallets", {"company_id": company["id"], "updated_at": now, "created_at": now}
        )

    ends = subscription["ends_at"]
    period: dict[str, Any] = (
        {}
        if extends
        else {
            # Новый период — с нуля и контакты, и отклики
            "contacts_used_this_period": 0,
            "responses_used_this_period": 0,
            "period_resets_at": ends if ends is not None else now + timedelta(days=30),
        }
    )
    eloquent.save(
        ctx,
        "wallets",
        wallet,
        {
            "promo_units": int(wallet.get("promo_units") or 0) + int(plan["promo_units"] or 0),
            **period,
        },
        section=None,
        model="Wallet",
        casts={
            "promo_units": "int",
            "contacts_used_this_period": "int",
            "responses_used_this_period": "int",
        },
    )

    until = _date(ends)
    title_key = "messages.order." + (
        "plan_assigned" if source == SOURCE_MANUAL else "plan_activated"
    )
    # Каждому сотруднику — на его языке, а не на языке того, кто оплатил
    _notify_company(
        ctx,
        company,
        "billing",
        lambda locale: ui.t(title_key, locale, plan=plan["name"]),
        "success",
        "/cabinet/billing",
        (lambda locale: ui.t("messages.order.plan_until", locale, date=until))
        if until is not None
        else (lambda locale: ui.t("messages.order.plan_forever", locale)),
    )

    return subscription


# ── Промокоды ───────────────────────────────────────────────────────


def normalize(code: str) -> str:
    """PromoCode::normalize: тире к одному, пробелы прочь, заглавными."""
    code = code.strip(" \t\n\r\0\x0b")

    for old, new in (("—", "-"), ("–", "-"), ("−", "-"), (" ", ""), ("_", "-")):
        code = code.replace(old, new)

    return code.upper()


def _assert_usable(ctx: Context, promo: dict[str, Any]) -> None:
    if promo["used_at"] is not None:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.used"))

    expires = promo["expires_at"]

    # isPast(): момент с долями секунды, а срок — целыми секундами
    if expires is not None and expires.replace(tzinfo=UTC) < datetime.now(UTC):
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.expired"))

    if not promo["is_active"]:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.disabled"))


def preview(ctx: Context, raw: str) -> dict[str, Any]:
    """
    PromoCodeService::preview: проверить код, ничего не погашая, — для
    страницы тарифов. Условия компании проверит активация в кабинете.
    """
    code = normalize(raw)

    if code == "":
        raise PromoCodeRejectedError(ctx.t("messages.billing.promo_required"))

    found = _rows("select * from promo_codes where code = %s limit 1", [code])

    if not found:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.unknown"))

    promo = found[0]
    _assert_usable(ctx, promo)
    plan = _plan_of(promo) if promo["plan_id"] is not None else None

    if plan is None or not plan["is_active"]:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.plan_gone"))

    discount = promo["discount_percent"] is not None

    if discount:
        if not 1 <= int(promo["discount_percent"]) <= 99:
            raise PromoCodeRejectedError(ctx.t("messages.promo_code.no_discount"))
    elif int(promo["days"] or 0) < 1:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.no_period"))

    return {
        "code": promo["code"],
        "plan_id": plan["id"],
        "plan_code": plan["code"],
        "discount_percent": int(promo["discount_percent"]) if discount else None,
        "days": None if discount else int(promo["days"]),
    }


def _assert_no_redeemed(ctx: Context, company_id: int) -> None:
    if _rows("select 1 from promo_codes where used_by_company_id = %s limit 1", [company_id]):
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.company_used"))


def eligible(company_id: int) -> bool:
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


def _capture(ctx: Context, promo: dict[str, Any], company: dict[str, Any], user_id: int) -> None:
    """Захват кода: условное обновление; одна компания — один код (уникальный индекс)."""
    now = _stamp(eloquent.now())

    try:
        with (
            transaction.atomic(),
            allowed_writes("promo_codes"),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "update promo_codes set used_at = %s, used_by_company_id = %s, "
                "used_by_user_id = %s, updated_at = %s where id = %s and used_at is null",
                [now, company["id"], user_id, now, promo["id"]],
            )
            captured = cursor.rowcount
    except IntegrityError as error:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.company_used")) from error

    if captured != 1:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.used"))


def _plan_of(promo: dict[str, Any]) -> dict[str, Any] | None:
    plans = _rows("select * from plans where id = %s", [promo["plan_id"]])

    return plans[0] if plans else None


def _link(promo_id: int, subscription_id: int) -> None:
    """Связь кода с подпиской — запросом мимо модели, с updated_at построителя."""
    with allowed_writes("promo_codes"), connection.cursor() as cursor:
        cursor.execute(
            "update promo_codes set subscription_id = %s, updated_at = %s where id = %s",
            [subscription_id, _stamp(eloquent.now()), promo_id],
        )


def _redeem_free(
    ctx: Context, promo: dict[str, Any], company: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """PromoCodeService::redeemFree: только новым компаниям без действующего тарифа."""
    if _rows(
        "select 1 from payments where company_id = %s and status in ('paid', 'refunded') limit 1",
        [company["id"]],
    ):
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.new_only"))

    if active_subscription(company["id"]) is not None:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.has_plan"))

    if int(promo["days"]) < 1:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.no_period"))

    _capture(ctx, promo, company, user["id"])
    plan = _plan_of(promo)
    assert plan is not None
    subscription = assign(
        ctx,
        company,
        plan,
        days=int(promo["days"]),
        source=SOURCE_PROMO,
        granted_by=user,
        reason=f"Промокод {promo['code']}",
    )
    # PromoCode::query()->update(): метку времени ставит построитель Eloquent
    _link(promo["id"], subscription["id"])
    subscription["plan"] = plan

    return subscription


def _redeem_discount(
    ctx: Context, promo: dict[str, Any], company: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """PromoCodeService::redeemDiscount: тот же тариф уже действует — отказ."""
    percent = int(promo["discount_percent"])

    if percent < 1 or percent > 99:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.no_discount"))

    active = active_subscription(company["id"])

    if active is not None and active["plan_id"] == promo["plan_id"]:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.plan_active"))

    _capture(ctx, promo, company, user["id"])
    plan = _plan_of(promo)
    assert plan is not None

    return order_plan_with_promo(ctx, company, plan, user, promo)


def _resume_discount(
    ctx: Context, promo: dict[str, Any], company: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """PromoCodeService::resumeDiscount: свой захваченный код — к его счёту."""
    pending = _rows(
        "select * from payments where promo_code_id = %s and company_id = %s "
        "and status = 'pending' order by created_at desc limit 1",
        [promo["id"], company["id"]],
    )

    if pending:
        return pending[0]

    if promo["subscription_id"] is not None:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.used"))

    plan = _plan_of(promo)

    if plan is None or not plan["is_active"]:
        raise PromoCodeRejectedError(ctx.t("messages.promo_code.plan_gone"))

    return order_plan_with_promo(ctx, company, plan, user, promo)


def redeem(
    ctx: Context, value: str, company: dict[str, Any], user: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """
    PromoCodeService::redeem одной транзакцией: ("subscription", подписка)
    или ("payment", счёт со скидкой). Отказ — PromoCodeRejectedError.
    """
    code = normalize(value)

    if code == "":
        raise PromoCodeRejectedError(ctx.t("messages.billing.promo_required"))

    with transaction.atomic():
        found = _rows("select * from promo_codes where code = %s limit 1", [code])

        if not found:
            raise PromoCodeRejectedError(ctx.t("messages.promo_code.unknown"))

        promo = found[0]
        discount = promo["discount_percent"] is not None

        if discount and promo["used_by_company_id"] == company["id"]:
            return "payment", _resume_discount(ctx, promo, company, user)

        _assert_usable(ctx, promo)
        _assert_no_redeemed(ctx, company["id"])
        plan = _plan_of(promo)

        if plan is None or not plan["is_active"]:
            raise PromoCodeRejectedError(ctx.t("messages.promo_code.plan_gone"))

        if discount:
            return "payment", _redeem_discount(ctx, promo, company, user)

        return "subscription", _redeem_free(ctx, promo, company, user)
