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
from django.db.models import Count, Q, QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest

from savdex.adminsite import SavdexModelAdmin, register
from savdex.geo.models import LOCALES, City, CityTranslation, Country, CountryTranslation


def _referenced_by(table: str, column: str, owner: str) -> RawSQL:
    """
    Сколько строк таблицы ссылается на запись — подзапросом в списке.

    Считает так же, как references() моделей (вместе с удалёнными в
    корзину), но одним запросом на страницу: через references() список
    из 50 городов стоил бы 300 запросов. Имена — из кода, не от человека.
    """
    return RawSQL(f"select count(*) from {table} where {table}.{column} = {owner}.id", ())


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


class TranslationsFormSet(forms.BaseInlineFormSet):  # type: ignore[type-arg]
    def clean(self) -> None:
        super().clean()

        locales = [
            form.cleaned_data.get("locale")
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]

        if "ru" not in locales:
            raise forms.ValidationError(
                "Нужно русское название — оно подставляется, если перевода нет."
            )


class TranslationsInline(admin.TabularInline):  # type: ignore[type-arg]
    """Названия на языках — часть записи: права на них — права на саму запись."""

    formset = TranslationsFormSet
    fields = ("locale", "name")
    extra = 0
    min_num = 1
    max_num = len(LOCALES)
    verbose_name = "название"
    verbose_name_plural = "Названия на языках"

    #: Модель-владелец в правах Django: «country», «city»
    parent: ClassVar[str]

    # Без этого Django искал бы отдельное право на «переводы» и молча
    # не сохранял их
    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm(f"geo.view_{self.parent}"))

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm(f"geo.{'change' if obj else 'add'}_{self.parent}"))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm(f"geo.{'change' if obj else 'add'}_{self.parent}"))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm(f"geo.{'change' if obj else 'add'}_{self.parent}"))


class CountryTranslationsInline(TranslationsInline):
    model = CountryTranslation
    parent = "country"


@register(Country, section="catalogs")
class CountryAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Country"
    title_list = "Страны"
    title_add = "Новая страна"
    title_change = "Страна"

    form = CountryForm
    inlines = (CountryTranslationsInline,)
    fieldsets = (
        ("Страна", {"fields": ("code", "phone_code", "currency_code", "sort", "is_active")}),
        ("Удаление", {"fields": ("held",)}),
    )
    readonly_fields = ("held",)
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
    search_fields = ("code", "translations__name")
    ordering = ("sort", "code")
    list_per_page = 50

    def get_queryset(self, request: HttpRequest) -> QuerySet[Country]:
        # Переводы и их число — одним запросом на страницу, а не на строку
        queryset: QuerySet[Country] = super().get_queryset(request)

        return queryset.prefetch_related("translations").annotate(
            _translations=Count("translations", distinct=True),
            _cities=_referenced_by("cities", "country_id", "countries"),
            _companies=_referenced_by("companies", "country_id", "countries"),
        )

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Country], search_term: str
    ) -> tuple[QuerySet[Country], bool]:
        if not search_term:
            return queryset, False

        return (
            queryset.filter(
                Q(code__icontains=search_term) | Q(translations__name__icontains=search_term)
            ).distinct(),
            True,
        )

    # ── Колонки ──

    @admin.display(description="Страна", ordering="code")
    def title(self, obj: Country) -> str:
        return f"{obj.name()} · {obj.code.upper()}"

    @admin.display(description="Переводов")
    def translations_count(self, obj: Country) -> str:
        count = getattr(obj, "_translations", 0)

        return f"{count} из {len(LOCALES)}" + ("" if count >= len(LOCALES) else " ⚠")

    @admin.display(description="Городов")
    def cities_count(self, obj: Country) -> int:
        return int(getattr(obj, "_cities", 0))

    @admin.display(description="Компаний")
    def companies_count(self, obj: Country) -> int:
        return int(getattr(obj, "_companies", 0))

    @admin.display(description="Можно ли удалить")
    def held(self, obj: Country | None) -> str:
        if obj is None or obj.pk is None:
            return "—"

        references = obj.references()

        if not references:
            return "Можно: на страну никто не ссылается."

        parts = ", ".join(f"{what} — {count}" for what, count in references.items())

        return f"Нельзя, на страну ссылаются: {parts}. Выключите её вместо удаления."

    # ── Удаление ──

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        """Страна, на которую ссылаются, не удаляется, — её выключают."""
        if not super().has_delete_permission(request, obj):
            return False

        return obj is None or not obj.references()

    # ── Журнал ──

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Поля страны и её названия: переименование — тоже правка страны."""
        names = {
            f"name:{t.locale}": t.name
            for t in CountryTranslation.objects.filter(country_id=obj.pk).order_by("locale")
        }

        return {**self.attributes(obj), **names}


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
    parent = "city"


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
        return queryset.filter(country_id=self.value()) if self.value() else queryset


@register(City, section="catalogs")
class CityAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\City"
    title_list = "Города"
    title_add = "Новый город"
    title_change = "Город"

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
    readonly_fields = ("held",)
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
    list_per_page = 50

    def get_queryset(self, request: HttpRequest) -> QuerySet[City]:
        queryset: QuerySet[City] = super().get_queryset(request)

        return (
            queryset.select_related("country")
            .prefetch_related("translations", "country__translations")
            .annotate(
                _translations=Count("translations", distinct=True),
                _companies=_referenced_by("companies", "city_id", "cities"),
                _listings=_referenced_by("listings", "city_id", "cities"),
            )
        )

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[City], search_term: str
    ) -> tuple[QuerySet[City], bool]:
        if not search_term:
            return queryset, False

        return (
            queryset.filter(
                Q(slug__icontains=search_term) | Q(translations__name__icontains=search_term)
            ).distinct(),
            True,
        )

    # «Найти» показывается, только если есть поля поиска
    search_fields = ("slug",)

    @admin.display(description="Город", ordering="slug")
    def title(self, obj: City) -> str:
        return f"{obj.name()} · {obj.slug}"

    @admin.display(description="Страна")
    def country_name(self, obj: City) -> str:
        return obj.country.name()

    @admin.display(description="Переводов")
    def translations_count(self, obj: City) -> str:
        count = getattr(obj, "_translations", 0)

        return f"{count} из {len(LOCALES)}" + ("" if count >= len(LOCALES) else " ⚠")

    @admin.display(description="Компаний")
    def companies_count(self, obj: City) -> int:
        return int(getattr(obj, "_companies", 0))

    @admin.display(description="Объявлений")
    def listings_count(self, obj: City) -> int:
        return int(getattr(obj, "_listings", 0))

    @admin.display(description="Можно ли удалить")
    def held(self, obj: City | None) -> str:
        if obj is None or obj.pk is None:
            return "—"

        references = obj.references()

        if not references:
            return "Можно: на город никто не ссылается."

        parts = ", ".join(f"{what} — {count}" for what, count in references.items())

        return f"Нельзя, на город ссылаются: {parts}. Выключите его вместо удаления."

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        if not super().has_delete_permission(request, obj):
            return False

        return obj is None or not obj.references()

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        names = {
            f"name:{t.locale}": t.name
            for t in CityTranslation.objects.filter(city_id=obj.pk).order_by("locale")
        }

        return {**self.attributes(obj), **names}
