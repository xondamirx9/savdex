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
превращается в сделку — кнопками на доске и странице лида и действием
над отмеченными в архиве.

Вместо списка лидов и сделок — доска по этапам воронки (savdex/crm/
board.py, OnBoard): карточки переводят перетаскиванием или кнопкой, весь
список с закрытыми — «Архив». Этапы и окно перевода правят суперадмин и
администратор (раздел «Этапы воронки», StageAdmin); модератор доски
видит, но не двигает.

Задачи и коммуникации — тоже «только свои»: задачи по исполнителю (список
дел отвечает на вопрос «что мне делать»), разговоры — по тому, кто
записал. Привязка к лиду или сделке — одним списком из тех, что видны
сотруднику; прежняя привязка остаётся, даже если лид ему не виден.

Удаление — в корзину (SoftDeletes), кроме записей разговоров: их удаляют
насовсем, как Filament. Право — только у суперадмина.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.db import connections, transaction
from django.db.models import Case, IntegerField, OuterRef, Q, QuerySet, Subquery, Sum, Value, When
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timesince import timesince

from savdex import access, audit
from savdex.accounts.models import User
from savdex.adminsite import SavdexModelAdmin, _admin_of, register, static_version
from savdex.catalog import now
from savdex.crm import board, stages
from savdex.crm.models import (
    COMMUNICATION_TYPES,
    LEAD_SOURCES,
    PIPELINES,
    STAGE_KINDS,
    SUBJECTS,
    Communication,
    Company,
    Contact,
    Deal,
    Lead,
    OnStage,
    Stage,
    Task,
    WithSubject,
)
from savdex.text import numeric, plural

#: Цвета значков — как у бейджей Filament. Светлая тема: в плашках
#: (.sx-pill) цвет берёт сама тема, здесь он остался для подписей,
#: которые красятся текстом, — «не назначен» и подобных
TONES = {
    "warning": "#b45309",
    "info": "#0369a1",
    "primary": "#1d4ed8",
    "success": "#15803d",
    "gray": "#6b7280",
    "danger": "#b91c1c",
}

#: Цвет этапа — по колонке: в работе, успех, отказ; новый — жёлтый
KIND_TONES = {"open": "info", "won": "success", "lost": "gray"}


def stage_badge(obj: OnStage) -> str:
    """Этап в списке: название и цвет — из подзапроса OnBoard.get_queryset."""
    code = getattr(obj, obj.stage_field)
    name = getattr(obj, "stage_name", None) or code
    kind = getattr(obj, "stage_kind", None) or "open"

    return _badge(name, "warning" if code == "new" else KIND_TONES.get(kind, "gray"))


def stage_choices(pipeline: str, current: str | None = None) -> list[tuple[str, str]]:
    """
    Этапы для поля формы. Лид становится сделкой только кнопкой
    «В сделку»: этапа «Стал сделкой» в форме нет, если лид уже не на нём.
    """
    return [
        (stage.code, stage.name)
        for stage in stages.of(pipeline)
        if not (pipeline == "leads" and stage.kind == "won" and stage.code != current)
    ]


def _badge(label: str, tone: str) -> str:
    """
    Состояние — плашкой, а не цветным словом.

    Цвет задавался здесь же, кодом светлой темы: в тёмной «Выполнена»
    выходила тёмно-зелёной по тёмно-синему и читалась хуже обычного
    текста. Теперь цвет берёт тема (.sx-pill--*), а подложка видна
    боковым зрением — список читается по цвету, не вчитываясь.
    """
    return format_html(
        '<span class="sx-pill sx-pill--{}">{}</span>',
        tone if tone in TONES else "gray",
        label,
    )


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
    #: Ответственный по умолчанию — тот, кто заводит (поле в форме)
    owner_by_default: ClassVar[bool] = True

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
        initial: dict[str, Any] = dict(super().get_changeform_initial_data(request))

        # Ответственный по умолчанию — тот, кто заводит
        if self.owner_by_default:
            initial[self.owner_column] = _admin_of(request).id

        return initial

    def owner_field(self, request: HttpRequest, **kwargs: Any) -> forms.ModelChoiceField:  # type: ignore[type-arg]
        field = forms.ModelChoiceField(
            # Ответственный — тот, кто может вести запись, а не только смотреть
            # (модератор видит доски лидов и сделок, но не ведёт их)
            queryset=User.objects.filter(pk__in=employees(f"{self.section}.edit")).order_by(
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
    all_label = "Все, и закрытые"
    open_q: ClassVar[Q]

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", self.all_label)]

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
            "display": self.all_label,
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
    status = forms.ChoiceField(label="Этап")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        current = self.instance.status if self.instance.pk else None
        field = self.fields["status"]
        assert isinstance(field, forms.ChoiceField)
        field.choices = stage_choices("leads", current)
        field.initial = current or "new"

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
            "lost_reason": "Обязательна на этапе отказа",
        }

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        if data.get("status") == "lost" and not data.get("lost_reason"):
            self.add_error("lost_reason", "Укажите причину отказа.")

        return data


class Outcome(admin.SimpleListFilter):
    """Архив: все записи, отбор — в работе, успех, отказ."""

    title = "итог"
    parameter_name = "outcome"
    pipeline: ClassVar[str]
    labels: ClassVar[dict[str, str]]

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(self.labels.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.value() not in self.labels:
            return queryset

        codes = [s.code for s in stages.of(self.pipeline) if s.kind == self.value()]

        return queryset.filter(**{f"{queryset.model.stage_field}__in": codes})


class StageFilter(admin.SimpleListFilter):
    """Этап — названиями из воронки, а не кодами."""

    title = "этап"
    parameter_name = "stage"
    pipeline: ClassVar[str]

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [(s.code, s.name) for s in stages.of(self.pipeline)]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.value():
            return queryset.filter(**{queryset.model.stage_field: self.value()})

        return queryset


class LeadOutcome(Outcome):
    pipeline = "leads"
    labels: ClassVar[dict[str, str]] = {
        "open": "В работе",
        "won": "Стали сделками",
        "lost": "Отказы",
    }


class LeadStage(StageFilter):
    pipeline = "leads"


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


# ── Доска вместо списка ─────────────────────────────────────────────


class OnBoard(Scoped):
    """
    Лиды и сделки: доска по этапам воронки вместо списка
    (savdex/crm/board.py). Список всех записей, закрытые тоже, — «Архив»
    (archive/), с массовыми действиями и отборами. С доски — перевод на
    этап (move/) и назначение ответственного (assign/).
    """

    archive_title: ClassVar[str]
    change_list_template = "admin/crm/archive.html"

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        """Название и колонка этапа — подзапросом: значок в архиве без запроса на строку."""
        same = Stage.objects.filter(
            pipeline=self.section,
            code=OuterRef(self.model.stage_field),
        )
        queryset: QuerySet[Any] = (
            super()
            .get_queryset(request)
            .annotate(
                stage_name=Subquery(same.values("name")[:1]),
                stage_kind=Subquery(same.values("kind")[:1]),
            )
        )

        return queryset

    def _url(self, name: str, *args: Any) -> str:
        info = self.model._meta

        return reverse(f"savdex_admin:{info.app_label}_{info.model_name}_{name}", args=args)

    def back(self, request: HttpRequest, default: str | None = None) -> str:
        """Куда вернуться после кнопки на доске: на доску с её отбором."""
        target = request.POST.get("next", "")

        if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return target

        return default or self._url("changelist")

    def get_urls(self) -> list[Any]:
        info = self.model._meta
        name = f"{info.app_label}_{info.model_name}"

        return [
            path("archive/", self.admin_site.admin_view(self.archive_view), name=f"{name}_archive"),
            path(
                "<path:object_id>/move/",
                self.admin_site.admin_view(self.move_view),
                name=f"{name}_move",
            ),
            path(
                "<path:object_id>/assign/",
                self.admin_site.admin_view(self.assign_view),
                name=f"{name}_assign",
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        # Массовые действия из архива и сам архив — список Django; иначе доска
        if request.method == "POST" or getattr(request, "_savdex_archive", False):
            return super().changelist_view(
                request, {"board_url": self._url("changelist"), **(extra_context or {})}
            )

        return self.board_view(request)

    def archive_view(self, request: HttpRequest) -> HttpResponse:
        request._savdex_archive = True  # type: ignore[attr-defined]

        return self.changelist_view(request, {"title": self.archive_title})

    def board_view(self, request: HttpRequest) -> HttpResponse:
        if not self.has_view_permission(request):
            raise PermissionDenied

        request.current_app = self.admin_site.name
        context = {
            **self.admin_site.each_context(request),
            "title": self.title_list,
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            "pipeline": self.section,
            "is_leads": self.model is Lead,
            "add_url": self._url("add") if self.has_add_permission(request) else "",
            "archive_url": self._url("archive"),
            "stages_url": reverse("savdex_admin:crm_stage_changelist")
            + f"?pipeline__exact={self.section}",
            "here": request.get_full_path(),
            "board_js": static_version("savdex/crm-board.js"),
            "board_css": static_version("savdex/crm-board.css"),
            **board.build(self, request),
        }

        return TemplateResponse(request, "admin/crm/board.html", context)

    def _card(self, request: HttpRequest, object_id: str) -> OnStage:
        """Карточка для кнопки доски: POST, право править, видна сотруднику."""
        if request.method != "POST" or not _admin_of(request).can(f"{self.section}.edit"):
            raise PermissionDenied

        obj = self.get_object(request, unquote(object_id))

        if not isinstance(obj, OnStage):
            raise PermissionDenied

        return obj

    def move_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        obj = self._card(request, object_id)
        back = self.back(request)
        stage = Stage.objects.filter(
            pipeline=self.section, code=request.POST.get("stage", "")
        ).first()

        if stage is None:
            self.message_user(request, "Такого этапа нет.", messages.ERROR)

            return HttpResponseRedirect(back)

        if self.model is Lead and stage.kind == "won":
            self.message_user(request, "Лид становится сделкой кнопкой «В сделку».", messages.ERROR)

            return HttpResponseRedirect(back)

        form = board.form_for(stage, board.owners(self.section))(request.POST)

        if not form.is_valid():
            problems = "; ".join(
                f"{form.fields[key].label}: {' '.join(str(e) for e in errors)}"
                if key in form.fields
                else " ".join(str(e) for e in errors)
                for key, errors in form.errors.items()
            )
            self.message_user(
                request, f"«{obj}» не переведена на «{stage.name}»: {problems}", messages.ERROR
            )

            return HttpResponseRedirect(back)

        board.move(self, request, obj, stage, form.cleaned_data)
        self.message_user(request, f"«{obj}» — на этапе «{stage.name}».", messages.SUCCESS)

        return HttpResponseRedirect(back)

    def assign_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """Назначить ответственного — тому, кто видит раздел целиком (не продавцу)."""
        obj = self._card(request, object_id)

        if _admin_of(request).scope_is_own(self.section):
            raise PermissionDenied

        raw = request.POST.get("owner", "")
        owner = board.owners(self.section).filter(pk=raw).first() if numeric(raw) else None

        # Сделка без ответственного не бывает; лид — бывает (виден всем продавцам)
        if owner is None and (raw or self.model is Deal):
            self.message_user(request, "Выберите ответственного из списка.", messages.ERROR)

            return HttpResponseRedirect(self.back(request))

        if obj.owner_id != (owner.pk if owner else None):  # type: ignore[attr-defined]
            before = self.snapshot(obj)
            obj.owner = owner  # type: ignore[attr-defined]
            obj.save()
            self.journal_update(request, obj, before)

        self.message_user(
            request,
            f"«{obj}»: ответственный — {owner.name}."
            if owner
            else f"«{obj}» — снова не распределён, виден всем продавцам.",
            messages.SUCCESS,
        )

        return HttpResponseRedirect(self.back(request))


@register(Lead, section="leads")
class LeadAdmin(OnBoard):
    laravel_model = "App\\Models\\Crm\\Lead"
    title_list = "Лиды"
    archive_title = "Архив лидов"
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
    list_filter = (LeadOutcome, LeadStage, "source", LeadOwner)
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

    @admin.display(description="этап", ordering="status")
    def state(self, obj: Lead) -> str:
        return stage_badge(obj)

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
            self.message_user(request, f"«{lead}» закреплён за вами.", messages.SUCCESS)

        # С доски — назад на доску, со страницы лида — на неё
        return HttpResponseRedirect(
            self.back(request, reverse("savdex_admin:crm_lead_change", args=[lead.pk]))
        )

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
    stage = forms.ChoiceField(label="Этап")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        current = self.instance.stage if self.instance.pk else None
        field = self.fields["stage"]
        assert isinstance(field, forms.ChoiceField)
        field.choices = stage_choices("deals", current)
        field.initial = current or "new"

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


class DealOutcome(Outcome):
    pipeline = "deals"
    labels: ClassVar[dict[str, str]] = {
        "open": "В работе",
        "won": "Выигранные",
        "lost": "Проигранные",
    }


class DealStage(StageFilter):
    pipeline = "deals"


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
class DealAdmin(OnBoard):
    laravel_model = "App\\Models\\Crm\\Deal"
    title_list = "Сделки"
    archive_title = "Архив сделок"
    title_add = "Новая сделка"
    title_change = "Сделка"

    form = DealForm
    fieldsets = (
        ("Сделка", {"fields": ("title", "stage", "owner", "expected_close_at")}),
        ("Сумма", {"fields": ("amount", "currency")}),
        ("Клиент", {"fields": ("company", "contact")}),
        ("Работа по сделке", {"fields": ("note", "lost_reason")}),
    )
    list_display = ("deal", "total", "state", "owner_name", "expected")
    list_filter = (DealOutcome, DealStage, DealMine)
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
        return stage_badge(obj)

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


# ── Этапы воронки ───────────────────────────────────────────────────


def _cards(stage: Stage) -> QuerySet[Any]:
    """Живые карточки этапа (удалённые в корзину не считаются)."""
    model: type[OnStage] = Lead if stage.pipeline == "leads" else Deal

    return model.objects.filter(**{model.stage_field: stage.code})


def _stage_form(pipeline: str, stage: Stage | None) -> type[forms.ModelForm]:  # type: ignore[type-arg]
    """
    Форма этапа: название, норма дней и поля окна — по каталогу воронки
    (stages.FIELDS), у каждого «не спрашивать / можно / обязательно».
    """
    chosen = stage.fields if stage is not None and isinstance(stage.fields, dict) else {}
    lost = stage is not None and stage.kind == "lost"
    fields: dict[str, Any] = {}

    for key, (label, hint) in stages.FIELDS[pipeline].items():
        if key == "lost_reason" and not lost:
            continue  # причину отказа спрашивает только этап отказа — и всегда

        fields[f"f_{key}"] = forms.ChoiceField(
            label=label,
            help_text=hint,
            required=False,
            choices=list(stages.MODES.items()),
            initial="required" if key == "lost_reason" else chosen.get(key, ""),
            disabled=key == "lost_reason",
        )

    class Meta:
        model = Stage
        fields = ("name", "limit_days")

    return type("StageForm", (forms.ModelForm,), {**fields, "Meta": Meta})


@register(Stage, section="pipelines")
class StageAdmin(CrmAdmin):
    """
    Этапы воронок лидов и сделок — правят суперадмин и администратор.
    Завести, переименовать, задать окно, сдвинуть выше или ниже, удалить
    пустой — каждое действие строкой журнала. Системные этапы (вход,
    успех, отказ) переименовываются, но не удаляются.
    """

    laravel_model = "App\\Models\\Crm\\Stage"
    title_list = "Этапы воронки"
    title_add = "Новый этап"
    title_change = "Этап воронки"
    change_form_template = "admin/crm/stage/change_form.html"
    change_list_template = "admin/crm/stage/change_list.html"

    list_display = ("name", "pipeline_name", "column", "norm", "window", "cards", "order")
    list_display_links = ("name",)
    list_filter = ("pipeline",)
    list_per_page = 100

    def get_queryset(self, request: HttpRequest) -> QuerySet[Stage]:
        # Как колонки доски: рабочие по порядку, затем успех, затем отказ
        queryset: QuerySet[Stage] = (
            super()
            .get_queryset(request)
            .annotate(
                column_order=Case(
                    When(kind="open", then=Value(0)),
                    When(kind="won", then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("pipeline", "column_order", "position", "id")
        )

        return queryset

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return {}

    def _pipeline(self, request: HttpRequest, obj: Stage | None) -> str:
        if obj is not None:
            return obj.pipeline

        asked = request.POST.get("pipeline") or request.GET.get("pipeline", "")

        return asked if asked in PIPELINES else "leads"

    def get_form(
        self,
        request: HttpRequest,
        obj: Any = None,  # noqa: ANN401
        change: bool = False,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        kwargs["form"] = _stage_form(self._pipeline(request, obj), obj)

        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        pipeline = self._pipeline(request, obj)
        window = [
            f"f_{key}"
            for key in stages.FIELDS[pipeline]
            if key != "lost_reason" or (obj is not None and obj.kind == "lost")
        ]

        # У нового этапа воронка — в заголовке, колонка — всегда «в работе»
        head: tuple[str, ...] = ("name", "limit_days")

        if obj is not None:
            head = ("pipeline_name", "column", *head)

        return (
            ("Этап", {"fields": head}),
            (
                "Окно при переводе на этап",
                {
                    "fields": window,
                    "description": "Что спросить у сотрудника, когда он переводит "
                    "карточку на этот этап — перетаскиванием или кнопкой.",
                },
            ),
        )

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        return ("pipeline_name", "column")

    @admin.display(description="воронка", ordering="pipeline")
    def pipeline_name(self, obj: Stage | None) -> str:
        return PIPELINES.get(obj.pipeline, obj.pipeline) if obj and obj.pk else ""

    @admin.display(description="колонка")
    def column(self, obj: Stage | None) -> str:
        if obj is None or not obj.pk:
            return "в работе"

        return STAGE_KINDS.get(obj.kind, obj.kind) + (" · системный" if obj.is_system else "")

    @admin.display(description="норма")
    def norm(self, obj: Stage) -> str:
        return f"{obj.limit_days} дн." if obj.limit_days else "—"

    @admin.display(description="окно спрашивает")
    def window(self, obj: Stage) -> str:
        catalog = stages.FIELDS.get(obj.pipeline, {})
        asked = stages.asked(obj)

        return (
            ", ".join(
                catalog[key][0].lower() + (" *" if mode == "required" else "")
                for key, mode in asked.items()
            )
            or "ничего — переводится сразу"
        )

    @admin.display(description="карточек")
    def cards(self, obj: Stage) -> int:
        return _cards(obj).count()

    @admin.display(description="порядок")
    def order(self, obj: Stage) -> str:
        if not obj.is_open:
            return ""

        # Кнопки отправляют форму списка (в ней токен) на свой адрес:
        # отдельная форма внутри формы списка невозможна
        return format_html(
            '<button type="submit" class="button sx-order" formaction="{}" '
            'title="Выше" aria-label="Выше">↑</button> '
            '<button type="submit" class="button sx-order" formaction="{}" '
            'title="Ниже" aria-label="Ниже">↓</button>',
            reverse("savdex_admin:crm_stage_up", args=[obj.pk]),
            reverse("savdex_admin:crm_stage_down", args=[obj.pk]),
        )

    # ── Запись ──

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        if not change:
            obj.pipeline = self._pipeline(request, None)
            obj.code = stages.new_code()
            obj.kind = "open"
            obj.position = stages.next_position(obj.pipeline)

        obj.fields = {
            key: form.cleaned_data[f"f_{key}"]
            for key in stages.FIELDS[obj.pipeline]
            if form.cleaned_data.get(f"f_{key}") in ("optional", "required")
        }

        if obj.kind == "lost":
            obj.fields["lost_reason"] = "required"

        super().save_model(request, obj, form, change)

    def why_not_delete(self, obj: Stage) -> str:
        if obj.is_system:
            return "Системный этап не удаляется: на нём держатся вход, «В сделку» и отчёты."

        count = _cards(obj).count()

        if count:
            return (
                f"На этапе {plural(count, 'карточка', 'карточки', 'карточек')} — "
                "сначала переведите их на другой этап (кнопка ниже), потом удаляйте."
            )

        return ""

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        allowed = super().has_delete_permission(request, obj)

        return allowed if obj is None or not allowed else not self.why_not_delete(obj)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        stage = self.get_object(request, unquote(object_id))
        extra = dict(extra_context or {})

        if isinstance(stage, Stage):
            extra["delete_blocked"] = self.why_not_delete(stage)
            extra["cards_count"] = _cards(stage).count()
            extra["move_targets"] = [
                s
                for s in stages.of(stage.pipeline)
                if s.pk != stage.pk and not (s.pipeline == "leads" and s.kind == "won")
            ]
            extra["can_move_all"] = self.has_change_permission(request, stage) and _admin_of(
                request
            ).can(f"{stage.pipeline}.edit")

        return super().change_view(request, object_id, form_url, extra)

    def add_view(
        self,
        request: HttpRequest,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        pipeline = self._pipeline(request, None)

        return super().add_view(
            request,
            form_url,
            {
                "title": f"Новый этап — {PIPELINES[pipeline].lower()}",
                "stage_pipeline": pipeline,
                **(extra_context or {}),
            },
        )

    def response_add(
        self,
        request: HttpRequest,
        obj: Any,  # noqa: ANN401
        post_url_continue: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        response = super().response_add(request, obj, post_url_continue)

        # «Сохранить и добавить другой» — в ту же воронку
        if "_addanother" in request.POST and isinstance(response, HttpResponseRedirect):
            response["Location"] = (
                reverse("savdex_admin:crm_stage_add") + f"?pipeline={obj.pipeline}"
            )

        return response

    # ── Порядок и перенос карточек ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/up/",
                self.admin_site.admin_view(self.up_view),
                name="crm_stage_up",
            ),
            path(
                "<path:object_id>/down/",
                self.admin_site.admin_view(self.down_view),
                name="crm_stage_down",
            ),
            path(
                "<path:object_id>/move-all/",
                self.admin_site.admin_view(self.move_all_view),
                name="crm_stage_move_all",
            ),
            *super().get_urls(),
        ]

    def _stage(self, request: HttpRequest, object_id: str) -> Stage:
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied

        stage = self.get_object(request, unquote(object_id))

        if not isinstance(stage, Stage):
            raise PermissionDenied

        return stage

    def _shift(self, request: HttpRequest, object_id: str, step: int) -> HttpResponse:
        """Поменять местами с соседним рабочим этапом той же воронки."""
        stage = self._stage(request, object_id)
        row = [s for s in stages.of(stage.pipeline) if s.is_open]
        index = next((i for i, s in enumerate(row) if s.pk == stage.pk), None)

        if index is not None and 0 <= index + step < len(row):
            # Порядок заново по местам: у старых этапов номера могли совпасть
            row[index], row[index + step] = row[index + step], row[index]

            for position, item in enumerate(row, 1):
                if item.position != position:
                    before = self.snapshot(item)
                    item.position = position
                    item.save()
                    self.journal_update(request, item, before)

            self.message_user(request, f"«{stage.name}» — на новом месте.", messages.SUCCESS)

        return HttpResponseRedirect(
            reverse("savdex_admin:crm_stage_changelist") + f"?pipeline__exact={stage.pipeline}"
        )

    def up_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self._shift(request, object_id, -1)

    def down_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self._shift(request, object_id, 1)

    def move_all_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """
        Перевести все карточки этапа на другой — чтобы этап можно было
        удалить. Каждая карточка — своя строка журнала, как при переводе
        с доски; окно этапа здесь не спрашивается.
        """
        stage = self._stage(request, object_id)

        if not _admin_of(request).can(f"{stage.pipeline}.edit"):
            raise PermissionDenied

        target = Stage.objects.filter(
            pipeline=stage.pipeline, code=request.POST.get("target", "")
        ).first()
        model: type[OnStage] = Lead if stage.pipeline == "leads" else Deal

        if target is None or target.pk == stage.pk or (model is Lead and target.kind == "won"):
            self.message_user(request, "Выберите, на какой этап перевести.", messages.ERROR)
        else:
            owner_admin = self.admin_site._registry[model]
            assert isinstance(owner_admin, OnBoard)
            moved = 0

            for card in _cards(stage):
                board.move(
                    owner_admin,
                    request,
                    card,
                    target,
                    {"lost_reason": "Этап удалён"} if target.kind == "lost" else {},
                )
                moved += 1

            self.message_user(request, f"Переведено на «{target.name}»: {moved}.", messages.SUCCESS)

        return HttpResponseRedirect(reverse("savdex_admin:crm_stage_change", args=[stage.pk]))


# ── Задачи и коммуникации: общее ────────────────────────────────────


def local_datetime(label: str, *, required: bool, help_text: str = "") -> forms.DateTimeField:
    """
    Одно поле с календарём браузера (DateTimePicker ->seconds(false));
    время — ташкентское (TIME_ZONE), в базу — UTC.
    """
    return forms.DateTimeField(
        label=label,
        required=required,
        help_text=help_text,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )


def when(value: datetime | None) -> str:
    """dateTime('d.m.Y H:i') в часовом поясе админки."""
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value is not None else ""


def _subject_key(subject_type: str | None, subject_id: int | None) -> str:
    return f"{subject_type}:{subject_id}" if subject_type and subject_id else ""


class SubjectForm(forms.ModelForm):  # type: ignore[type-arg]
    """
    MorphToSelect «Связана с»: лид или сделка одним списком. Выбор — из
    видимых сотруднику (заполняет раздел), прежняя привязка остаётся.
    """

    subject = forms.ChoiceField(label="Связана с", required=False)

    #: Группы выбора: [(«Лиды», [(ключ, название), …]), …] — от раздела
    subject_groups: ClassVar[list[tuple[str, list[tuple[str, str]]]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        instance: WithSubject = self.instance
        current = _subject_key(instance.subject_type, instance.subject_id)
        groups = [(title, list(options)) for title, options in self.subject_groups]
        known = {key for _, options in groups for key, _ in options}

        if current and current not in known:
            label = instance.subject_title() or f"№{instance.subject_id}"
            kind = SUBJECTS.get(str(instance.subject_type), ("Запись", Lead))[0]
            groups.insert(0, ("Сейчас", [(current, f"{kind}: {label}")]))

        field = self.fields["subject"]
        assert isinstance(field, forms.ChoiceField)
        field.choices = [("", "— ни к чему"), *groups]
        field.initial = current

    def clean_subject(self) -> tuple[str | None, int | None]:
        value = self.cleaned_data.get("subject") or ""

        if not value:
            return None, None

        subject_type, _, subject_id = value.rpartition(":")

        return subject_type, int(subject_id)

    def save(self, commit: bool = True) -> Any:  # noqa: ANN401
        self.instance.subject_type, self.instance.subject_id = self.cleaned_data["subject"]

        return super().save(commit)


class WithSubjectAdmin(Scoped):
    """Выбор «к чему относится» — лиды и сделки, видимые сотруднику."""

    def subject_groups(self, request: HttpRequest) -> list[tuple[str, list[tuple[str, str]]]]:
        staff = _admin_of(request)
        groups = []

        for laravel, (_, model) in SUBJECTS.items():
            section = "leads" if model is Lead else "deals"

            if not staff.can(f"{section}.view"):
                continue

            queryset = self.admin_site._registry[model].get_queryset(request)
            title = "Лиды" if model is Lead else "Сделки"
            groups.append(
                (
                    title,
                    [
                        (f"{laravel}:{obj.pk}", str(obj))
                        for obj in queryset.order_by("-created_at", "-id").only("id", "title")
                    ],
                )
            )

        return groups

    def get_form(
        self,
        request: HttpRequest,
        obj: Any = None,  # noqa: ANN401
        change: bool = False,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        form = super().get_form(request, obj, change=change, **kwargs)
        form.subject_groups = self.subject_groups(request)

        return form

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        if db_field.name == "assignee":
            return self.owner_field(request, required=True, label="Исполнитель")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ── Задачи ──────────────────────────────────────────────────────────


class TaskForm(SubjectForm):
    due_at = local_datetime("Срок", required=False, help_text="Задача без срока не напомнит о себе")
    done_at = local_datetime("Выполнена", required=False, help_text="Пусто — ещё нет")

    class Meta:
        model = Task
        fields = ("title", "assignee", "due_at", "done_at", "description")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["title"].label = "Что сделать"
        self.fields["title"].widget.attrs["placeholder"] = "Позвонить и уточнить объём"
        self.fields["description"].label = "Что именно"


class TaskOpen(OpenFilter):
    title = "выполнение"
    open_label = "Только невыполненные"
    all_label = "Все, и выполненные"
    open_q = Q(done_at__isnull=True)


def _today() -> tuple[datetime, datetime]:
    """Сутки по часовому поясу админки — в UTC."""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

    return start, start + timedelta(days=1)


class TaskDue(admin.SimpleListFilter):
    title = "срок"
    parameter_name = "due"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("overdue", "Просроченные"), ("today", "На сегодня")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Task]) -> QuerySet[Task]:
        if self.value() == "overdue":
            return queryset.filter(done_at__isnull=True, due_at__lt=now())

        if self.value() == "today":
            start, end = _today()

            return queryset.filter(done_at__isnull=True, due_at__gte=start, due_at__lt=end)

        return queryset


class Mine(admin.SimpleListFilter):
    """Фильтр «Мои» у Filament: по столбцу «своего» у раздела."""

    title = "чьи"
    parameter_name = "mine"

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        model: Any,  # noqa: ANN401
        model_admin: Any,  # noqa: ANN401
    ) -> None:
        super().__init__(request, params, model, model_admin)
        self.column = f"{model_admin.owner_column}_id"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Мои")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.value() == "1":
            return queryset.filter(**{self.column: _admin_of(request).id})

        return queryset


@register(Task, section="tasks")
class TaskAdmin(WithSubjectAdmin):
    laravel_model = "App\\Models\\Crm\\Task"
    title_list = "Задачи"
    title_add = "Поставить задачу"
    title_change = "Задача"
    change_form_template = "admin/crm/task/change_form.html"

    form = TaskForm
    owner_column = "assignee"
    fieldsets = (
        ("Задача", {"fields": ("title", "assignee", "due_at", "done_at")}),
        (
            "К чему относится",
            {"fields": ("subject",), "description": "Необязательно: бывают задачи сами по себе"},
        ),
        ("Подробности", {"fields": ("description",)}),
    )
    list_display = ("task", "due", "assignee_name", "done", "toggle")
    list_filter = (TaskOpen, TaskDue, Mine)
    list_select_related = ("assignee",)
    search_fields = ("title",)
    ordering = ("due_at", "id")
    actions = ("done_selected", "reopen_selected")

    @admin.display(description="что сделать", ordering="title")
    def task(self, obj: Task) -> str:
        # Выполненное — серым, а не пропадает: «я это уже делал» —
        # частый и законный вопрос
        return format_html(
            '<span style="color:{}">{}</span><br><small>{}</small>',
            TONES["gray"] if obj.is_done else "inherit",
            obj.title,
            obj.subject_title() or "",
        )

    @admin.display(description="срок", ordering="due_at")
    def due(self, obj: Task) -> str:
        if obj.due_at is None:
            return "без срока"

        if obj.is_overdue:
            return format_html(
                '{}<br><small style="color:{}">просрочена</small>',
                _badge(when(obj.due_at), "danger"),
                TONES["danger"],
            )

        return when(obj.due_at)

    @admin.display(description="исполнитель", ordering="assignee__name")
    def assignee_name(self, obj: Task) -> str:
        return obj.assignee.name if obj.assignee is not None else "—"

    @admin.display(description="выполнена", ordering="done_at")
    def done(self, obj: Task) -> str:
        return when(obj.done_at) or "—"

    @admin.display(description="")
    def toggle(self, obj: Task) -> str:
        """
        Отметка одной кнопкой: открывать форму ради одной галочки никто не
        станет. Кнопка отправляет форму списка (в ней токен) на свой адрес.
        """
        return format_html(
            '<button type="submit" class="button" formaction="{}" formmethod="post">{}</button>',
            reverse("savdex_admin:crm_task_done", args=[obj.pk]),
            "Вернуть в работу" if obj.is_done else "Выполнена",
        )

    def get_list_display(self, request: HttpRequest) -> Any:  # noqa: ANN401
        shown = super().get_list_display(request)

        return shown if self.has_done_permission(request) else [c for c in shown if c != "toggle"]

    # ── Выполнена ──

    def has_done_permission(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("tasks.edit")

    def mark(self, request: HttpRequest, task: Task, *, done: bool) -> bool:
        """forceFill(['done_at' => …])->save(): строка журнала «изменено»."""
        if task.is_done == done:
            return False

        before = self.snapshot(task)
        task.done_at = now() if done else None
        task.save()
        self.journal_update(request, task, before)

        return True

    @admin.action(description="Выполнена", permissions=["done"])
    def done_selected(self, request: HttpRequest, queryset: QuerySet[Task]) -> None:
        count = sum(self.mark(request, task, done=True) for task in queryset)
        self.message_user(request, f"Выполнено: {count}.", messages.SUCCESS)

    @admin.action(description="Вернуть в работу", permissions=["done"])
    def reopen_selected(self, request: HttpRequest, queryset: QuerySet[Task]) -> None:
        count = sum(self.mark(request, task, done=False) for task in queryset)
        self.message_user(request, f"Снова в работе: {count}.", messages.SUCCESS)

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/done/",
                self.admin_site.admin_view(self.done_view),
                name="crm_task_done",
            ),
            *super().get_urls(),
        ]

    def done_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.has_done_permission(request):
            raise PermissionDenied

        task = self.get_object(request, object_id)

        if not isinstance(task, Task) or not self.has_change_permission(request, task):
            raise PermissionDenied

        self.mark(request, task, done=not task.is_done)
        self.message_user(
            request,
            "Задача выполнена." if task.is_done else "Задача снова в работе.",
            messages.SUCCESS,
        )

        # Назад — туда, откуда нажали: в список с его отбором или в задачу
        back = request.headers.get("Referer", "")

        if not url_has_allowed_host_and_scheme(
            back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            back = reverse("savdex_admin:crm_task_changelist")

        return HttpResponseRedirect(back)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        task = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(task, Task) and self.has_change_permission(request, task):
            extra["can_mark"] = self.has_done_permission(request)
            extra["task_done"] = task.is_done

        return super().change_view(request, object_id, form_url, extra)

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        # CreateTask::mutateFormDataBeforeCreate: кто поставил
        if not change:
            obj.created_by = _admin_of(request).id

        super().save_model(request, obj, form, change)


# ── Коммуникации ────────────────────────────────────────────────────

COMMUNICATION_TONES = {"call": "success", "meeting": "warning", "email": "info"}


class CommunicationForm(SubjectForm):
    happened_at = local_datetime("Когда", required=True)

    class Meta:
        model = Communication
        fields = ("type", "happened_at", "contact", "summary", "body")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["subject"].label = "Связан с"
        self.fields["summary"].widget.attrs["placeholder"] = "Договорились о пробной партии 20 тонн"


class LastWeek(admin.SimpleListFilter):
    title = "когда"
    parameter_name = "week"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "За неделю")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[Communication]
    ) -> QuerySet[Communication]:
        if self.value() == "1":
            return queryset.filter(happened_at__gte=now() - timedelta(weeks=1))

        return queryset


@register(Communication, section="communications")
class CommunicationAdmin(WithSubjectAdmin):
    laravel_model = "App\\Models\\Crm\\Communication"
    title_list = "Коммуникации"
    title_add = "Записать разговор"
    title_change = "Запись разговора"

    form = CommunicationForm
    owner_column = "author"
    # Кто записал — тот, кто записывает: в форме этого поля нет
    owner_by_default = False
    fieldsets = (
        ("Разговор", {"fields": ("type", "happened_at", "contact", "summary")}),
        ("К чему относится", {"fields": ("subject",)}),
        ("Подробности", {"fields": ("body",)}),
    )
    list_display = ("moment", "kind", "summary", "contact_name", "subject_name", "author_name")
    list_filter = ("type", Mine, LastWeek)
    list_select_related = ("author", "contact")
    search_fields = ("summary",)
    ordering = ("-happened_at", "-id")

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        return {**super().get_changeform_initial_data(request), "happened_at": now()}

    @admin.display(description="когда", ordering="happened_at")
    def moment(self, obj: Communication) -> str:
        ago = timesince(obj.happened_at, depth=1) if obj.happened_at <= now() else ""

        return format_html(
            "{}<br><small>{}</small>", when(obj.happened_at), f"{ago} назад" if ago else ""
        )

    @admin.display(description="что", ordering="type")
    def kind(self, obj: Communication) -> str:
        return _badge(
            COMMUNICATION_TYPES.get(obj.type, obj.type),
            COMMUNICATION_TONES.get(obj.type, "gray"),
        )

    @admin.display(description="с кем")
    def contact_name(self, obj: Communication) -> str:
        contact = obj.contact

        return contact.name if contact is not None and contact.deleted_at is None else "—"

    @admin.display(description="по чему")
    def subject_name(self, obj: Communication) -> str:
        return obj.subject_title() or "—"

    @admin.display(description="кто записал", ordering="author__name")
    def author_name(self, obj: Communication) -> str:
        return obj.author.name if obj.author is not None else "—"

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        # CreateCommunication::mutateFormDataBeforeCreate: автор — сам
        if not change:
            obj.author_id = _admin_of(request).id

        super().save_model(request, obj, form, change)

    def delete_model(self, request: HttpRequest, obj: Any) -> None:  # noqa: ANN401
        """
        Насовсем — мягкого удаления у разговоров нет. Номер записи нужен
        журналу после удаления, а Model.delete() его обнуляет.
        """
        label = str(obj)
        Communication.objects.filter(pk=obj.pk).delete()
        self.journal(request, "deleted", obj)
        request._savdex_done = f"Удалено: {label}"  # type: ignore[attr-defined]
