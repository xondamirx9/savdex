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
from savdex.billing.models import Plan
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


# ── Подписки ────────────────────────────────────────────────────────

#: Subscription::SOURCE_* — «Откуда» у Filament
SOURCES = {"payment": "Оплачен", "manual": "Выдан вручную", "promo": "Промокод"}

#: Статусы подписки у Filament
SUBSCRIPTION_STATUSES = {"active": "Активна", "expired": "Истекла", "cancelled": "Отменена"}


class Subscription(models.Model):
    """App\\Models\\Subscription: тариф компании."""

    company = models.ForeignKey(
        Company, verbose_name="компания", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    plan = models.ForeignKey(
        Plan, verbose_name="тариф", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    status = models.CharField("статус", max_length=255)
    started_at = UTCDateTimeField("начало")
    ends_at = UTCDateTimeField("до", null=True)
    auto_renew = models.BooleanField("автопродление", default=True)
    cancelled_at = UTCDateTimeField(null=True)
    source = models.CharField("откуда", max_length=255)
    granted_by = models.ForeignKey(
        User, verbose_name="кто выдал", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, db_column="granted_by", related_name="+",
    )  # fmt: skip
    grant_reason = models.CharField("основание", max_length=255, null=True)
    created_at = UTCDateTimeField(null=True)
    updated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "subscriptions"
        verbose_name = "подписка"
        verbose_name_plural = "Подписки"

    def __str__(self) -> str:
        return f"Подписка #{self.pk}"


# ── Промокоды ───────────────────────────────────────────────────────


class PromoCode(models.Model):
    """App\\Models\\PromoCode: код на бесплатный период или скидку."""

    code = models.CharField("код", max_length=32)
    plan = models.ForeignKey(
        Plan, verbose_name="тариф", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    days = models.IntegerField("дней")
    discount_percent = models.IntegerField("скидка, %", null=True)
    expires_at = UTCDateTimeField("активировать до", null=True)
    is_active = models.BooleanField("действует", default=True)
    note = models.CharField("для кого / повод", max_length=255, null=True)
    used_at = UTCDateTimeField("активирован", null=True)
    used_by_company = models.ForeignKey(
        Company, verbose_name="кем", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, related_name="+",
    )  # fmt: skip
    subscription_id = models.BigIntegerField(null=True)
    created_by = models.ForeignKey(
        User, verbose_name="кто выпустил", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, db_column="created_by", related_name="+",
    )  # fmt: skip
    created_at = UTCDateTimeField("выпущен", null=True)
    updated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "promo_codes"
        verbose_name = "промокод"
        verbose_name_plural = "Промокоды"

    def __str__(self) -> str:
        return self.code


# ── Возвраты ────────────────────────────────────────────────────────

#: Refund::STATUSES
REFUND_STATUSES = {"requested": "Заявлен", "done": "Проведён", "rejected": "Отклонён"}


class Refund(models.Model):
    """App\\Models\\Refund: возврат по оплаченному счёту."""

    payment = models.ForeignKey(
        Payment, verbose_name="счёт", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    company = models.ForeignKey(
        Company, verbose_name="компания", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, related_name="+",
    )  # fmt: skip
    amount = models.BigIntegerField("сумма")
    currency = models.CharField(max_length=3)
    reason = models.TextField("причина")
    status = models.CharField("решение", max_length=20)
    created_by = models.ForeignKey(
        User, verbose_name="заявил", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, db_column="created_by", related_name="+",
    )  # fmt: skip
    decided_by = models.ForeignKey(
        User, verbose_name="решил", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, db_column="decided_by", related_name="+",
    )  # fmt: skip
    decided_at = UTCDateTimeField(null=True)
    decision_note = models.TextField(null=True)
    created_at = UTCDateTimeField("заявлен", null=True)
    updated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "refunds"
        verbose_name = "возврат"
        verbose_name_plural = "Возвраты"

    def __str__(self) -> str:
        return f"Возврат #{self.pk}"

    def money(self) -> str:
        """Refund::money: «429 500 сум» — с пробелами."""
        return f"{int(self.amount):,}".replace(",", " ") + f" {self.currency}"


# ── Жалобы на контакты ──────────────────────────────────────────────

#: Решения по жалобе у Filament
COMPLAINT_STATUSES = {"pending": "Ждёт", "accepted": "Возвращено", "declined": "Отказано"}


class Complaint(models.Model):
    """
    App\\Models\\ContactUnlock с жалобой: раскрытый контакт, который
    покупатель назвал нерабочим. Обоснованная жалоба возвращает кредит —
    поэтому раздел денежный.
    """

    company = models.ForeignKey(
        Company, verbose_name="жалуется", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    target_company = models.ForeignKey(
        Company, verbose_name="на кого", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    credits_spent = models.IntegerField("списано")
    complaint_status = models.CharField("решение", max_length=255, null=True)
    complaint_reason = models.TextField("суть жалобы", null=True)
    complained_at = UTCDateTimeField("подана", null=True)
    refunded = models.BooleanField(default=False)
    moderator_note = models.TextField(null=True)
    moderated_by = models.ForeignKey(
        User, verbose_name="решил", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, db_column="moderated_by", related_name="+",
    )  # fmt: skip
    moderated_at = UTCDateTimeField(null=True)
    created_at = UTCDateTimeField(null=True)
    updated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "contact_unlocks"
        verbose_name = "жалоба на контакт"
        verbose_name_plural = "Жалобы на контакты"

    def __str__(self) -> str:
        return f"Жалоба #{self.pk}"


# ── Финансовые операции ────────────────────────────────────────────

#: FinanceOperations::REASONS
WALLET_REASONS = {
    "unlock": "Раскрытие контакта",
    "purchase": "Покупка",
    "refund": "Возврат",
    "complaint_refund": "Возврат по жалобе",
    "plan_grant": "Начисление по тарифу",
    "promotion": "Продвижение",
}

WALLET_KINDS = {"credits": "Кредиты", "promo_units": "Продвижение"}


class WalletTransaction(models.Model):
    """App\\Models\\WalletTransaction: движение по кошельку компании."""

    company = models.ForeignKey(
        Company, verbose_name="компания", on_delete=models.DO_NOTHING, db_constraint=False,
        related_name="+",
    )  # fmt: skip
    user = models.ForeignKey(
        User, verbose_name="кто провёл", null=True, on_delete=models.DO_NOTHING,
        db_constraint=False, related_name="+",
    )  # fmt: skip
    kind = models.CharField("что", max_length=255)
    amount = models.IntegerField("сколько")
    balance_after = models.IntegerField("остаток после")
    reason = models.CharField("основание", max_length=255)
    subject_type = models.CharField(max_length=255, null=True)
    subject_id = models.BigIntegerField(null=True)
    comment = models.CharField("комментарий", max_length=255, null=True)
    created_at = UTCDateTimeField("когда", null=True)
    updated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "wallet_transactions"
        verbose_name = "операция"
        verbose_name_plural = "Финансовые операции"

    def __str__(self) -> str:
        return f"Операция #{self.pk}"
