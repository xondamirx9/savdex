"""
Кошелёк компании — Wallet::spend со стороны Django.

Условное списание (счёт не уходит в минус) и строка истории по
фактическому остатку после списания — двойная запись, как у модели.
Вызывается внутри транзакции того, кто списывает.
"""

from __future__ import annotations

from typing import Any

from django.db import connection

from savdex.guards import allowed_writes
from savdex.web import eloquent
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _stamp

#: Wallet::KINDS
KINDS = ("credits", "promo_units")


def ensure(company_id: int) -> dict[str, Any]:
    """
    Кошелёк компании — найти или завести, всегда с датой смены периода.

    У компании на бесплатном тарифе подписки нет, а кошелёк заводился
    только при выдаче тарифа: раскрытие контакта и продвижение отвечали
    «Кошелёк не найден». А кошелёк без period_resets_at смена периода
    не трогала — месячный лимит бесплатных контактов не обновлялся.
    """
    from datetime import timedelta

    from savdex.web.cabinet import company_plan

    now = eloquent.now()
    days = int(company_plan(company_id).get("period_days") or 30)

    with allowed_writes("wallets"), connection.cursor() as cursor:
        cursor.execute(
            "insert into wallets (company_id, period_resets_at, created_at, updated_at) "
            "select %s, %s, %s, %s where not exists "
            "(select 1 from wallets where company_id = %s)",
            [company_id, _stamp(now + timedelta(days=days)), _stamp(now), _stamp(now), company_id],
        )
        cursor.execute(
            "update wallets set period_resets_at = %s where company_id = %s "
            "and period_resets_at is null",
            [_stamp(now + timedelta(days=days)), company_id],
        )

    return _rows("select * from wallets where company_id = %s order by id limit 1", [company_id])[0]


def spend(
    wallet_id: int,
    kind: str,
    amount: int,
    reason: str,
    subject: tuple[str, int] | None,
    user_id: int | None,
) -> bool:
    """Wallet::spend: списать amount со счёта kind; не хватает — False."""
    assert kind in KINDS
    now = _stamp(eloquent.now())

    with allowed_writes("wallets", "wallet_transactions"), connection.cursor() as cursor:
        cursor.execute(
            f"update wallets set {kind} = {kind} - %s, updated_at = %s "
            f"where id = %s and {kind} >= %s",
            [amount, now, wallet_id, amount],
        )

        if cursor.rowcount == 0:
            return False

        fresh = _rows(
            f"select company_id, {kind} as balance from wallets where id = %s", [wallet_id]
        )[0]
        cursor.execute(
            "insert into wallet_transactions (company_id, user_id, kind, amount, "
            "balance_after, reason, subject_type, subject_id, updated_at, created_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                fresh["company_id"],
                user_id,
                kind,
                -amount,
                fresh["balance"],
                reason,
                None if subject is None else f"App\\Models\\{subject[0]}",
                None if subject is None else subject[1],
                now,
                now,
            ],
        )

    return True
