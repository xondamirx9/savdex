"""
Журнал действий в админке Django (этап 6) — вместо раздела Filament.

Только чтение: ни создать, ни изменить, ни удалить — журнал, который
можно подчистить, защищает ровно до того момента, когда он понадобится.
Свежее сверху; отборы по разделу, действию, сотруднику и «за сегодня»,
поиск по сотруднику и по тому, с чем действовали. Страница записи —
«что изменилось»: поле, было, стало (AdminLog::readable).
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.timesince import timesince

from savdex import access
from savdex.adminsite import SavdexModelAdmin, register
from savdex.crm.admin import _badge, when
from savdex.journal.models import ACTIONS, AdminAction
from savdex.text import numeric

#: AdminActionsTable::TONE
ACTION_TONES = {
    "created": "success",
    "approved": "success",
    "unblocked": "success",
    "restored": "success",
    "deleted": "danger",
    "force_deleted": "danger",
    "rejected": "danger",
    "blocked": "danger",
    "revoked": "danger",
    "returned": "warning",
    "hidden": "warning",
    "granted": "info",
    "exported": "info",
    "downloaded": "info",
    "imported": "info",
    "refunded": "warning",
    "paid": "success",
    "sent": "info",
}


def readable(value: Any) -> str:  # noqa: ANN401
    """AdminLog::readable: пусто, да/нет, массив — JSON."""
    if value is None:
        return "—"

    if value == "":
        return "(пусто)"

    if isinstance(value, bool):
        return "да" if value else "нет"

    if isinstance(value, dict | list):
        # json_encode(…, JSON_UNESCAPED_UNICODE): без пробелов, «/» — «\/»
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("/", "\\/")

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


class SectionFilter(admin.SimpleListFilter):
    title = "раздел"
    parameter_name = "section"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(access.SECTIONS.items())

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[AdminAction]
    ) -> QuerySet[AdminAction]:
        return queryset.filter(section=self.value()) if self.value() else queryset


class StaffFilter(admin.SimpleListFilter):
    """Сотрудник — из тех, кто есть в журнале (имя — последнее записанное)."""

    title = "сотрудник"
    parameter_name = "user"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        rows = (
            AdminAction.objects.filter(user_id__isnull=False)
            .order_by("user_id", "-id")
            .distinct("user_id")
            .values_list("user_id", "user_name")
        )

        return sorted(((str(pk), name) for pk, name in rows), key=lambda row: row[1])

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[AdminAction]
    ) -> QuerySet[AdminAction]:
        value = self.value()

        return queryset.filter(user_id=int(value)) if value and numeric(value) else queryset


class Today(admin.SimpleListFilter):
    title = "когда"
    parameter_name = "today"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Только за сегодня")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[AdminAction]
    ) -> QuerySet[AdminAction]:
        if self.value() != "1":
            return queryset

        # Сутки по часовому поясу админки (у Filament whereDate — по UTC)
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

        return queryset.filter(created_at__gte=start, created_at__lt=start + timedelta(days=1))


@register(AdminAction, section="audit")
class AdminActionAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\AdminAction"
    title_list = "Журнал действий"
    title_change = "Что изменилось"

    list_display = ("moment", "who", "what", "where", "subject", "wording")
    list_display_links = ("moment",)
    list_filter = (SectionFilter, "action", StaffFilter, Today)
    search_fields = ("user_name", "subject_label")
    ordering = ("-created_at", "-id")
    list_per_page = 50
    # Журнал большой: без второго подсчёта всех строк на каждой странице
    show_full_result_count = False

    fields = ("moment", "who", "what", "where", "subject", "wording", "ip", "diff")
    readonly_fields = fields

    # ── Только чтение ──

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    # ── Столбцы ──

    @admin.display(description="когда", ordering="created_at")
    def moment(self, obj: AdminAction) -> str:
        return format_html(
            "{}<br><small>{} назад</small>",
            when(obj.created_at),
            timesince(obj.created_at, depth=1),
        )

    @admin.display(description="кто", ordering="user_name")
    def who(self, obj: AdminAction) -> str:
        # Роль на момент действия, а не нынешняя: вопрос всегда про тогда
        role = access.ROLES.get(obj.user_role or "", obj.user_role or "")

        return format_html("{}<br><small>{}</small>", obj.user_name, role)

    @admin.display(description="что сделал", ordering="action")
    def what(self, obj: AdminAction) -> str:
        return _badge(ACTIONS.get(obj.action, obj.action), ACTION_TONES.get(obj.action, "gray"))

    @admin.display(description="раздел", ordering="section")
    def where(self, obj: AdminAction) -> str:
        return access.SECTIONS.get(obj.section, obj.section)

    @admin.display(description="с чем")
    def subject(self, obj: AdminAction) -> str:
        return obj.subject_label or "—"

    @admin.display(description="формулировка")
    def wording(self, obj: AdminAction) -> str:
        return obj.note or "—"

    @admin.display(description="что изменилось")
    def diff(self, obj: AdminAction) -> str:
        changes = obj.changes if isinstance(obj.changes, dict) else {}
        before = changes.get("before") or {}
        after = changes.get("after") or {}
        fields = [*before, *(k for k in after if k not in before)]

        if not fields:
            return "—"

        rows = format_html_join(
            "",
            "<tr><td><code>{}</code></td><td>{}</td><td><b>{}</b></td></tr>",
            ((f, readable(before.get(f)), readable(after.get(f))) for f in fields),
        )

        return format_html(
            "<table><thead><tr><th>Поле</th><th>Было</th><th>Стало</th></tr></thead>"
            "<tbody>{}</tbody></table>",
            rows,
        )
