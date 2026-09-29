"""
CRM в админке Django (этап 6) — вместо разделов Filament.

Контакты — люди у клиентов, общие для всех: у раздела нет «только
свои» ни у одной роли (AdminAccess). Как в Filament: поиск по имени,
почте и компании, отбор «Без компании», число лидов и сделок контакта
(удалённые не считаются), кто завёл — при создании. Удаление — в
корзину (SoftDeletes), право только у суперадмина.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.models import Company, Contact


class NoCompany(admin.SimpleListFilter):
    """Фильтр «Без компании» у Filament."""

    title = "компания"
    parameter_name = "company"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("none", "Без компании")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Contact]) -> QuerySet[Contact]:
        if self.value() == "none":
            return queryset.filter(company__isnull=True)

        return queryset


def _count(table: str) -> RawSQL:
    """withCount: удалённые (SoftDeletes) не считаются."""
    return RawSQL(
        f"select count(*) from {table} where {table}.contact_id = crm_contacts.id "
        f"and {table}.deleted_at is null",
        [],
    )


@register(Contact, section="contacts")
class ContactAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Crm\\Contact"
    title_list = "Контакты"
    title_add = "Новый контакт"
    title_change = "Контакт"

    fields = ("name", "position", "company", "phone", "email", "telegram", "note")
    list_display = ("person", "company_name", "phone", "email", "leads", "deals")
    list_filter = (NoCompany,)
    search_fields = ("name", "email", "company__name")
    ordering = ("name", "id")
    list_per_page = 50

    def get_queryset(self, request: HttpRequest) -> QuerySet[Contact]:
        queryset: QuerySet[Contact] = super().get_queryset(request)

        return queryset.select_related("company").annotate(
            leads_count=_count("crm_leads"), deals_count=_count("crm_deals")
        )

    @admin.display(description="имя", ordering="name")
    def person(self, obj: Contact) -> str:
        return str(obj)

    @admin.display(description="компания")
    def company_name(self, obj: Contact) -> str:
        company = obj.company

        return company.name if company is not None and company.deleted_at is None else "—"

    @admin.display(description="лидов")
    def leads(self, obj: Contact) -> int:
        return int(getattr(obj, "leads_count", 0))

    @admin.display(description="сделок")
    def deals(self, obj: Contact) -> int:
        return int(getattr(obj, "deals_count", 0))

    def formfield_for_dbfield(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        """ConvertEmptyStringsToNull: пустое поле — NULL, и у многострочных тоже."""
        if getattr(db_field, "null", False) and db_field.get_internal_type() == "TextField":
            kwargs["empty_value"] = None

        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        """Компании — действующие, по названию."""
        if db_field.name == "company":
            kwargs["queryset"] = Company.objects.filter(deleted_at__isnull=True).order_by(
                "name", "id"
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        # CreateContact::mutateFormDataBeforeCreate: кто завёл
        if not change:
            obj.created_by = _admin_of(request).id

        super().save_model(request, obj, form, change)

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление было в Filament — только с правом удалять
        # (у суперадмина); удаляет в корзину, по строке журнала на запись
        return super(SavdexModelAdmin, self).get_actions(request)
