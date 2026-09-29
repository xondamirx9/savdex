"""
Данные площадки в админке Django (этап 6) — вместо разделов Filament
группы «Данные».

IT-задачи: список с отбором по статусу и виду услуги, правка (создаются
только из кабинета — задача от имени заказчика), «Снять» с витрины для
спама и нарушений (заказчик увидит её в кабинете архивной), «На сайте» у
открытой, удаление — с правом удалять.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex.adminsite import SavdexModelAdmin, register
from savdex.crm.admin import _badge
from savdex.data.models import IT_STATUSES, SERVICE_TYPES, ItTask


class StackField(forms.CharField):
    """TagsInput: теги через запятую — список в JSON."""

    def prepare_value(self, value: Any) -> Any:  # noqa: ANN401
        if isinstance(value, list):
            return ", ".join(str(tag) for tag in value)

        return value

    def to_python(self, value: Any) -> Any:  # noqa: ANN401
        text = super().to_python(value) or ""
        tags = [tag.strip() for tag in str(text).split(",") if tag.strip()]

        return tags or None


class ItTaskForm(forms.ModelForm):  # type: ignore[type-arg]
    stack = StackField(label="Стек", required=False, help_text="Через запятую: Laravel, React…")

    class Meta:
        model = ItTask
        fields = (
            "title",
            "description",
            "service_type",
            "stack",
            "budget_type",
            "budget_from",
            "budget_to",
            "currency",
            "deadline_at",
            "status",
        )

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        for name in ("budget_from", "budget_to"):
            value = data.get(name)

            if value is not None and value < 0:
                self.add_error(name, "Не меньше нуля.")

        return data


class ItStatus(admin.SimpleListFilter):
    title = "статус"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(IT_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(status=self.value()) if self.value() else queryset


class ServiceType(admin.SimpleListFilter):
    title = "вид услуги"
    parameter_name = "service"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(SERVICE_TYPES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(service_type=self.value()) if self.value() else queryset


@register(ItTask, section="ittasks")
class ItTaskAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\ItTask"
    title_list = "IT-задачи"
    title_change = "IT-задача"

    form = ItTaskForm
    fieldsets = (
        ("Задача", {"fields": ("title", "description", "service_type", "stack")}),
        (
            "Условия",
            {"fields": ("budget_type", "budget_from", "budget_to", "currency", "deadline_at")},
        ),
        ("Статус", {"fields": ("status",)}),
    )
    list_display = ("task", "service", "responses_count", "state", "published", "row_actions")
    list_filter = (ItStatus, ServiceType)
    list_select_related = ("company",)
    search_fields = ("title",)
    ordering = ("-created_at", "-id")
    list_per_page = 50
    actions = ("delete_selected",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Задача — от имени заказчика: заводится только в кабинете
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление — как DeleteBulkAction: только с правом удалять
        return super(SavdexModelAdmin, self).get_actions(request)

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Поиск и просмотры — не правка администратора: в журнал не идут."""
        attributes = self.attributes(obj)

        for column in ("search_text", "views_count"):
            attributes.pop(column, None)

        return attributes

    @admin.display(description="задача", ordering="title")
    def task(self, obj: ItTask) -> str:
        title = obj.title if len(obj.title) <= 80 else obj.title[:80].rstrip() + "..."
        company = obj.company

        return format_html(
            "{}<br><small>{}</small>",
            title,
            company.name if company is not None and company.deleted_at is None else "",
        )

    @admin.display(description="вид услуги", ordering="service_type")
    def service(self, obj: ItTask) -> str:
        return SERVICE_TYPES.get(obj.service_type, obj.service_type)

    @admin.display(description="статус", ordering="status")
    def state(self, obj: ItTask) -> str:
        return _badge(
            IT_STATUSES.get(obj.status, obj.status), "success" if obj.status == "active" else "gray"
        )

    @admin.display(description="опубликована", ordering="published_at")
    def published(self, obj: ItTask) -> str:
        return timezone.localtime(obj.published_at).strftime("%d.%m.%Y") if obj.published_at else ""

    @admin.display(description="")
    def row_actions(self, obj: ItTask) -> str:
        """«На сайте» и «Снять» — у открытой задачи."""
        if obj.status != "active":
            return ""

        link = (
            format_html(
                '<a href="/it-services/{}" target="_blank" rel="noopener">На сайте</a> ', obj.slug
            )
            if obj.slug
            else ""
        )
        button = (
            format_html(
                '<button type="submit" class="button" formaction="{}" formmethod="post" '
                "onclick=\"return confirm('Снять задачу с витрины? Заказчик увидит её в кабинете "
                "архивной.')\">Снять</button>",
                reverse("savdex_admin:data_ittask_archive", args=[obj.pk]),
            )
            if self._can_archive
            else ""
        )

        return format_html("{}{}", link, button)

    _can_archive = False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_archive = self.has_change_permission(request)

        return super().changelist_view(request, extra_context)

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/archive/",
                self.admin_site.admin_view(self.archive_view),
                name="data_ittask_archive",
            ),
            *super().get_urls(),
        ]

    def archive_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """«Снять»: в архив и дата закрытия — для спама и нарушений."""
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied

        task = self.get_object(request, object_id)

        if not isinstance(task, ItTask):
            raise PermissionDenied

        if task.status == "active":
            before = self.snapshot(task)
            task.status = "archived"
            task.closed_at = timezone.now().replace(microsecond=0)
            task.save()
            after = self.snapshot(task)
            changed = {k: v for k, v in after.items() if before.get(k) != v}
            self.journal(
                request,
                "updated",
                task,
                {"before": {k: before.get(k) for k in changed}, "after": changed},
            )
            messages.success(request, "Задача снята с витрины.")

        return HttpResponseRedirect(reverse("savdex_admin:data_ittask_changelist"))
