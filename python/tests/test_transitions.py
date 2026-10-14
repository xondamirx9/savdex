"""Разрешённые смены статуса (savdex/web/transitions.py) — без базы."""

from __future__ import annotations

import pytest

from savdex.web import transitions as t


@pytest.mark.parametrize(
    ("before", "after", "actor", "можно"),
    [
        # Владелец: публикация, продление, архив, «Отправить снова»
        ("draft", "active", "owner", True),
        ("archived", "active", "owner", True),
        ("expired", "active", "owner", True),
        ("needs_changes", "active", "owner", True),
        ("active", "archived", "owner", True),
        # …но отклонённое и ждущее модератора сам не выпустит (п. 3 аудита)
        ("rejected", "active", "owner", False),
        ("moderation", "active", "owner", False),
        ("draft", "archived", "owner", False),
        ("rejected", "archived", "owner", False),
        # Модератор решает из любого статуса
        ("moderation", "active", "moderator", True),
        ("rejected", "active", "moderator", True),
        ("active", "rejected", "moderator", True),
        ("active", "archived", "moderator", False),
        # Расписание — только «истёк»
        ("active", "expired", "system", True),
        ("draft", "expired", "system", False),
    ],
)
def test_объявление(before, after, actor, можно):
    assert t.listing_allowed(before, after, actor) is можно


@pytest.mark.parametrize(
    ("before", "after", "можно"),
    [
        ("pending", "paid", True),
        ("pending", "failed", True),
        # Опоздавший перевод по закрытому счёту
        ("failed", "paid", True),
        ("paid", "refunded", True),
        # Отмена не затирает оплату (п. 7), возврат не оплачивается снова
        ("paid", "failed", False),
        ("refunded", "paid", False),
        ("paid", "paid", False),
    ],
)
def test_счёт(before, after, можно):
    assert t.payment_allowed(before, after) is можно


def test_запрещённое_не_проходит():
    with pytest.raises(t.TransitionError):
        t.check_listing("rejected", "active", listing_id=7)

    with pytest.raises(t.TransitionError):
        t.check_payment("refunded", "paid", payment_id=7)
