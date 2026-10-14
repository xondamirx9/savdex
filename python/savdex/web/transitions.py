"""
Разрешённые смены статуса — объявления и счёта, в одном месте.

Раньше каждое действие само решало, из какого статуса можно уйти, и
правила расходились: «Архив → Продлить» выводил на витрину отклонённое,
«Отправить снова» — без проверок, отмена затирала оплаченный счёт.
Теперь сохранение объявления (listing_actions.save_listing, мастер) и
зачисление/отмена/возврат счёта сверяются с таблицами ниже; переход не
из таблицы — TransitionError: это ошибка в коде, а не ввод посетителя,
и он не записывается.

Объявление — по тому, кто меняет:
- owner — владелец на сайте: публикация, продление, архив, «Отправить
  снова»; отклонённое и ждущее модерации сам не выпустит;
- moderator — модератор: одобрить, вернуть на исправление, отклонить —
  из любого статуса;
- system — расписание: истёк срок.
Администратор в разделе «Объявления» правит статус формой Django — это
его право, сюда не попадает.

Счёт: ждёт оплаты → оплачен или «не прошёл»; «не прошёл» → оплачен
(опоздавший перевод, закрытый по сроку счёт); оплачен → возвращён.
Возвращённый снова оплаченным не становится: поздний колбэк провайдера
иначе выдал бы купленное второй раз.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

DRAFT, MODERATION, ACTIVE = "draft", "moderation", "active"
ARCHIVED, EXPIRED = "archived", "expired"
NEEDS_CHANGES, REJECTED = "needs_changes", "rejected"

#: Объявление: кто → из какого статуса → в какие
LISTING: dict[str, dict[str, frozenset[str]]] = {
    "owner": {
        DRAFT: frozenset({ACTIVE}),
        # Правка на витрине — публикация того же объявления
        ACTIVE: frozenset({ACTIVE, ARCHIVED}),
        ARCHIVED: frozenset({ACTIVE}),
        EXPIRED: frozenset({ACTIVE, ARCHIVED}),
        NEEDS_CHANGES: frozenset({ACTIVE}),
        MODERATION: frozenset(),
        REJECTED: frozenset(),
    },
    "moderator": {
        status: frozenset({ACTIVE, NEEDS_CHANGES, REJECTED})
        for status in (DRAFT, MODERATION, ACTIVE, ARCHIVED, EXPIRED, NEEDS_CHANGES, REJECTED)
    },
    "system": {ACTIVE: frozenset({EXPIRED})},
}

PENDING, PAID, FAILED, REFUNDED = "pending", "paid", "failed", "refunded"

#: Счёт: из какого статуса → в какие
PAYMENT: dict[str, frozenset[str]] = {
    PENDING: frozenset({PAID, FAILED}),
    FAILED: frozenset({PAID}),
    PAID: frozenset({REFUNDED}),
    REFUNDED: frozenset(),
}


class TransitionError(ValueError):
    """Смена статуса, которой нет в таблице: ошибка в коде, не ввод посетителя."""


def listing_allowed(before: str, after: str, actor: str = "owner") -> bool:
    """Можно ли actor перевести объявление из before в after."""
    if before == after and actor != "owner":
        return True

    return after in LISTING.get(actor, {}).get(before, frozenset())


def check_listing(
    before: str, after: str, actor: str = "owner", *, listing_id: object = None
) -> None:
    if not listing_allowed(before, after, actor):
        log.error("transition.listing.refused id=%s %s→%s by %s", listing_id, before, after, actor)

        raise TransitionError(f"объявление {listing_id}: {before} → {after} ({actor}) запрещено")


def payment_allowed(before: str, after: str) -> bool:
    """Можно ли перевести счёт из before в after."""
    return after in PAYMENT.get(before, frozenset())


def check_payment(before: str, after: str, *, payment_id: object = None) -> None:
    if not payment_allowed(before, after):
        log.error("transition.payment.refused id=%s %s→%s", payment_id, before, after)

        raise TransitionError(f"счёт {payment_id}: {before} → {after} запрещено")
