"""
Пакеты контактов — перешли к Django (этап 2).

Таблица создана миграцией Laravel
(database/migrations/2026_07_29_130000_create_credit_packs_and_orders.php):
managed = False, схему по-прежнему меняет только Laravel.

Счёт на пакет (payments.credit_pack_id) ссылается на пакет, а кредиты
при оплате начисляются по самому пакету (OrderService::grantCredits),
а не по счёту. Поэтому:

- пакет, на который выставлен хоть один счёт, не удаляется. В Filament
  комментарий обещал «удаления нет», а кнопка «Удалить» на странице
  правки была: удалённый пакет обнулялся у счетов, и неоплаченный счёт
  после оплаты не начислял ни одного кредита — молча;
- код не меняется после создания — по нему пакет узнаёт шлюз оплаты.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import connection, models

from savdex.catalog import Guarded, Reference


class CreditPack(Guarded):
    REFERENCES: ClassVar[tuple[Reference, ...]] = (
        Reference("payments", "credit_pack_id", "счета"),
    )
    HELD_AS = "на пакет"
    INSTEAD = "Выключите его — он исчезнет из кабинета, а выставленные счета останутся в силе."

    code = models.CharField("код", max_length=30, unique=True)
    name = models.CharField("название", max_length=60)
    credits = models.PositiveIntegerField("кредитов в пакете")
    price_usd = models.DecimalField("цена, $", max_digits=10, decimal_places=2)
    price_uzs = models.PositiveBigIntegerField("цена в сумах", null=True, blank=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("продаётся", default=True)

    class Meta:
        managed = False
        db_table = "credit_packs"
        ordering = ("sort", "code")
        verbose_name = "пакет контактов"
        verbose_name_plural = "пакеты контактов"

    def __str__(self) -> str:
        return self.name if self.pk else "новый пакет"

    def unpaid_invoices(self) -> int:
        """Счета, по которым кредиты ещё будут начислены — по пакету, не по счёту."""
        if self.pk is None:
            return 0

        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from payments where credit_pack_id = %s and status = 'pending'",
                [self.pk],
            )
            row = cursor.fetchone()

        return int(row[0]) if row else 0
