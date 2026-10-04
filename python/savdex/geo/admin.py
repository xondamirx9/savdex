"""
Разделы «Страны» и «Города» админки на Django (этап 2) — вместо Filament
CountryResource и CityResource.

Всё, что было в Filament (app/Filament/Resources/Countries), и то, что
там было неправильно:

- код страны проверяется на уникальность уже приведённым к нижнему
  регистру — в Filament «UZ» проходил проверку и падал на уникальности
  при сохранении, потому что модель переводила его в «uz» позже;
- русское название обязательно — в Filament это было написано, но не
  проверялось, и страна без него показывалась кодом;
- удаление недоступно, пока на страну ссылаются города, компании,
  тендеры или резюме (резюме Filament не учитывал);
- смена названий попадает в журнал — в Filament переводы жили
  отдельной моделью, которую журнал не видел.

Для городов то же, и ещё:

- адрес города (slug) проверяется: латиница, цифры и дефис, и не
  повторяется внутри страны — Filament пускал дубли, и два «Ташкента»
  в одной стране различались бы только номером;
- резюме удерживают город от удаления (Filament не учитывал).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from savdex.adminsite import register
from savdex.catalog_admin import CatalogAdmin, TranslationsInline
from savdex.geo.models import City, CityTranslation, Country, CountryTranslation
from savdex.text import numeric


class CountryForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = Country
        fields = ("code", "phone_code", "currency_code", "sort", "is_active")
        help_texts: ClassVar[dict[str, str]] = {
            "code": "Две буквы по ISO 3166-1: uz, kz, cn. Участвует в проверке ИНН",
            "phone_code": "Со знаком плюс: +998",
            "currency_code": "Три буквы по ISO 4217: UZS, KZT, USD",
            "sort": "Меньше — выше в списке. Внутри одного порядка страны идут по алфавиту",
            "is_active": "Выключенная страна исчезает из выбора, "
            "но у компаний, которые её уже выбрали, остаётся",
        }

    def clean_code(self) -> str:
        """Как сохранит модель — строчными, и уже такой код проверяется на повтор."""
        code = str(self.cleaned_data.get("code") or "").strip().lower()

        if len(code) != 2:
            raise forms.ValidationError("Код страны — ровно две буквы.")

        taken = Country.objects.filter(code=code)

        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)

        if taken.exists():
            raise forms.ValidationError("Страна с таким кодом уже есть.")

        return code

    def clean_currency_code(self) -> str:
        currency = str(self.cleaned_data.get("currency_code") or "")

        if len(currency) != 3:
            raise forms.ValidationError("Валюта — ровно три буквы.")

        return currency

    def validate_unique(self) -> None:
        # Код уже проверен в clean_code — после приведения к нижнему регистру
        self.instance.code = self.cleaned_data.get("code", self.instance.code)
        super().validate_unique()


class CountryTranslationsInline(TranslationsInline):
    model = CountryTranslation


@register(Country, section="catalogs")
class CountryAdmin(CatalogAdmin):
    laravel_model = "App\\Models\\Country"
    title_list = "Страны"
    title_add = "Новая страна"
    title_change = "Страна"
    COUNTED: ClassVar[dict[str, str]] = {"_cities": "города", "_companies": "компании"}
    search_fields = ("code",)

    form = CountryForm
    inlines = (CountryTranslationsInline,)
    fieldsets = (
        ("Страна", {"fields": ("code", "phone_code", "currency_code", "sort", "is_active")}),
        ("Удаление", {"fields": ("held",)}),
    )
    list_display = (
        "title",
        "phone_code",
        "currency_code",
        "translations_count",
        "cities_count",
        "companies_count",
        "sort",
        "is_active",
    )
    list_filter = ("is_active",)
    ordering = ("sort", "code")

    @admin.display(description="Страна", ordering="code")
    def title(self, obj: Country) -> str:
        return f"{obj.name()} · {obj.code.upper()}"

    @admin.display(description="Городов")
    def cities_count(self, obj: Country) -> int:
        return int(getattr(obj, "_cities", 0))

    @admin.display(description="Компаний")
    def companies_count(self, obj: Country) -> int:
        return int(getattr(obj, "_companies", 0))


# ── Города ──────────────────────────────────────────────────────────

#: Адрес города: латиница, цифры, дефис — как у всех 334 городов из сидера
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class CountryChoice(forms.ModelChoiceField):  # type: ignore[type-arg]
    """
    Страна в выборе — названием, а не кодом.

    Выключенные страны в списке остаются намеренно (как в Filament): их
    города никуда не делись, и форму такого города надо уметь сохранить.
    """

    def label_from_instance(self, obj: Any) -> str:  # noqa: ANN401
        return str(obj.name())


class CityForm(forms.ModelForm):  # type: ignore[type-arg]
    country = CountryChoice(
        queryset=Country.objects.prefetch_related("translations").order_by("sort", "code"),
        label="Страна",
        help_text="Выключенные страны тоже доступны — их города продолжают жить",
    )

    class Meta:
        model = City
        fields = ("country", "slug", "sort", "is_active", "lat", "lng")
        help_texts: ClassVar[dict[str, str]] = {
            "slug": "Латиницей, строчными, через дефис: tashkent, nur-sultan",
            "sort": "Меньше — выше в списке",
            "lat": "Например 41.2995",
            "lng": "Например 69.2401",
        }

    def clean_slug(self) -> str:
        slug = str(self.cleaned_data.get("slug") or "").strip()

        if not SLUG.fullmatch(slug):
            raise forms.ValidationError(
                "Только латиница в нижнем регистре, цифры и дефис: tashkent, nur-sultan."
            )

        return slug

    def clean_lat(self) -> Any:  # noqa: ANN401
        return self._within("lat", 90)

    def clean_lng(self) -> Any:  # noqa: ANN401
        return self._within("lng", 180)

    def _within(self, field: str, limit: int) -> Any:  # noqa: ANN401
        value = self.cleaned_data.get(field)

        if value is not None and not -limit <= value <= limit:
            raise forms.ValidationError(f"От −{limit} до {limit}.")

        return value

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        country, slug = cleaned.get("country"), cleaned.get("slug")

        if country is not None and slug:
            taken = City.objects.filter(country=country, slug=slug)

            if self.instance.pk:
                taken = taken.exclude(pk=self.instance.pk)

            if taken.exists():
                self.add_error("slug", "В этой стране уже есть город с таким адресом.")

        return cleaned


class CityTranslationsInline(TranslationsInline):
    model = CityTranslation


class CountryFilter(admin.SimpleListFilter):
    """Фильтр по стране — главный способ найти город: их сотни."""

    title = "страна"
    parameter_name = "country"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [
            (str(c.pk), c.name())
            for c in Country.objects.prefetch_related("translations").order_by("sort", "code")
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        # Не номер в адресе (?country=abc) — без фильтра, а не 500
        value = self.value() or ""

        return queryset.filter(country_id=int(value)) if numeric(value) else queryset


@register(City, section="catalogs")
class CityAdmin(CatalogAdmin):
    laravel_model = "App\\Models\\City"
    title_list = "Города"
    title_add = "Новый город"
    title_change = "Город"
    COUNTED: ClassVar[dict[str, str]] = {"_companies": "компании", "_listings": "объявления"}
    search_fields = ("slug",)

    form = CityForm
    inlines = (CityTranslationsInline,)
    fieldsets = (
        ("Город", {"fields": ("country", "slug", "sort", "is_active")}),
        (
            "Координаты",
            {
                "fields": ("lat", "lng"),
                "classes": ("collapse",),
                "description": "Необязательны. Нужны там, где город показывается на карте.",
            },
        ),
        ("Удаление", {"fields": ("held",)}),
    )
    list_display = (
        "title",
        "country_name",
        "translations_count",
        "companies_count",
        "listings_count",
        "sort",
        "is_active",
    )
    list_filter = (CountryFilter, "is_active")
    ordering = ("sort", "slug")

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        with_country: QuerySet[Any] = queryset.select_related("country").prefetch_related(
            "country__translations"
        )

        return with_country

    @admin.display(description="Город", ordering="slug")
    def title(self, obj: City) -> str:
        return f"{obj.name()} · {obj.slug}"

    @admin.display(description="Страна")
    def country_name(self, obj: City) -> str:
        return obj.country.name()

    @admin.display(description="Компаний")
    def companies_count(self, obj: City) -> int:
        return int(getattr(obj, "_companies", 0))

    @admin.display(description="Объявлений")
    def listings_count(self, obj: City) -> int:
        return int(getattr(obj, "_listings", 0))
