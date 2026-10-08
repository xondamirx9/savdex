"""
Спам в поддержке: «Спам» в обращении и спам-фильтр.

- «Спам» — обращение уходит в корзину с отметкой spam_at, адрес
  отправителя — в спам-фильтр (support_blocked_senders): его письма на
  ящик поддержки больше не становятся обращениями (savdex/support/mail.py);
- «Вернуть» в спам-фильтре — адрес снова пропускается, обращения,
  убранные с ним как спам, возвращаются из корзины. Удалённое по другим
  причинам не трогается: его выдаёт пустой spam_at.

Адрес — в нижнем регистре: письма и обращения сравниваются без учёта
регистра.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Q

from savdex.catalog import now
from savdex.support.models import BlockedSender, Ticket


def normalized(email: str | None) -> str:
    return (email or "").strip().lower()


def is_blocked(email: str | None) -> bool:
    address = normalized(email)

    return bool(address) and BlockedSender.objects.filter(email=address).exists()


def block(email: str, by: int | None) -> bool:
    """В спам-фильтр; уже там — False."""
    address = normalized(email)

    if not address or BlockedSender.objects.filter(email=address).exists():
        return False

    try:
        with transaction.atomic():
            BlockedSender(email=address, blocked_by_id=by).save()
    except IntegrityError:
        # Тот же адрес только что заблокировали в соседнем запросе
        return False

    return True


def mark(ticket: Ticket, email: str, by: int | None) -> bool:
    """
    «Спам»: обращение — в корзину с отметкой, отправитель — в фильтр.
    Возвращает, был ли адрес заблокирован только что.
    """
    stamp = now()

    with transaction.atomic():
        blocked = block(email, by)
        Ticket.everything.filter(pk=ticket.pk).update(
            spam_at=stamp, deleted_at=stamp, updated_at=stamp
        )

    ticket.spam_at = ticket.deleted_at = ticket.updated_at = stamp

    return blocked


@dataclass
class Released:
    email: str
    tickets: int


def release(email: str) -> Released | None:
    """
    «Вернуть»: адрес — из фильтра, его обращения, убранные как спам, — из
    корзины. Адреса в фильтре не было — None.
    """
    address = normalized(email)
    stamp = now()

    with transaction.atomic():
        removed, _ = BlockedSender.objects.filter(email=address).delete()

        if not removed:
            return None

        tickets = Ticket.everything.filter(spam_at__isnull=False).filter(
            Q(author_email__iexact=address) | Q(user__email__iexact=address)
        )
        restored = tickets.update(spam_at=None, deleted_at=None, updated_at=stamp)

    return Released(address, restored)


def removed_count(email: str) -> int:
    """Сколько обращений с этого адреса сейчас убрано как спам."""
    address = normalized(email)

    return (
        Ticket.everything.filter(spam_at__isnull=False)
        .filter(Q(author_email__iexact=address) | Q(user__email__iexact=address))
        .count()
    )
