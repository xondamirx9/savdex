"""
Денежные задачи по расписанию (шаг 72) — вместо promotions:finish и
billing:reset-periods у Laravel (routes/console.php). Запускает
savdex/schedule.py: продвижения — каждый час, периоды — в 00:30 UTC.

Сохранение — как forceFill()->save() у Eloquent (savdex/web/eloquent.py):
updated_at, только если что-то изменилось; у продвижения — событие
saving (active_key); журнала нет — это не действие администратора.
Уведомления — как Notifier::company. Язык писем и счетов — русский
(app.locale у консоли Laravel).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from savdex.web import eloquent, ui
from savdex.web.cabinet import _rows, company_plan
from savdex.web.shared import Context

#: ResetBillingPeriods::RENEW_BEFORE_DAYS
RENEW_BEFORE_DAYS = 7


@dataclass
class _Console:
    """Контекст без запроса: у консоли Laravel нет вошедшего, язык — ru."""

    locale: str = "ru"
    user: None = None
    request: None = None

    def t(self, key: str, **replace: object) -> str:
        return ui.t(key, self.locale, **replace)


def _console() -> Context:
    return cast(Context, _Console())


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


# ── Продвижения ─────────────────────────────────────────────────────


def _active_key(row: dict[str, Any]) -> dict[str, Any]:
    """Promotion::saving: ключ «одно продвижение на объявление» — только у активной."""
    active = row.get("status") == "active"

    return {"active_key": f"{row['listing_id']}:{row['promotion_type_id']}" if active else None}


def finish_promotions(now: datetime) -> int:
    """
    FinishPromotions: активные с истёкшим сроком — «завершено»; показы
    на момент завершения (разница с impressions_before — эффект за период).
    Слоты «ТОП категории» и «ТОП главной» ограничены: без этого занятое
    место не освобождалось бы никогда.
    """
    promotions = _rows(
        "select p.*, l.impressions_count as listing_impressions from promotions p "
        "left join listings l on l.id = p.listing_id and l.deleted_at is null "
        "where p.status = 'active' and p.ends_at is not null and p.ends_at <= %s order by p.id",
        [_stamp(now)],
    )

    for promotion in promotions:
        impressions = promotion.pop("listing_impressions")
        eloquent.save(
            None,
            "promotions",
            promotion,
            {
                "status": "finished",
                "impressions_after": impressions
                if impressions is not None
                else promotion["impressions_before"],
            },
            section=None,
            model="Promotion",
            saving=_active_key,
        )

    return len(promotions)


# ── Периоды ─────────────────────────────────────────────────────────


def _issue_renewals(now: datetime) -> int:
    """
    Счёт на продление за неделю до конца срока подписки с автопродлением:
    у бухгалтерии остаётся неделя, чтобы провести платёж без разрыва.
    Уже выставленный (ждёт оплаты, тот же тариф) — второй не нужен.
    """
    from savdex.web import orders

    subscriptions = _rows(
        "select * from subscriptions where status = 'active' and auto_renew = true "
        "and ends_at is not null and ends_at between %s and %s order by id",
        [_stamp(now), _stamp(now + timedelta(days=RENEW_BEFORE_DAYS))],
    )
    issued = 0

    for subscription in subscriptions:
        companies = _rows(
            "select * from companies where id = %s and deleted_at is null",
            [subscription["company_id"]],
        )
        plans = _rows("select * from plans where id = %s", [subscription["plan_id"]])
        # $company->users->first(): без сортировки у Laravel — первый по номеру
        users = _rows(
            "select * from users where company_id = %s and deleted_at is null order by id limit 1",
            [subscription["company_id"]],
        )

        if not companies or not plans or not users:
            continue

        if _rows(
            "select 1 from payments where company_id = %s and status = 'pending' "
            "and plan_id = %s limit 1",
            [subscription["company_id"], subscription["plan_id"]],
        ):
            continue

        orders.order_plan(_console(), companies[0], plans[0], users[0])
        issued += 1

    return issued


def _expire_subscriptions(now: datetime) -> int:
    """
    Подписка с истёкшим сроком закрывается; компания не блокируется —
    переходит на Free (Company::plan без действующей подписки).
    """
    from savdex.web.listing_actions import _notify_company

    subscriptions = _rows(
        "select * from subscriptions where status = 'active' and ends_at is not null "
        "and ends_at <= %s order by id",
        [_stamp(now)],
    )

    for subscription in subscriptions:
        eloquent.save(
            None,
            "subscriptions",
            subscription,
            {"status": "expired"},
            section=None,
            model="Subscription",
            casts={"auto_renew": "bool"},
        )
        companies = _rows(
            "select * from companies where id = %s and deleted_at is null",
            [subscription["company_id"]],
        )

        if companies:
            _notify_company(
                None,
                companies[0],
                "payment",
                lambda locale: ui.t("messages.billing.plan_expired_title", locale),
                "warning",
                "/cabinet/billing",
                lambda locale: ui.t("messages.billing.plan_expired_body", locale),
            )

    return len(subscriptions)


def _reset_wallets(now: datetime) -> int:
    """
    Новый расчётный период: счётчики контактов и откликов — в ноль,
    единицы продвижения — заново по тарифу (месячная квота, не копятся).
    Кредиты не сгорают — они живут 12 месяцев (§3.2 ТЗ).
    """
    wallets = _rows(
        "select * from wallets where period_resets_at is not null and period_resets_at <= %s "
        "order by id",
        [_stamp(now)],
    )

    for wallet in wallets:
        alive = _rows(
            "select 1 from companies where id = %s and deleted_at is null", [wallet["company_id"]]
        )
        plan = company_plan(int(wallet["company_id"])) if alive else None
        eloquent.save(
            None,
            "wallets",
            wallet,
            {
                "contacts_used_this_period": 0,
                "responses_used_this_period": 0,
                "promo_units": (plan or {}).get("promo_units") or 0,
                "period_resets_at": now
                + timedelta(days=int((plan or {}).get("period_days") or 30)),
            },
            section=None,
            model="Wallet",
            casts={
                "contacts_used_this_period": "int",
                "responses_used_this_period": "int",
                "promo_units": "int",
            },
        )

    return len(wallets)


def reset_periods(now: datetime) -> tuple[int, int, int]:
    """ResetBillingPeriods: продление, конец подписок, сброс кошельков — в этом порядке."""
    return _issue_renewals(now), _expire_subscriptions(now), _reset_wallets(now)
