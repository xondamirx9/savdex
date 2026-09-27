"""
Раздел «Типы компаний» админки на Django — вместо Filament CompanyTypeResource.

Всё, что было в Filament, и то, что там было неправильно:

- код проверяется на вид (латиница, цифры, дефис, подчёркивание) и
  приводится к нижнему регистру — Filament только просил «латиницей»
  в подсказке и пропускал «Логистика» и «Logistics» рядом с «logistics»;
- русское название обязательно — в Filament было обязательным на словах;
- удаление недоступно, пока тип выбрала хоть одна компания (в том числе
  удалённая в корзину): у неё осталась бы ссылка в никуда;
- переименование попадает в журнал.

Перетаскивания строк для порядка, как в Filament, нет: порядок задаётся
числом в форме. Правка прямо в списке здесь не годится — она прошла бы
мимо снимка «было» для журнала.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest

from savdex.adminsite import register
from savdex.catalog_admin import CatalogAdmin, TranslationsInline
from savdex.catalogs.models import CompanyType, CompanyTypeTranslation

#: Код типа: как у пяти типов из миграции — manufacturer, importer, …
CODE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


class CompanyTypeForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = CompanyType
        fields = ("code", "sort", "is_active")
        help_texts: ClassVar[dict[str, str]] = {
            "code": "Латиницей, например logistics. После создания не меняется — "
            "он записан в карточках компаний",
            "sort": "Меньше — выше в списке при выборе",
            "is_active": "Выключенный тип исчезает из формы регистрации, "
            "но остаётся у компаний, которые его уже выбрали",
        }

    def clean_code(self) -> str:
        code = str(self.cleaned_data.get("code") or "").strip().lower()

        if not CODE.fullmatch(code):
            raise forms.ValidationError(
                "Только латиница, цифры, дефис и подчёркивание: logistics, raw-materials."
            )

        if CompanyType.objects.filter(code=code).exists():
            raise forms.ValidationError("Тип с таким кодом уже есть.")

        return code

    def validate_unique(self) -> None:
        # Код уже проверен в clean_code — после приведения к нижнему регистру
        if "code" in self.cleaned_data:
            self.instance.code = self.cleaned_data["code"]
        super().validate_unique()


class CompanyTypeTranslationsInline(TranslationsInline):
    model = CompanyTypeTranslation


@register(CompanyType, section="catalogs")
class CompanyTypeAdmin(CatalogAdmin):
    laravel_model = "App\\Models\\CompanyType"
    title_list = "Типы компаний"
    title_add = "Новый тип компании"
    title_change = "Тип компании"
    COUNTED: ClassVar[dict[str, str]] = {"_companies": "компании"}
    search_fields = ("code",)

    form = CompanyTypeForm
    inlines = (CompanyTypeTranslationsInline,)
    fieldsets = (
        ("Тип", {"fields": ("code", "sort", "is_active")}),
        ("Удаление", {"fields": ("held",)}),
    )
    list_display = ("title", "translations_count", "companies_count", "sort", "is_active")
    list_filter = ("is_active",)
    ordering = ("sort", "code")
    list_per_page = 100

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        """Код после создания не меняется: он записан в карточках компаний."""
        return ("code", "held") if obj is not None else ("held",)

    @admin.display(description="Тип", ordering="code")
    def title(self, obj: CompanyType) -> str:
        return f"{obj.name()} · {obj.code}"

    @admin.display(description="Компаний")
    def companies_count(self, obj: CompanyType) -> int:
        return int(getattr(obj, "_companies", 0))
