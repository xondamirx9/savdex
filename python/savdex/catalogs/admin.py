"""
Разделы «Типы компаний» и «Категории» админки на Django — вместо Filament
CompanyTypeResource и CategoryResource. Про категории — у CategoryAdmin ниже.

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
from django.db.models import Case, QuerySet, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest

from savdex.adminsite import register
from savdex.catalog_admin import CatalogAdmin, TranslationsInline
from savdex.catalogs.models import (
    Category,
    CategoryTranslation,
    CompanyType,
    CompanyTypeTranslation,
)
from savdex.text import numeric

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


# ── Категории ───────────────────────────────────────────────────────

#: Адрес категории: латиница, цифры, дефис — как у всех категорий из сидера
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

#: Значки, которые витрина умеет рисовать (CATEGORY_ICONS в
#: resources/js/pages/Home.tsx; совпадение сверяется тестом). В Filament
#: значок вводился словом наугад, и всё незнакомое витрина молча
#: подменяла коробкой
ICONS: dict[str, str] = {
    "package": "Стройка — каска",
    "shirt": "Одежда — футболка",
    "layers": "Металлы — слои",
    "wheat": "Продукты — колос",
    "box": "Упаковка — коробка",
    "settings": "Оборудование — шестерня",
    "briefcase": "Услуги — портфель",
    "armchair": "Мебель — кресло",
    "presentation": "Презентация — доска",
    "truck": "Перевозки — грузовик",
    "other": "Разное — фигуры",
    "textile": "Текстиль — футболка",
    "food": "Еда — приборы",
    "construction": "Стройка — каска",
    "electronics": "Электроника — микросхема",
    "machinery": "Техника — шестерня",
    "chemistry": "Химия — колба",
    "chemicals": "Химия — колба",
}


class SectionChoice(forms.ModelChoiceField):  # type: ignore[type-arg]
    """Раздел в выборе — названием, а не адресом."""

    def label_from_instance(self, obj: Any) -> str:  # noqa: ANN401
        return str(obj.name())


def _sections() -> Any:  # noqa: ANN401
    return Category.objects.filter(parent__isnull=True).prefetch_related("translations")


class CategoryForm(forms.ModelForm):  # type: ignore[type-arg]
    parent = SectionChoice(
        queryset=_sections(),
        required=False,
        label="Раздел",
        empty_label="— верхний уровень: это сам раздел",
        help_text="Подкатегорию нельзя вложить в подкатегорию: дерево на два уровня",
    )
    icon = forms.ChoiceField(
        label="Значок",
        required=False,
        help_text="Показывается у раздела на главной. Для подкатегорий не нужен",
    )

    class Meta:
        model = Category
        fields = ("parent", "slug", "icon", "sort", "is_active")
        help_texts: ClassVar[dict[str, str]] = {
            "slug": "Латиницей, строчными, через дефис: cement-beton. Участвует в адресе страницы",
            "sort": "Меньше — выше в списке",
            "is_active": "Выключенная скрыта из каталога и мастера объявлений",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        sections = _sections()

        if self.instance.pk:
            # Сама себе раздел — петля в дереве
            sections = sections.exclude(pk=self.instance.pk)

        parent_field: Any = self.fields["parent"]
        parent_field.queryset = sections

        choices = [("", "— без значка (коробка)"), *ICONS.items()]
        current = self.instance.icon

        if current and current not in ICONS:
            # Заведённое в Filament словом, которого витрина не знает:
            # показываем как есть, чтобы сохранение не спотыкалось
            choices.append((current, f"{current} — витрина не знает, рисует коробку"))

        icon_field: Any = self.fields["icon"]
        icon_field.choices = choices

    def clean_slug(self) -> str:
        slug = str(self.cleaned_data.get("slug") or "").strip()

        if not SLUG.fullmatch(slug):
            raise forms.ValidationError(
                "Только латиница в нижнем регистре, цифры и дефис: cement-beton."
            )

        return slug

    def clean_icon(self) -> str | None:
        return self.cleaned_data.get("icon") or None

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        parent = cleaned.get("parent")

        if (
            parent is not None
            and self.instance.pk
            and Category.objects.filter(parent_id=self.instance.pk).exists()
        ):
            # Раздел с подкатегориями, вложенный в другой раздел, — это
            # третий уровень для его подкатегорий
            self.add_error(
                "parent",
                "У этого раздела есть подкатегории — он может быть только верхнего уровня. "
                "Сначала перенесите подкатегории в другой раздел.",
            )

        return cleaned


class CategoryTranslationsInline(TranslationsInline):
    model = CategoryTranslation


class SectionFilter(admin.SimpleListFilter):
    """Фильтр по разделу — названиями, а не адресами (как чинили в Filament)."""

    title = "раздел"
    parameter_name = "section"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [
            ("top", "Только разделы"),
            *((str(c.pk), c.name()) for c in _sections().order_by("sort", "slug")),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        value = self.value()

        if value == "top":
            return queryset.filter(parent__isnull=True)

        return queryset.filter(parent_id=int(value)) if value and numeric(value) else queryset


@register(Category, section="catalogs")
class CategoryAdmin(CatalogAdmin):
    """
    Раздел «Категории». Всё, что было в Filament, и то, что там было
    неправильно:

    - удаление ничем не было защищено (и массовое тоже): подкатегории
      раздела становились разделами, у объявлений, тендеров и
      продвижений категория обнулялась, привязки компаний стирались.
      Теперь удалить можно только категорию без ссылок;
    - дерево на два уровня держалось только на списке выбора: раздел
      с подкатегориями можно было вложить в другой раздел (третий
      уровень), а раздел — в самого себя;
    - адрес не проверялся на вид; значок вводился словом наугад, и
      незнакомое витрина молча рисовала коробкой — теперь выбор из
      того, что она умеет;
    - русское название обязательно не только на словах.
    """

    laravel_model = "App\\Models\\Category"
    title_list = "Категории"
    title_add = "Новая категория"
    title_change = "Категория"
    COUNTED: ClassVar[dict[str, str]] = {
        "_children": "подкатегории",
        "_listings": "объявления",
    }
    search_fields = ("slug",)

    form = CategoryForm
    inlines = (CategoryTranslationsInline,)
    fieldsets = (
        ("Категория", {"fields": ("parent", "slug", "icon", "sort", "is_active")}),
        ("Удаление", {"fields": ("held",)}),
    )
    list_display = (
        "title",
        "section_name",
        "translations_count",
        "children_count",
        "listings_count",
        "sort",
        "is_active",
    )
    list_filter = (SectionFilter, "is_active")
    list_per_page = 100

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Деревом: раздел, под ним его подкатегории по порядку."""
        tree: QuerySet[Any] = (
            queryset.select_related("parent")
            .prefetch_related("parent__translations")
            .annotate(
                _branch_sort=Coalesce("parent__sort", "sort"),
                _branch=Coalesce("parent_id", "id"),
                _level=Case(When(parent__isnull=True, then=Value(0)), default=Value(1)),
            )
        )

        return tree

    def get_ordering(self, request: HttpRequest) -> tuple[str, ...]:
        return ("_branch_sort", "_branch", "_level", "sort", "slug")

    @admin.display(description="Категория", ordering="slug")
    def title(self, obj: Category) -> str:
        return f"{'↳ ' if obj.parent_id else ''}{obj.name()} · {obj.slug}"

    @admin.display(description="Раздел")
    def section_name(self, obj: Category) -> str:
        return obj.parent.name() if obj.parent else "— верхний уровень"

    @admin.display(description="Подкатегорий")
    def children_count(self, obj: Category) -> int:
        return int(getattr(obj, "_children", 0))

    @admin.display(description="Объявлений")
    def listings_count(self, obj: Category) -> int:
        return int(getattr(obj, "_listings", 0))
