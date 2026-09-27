"""
Раздел «Пакеты контактов» админки на Django — вместо Filament CreditPackResource.

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
from savdex.billing.models import CreditPack
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
