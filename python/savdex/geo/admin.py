"""
Раздел «Страны» админки на Django (этап 2) — вместо Filament CountryResource.

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
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest

from savdex.adminsite import SavdexModelAdmin, register
from savdex.geo.models import LOCALES, Country, CountryTranslation


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
    model = CountryTranslation
    formset = TranslationsFormSet
    fields = ("locale", "name")
    extra = 0
    min_num = 1
    max_num = len(LOCALES)
    verbose_name = "название"
    verbose_name_plural = "Названия на языках"

    # Названия — часть страны: права на них — права на саму страну.
    # Без этого Django искал бы отдельное право на «переводы» и молча
    # не сохранял их
    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm("geo.view_country"))

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm("geo.change_country" if obj else "geo.add_country"))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm("geo.change_country" if obj else "geo.add_country"))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return bool(request.user.has_perm("geo.change_country" if obj else "geo.add_country"))


@register(Country, section="catalogs")
class CountryAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Country"
    title_list = "Страны"
    title_add = "Новая страна"
    title_change = "Страна"

    form = CountryForm
    inlines = (TranslationsInline,)
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
            _translations=Count("translations", distinct=True)
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
        return obj.references().get("города", 0)

    @admin.display(description="Компаний")
    def companies_count(self, obj: Country) -> int:
        return obj.references().get("компании", 0)

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
