"""
Общее у разделов справочников в админке на Django.

- названия на языках — вложенной таблицей, русское обязательно:
  оно подставляется, если перевода нет;
- права на названия — права на саму запись: иначе Django искал бы
  отдельное право на «переводы» и молча их не сохранял;
- удаление недоступно, пока на запись ссылаются, а форма объясняет
  почему;
- переименование попадает в журнал: названия — часть записи.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import Count, Q, QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest

from savdex.adminsite import SavdexModelAdmin
from savdex.catalog import LOCALES, Catalog, Guarded


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

    def _parent_perm(self, request: HttpRequest, action: str) -> bool:
        meta = self.parent_model._meta

        return bool(request.user.has_perm(f"{meta.app_label}.{action}_{meta.model_name}"))

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "view")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change" if obj else "add")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change" if obj else "add")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change" if obj else "add")


class GuardedAdmin(SavdexModelAdmin):
    """Раздел записей, которые не удаляются, пока на них ссылаются."""

    #: Какие ссылки считать в списке: имя аннотации → подпись Reference
    COUNTED: ClassVar[dict[str, str]] = {}

    readonly_fields: ClassVar[Any] = ("held",)
    list_per_page = 50

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        """
        Счётчики ссылок — одним запросом на страницу.

        Через references() каждой записи список из 50 городов стоил бы
        300 запросов.
        """
        # Как ModelAdmin.get_queryset, но порядок — после подсчётов и
        # annotate(): раздел может сортировать по вычисленному (дерево
        # категорий), а order_by по ещё не объявленному полю — ошибка
        model: type[Guarded] = self.model
        queryset = self.annotate(model._default_manager.get_queryset())
        refs = {ref.label: ref for ref in model.REFERENCES}
        counted = {
            name: RawSQL(refs[label].subquery(model._meta.db_table), ())
            for name, label in self.COUNTED.items()
        }

        annotated: QuerySet[Any] = self.enrich(queryset.annotate(**counted))
        ordering = self.get_ordering(request)

        return annotated.order_by(*ordering) if ordering else annotated

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Что разделу нужно в списке сверх счётчиков."""
        return queryset

    def enrich(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Общее для семейства разделов (у справочников — названия)."""
        return queryset

    @admin.display(description="Можно ли удалить")
    def held(self, obj: Guarded | None) -> str:
        return "—" if obj is None or obj.pk is None else obj.held()

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        """Запись, на которую ссылаются, не удаляется, — её выключают."""
        if not super().has_delete_permission(request, obj):
            return False

        return obj is None or not obj.references()


class CatalogAdmin(GuardedAdmin):
    """Раздел справочника: записи с названиями и запретом удаления при ссылках."""

    def enrich(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Названия и их число — тоже одним запросом на страницу."""
        with_names: QuerySet[Any] = queryset.prefetch_related("translations").annotate(
            _translations=Count("translations", distinct=True)
        )

        return with_names

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Any], search_term: str
    ) -> tuple[QuerySet[Any], bool]:
        """Поиск по коду (search_fields) и по названию на любом языке."""
        if not search_term:
            return queryset, False

        by_code = Q(**{f"{self.search_fields[0]}__icontains": search_term})

        return (
            queryset.filter(by_code | Q(translations__name__icontains=search_term)).distinct(),
            True,
        )

    @admin.display(description="Переводов")
    def translations_count(self, obj: Catalog) -> str:
        count = getattr(obj, "_translations", 0)

        return f"{count} из {len(LOCALES)}" + ("" if count >= len(LOCALES) else " ⚠")

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Поля записи и её названия: переименование — тоже правка записи."""
        # Свежим запросом, мимо закэшированных до правки
        names = {f"name:{t.locale}": t.name for t in obj.translations.order_by("locale")}

        return {**self.attributes(obj), **names}
