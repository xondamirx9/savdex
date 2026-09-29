"""
Кошелёк компании — Wallet::spend со стороны Django.

Условное списание (счёт не уходит в минус) и строка истории по
фактическому остатку после списания — двойная запись, как у модели.
Вызывается внутри транзакции того, кто списывает.
"""

from __future__ import annotations

from django.db import connection

from savdex.guards import allowed_writes
from savdex.web import eloquent
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _stamp

#: Wallet::KINDS
KINDS = ("credits", "promo_units")


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
