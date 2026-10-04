"""
Обращения в поддержку в админке Django (этап 6) — вместо раздела Filament.

Очередь поддержки: по умолчанию только открытые, свежие сверху; отбор по
статусу, важности, «мои» и «ничьи». Раздел общий для всей поддержки —
«только своих» у него нет ни у одной роли (AdminAccess).

Как в Filament:

- «Взять» — ничьё обращение мне, открытое — сразу «В работе»;
- «Ответить» — ответ клиенту или внутренняя заметка одной формой с
  галочкой (раздельные кнопки означали бы, что однажды нажмут не ту и
  заметка уедет клиенту); ответ ставит «Ждёт ответа клиента», заметка
  статус не трогает — клиент ничего не получил;
- «Закрыть» и «Открыть снова»; дата закрытия — сама (Ticket::saving);
- удаление — в корзину, только суперадмин.

Отличия: переписка видна на странице обращения (у Filament её не было
видно нигде), и ответ пишет в журнал одну строку — с изменениями и
пометкой «Ответ клиенту» или «Внутренняя заметка» (у Filament две:
наблюдатель и пометка отдельно).
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connections, transaction
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timesince import timesince

from savdex import audit
from savdex.accounts.models import User
from savdex.adminsite import PerRequest, _admin_of, register
from savdex.catalog import now
from savdex.crm.admin import TONES, CrmAdmin, OpenFilter, _badge, employees, when
from savdex.crm.models import Company
from savdex.support.models import (
    CHANNELS,
    PRIORITIES,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_WAITING,
    STATUS_WORKING,
    STATUSES,
    Message,
    Ticket,
)

#: TicketsTable::TONE
STATUS_TONES = {
    STATUS_OPEN: "warning",
    STATUS_WORKING: "info",
    STATUS_WAITING: "gray",
    STATUS_CLOSED: "success",
}

PRIORITY_TONES = {"high": "danger", "low": "gray"}


class TicketForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = Ticket
        fields = (
            "subject",
            "status",
            "priority",
            "channel",
            "assignee",
            "user",
            "company",
            "author_name",
            "author_email",
        )


class TicketOpen(OpenFilter):
    title = "открытые"
    open_label = "Только открытые"
    open_q = ~Q(status=STATUS_CLOSED)


class TicketWho(admin.SimpleListFilter):
    title = "кто ведёт"
    parameter_name = "who"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("mine", "Мои"), ("none", "Ничьи")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Ticket]) -> QuerySet[Ticket]:
        if self.value() == "mine":
            return queryset.filter(assignee_id=_admin_of(request).id)

        if self.value() == "none":
            return queryset.filter(assignee__isnull=True)

        return queryset


@register(Ticket, section="support")
class TicketAdmin(CrmAdmin):
    laravel_model = "App\\Models\\Support\\Ticket"
    title_list = "Обращения"
    title_add = "Завести обращение"
    title_change = "Обращение"
    change_form_template = "admin/support/ticket/change_form.html"

    form = TicketForm
    fieldsets = (
        ("Обращение", {"fields": ("subject", "status", "priority", "channel", "assignee")}),
        (
            "Кто обратился",
            {
                "fields": ("user", "company", "author_name", "author_email"),
                "description": "Обращение бывает и от того, кто не смог войти, — "
                "тогда заполняются имя и почта",
            },
        ),
    )
    list_display = ("topic", "who", "importance", "state", "assignee_name", "count", "arrived")
    list_filter = (TicketOpen, "status", "priority", TicketWho)
    list_select_related = ("user", "company", "assignee")
    search_fields = ("subject", "author_name")
    ordering = ("-created_at", "-id")
    actions = ("take_selected",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Ticket]:
        queryset: QuerySet[Ticket] = super().get_queryset(request)

        return queryset.annotate(messages_count=Count("messages"))

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        if db_field.name == "assignee":
            field = forms.ModelChoiceField(
                queryset=User.objects.filter(pk__in=employees("support.view")).order_by(
                    "name", "id"
                ),
                required=False,
                label="Кто ведёт",
                empty_label="Не назначен — виден всей поддержке",
            )
            field.label_from_instance = lambda obj: obj.name  # type: ignore[method-assign]

            return field

        if db_field.name == "user":
            field = forms.ModelChoiceField(
                queryset=User.objects.filter(deleted_at__isnull=True).order_by("email", "id"),
                required=False,
                label="Пользователь",
            )
            field.label_from_instance = lambda obj: obj.email  # type: ignore[method-assign]

            return field

        if db_field.name == "company":
            kwargs["queryset"] = Company.objects.filter(deleted_at__isnull=True).order_by(
                "name", "id"
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # ── Список ──

    @admin.display(description="тема", ordering="subject")
    def topic(self, obj: Ticket) -> str:
        return format_html(
            "{}<br><small>{}</small>", obj.subject, CHANNELS.get(obj.channel, obj.channel)
        )

    @admin.display(description="кто")
    def who(self, obj: Ticket) -> str:
        return format_html("{}<br><small>{}</small>", obj.author(), self.company_label(obj.company))

    @admin.display(description="важность", ordering="priority")
    def importance(self, obj: Ticket) -> str:
        return _badge(
            PRIORITIES.get(obj.priority, obj.priority), PRIORITY_TONES.get(obj.priority, "info")
        )

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Ticket) -> str:
        return _badge(STATUSES.get(obj.status, obj.status), STATUS_TONES.get(obj.status, "gray"))

    @admin.display(description="ведёт", ordering="assignee__name")
    def assignee_name(self, obj: Ticket) -> str:
        if obj.assignee is not None:
            return str(obj.assignee.name)

        if self._can_take:
            return format_html(
                '<button type="submit" class="button" formaction="{}" formmethod="post">'
                "Взять</button>",
                reverse("savdex_admin:support_ticket_take", args=[obj.pk]),
            )

        return format_html('<span style="color:{}">не назначен</span>', TONES["gray"])

    @admin.display(description="сообщений")
    def count(self, obj: Ticket) -> int:
        return int(getattr(obj, "messages_count", 0))

    @admin.display(description="пришло", ordering="created_at")
    def arrived(self, obj: Ticket) -> str:
        if obj.created_at is None:
            return ""

        return format_html(
            "{}<br><small>{} назад</small>",
            when(obj.created_at),
            timesince(obj.created_at, depth=1),
        )

    _can_take = PerRequest()

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        # Кнопка «Взять» в строке — только с правом правки
        self._can_take = self.has_edit(request)

        return super().changelist_view(request, extra_context)

    # ── Взять, ответить, закрыть ──

    def has_edit(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("support.edit")

    def has_take_permission(self, request: HttpRequest) -> bool:
        return self.has_edit(request)

    def _changed(
        self, request: HttpRequest, ticket: Ticket, before: dict[str, Any], note: str | None = None
    ) -> None:
        """Строка «изменено»: только то, что поменялось, и пометка."""
        after = self.snapshot(ticket)
        changed = {k: v for k, v in after.items() if before.get(k) != v and k not in audit.NOISE}

        if not changed and note is None:
            return

        audit.record(
            connections["default"],
            action="updated",
            section=self.section,
            actor=_admin_of(request),
            subject_type=self.laravel_model,
            subject_id=ticket.pk,
            subject_label=ticket.subject,
            changes={"before": {k: before.get(k) for k in changed}, "after": changed}
            if changed
            else None,
            note=note,
            ip=audit.client_ip(request),
        )

    def take(self, request: HttpRequest, ticket: Ticket) -> bool:
        """«Взять»: ничьё — мне, открытое — «В работе»."""
        if ticket.assignee_id is not None:
            return False

        before = self.snapshot(ticket)
        ticket.assignee_id = _admin_of(request).id

        if ticket.status == STATUS_OPEN:
            ticket.status = STATUS_WORKING

        ticket.save()
        self._changed(request, ticket, before)

        return True

    def toggle(self, request: HttpRequest, ticket: Ticket) -> None:
        """«Закрыть» и «Открыть снова» (в работу)."""
        before = self.snapshot(ticket)
        ticket.status = STATUS_WORKING if ticket.is_closed else STATUS_CLOSED
        ticket.save()
        self._changed(request, ticket, before)

    def reply(self, request: HttpRequest, ticket: Ticket, body: str, *, internal: bool) -> None:
        """
        Сообщение от поддержки. Ответ — «Ждёт ответа клиента»; внутренняя
        заметка статус не меняет: клиент ничего не получил.
        """
        before = self.snapshot(ticket)

        with transaction.atomic():
            Message(
                ticket_id=ticket.pk,
                author_id=_admin_of(request).id,
                from_staff=True,
                is_internal=internal,
                body=body,
            ).save()
            ticket.last_reply_at = now()

            if not internal:
                ticket.status = STATUS_WAITING

            ticket.save()

        self._changed(
            request, ticket, before, note="Внутренняя заметка" if internal else "Ответ клиенту"
        )

    @admin.action(description="Взять себе", permissions=["take"])
    def take_selected(self, request: HttpRequest, queryset: QuerySet[Ticket]) -> None:
        done = sum(self.take(request, ticket) for ticket in queryset)
        self.message_user(
            request,
            f"Закреплено за вами: {done}." if done else "Ничьих среди отмеченных нет.",
            messages.SUCCESS if done else messages.WARNING,
        )

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/take/",
                self.admin_site.admin_view(self.take_view),
                name="support_ticket_take",
            ),
            path(
                "<path:object_id>/toggle/",
                self.admin_site.admin_view(self.toggle_view),
                name="support_ticket_toggle",
            ),
            path(
                "<path:object_id>/reply/",
                self.admin_site.admin_view(self.reply_view),
                name="support_ticket_reply",
            ),
            *super().get_urls(),
        ]

    def _one(self, request: HttpRequest, object_id: str) -> Ticket:
        if request.method != "POST" or not self.has_edit(request):
            raise PermissionDenied

        ticket = self.get_object(request, object_id)

        if not isinstance(ticket, Ticket) or not self.has_change_permission(request, ticket):
            raise PermissionDenied

        return ticket

    def _back(self, request: HttpRequest, ticket: Ticket) -> HttpResponse:
        """Туда, откуда нажали: в очередь с её отбором или в обращение."""
        back = request.headers.get("Referer", "")

        if not url_has_allowed_host_and_scheme(
            back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            back = reverse("savdex_admin:support_ticket_change", args=[ticket.pk])

        return HttpResponseRedirect(back)

    def take_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        ticket = self._one(request, object_id)

        if self.take(request, ticket):
            self.message_user(request, "Обращение закреплено за вами.", messages.SUCCESS)

        return self._back(request, ticket)

    def toggle_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        ticket = self._one(request, object_id)
        self.toggle(request, ticket)
        self.message_user(request, "Статус изменён.", messages.SUCCESS)

        return self._back(request, ticket)

    def reply_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        ticket = self._one(request, object_id)
        body = (request.POST.get("body") or "").strip()
        internal = request.POST.get("is_internal") in ("1", "on", "true")

        if not body:
            self.message_user(request, "Напишите текст.", messages.ERROR)

            return HttpResponseRedirect(
                reverse("savdex_admin:support_ticket_change", args=[ticket.pk])
            )

        self.reply(request, ticket, body, internal=internal)
        self.message_user(
            request, "Заметка сохранена." if internal else "Ответ записан.", messages.SUCCESS
        )

        return HttpResponseRedirect(reverse("savdex_admin:support_ticket_change", args=[ticket.pk]))

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        ticket = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(ticket, Ticket) and self.has_view_permission(request, ticket):
            editable = self.has_edit(request) and self.has_change_permission(request, ticket)
            extra["ticket_messages"] = list(
                Message.objects.filter(ticket_id=ticket.pk)
                .select_related("author")
                .order_by("created_at", "id")
            )
            extra["can_take"] = editable and ticket.assignee_id is None
            extra["can_reply"] = editable
            extra["can_toggle"] = editable
            extra["ticket_closed"] = ticket.is_closed

        return super().change_view(request, object_id, form_url, extra)
