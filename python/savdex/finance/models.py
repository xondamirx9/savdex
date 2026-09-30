"""
Деньги глазами админки Django (этап 7). Схема — у Laravel (managed =
False), хозяин таблиц — тоже он, пока сверка денег не проработает месяц
без расхождений (docs/migration-to-python.md, этап 7). Поэтому модели
здесь только для списков: всё, что меняет деньги, идёт через те же
службы, что и у сайта, — savdex/web/settlement.py (выдача купленного) и
savdex/web/orders.py (отмена счёта), прямым SQL и под allowed_writes.
"""

from __future__ import annotations

from django.db import models

from savdex.accounts.models import User
from savdex.catalog import UTCDateTimeField
from savdex.crm.models import Company

#: Payment::STATUSES
STATUSES = {
    "pending": "Ожидает оплаты",
    "paid": "Оплачен",
    "failed": "Отменён",
    "refunded": "Возвращён",
}

#: За что счёт — фильтр списка у Filament
PURPOSES = {"subscription": "Тариф", "credits": "Кредиты", "promo_units": "Продвижение"}


class Payment(models.Model):
    """App\\Models\\Payment: счёт компании."""

    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    number = models.CharField("счёт", max_length=20, null=True)
    purpose = models.CharField("за что", max_length=255)
    description = models.CharField("описание", max_length=255)
    amount = models.BigIntegerField("сумма")
    currency = models.CharField("валюта", max_length=3)
    provider = models.CharField("провайдер", max_length=255, null=True)
    external_id = models.CharField("номер у провайдера", max_length=255, null=True)
    status = models.CharField("статус", max_length=255, choices=list(STATUSES.items()))
    paid_at = UTCDateTimeField("оплачен", null=True)
    plan_id = models.BigIntegerField(null=True)
    credit_pack_id = models.BigIntegerField(null=True)
    promo_code_id = models.BigIntegerField(null=True)
    subscription_id = models.BigIntegerField(null=True)
    confirmed_by = models.ForeignKey(
        User,
        verbose_name="кто отметил",
        null=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="confirmed_by",
        related_name="+",
    )
    admin_note = models.TextField("отметка", null=True)
    created_at = UTCDateTimeField("выставлен", null=True)
    updated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "payments"
        verbose_name = "счёт"
        verbose_name_plural = "Счета и оплаты"

    def __str__(self) -> str:
        return self.number or f"Счёт #{self.pk}"

    def amount_label(self) -> str:
        """Payment::amountLabel."""
        label = f"{int(self.amount):,}".replace(",", " ")

        return f"{label} {'сум' if self.currency == 'UZS' else self.currency}"
