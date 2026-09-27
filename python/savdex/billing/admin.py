"""
Разделы «Пакеты контактов» и «Тарифы» админки на Django — вместо Filament
CreditPackResource и PlanResource. Про тарифы — у PlanAdmin ниже.

Пакеты контактов.

Всё, что было в Filament, и то, что там было неправильно:

- пакет, на который выставлены счета, удалялся кнопкой на странице
  правки — хотя комментарий в таблице обещал, что удаления нет.
  Неоплаченный счёт на удалённый пакет после оплаты не начислял ни
  одного кредита: деньги пришли, контактов нет, ошибки нет;
- число кредитов меняется, пока на пакет есть неоплаченные счета:
  кредиты начисляются по пакету, а не по счёту, и покупатель,
  заплативший за «30 контактов», получил бы другое число. Теперь
  форма это не пропускает и предлагает завести новый пакет;
- цена могла быть отрицательной, код — любым словом.

Цена в сумах по курсу ЦБ здесь не показывается: курс живёт в кэше
Laravel. Витрина считает её как раньше.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest

from savdex.adminsite import register
from savdex.billing.models import CreditPack, Plan
from savdex.catalog_admin import GuardedAdmin

#: Код пакета: как у трёх пакетов из миграции — pack_10, pack_30, pack_100
CODE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


class CreditPackForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = CreditPack
        fields = ("code", "name", "credits", "sort", "price_usd", "price_uzs", "is_active")
        help_texts: ClassVar[dict[str, str]] = {
            "code": "Латиницей, например pack_50. После создания не меняется — "
            "по нему пакет узнаёт шлюз оплаты",
            "name": "То, что видит покупатель: «30 контактов»",
            "sort": "Меньше — выше в кабинете",
            "price_usd": "Пересчитывается в сумы по курсу ЦБ",
            "price_uzs": "Заполните, только если цену зафиксировали — тогда курс не применяется",
            "is_active": "Выключенный пакет исчезает из кабинета; "
            "уже выставленные счета остаются в силе",
        }

    def clean_code(self) -> str:
        code = str(self.cleaned_data.get("code") or "").strip().lower()

        if not CODE.fullmatch(code):
            raise forms.ValidationError("Только латиница, цифры, дефис и подчёркивание: pack_50.")

        if CreditPack.objects.filter(code=code).exists():
            raise forms.ValidationError("Пакет с таким кодом уже есть.")

        return code

    def clean_credits(self) -> int:
        credits = int(self.cleaned_data.get("credits") or 0)

        if credits < 1:
            raise forms.ValidationError("Хотя бы один кредит.")

        pack: CreditPack = self.instance
        unpaid = pack.unpaid_invoices()

        if pack.pk and credits != pack.credits and unpaid:
            raise forms.ValidationError(
                f"На пакет выставлено неоплаченных счетов: {unpaid}. Кредиты начисляются "
                "по пакету, и за них пришло бы другое число контактов, чем в счёте. "
                "Заведите новый пакет, а этот выключите."
            )

        return credits

    def clean_price_usd(self) -> Decimal:
        price = self.cleaned_data.get("price_usd")

        if price is None or price <= 0:
            raise forms.ValidationError("Цена должна быть больше нуля.")

        return Decimal(price)

    def clean_price_uzs(self) -> int | None:
        price = self.cleaned_data.get("price_uzs")

        if price is not None and price <= 0:
            raise forms.ValidationError("Цена должна быть больше нуля — или оставьте пустым.")

        return price

    def validate_unique(self) -> None:
        # Код уже проверен в clean_code — после приведения к нижнему регистру
        if "code" in self.cleaned_data:
            self.instance.code = self.cleaned_data["code"]
        super().validate_unique()


@register(CreditPack, section="creditpacks")
class CreditPackAdmin(GuardedAdmin):
    laravel_model = "App\\Models\\CreditPack"
    title_list = "Пакеты контактов"
    title_add = "Новый пакет"
    title_change = "Пакет контактов"
    COUNTED: ClassVar[dict[str, str]] = {"_invoices": "счета"}

    form = CreditPackForm
    fieldsets = (
        ("Пакет", {"fields": ("code", "name", "credits", "sort")}),
        ("Цена", {"fields": ("price_usd", "price_uzs", "is_active")}),
        ("Удаление", {"fields": ("held",)}),
    )
    list_display = ("title", "credits", "price", "sold", "is_active")
    ordering = ("sort", "code")

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        sold: QuerySet[Any] = queryset.annotate(
            _sold=RawSQL(
                "select count(*) from payments "
                "where payments.credit_pack_id = credit_packs.id and payments.status = 'paid'",
                (),
            )
        )

        return sold

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        """Код после создания не меняется: по нему пакет узнаёт шлюз оплаты."""
        return ("code", "held") if obj is not None else ("held",)

    @admin.display(description="Пакет", ordering="code")
    def title(self, obj: CreditPack) -> str:
        return f"{obj.name} · {obj.code}"

    @admin.display(description="Цена")
    def price(self, obj: CreditPack) -> str:
        price = obj.price_usd
        usd = f"${int(price) if price == price.to_integral_value() else price}"

        if obj.price_uzs is None:
            return f"{usd} по курсу"

        return f"{obj.price_uzs:,} сум (зафиксирована)".replace(",", " ")

    @admin.display(description="Продано")
    def sold(self, obj: CreditPack) -> int:
        return int(getattr(obj, "_sold", 0))


# ── Тарифы ──────────────────────────────────────────────────────────


class PlanForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = Plan
        fields = (
            "code",
            "name",
            "sort",
            "price_usd",
            "price_uzs",
            "period_days",
            "listing_days",
            "listings_limit",
            "contacts_limit",
            "responses_limit",
            "promo_units",
            "verification_days",
            "advanced_analytics",
            "sees_interested_names",
            "has_microsite",
            "is_active",
        )
        help_texts: ClassVar[dict[str, str]] = {
            "code": "Латиницей. После создания не меняется — на код ссылаются подписки "
            "и код приложения",
            "sort": "Меньше — левее на странице тарифов",
            "price_usd": "Пересчитывается в сумы по курсу ЦБ. У бесплатного — 0",
            "price_uzs": "Заполните, только если цену зафиксировали — тогда курс не применяется",
            "period_days": "Сколько действует одна оплата",
            "listing_days": "Сколько висит объявление до продления",
            "listings_limit": "Пусто — без ограничений",
            "contacts_limit": "Пусто — без ограничений. Сверх лимита списываются кредиты",
            "responses_limit": "Пусто — без ограничений. Пока витринный лимит: "
            "показывается в карточке тарифа",
            "promo_units": "Начисляются при активации тарифа",
            "verification_days": "За сколько дней проверяем компанию",
            "is_active": "Выключенный тариф исчезает с витрины, "
            "но у купивших продолжает действовать",
        }

    def clean_code(self) -> str:
        code = str(self.cleaned_data.get("code") or "").strip().lower()

        if not CODE.fullmatch(code):
            raise forms.ValidationError("Только латиница, цифры, дефис и подчёркивание: business.")

        if Plan.objects.filter(code=code).exists():
            raise forms.ValidationError("Тариф с таким кодом уже есть.")

        return code

    def clean_price_usd(self) -> Decimal:
        price = self.cleaned_data.get("price_usd")

        if price is None or price < 0:
            raise forms.ValidationError("Цена не может быть меньше нуля.")

        return Decimal(price)

    def clean_price_uzs(self) -> int | None:
        price = self.cleaned_data.get("price_uzs")

        if price is not None and price <= 0:
            raise forms.ValidationError("Больше нуля — или оставьте пустым.")

        return price

    def _at_least_one(self, field: str) -> int:
        value = self.cleaned_data.get(field)

        if value is None or value < 1:
            raise forms.ValidationError("Хотя бы один день.")

        return int(value)

    def clean_period_days(self) -> int:
        return self._at_least_one("period_days")

    def clean_listing_days(self) -> int:
        return self._at_least_one("listing_days")

    def validate_unique(self) -> None:
        if "code" in self.cleaned_data:
            self.instance.code = self.cleaned_data["code"]
        super().validate_unique()


@register(Plan, section="plans")
class PlanAdmin(GuardedAdmin):
    """
    Раздел «Тарифы» — вместо Filament PlanResource.

    Что изменилось против Filament:

    - цены и лимиты задаёт админка: PlanSeeder больше не возвращает их
      из кода на каждом деплое;
    - удаление защищено: тариф с подписками, счетами или промокодами не
      удаляется (промокоды уходили каскадом, тариф с подписками падал на
      внешнем ключе), free и vip — никогда;
    - цена не бывает отрицательной, сроки — меньше дня.
    """

    laravel_model = "App\\Models\\Plan"
    title_list = "Тарифы"
    title_add = "Новый тариф"
    title_change = "Тариф"
    COUNTED: ClassVar[dict[str, str]] = {"_subscriptions": "подписки"}

    form = PlanForm
    fieldsets = (
        ("Тариф", {"fields": ("code", "name", "sort")}),
        (
            "Цена и сроки",
            {"fields": ("price_usd", "price_uzs", "period_days", "listing_days")},
        ),
        (
            "Лимиты",
            {
                "fields": (
                    "listings_limit",
                    "contacts_limit",
                    "responses_limit",
                    "promo_units",
                    "verification_days",
                )
            },
        ),
        (
            "Возможности",
            {
                "fields": (
                    "advanced_analytics",
                    "sees_interested_names",
                    "has_microsite",
                    "is_active",
                )
            },
        ),
        ("Удаление", {"fields": ("held",)}),
    )
    list_display = (
        "title",
        "price",
        "active_companies",
        "listings",
        "contacts",
        "promo_units",
        "is_active",
    )
    ordering = ("sort", "code")

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        active: QuerySet[Any] = queryset.annotate(
            _active=RawSQL(
                "select count(*) from subscriptions "
                "where subscriptions.plan_id = plans.id and subscriptions.status = 'active'",
                (),
            )
        )

        return active

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        """Код после создания не меняется: на него ссылаются подписки и код приложения."""
        return ("code", "held") if obj is not None else ("held",)

    @admin.display(description="Тариф", ordering="name")
    def title(self, obj: Plan) -> str:
        return f"{obj.name} · {obj.code}"

    @admin.display(description="Цена")
    def price(self, obj: Plan) -> str:
        if obj.price_uzs is not None:
            price = f"{obj.price_uzs:,} сум".replace(",", " ")
        else:
            usd = obj.price_usd
            price = f"${int(usd) if usd == usd.to_integral_value() else usd}"

        return f"{price} за {obj.period_days} дн."

    @admin.display(description="Компаний")
    def active_companies(self, obj: Plan) -> int:
        return int(getattr(obj, "_active", 0))

    @staticmethod
    def _limit(value: int | None) -> str:
        return "без ограничений" if value is None else str(value)

    @admin.display(description="Объявлений")
    def listings(self, obj: Plan) -> str:
        return self._limit(obj.listings_limit)

    @admin.display(description="Контактов")
    def contacts(self, obj: Plan) -> str:
        return self._limit(obj.contacts_limit)
