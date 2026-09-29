"""
CRM в админке Django (этап 6) — вместо разделов Filament.

Контакты — люди у клиентов, общие для всех: у раздела нет «только
свои» ни у одной роли (AdminAccess). Как в Filament: поиск по имени,
почте и компании, отбор «Без компании», число лидов и сделок контакта
(удалённые не считаются), кто завёл — при создании.

Лиды и сделки — с «только свои» (AdminScope у Laravel): продавец видит
свои лиды и нераспределённые, сделки — только свои. Открыть можно ровно
то, что видно в списке: у Filament по прямой ссылке открывалась и
сделка без ответственного, которой в списке нет. Лид берётся себе и
превращается в сделку — кнопками на странице лида и действием над
отмеченными в списке.

Удаление везде — в корзину (SoftDeletes), право только у суперадмина.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connections, transaction
from django.db.models import Q, QuerySet, Sum
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from savdex import access, audit
from savdex.accounts.models import User
from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.models import (
    DEAL_STAGES,
    LEAD_SOURCES,
    LEAD_STATUSES,
    Company,
    Contact,
    Deal,
    Lead,
)

#: Цвета значков — как у бейджей Filament
TONES = {
    "warning": "#b45309",
    "info": "#0369a1",
    "primary": "#1d4ed8",
    "success": "#15803d",
    "gray": "#6b7280",
    "danger": "#b91c1c",
}

LEAD_TONES = {
    "new": "warning",
    "working": "info",
    "qualified": "primary",
    "converted": "success",
    "lost": "gray",
}

DEAL_TONES = {
    "new": "gray",
    "negotiation": "info",
    "proposal": "warning",
    "won": "success",
    "lost": "danger",
}


def _badge(label: str, tone: str) -> str:
    return format_html('<b style="color:{}">{}</b>', TONES.get(tone, TONES["gray"]), label)


def employees(ability: str) -> list[int]:
    """
    LeadForm::employees: действующие сотрудники с правом ability — они
    и только они бывают ответственными.
    """
    with connections["default"].cursor() as cursor:
        cursor.execute(
            "select id, name, email, is_admin, admin_role, status, admin_permissions "
            "from users where is_admin and status = 'active' and deleted_at is null "
            "order by name, id"
        )
        rows = cursor.fetchall()

    ids = []

    for row in rows:
        permissions = row[6]

        if isinstance(permissions, str | bytes):
            try:
                permissions = json.loads(permissions)
            except ValueError:
                permissions = None

        staff = access.Admin(
            id=int(row[0]),
            name=str(row[1]),
            email=str(row[2]),
            is_admin=bool(row[3]),
            role=row[4],
            status=str(row[5]),
            permissions=permissions if isinstance(permissions, dict) else {},
        )

        if staff.can(ability):
            ids.append(staff.id)

    return ids


# ── Общее ───────────────────────────────────────────────────────────


class CrmAdmin(SavdexModelAdmin):
    """Разделы CRM: пустое — NULL, компании — действующие, массовое удаление с правом."""

    list_per_page = 50

    def formfield_for_dbfield(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        """ConvertEmptyStringsToNull: пустое поле — NULL, и у многострочных тоже."""
        if getattr(db_field, "null", False) and db_field.get_internal_type() == "TextField":
            kwargs["empty_value"] = None

        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        if db_field.name == "company":
            kwargs["queryset"] = Company.objects.filter(deleted_at__isnull=True).order_by(
                "name", "id"
            )
        elif db_field.name == "contact":
            kwargs["queryset"] = Contact.objects.order_by("name", "id")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление было в Filament — только с правом удалять
        # (у суперадмина); удаляет в корзину, по строке журнала на запись
        return super(SavdexModelAdmin, self).get_actions(request)

    @staticmethod
    def company_label(company: Company | None) -> str:
        return company.name if company is not None and company.deleted_at is None else ""

    def journal_update(self, request: HttpRequest, obj: Any, before: dict[str, Any]) -> None:  # noqa: ANN401
        """Строка «изменено», как AuditObserver::updated: только то, что поменялось."""
        after = self.snapshot(obj)
        changed = {k: v for k, v in after.items() if before.get(k) != v and k not in audit.NOISE}

        if changed:
            self.journal(
                request,
                "updated",
                obj,
                {"before": {k: before.get(k) for k in changed}, "after": changed},
            )


class Scoped(CrmAdmin):
    """
    «Только свои» — AdminScope: столбец ответственного, у лидов видны и
    нераспределённые. Права на запись — только в пределах списка.
    """

    owner_column: ClassVar[str] = "owner"
    orphans_visible: ClassVar[bool] = False

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        queryset: QuerySet[Any] = super().get_queryset(request)
        staff = _admin_of(request)

        if not staff.scope_is_own(self.section):
            return queryset

        mine = Q(**{f"{self.owner_column}_id": staff.id})

        if self.orphans_visible:
            mine |= Q(**{f"{self.owner_column}__isnull": True})

        return queryset.filter(mine)

    def _visible(self, request: HttpRequest, obj: Any) -> bool:  # noqa: ANN401
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        allowed = super().has_view_permission(request, obj)

        return allowed if obj is None or not allowed else self._visible(request, obj)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        allowed = super().has_change_permission(request, obj)

        return allowed if obj is None or not allowed else self._visible(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        allowed = super().has_delete_permission(request, obj)

        return allowed if obj is None or not allowed else self._visible(request, obj)

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        # Ответственный по умолчанию — тот, кто заводит
        return {**super().get_changeform_initial_data(request), "owner": _admin_of(request).id}

    def owner_field(self, request: HttpRequest, **kwargs: Any) -> forms.ModelChoiceField:  # type: ignore[type-arg]
        field = forms.ModelChoiceField(
            queryset=User.objects.filter(pk__in=employees(f"{self.section}.view")).order_by(
                "name", "id"
            ),
            **kwargs,
        )
        field.label_from_instance = lambda obj: obj.name  # type: ignore[method-assign]

        return field


class OpenFilter(admin.SimpleListFilter):
    """«Только в работе» — включён по умолчанию, как у Filament."""

    # Не «all»: так ChangeList называет «показать всё без страниц»
    parameter_name = "closed"
    open_label = "Только в работе"
    open_q: ClassVar[Q]

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Все, и закрытые")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset if self.value() == "1" else queryset.filter(self.open_q)

    def choices(self, changelist: Any) -> Iterator[Any]:  # noqa: ANN401
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": self.open_label,
        }
        yield {
            "selected": self.value() == "1",
            "query_string": changelist.get_query_string({self.parameter_name: "1"}),
            "display": "Все, и закрытые",
        }


# ── Контакты ────────────────────────────────────────────────────────


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
class ContactAdmin(CrmAdmin):
    laravel_model = "App\\Models\\Crm\\Contact"
    title_list = "Контакты"
    title_add = "Новый контакт"
    title_change = "Контакт"

    fields = ("name", "position", "company", "phone", "email", "telegram", "note")
    list_display = ("person", "company_name", "phone", "email", "leads", "deals")
    list_filter = (NoCompany,)
    search_fields = ("name", "email", "company__name")
    ordering = ("name", "id")

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
        return self.company_label(obj.company) or "—"

    @admin.display(description="лидов")
    def leads(self, obj: Contact) -> int:
        return int(getattr(obj, "leads_count", 0))

    @admin.display(description="сделок")
    def deals(self, obj: Contact) -> int:
        return int(getattr(obj, "deals_count", 0))

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        # CreateContact::mutateFormDataBeforeCreate: кто завёл
        if not change:
            obj.created_by = _admin_of(request).id

        super().save_model(request, obj, form, change)


# ── Лиды ────────────────────────────────────────────────────────────


class LeadForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = Lead
        fields = (
            "title",
            "source",
            "status",
            "owner",
            "company",
            "contact",
            "contact_name",
            "contact_phone",
            "contact_email",
            "note",
            "lost_reason",
        )
        help_texts: ClassVar[dict[str, str]] = {
            "title": "Коротко: что нужно клиенту — «Поставка цемента М400, 20 т»",
            "owner": "Пусто — лид не распределён и виден всем продавцам",
            "lost_reason": "Обязательна при статусе «Отказ»",
        }

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        if data.get("status") == "lost" and not data.get("lost_reason"):
            self.add_error("lost_reason", "Укажите причину отказа.")

        return data


class LeadOpen(OpenFilter):
    title = "в работе"
    open_q = ~Q(status__in=("converted", "lost"))


class LeadOwner(admin.SimpleListFilter):
    title = "ответственный"
    parameter_name = "owner"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("mine", "Мои"), ("none", "Не распределены")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Lead]) -> QuerySet[Lead]:
        if self.value() == "mine":
            return queryset.filter(owner_id=_admin_of(request).id)

        if self.value() == "none":
            return queryset.filter(owner__isnull=True)

        return queryset


@register(Lead, section="leads")
class LeadAdmin(Scoped):
    laravel_model = "App\\Models\\Crm\\Lead"
    title_list = "Лиды"
    title_add = "Новый лид"
    title_change = "Лид"
    change_form_template = "admin/crm/lead/change_form.html"

    form = LeadForm
    orphans_visible = True
    fieldsets = (
        ("Заявка", {"fields": ("title", "source", "status", "owner")}),
        (
            "Кто обратился",
            {"fields": ("company", "contact", "contact_name", "contact_phone", "contact_email")},
        ),
        ("Работа по лиду", {"fields": ("note", "lost_reason")}),
    )
    list_display = ("lead", "who", "phone", "state", "owner_name", "created_at")
    list_filter = (LeadOpen, "status", "source", LeadOwner)
    list_select_related = ("company", "contact", "owner")
    search_fields = ("title",)
    ordering = ("-created_at", "-id")
    actions = ("claim_selected", "convert_selected")

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        if db_field.name == "owner":
            return self.owner_field(
                request,
                required=False,
                label="Ответственный",
                empty_label="Не распределён — виден всем продавцам",
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # ── Список ──

    @admin.display(description="лид", ordering="title")
    def lead(self, obj: Lead) -> str:
        return format_html(
            "{}<br><small>{}</small>", obj.title, LEAD_SOURCES.get(obj.source, obj.source)
        )

    @admin.display(description="кто обратился")
    def who(self, obj: Lead) -> str:
        return format_html(
            "{}<br><small>{}</small>",
            obj.contact_label() or "—",
            self.company_label(obj.company),
        )

    @admin.display(description="телефон")
    def phone(self, obj: Lead) -> str:
        contact = obj.contact
        live = contact is not None and contact.deleted_at is None

        return (contact.phone if live and contact is not None else None) or obj.contact_phone or ""

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Lead) -> str:
        return _badge(LEAD_STATUSES.get(obj.status, obj.status), LEAD_TONES.get(obj.status, "gray"))

    @admin.display(description="ответственный", ordering="owner__name")
    def owner_name(self, obj: Lead) -> str:
        return obj.owner.name if obj.owner is not None else "не распределён"

    # ── Взять себе, в сделку ──

    def has_claim_permission(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("leads.edit")

    def has_convert_permission(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("deals.create")

    def claim(self, request: HttpRequest, lead: Lead) -> bool:
        """«Взять себе»: нераспределённый — мне, новый — сразу в работу."""
        if lead.owner_id is not None:
            return False

        before = self.snapshot(lead)
        lead.owner_id = _admin_of(request).id

        if lead.status == "new":
            lead.status = "working"

        lead.save()
        self.journal_update(request, lead, before)

        return True

    def convert(self, request: HttpRequest, lead: Lead) -> Deal | None:
        """
        «В сделку»: компания, контакт и ответственный — в новую сделку,
        лид — «Стал сделкой». Одной транзакцией (у Filament — без неё) и
        одной строкой журнала о сделке с пометкой «Из лида №N» (у Filament
        их две: наблюдатель и пометка отдельно).
        """
        if not lead.is_open:
            return None

        before = self.snapshot(lead)

        with transaction.atomic():
            deal = Deal(
                title=lead.title,
                company_id=lead.company_id,
                contact_id=lead.contact_id,
                lead_id=lead.pk,
                owner_id=lead.owner_id or _admin_of(request).id,
                stage="new",
            )
            deal.save()
            lead.status = "converted"
            lead.save()

        audit.record(
            connections["default"],
            action="created",
            section="deals",
            actor=_admin_of(request),
            subject_type="App\\Models\\Crm\\Deal",
            subject_id=deal.pk,
            subject_label=deal.title,
            changes={"after": self.attributes(deal)},
            note=f"Из лида №{lead.pk}",
            ip=audit.client_ip(request),
        )
        self.journal_update(request, lead, before)

        return deal

    @admin.action(description="Взять себе", permissions=["claim"])
    def claim_selected(self, request: HttpRequest, queryset: QuerySet[Lead]) -> None:
        done = sum(self.claim(request, lead) for lead in queryset)
        self.message_user(
            request,
            f"Закреплено за вами: {done}." if done else "Нераспределённых среди отмеченных нет.",
            messages.SUCCESS if done else messages.WARNING,
        )

    @admin.action(description="В сделку", permissions=["convert"])
    def convert_selected(self, request: HttpRequest, queryset: QuerySet[Lead]) -> None:
        done = sum(self.convert(request, lead) is not None for lead in queryset)
        self.message_user(
            request,
            f"Сделок создано: {done}. Сумму и этап заполните в разделе «Сделки»."
            if done
            else "Среди отмеченных нет лидов в работе.",
            messages.SUCCESS if done else messages.WARNING,
        )

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/claim/",
                self.admin_site.admin_view(self.claim_view),
                name="crm_lead_claim",
            ),
            path(
                "<path:object_id>/convert/",
                self.admin_site.admin_view(self.convert_view),
                name="crm_lead_convert",
            ),
            *super().get_urls(),
        ]

    def _one(self, request: HttpRequest, object_id: str) -> Lead:
        if request.method != "POST":
            raise PermissionDenied

        lead = self.get_object(request, object_id)

        if not isinstance(lead, Lead) or not self.has_change_permission(request, lead):
            raise PermissionDenied

        return lead

    def claim_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if not self.has_claim_permission(request):
            raise PermissionDenied

        lead = self._one(request, object_id)

        if self.claim(request, lead):
            self.message_user(request, "Лид закреплён за вами.", messages.SUCCESS)

        return HttpResponseRedirect(reverse("savdex_admin:crm_lead_change", args=[lead.pk]))

    def convert_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if not self.has_convert_permission(request):
            raise PermissionDenied

        lead = self._one(request, object_id)
        deal = self.convert(request, lead)

        if deal is None:
            return HttpResponseRedirect(reverse("savdex_admin:crm_lead_change", args=[lead.pk]))

        self.message_user(
            request,
            "Сделка создана. Сумму и этап заполните здесь.",
            messages.SUCCESS,
        )

        return HttpResponseRedirect(reverse("savdex_admin:crm_deal_change", args=[deal.pk]))

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        lead = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if lead is not None and self.has_change_permission(request, lead):
            extra["can_claim"] = lead.owner_id is None and self.has_claim_permission(request)
            extra["can_convert"] = lead.is_open and self.has_convert_permission(request)

        return super().change_view(request, object_id, form_url, extra)


# ── Сделки ──────────────────────────────────────────────────────────


class DealForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = Deal
        fields = (
            "title",
            "stage",
            "owner",
            "expected_close_at",
            "amount",
            "currency",
            "company",
            "contact",
            "note",
            "lost_reason",
        )
        help_texts: ClassVar[dict[str, str]] = {
            "amount": "Целым числом, без копеек",
            "lost_reason": "Обязательна, если сделка проиграна",
        }

    def clean_amount(self) -> int:
        amount = int(self.cleaned_data.get("amount") or 0)

        if amount < 0:
            raise forms.ValidationError("Сумма не может быть отрицательной.")

        return amount

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        if data.get("stage") == "lost" and not data.get("lost_reason"):
            self.add_error("lost_reason", "Укажите причину проигрыша.")

        return data


class DealOpen(OpenFilter):
    title = "в работе"
    open_q = ~Q(stage__in=("won", "lost"))


class DealMine(admin.SimpleListFilter):
    title = "мои и просроченные"
    parameter_name = "only"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("mine", "Мои"), ("overdue", "Просроченные")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Deal]) -> QuerySet[Deal]:
        if self.value() == "mine":
            return queryset.filter(owner_id=_admin_of(request).id)

        if self.value() == "overdue":
            return queryset.filter(DealOpen.open_q, expected_close_at__lt=date.today())

        return queryset


@register(Deal, section="deals")
class DealAdmin(Scoped):
    laravel_model = "App\\Models\\Crm\\Deal"
    title_list = "Сделки"
    title_add = "Новая сделка"
    title_change = "Сделка"
    change_list_template = "admin/crm/deal/change_list.html"

    form = DealForm
    fieldsets = (
        ("Сделка", {"fields": ("title", "stage", "owner", "expected_close_at")}),
        ("Сумма", {"fields": ("amount", "currency")}),
        ("Клиент", {"fields": ("company", "contact")}),
        ("Работа по сделке", {"fields": ("note", "lost_reason")}),
    )
    list_display = ("deal", "total", "state", "owner_name", "expected")
    list_filter = (DealOpen, "stage", DealMine)
    list_select_related = ("company", "owner")
    search_fields = ("title",)
    ordering = ("expected_close_at", "id")

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        if db_field.name == "owner":
            return self.owner_field(request, required=True, label="Ответственный")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="сделка", ordering="title")
    def deal(self, obj: Deal) -> str:
        return format_html("{}<br><small>{}</small>", obj.title, self.company_label(obj.company))

    @admin.display(description="сумма", ordering="amount")
    def total(self, obj: Deal) -> str:
        return obj.money()

    @admin.display(description="этап", ordering="stage")
    def state(self, obj: Deal) -> str:
        return _badge(DEAL_STAGES.get(obj.stage, obj.stage), DEAL_TONES.get(obj.stage, "gray"))

    @admin.display(description="ответственный", ordering="owner__name")
    def owner_name(self, obj: Deal) -> str:
        return obj.owner.name if obj.owner is not None else "—"

    @admin.display(description="закрыть до", ordering="expected_close_at")
    def expected(self, obj: Deal) -> str:
        if obj.expected_close_at is None:
            return "не указана"

        text = obj.expected_close_at.strftime("%d.%m.%Y")

        # Просрочена — только незакрытая
        if obj.closed_at is None and obj.expected_close_at < date.today():
            return _badge(text, "danger")

        return text

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        response = super().changelist_view(request, extra_context)

        # «Итого» под суммой, как Sum у Filament — по отобранным
        if isinstance(response, TemplateResponse) and response.context_data is not None:
            changelist = response.context_data.get("cl")

            if changelist is not None:
                total = changelist.queryset.aggregate(total=Sum("amount"))["total"] or 0
                response.context_data["crm_total"] = f"{total:,}".replace(",", " ")

        return response
