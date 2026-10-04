"""
Система в админке Django (этап 6) — вместо разделов Filament группы
«Система».

Рассылки: черновик правится, пока не отправлен; «Отправить» — отдельной
кнопкой со вторым подтверждением и точным числом получателей: уведомление
уходит тысячам людей, и отозвать его нельзя. Охват сегмента виден до
отправки. Удаление — с правом удалять.
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

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.system import broadcasts
from savdex.system.models import Broadcast
from savdex.text import plural


def _plans() -> list[tuple[str, str]]:
    from savdex.billing.models import Plan

    return [(plan.code, plan.name) for plan in Plan.objects.order_by("sort", "id")]


class BroadcastForm(forms.ModelForm):  # type: ignore[type-arg]
    audience_value = forms.ChoiceField(label="Тариф", required=False)

    class Meta:
        model = Broadcast
        fields = ("title", "body", "url", "tone", "audience", "audience_value")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if "audience_value" in self.fields:
            field = self.fields["audience_value"]
            assert isinstance(field, forms.ChoiceField)
            field.choices = [("", "—"), *_plans()]
            field.help_text = "Только для получателей «Компании на тарифе»"

        # У отправленной рассылки и у роли «только чтение» текст — не поле формы
        if "body" in self.fields:
            self.fields["body"].widget = forms.Textarea(attrs={"rows": 4})

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        if data.get("audience") == "plan":
            if not data.get("audience_value"):
                self.add_error("audience_value", "Выберите тариф.")
        else:
            data["audience_value"] = None

        return data


@register(Broadcast, section="broadcasts")
class BroadcastAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Broadcast"
    title_list = "Рассылки"
    title_add = "Новая рассылка"
    title_change = "Рассылка"
    change_form_template = "admin/system/broadcast/change_form.html"

    form = BroadcastForm
    fieldsets = (
        ("Сообщение", {"fields": ("title", "body", "url", "tone")}),
        ("Кому", {"fields": ("audience", "audience_value")}),
    )
    list_display = ("message", "whom", "recipients_count", "sent", "author")
    list_select_related = ("sent_by",)
    search_fields = ("title",)
    ordering = ("-created_at", "-id")
    actions = ("delete_selected",)

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return super(SavdexModelAdmin, self).get_actions(request)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        # Отправленную править бессмысленно: уведомления уже живут своей жизнью
        if isinstance(obj, Broadcast) and obj.sent_at is not None:
            return False

        return super().has_change_permission(request, obj)

    @admin.display(description="заголовок", ordering="title")
    def message(self, obj: Broadcast) -> str:
        body = obj.body if len(obj.body) <= 80 else obj.body[:80].rstrip() + "..."

        return format_html("{}<br><small>{}</small>", obj.title, body)

    @admin.display(description="кому", ordering="audience")
    def whom(self, obj: Broadcast) -> str:
        return obj.audience_label()

    @admin.display(description="отправлена", ordering="sent_at")
    def sent(self, obj: Broadcast) -> str:
        return (
            timezone.localtime(obj.sent_at).strftime("%d.%m.%Y %H:%M")
            if obj.sent_at
            else "черновик"
        )

    @admin.display(description="автор")
    def author(self, obj: Broadcast) -> str:
        return obj.sent_by.name if obj.sent_by is not None else "—"

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/send/",
                self.admin_site.admin_view(self.send_view),
                name="system_broadcast_send",
            ),
            *super().get_urls(),
        ]

    def send_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        broadcast = self.get_object(request, object_id)

        if (
            request.method != "POST"
            or not isinstance(broadcast, Broadcast)
            or broadcast.sent_at is not None
            or not self.has_change_permission(request, broadcast)
        ):
            raise PermissionDenied

        sent = broadcasts.send(broadcast, _admin_of(request).id)

        if sent is None:
            messages.warning(request, "Рассылка уже отправлена.")
        else:
            # Отправка — в журнал: кто, кому и сколько получили
            self.journal(
                request,
                "sent",
                broadcast,
                {"after": {"получателей": sent, "аудитория": broadcast.audience}},
            )
            messages.success(
                request,
                "Рассылка отправлена: "
                + plural(sent, "получатель", "получателя", "получателей")
                + ".",
            )

        return HttpResponseRedirect(reverse("savdex_admin:system_broadcast_changelist"))

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        broadcast = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(broadcast, Broadcast):
            extra["recipients"] = broadcasts.count_recipients(
                broadcast.audience, broadcast.audience_value
            )
            extra["can_send"] = broadcast.sent_at is None and self.has_change_permission(
                request, broadcast
            )

        return super().change_view(request, object_id, form_url, extra)
