"""
Раздел админки «ILMORA — регистрации»: заявки с формы /register/ilmora-register.

Только чтение: заявку не создают, не правят и не удаляют — время принятия
принятия оферты в ней юридическое. Новые сверху, по 50 на страницу; поиск по ФИО,
телефону, ПИНФЛ и ИНН; отборы по типу лица, дате и повторам. Повтор —
другая заявка с тем же телефоном, ПИНФЛ или ИНН: не запрещён, но виден
плашкой «повтор». Карточка — все поля, включая время принятия оферты, IP и язык.

Право — ilmora.view (суперадмин и администратор, savdex/access.py): тут
ПИНФЛ. Выгрузка в Excel и CSV — отдельное право ilmora.export, каждая
выгрузка — строка журнала «Выгрузка».
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.admin import _badge, when
from savdex.ilmora.models import PERSON_TYPES, Registration

LOCALES = {"ru": "Русский", "uz": "Узбекский"}


def _repeats(queryset: QuerySet[Registration]) -> QuerySet[Registration]:
    """Пометки повторов: есть ли другая заявка с тем же телефоном или номером."""
    others = Registration.objects.exclude(pk=OuterRef("pk"))

    return queryset.annotate(
        phone_repeat=Exists(others.filter(phone=OuterRef("phone"))),
        number_repeat=Exists(
            others.filter(
                Q(pinfl__isnull=False, pinfl=OuterRef("pinfl"))
                | Q(tin__isnull=False, tin=OuterRef("tin"))
            )
        ),
    )


class RepeatFilter(admin.SimpleListFilter):
    title = "повторы"
    parameter_name = "repeat"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Только повторы")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[Registration]
    ) -> QuerySet[Registration]:
        if self.value() != "1":
            return queryset

        return queryset.filter(Q(phone_repeat=True) | Q(number_repeat=True))


def _offer(value: Any) -> str:  # noqa: ANN401
    return format_html("✓ {}", when(value)) if value is not None else "—"


#: Столбцы выгрузки
EXPORT: list[tuple[str, Any]] = [
    ("Номер", lambda r: r.pk),
    ("Дата", lambda r: r.created_at),
    ("ФИО", lambda r: r.full_name),
    ("Телефон", lambda r: r.phone),
    ("Тип лица", lambda r: PERSON_TYPES.get(r.person_type, r.person_type)),
    ("ПИНФЛ", lambda r: r.pinfl),
    ("ИНН", lambda r: r.tin),
    ("Ознакомился с офертой", lambda r: r.offer_accepted_at),
    ("Подписал заявление", lambda r: r.offer_signed_at),
    ("Редакция оферты", lambda r: r.offer_version),
    ("Язык", lambda r: r.locale),
    ("IP-адрес", lambda r: r.ip),
    ("Повтор", lambda r: "да" if r.phone_repeat or r.number_repeat else ""),
]


@register(Registration, section="ilmora")
class RegistrationAdmin(SavdexModelAdmin):
    laravel_model = "Savdex\\Ilmora\\Registration"
    title_list = "ILMORA — регистрации"
    title_change = "Заявка ILMORA"
    change_list_template = "admin/ilmora/registration/change_list.html"

    list_display = ("moment", "name", "phone_number", "kind", "number", "offer")
    list_display_links = ("moment", "name")
    list_filter = ("person_type", ("created_at", admin.DateFieldListFilter), RepeatFilter)
    search_fields = ("full_name", "phone", "pinfl", "tin")
    ordering = ("-created_at", "-id")
    list_per_page = 50

    fields = (
        "moment",
        "name",
        "phone_number",
        "kind",
        "pinfl",
        "tin",
        "offer_accepted",
        "offer_signed",
        "offer_version",
        "language",
        "ip",
        "user_agent",
    )
    readonly_fields = fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[Registration]:
        return _repeats(super().get_queryset(request))

    # ── Только чтение ──

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    # ── Столбцы ──

    @admin.display(description="дата", ordering="created_at")
    def moment(self, obj: Registration) -> str:
        return when(obj.created_at)

    @admin.display(description="ФИО", ordering="full_name")
    def name(self, obj: Registration) -> str:
        if getattr(obj, "phone_repeat", False) or getattr(obj, "number_repeat", False):
            return format_html("{} {}", obj.full_name, _badge("повтор", "warning"))

        return obj.full_name

    @admin.display(description="телефон", ordering="phone")
    def phone_number(self, obj: Registration) -> str:
        if getattr(obj, "phone_repeat", False):
            return format_html("{} {}", obj.phone, _badge("повтор", "warning"))

        return obj.phone

    @admin.display(description="тип лица", ordering="person_type")
    def kind(self, obj: Registration) -> str:
        return PERSON_TYPES.get(obj.person_type, obj.person_type)

    @admin.display(description="ПИНФЛ / ИНН")
    def number(self, obj: Registration) -> str:
        label = "ПИНФЛ" if obj.person_type == "individual" else "ИНН"
        value = obj.number or "—"

        if getattr(obj, "number_repeat", False):
            return format_html("{} {} {}", label, value, _badge("повтор", "warning"))

        return format_html("{} {}", label, value)

    @admin.display(description="оферта")
    def offer(self, obj: Registration) -> str:
        if obj.offer_accepted_at is not None and obj.offer_signed_at is not None:
            return _badge("ознакомлен и подписал", "success")

        return _badge("нет", "danger")

    @admin.display(description="ознакомился с офертой")
    def offer_accepted(self, obj: Registration) -> str:
        return _offer(obj.offer_accepted_at)

    @admin.display(description="подписал заявление")
    def offer_signed(self, obj: Registration) -> str:
        return _offer(obj.offer_signed_at)

    @admin.display(description="язык")
    def language(self, obj: Registration) -> str:
        return LOCALES.get(obj.locale or "", obj.locale or "—")

    # ── Выгрузка ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "export/",
                self.admin_site.admin_view(self.export_view),
                name="ilmora_registration_export",
            ),
            *super().get_urls(),
        ]

    def export_view(self, request: HttpRequest) -> HttpResponse:
        """Список с отборами экрана в XLSX или CSV, право ilmora.export."""
        if not _admin_of(request).can("ilmora.export"):
            raise PermissionDenied

        from savdex import admin_export

        query = request.GET.copy()
        file_format = query.pop("format", ["xlsx"])[-1]
        request.GET = query  # type: ignore[assignment]
        records = self.get_changelist_instance(request).get_queryset(request)

        return admin_export.respond(
            request,
            section="ilmora",
            filename="ilmora-registrations",
            file_format="csv" if file_format == "csv" else "xlsx",
            columns=EXPORT,
            records=records.order_by("-created_at", "-id").iterator(),
        )

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        query = request.GET.urlencode()

        return super().changelist_view(
            request,
            {
                "can_export": _admin_of(request).can("ilmora.export"),
                "export_url": reverse("savdex_admin:ilmora_registration_export")
                + (f"?{query}" if query else ""),
                "export_sep": "&" if query else "?",
                **(extra_context or {}),
            },
        )
