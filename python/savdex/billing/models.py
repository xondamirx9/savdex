"""
Пакеты контактов и тарифы — перешли к Django (этап 2). Про тарифы — у Plan ниже.

Пакеты контактов.

Таблица создана миграцией Laravel
(database/migrations/2026_07_29_130000_create_credit_packs_and_orders.php):
managed = False, схему по-прежнему меняет только Laravel.

Счёт на пакет (payments.credit_pack_id) ссылается на пакет и сам хранит
число кредитов (payments.credits, записывается при выставлении): оплата
начисляет обещанное в счёте, а не то, что к тому времени окажется в
пакете. Раньше начислялось по пакету, и от расхождения защищал запрет
менять кредиты при счетах «ждёт оплаты», но и отменённый счёт может
стать оплаченным. Теперь число кредитов в пакете менять можно всегда.

- пакет, на который выставлен хоть один счёт, не удаляется. В Filament
  комментарий обещал «удаления нет», а кнопка «Удалить» на странице
  правки была: удалённый пакет обнулялся у счетов;
- код не меняется после создания — по нему пакет узнаёт шлюз оплаты.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

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


class Plan(Guarded):
    """
    Тариф — копия правил App\\Models\\Plan.

    С этапа 2 переноса цены и лимиты задаёт админка (решение заказчика):
    PlanSeeder на деплое только досоздаёт недостающие тарифы, а раньше
    возвращал цену, лимиты и название из кода, и правка тарифа жила до
    следующего деплоя.

    Удаление в Filament ничем не было защищено: промокоды на тариф
    уходили каскадом, у счетов обнулялся тариф, а тариф с подписками
    падал на внешнем ключе. Теперь тариф с подписками, счетами или
    промокодами не удаляется, а free и vip — никогда: их читает код.
    """

    REFERENCES: ClassVar[tuple[Reference, ...]] = (
        Reference("subscriptions", "plan_id", "подписки"),
        Reference("payments", "plan_id", "счета"),
        Reference("promo_codes", "plan_id", "промокоды"),
    )
    HELD_AS = "на тариф"
    INSTEAD = "Выключите его — он исчезнет с витрины, а у купивших продолжит действовать."

    #: Plan::FREE и Plan::VIP — на них опирается код площадки
    SYSTEM: ClassVar[frozenset[str]] = frozenset({"free", "vip"})

    code = models.CharField("код", max_length=30, unique=True)
    name = models.CharField("название", max_length=60)
    price_usd = models.DecimalField("цена, $", max_digits=10, decimal_places=2, default=0)
    price_uzs = models.PositiveBigIntegerField("цена в сумах", null=True, blank=True)
    period_days = models.PositiveSmallIntegerField("срок, дней", default=30)
    listing_days = models.PositiveSmallIntegerField("срок объявления, дней", default=30)
    listings_limit = models.PositiveIntegerField("объявлений", null=True, blank=True)
    contacts_limit = models.PositiveIntegerField("контактов в месяц", null=True, blank=True)
    responses_limit = models.PositiveIntegerField("откликов в месяц", null=True, blank=True)
    promo_units = models.PositiveIntegerField("промо-единиц", default=0)
    verification_days = models.PositiveSmallIntegerField("проверка, дней", default=5)
    advanced_analytics = models.BooleanField("расширенная аналитика", default=False)
    sees_interested_names = models.BooleanField("видит, кто интересуется", default=False)
    has_microsite = models.BooleanField("микросайт компании", default=False)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("продаётся", default=True)

    class Meta:
        managed = False
        db_table = "plans"
        ordering = ("sort", "code")
        verbose_name = "тариф"
        verbose_name_plural = "тарифы"

    def __str__(self) -> str:
        return self.name if self.pk else "новый тариф"

    def references(self) -> dict[str, int]:
        references = super().references()

        if self.code in self.SYSTEM:
            # Не ссылка, но держит так же: без этого тарифа код сломается
            references = {"код площадки": 1, **references}

        return references

    def held(self) -> str:
        if self.code in self.SYSTEM:
            return (
                f"Нельзя: на тариф «{self.code}» опирается код площадки "
                "(лимиты компаний без подписки, лента главной)."
            )

        return super().held()
