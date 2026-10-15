"""
Обращения в поддержку в админке Django (этап 6) — вместо раздела Filament.

Очередь поддержки: по умолчанию только открытые, свежие сверху; отбор по
статусу, важности, «мои» и «ничьи». Раздел общий для всей поддержки —
«только своих» у него нет ни у одной роли (AdminAccess).

Как в Filament:

- «Взять» — ничьё обращение мне, открытое — сразу «В работе»;
- «Ответить» — ответ клиенту или внутренняя заметка одной формой с
  галочкой (раздельные кнопки означали бы, что однажды нажмут не ту и
  заметка уедет клиенту); ответ ставит «Ждёт ответа клиента» и уходит
  клиенту письмом (savdex/support/mail.py), заметка статус не трогает и
  никуда не уходит;
- письма на ящик поддержки становятся обращениями (тот же модуль),
  вложения скачиваются со страницы обращения;
- «Закрыть» и «Открыть снова»; дата закрытия — сама (Ticket::saving);
- удаление — в корзину, только суперадмин.

Своё: «Спам» (в обращении и над отмеченными) — обращение в корзину,
отправитель в спам-фильтр, его письма больше не становятся обращениями;
«Спам-фильтр» над очередью — список адресов и «Вернуть» (savdex/support/spam.py).

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
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
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
from savdex.laravel_storage import private_root
from savdex.support import mail as support_mail
from savdex.support import spam
from savdex.support.models import (
    CHANNELS,
    PRIORITIES,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_WAITING,
    STATUS_WORKING,
    STATUSES,
    BlockedSender,
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


def _size(value: Any) -> str:  # noqa: ANN401
    """Размер вложения: «340 КБ», «2,4 МБ»."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        return ""

    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} КБ"

    return f"{size / 1024 / 1024:.1f} МБ".replace(".", ",")


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
    change_list_template = "admin/support/ticket/change_list.html"

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
    actions = ("take_selected", "spam_selected")

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
        extra = {
            **(extra_context or {}),
            "spam_url": reverse("savdex_admin:support_ticket_spam_list"),
            "spam_count": BlockedSender.objects.count(),
        }

        return super().changelist_view(request, extra)

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

    def reply(
        self, request: HttpRequest, ticket: Ticket, body: str, *, internal: bool
    ) -> tuple[bool, str] | None:
        """
        Сообщение от поддержки. Ответ — «Ждёт ответа клиента» и письмо
        клиенту (savdex/support/mail.py): ушло ли и кому или почему нет.
        Внутренняя заметка статус не меняет и никуда не уходит — None.
        """
        before = self.snapshot(ticket)

        with transaction.atomic():
            message = Message(
                ticket_id=ticket.pk,
                author_id=_admin_of(request).id,
                from_staff=True,
                is_internal=internal,
                body=body,
            )
            message.save()
            ticket.last_reply_at = now()

            if not internal:
                ticket.status = STATUS_WAITING

            ticket.save()

        self._changed(
            request, ticket, before, note="Внутренняя заметка" if internal else "Ответ клиенту"
        )

        if internal:
            return None

        return support_mail.reply(ticket, message)

    def mark_spam(self, request: HttpRequest, ticket: Ticket) -> str | None:
        """«Спам»: обращение в корзину, отправитель в фильтр. Без почты — None."""
        email = support_mail.recipient(ticket)

        if not email:
            return None

        address = spam.normalized(email)
        blocked = spam.mark(ticket, address, _admin_of(request).id)
        audit.record(
            connections["default"],
            action="deleted",
            section=self.section,
            actor=_admin_of(request),
            subject_type=self.laravel_model,
            subject_id=ticket.pk,
            subject_label=ticket.subject,
            note=f"Спам: письма с {address} больше не становятся обращениями"
            if blocked
            else f"Спам ({address} уже в спам-фильтре)",
            ip=audit.client_ip(request),
        )

        return address

    @admin.action(
        description="Спам — убрать и не принимать письма отправителя", permissions=["take"]
    )
    def spam_selected(self, request: HttpRequest, queryset: QuerySet[Ticket]) -> None:
        tickets = list(queryset)
        done = [address for ticket in tickets if (address := self.mark_spam(request, ticket))]
        skipped = len(tickets) - len(done)

        if done:
            self.message_user(
                request,
                f"Убрано в спам: {len(done)}. Письма с этих адресов больше не станут "
                "обращениями — вернуть можно в «Спам-фильтре».",
                messages.SUCCESS,
            )

        if skipped:
            self.message_user(
                request,
                f"Без почты отправителя, не тронуто: {skipped}.",
                messages.WARNING,
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
                "spam/",
                self.admin_site.admin_view(self.spam_list_view),
                name="support_ticket_spam_list",
            ),
            path(
                "spam/release/",
                self.admin_site.admin_view(self.spam_release_view),
                name="support_ticket_spam_release",
            ),
            path(
                "<path:object_id>/spam/",
                self.admin_site.admin_view(self.spam_view),
                name="support_ticket_spam",
            ),
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
            path(
                "<path:object_id>/file/<int:message_id>/<int:number>/",
                self.admin_site.admin_view(self.file_view),
                name="support_ticket_file",
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

    def spam_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        ticket = self._one(request, object_id)
        address = self.mark_spam(request, ticket)

        if address is None:
            self.message_user(
                request, "У обращения нет почты отправителя — блокировать нечего.", messages.ERROR
            )

            return HttpResponseRedirect(
                reverse("savdex_admin:support_ticket_change", args=[ticket.pk])
            )

        self.message_user(
            request,
            f"Обращение убрано в спам. Письма с {address} больше не станут обращениями — "
            "вернуть можно в «Спам-фильтре».",
            messages.SUCCESS,
        )

        return HttpResponseRedirect(reverse("savdex_admin:support_ticket_changelist"))

    def spam_list_view(self, request: HttpRequest) -> HttpResponse:
        """Спам-фильтр: заблокированные адреса и «Вернуть»."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        senders = [
            {"sender": sender, "removed": spam.removed_count(sender.email)}
            for sender in BlockedSender.objects.select_related("blocked_by")
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": "Спам-фильтр",
            "opts": self.model._meta,
            "senders": senders,
            "can_release": self.has_edit(request),
        }

        return TemplateResponse(request, "admin/support/ticket/spam.html", context)

    def spam_release_view(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST" or not self.has_edit(request):
            raise PermissionDenied

        released = spam.release(request.POST.get("email", ""))

        if released is None:
            self.message_user(request, "Этого адреса в спам-фильтре уже нет.", messages.WARNING)
        else:
            audit.record(
                connections["default"],
                action="restored",
                section=self.section,
                actor=_admin_of(request),
                subject_label=released.email,
                note=f"Спам-фильтр: письма с {released.email} снова принимаются, "
                f"возвращено обращений: {released.tickets}",
                ip=audit.client_ip(request),
            )
            self.message_user(
                request,
                f"Письма с {released.email} снова принимаются. "
                f"Возвращено обращений: {released.tickets}.",
                messages.SUCCESS,
            )

        return HttpResponseRedirect(reverse("savdex_admin:support_ticket_spam_list"))

    def reply_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        ticket = self._one(request, object_id)
        body = (request.POST.get("body") or "").strip()
        internal = request.POST.get("is_internal") in ("1", "on", "true")

        if not body:
            self.message_user(request, "Напишите текст.", messages.ERROR)

            return HttpResponseRedirect(
                reverse("savdex_admin:support_ticket_change", args=[ticket.pk])
            )

        sent = self.reply(request, ticket, body, internal=internal)

        if sent is None:
            self.message_user(request, "Заметка сохранена.", messages.SUCCESS)
        elif sent[0]:
            self.message_user(request, f"Ответ отправлен клиенту на {sent[1]}.", messages.SUCCESS)
        else:
            self.message_user(
                request,
                f"Ответ записан, но письмо клиенту не ушло: {sent[1]}.",
                messages.WARNING,
            )

        return HttpResponseRedirect(reverse("savdex_admin:support_ticket_change", args=[ticket.pk]))

    def file_view(
        self, request: HttpRequest, object_id: str, message_id: int, number: int
    ) -> FileResponse:
        """Вложение письма клиента — скачивается, в браузере не открывается."""
        ticket = self.get_object(request, object_id)

        if not isinstance(ticket, Ticket) or not self.has_view_permission(request, ticket):
            raise PermissionDenied

        message = Message.objects.filter(pk=message_id, ticket_id=ticket.pk).first()
        files = message.attachments if message is not None else None

        if not isinstance(files, list) or not 0 <= number < len(files):
            raise Http404

        item = files[number]
        root = (private_root() / "support").resolve()
        target = (private_root() / str(item.get("path", ""))).resolve()

        if not target.is_relative_to(root) or not target.is_file():
            raise Http404

        return FileResponse(
            target.open("rb"),
            as_attachment=True,
            filename=str(item.get("name") or target.name),
            content_type="application/octet-stream",
        )

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

            for message in extra["ticket_messages"]:
                files = message.attachments if isinstance(message.attachments, list) else []
                message.files = [
                    {
                        "name": item.get("name") or "файл",
                        "size": _size(item.get("size")),
                        "url": reverse(
                            "savdex_admin:support_ticket_file", args=[ticket.pk, message.pk, n]
                        ),
                    }
                    for n, item in enumerate(files)
                    if isinstance(item, dict)
                ]

            extra["client_email"] = support_mail.recipient(ticket)
            extra["can_spam"] = editable and bool(extra["client_email"])
            extra["can_take"] = editable and ticket.assignee_id is None
            extra["can_reply"] = editable
            extra["can_toggle"] = editable
            extra["ticket_closed"] = ticket.is_closed

        return super().change_view(request, object_id, form_url, extra)
