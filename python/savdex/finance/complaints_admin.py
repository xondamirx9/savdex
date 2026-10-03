"""
«Жалобы на контакты» в админке Django (этап 7, шаг 59) — вместо страницы
Filament Complaints; решения — копия ModerationService::acceptComplaint
и ::declineComplaint.

Покупатель платит кредит за контакт и получает обещание: «проверим и
вернём, если контакт нерабочий». У раскрытия ровно два решения —
вернуть или отказать, формы правки и создания нет.

- «Вернуть списанное»: кредит — обратно в кошелёк (Wallet::grant,
  «complaint_refund»), контакт по тарифу (ничего не списано) — в месячный
  лимит; дважды не возвращается (refunded). Сам контакт остаётся открытым;
- «Отказать» — с объяснением.

Формулировка решения — от 15 знаков: компания видит её как ответ.
Уведомление компании, строка журнала «refunded» или «rejected» с
пометкой — как у Laravel (наблюдателя у ContactUnlock нет).

Отличие от Filament: решения — с правом complaints.edit. У Filament
кнопки видел любой, кто открыл раздел, и поддержка (раздел у неё только
на просмотр) могла вернуть кредит.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex import access, audit
from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.admin import OpenFilter, _badge
from savdex.finance.models import COMPLAINT_STATUSES, Complaint
from savdex.finance.refunds_admin import _limit
from savdex.guards import allowed_writes
from savdex.moderation.services import context_of
from savdex.web import eloquent, settlement, ui
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _notify_company, _stamp
from savdex.web.shared import Context

STATUS_TONES = {"pending": "warning", "accepted": "success"}


def _log(ctx: Context, actor: access.Admin, action: str, unlock: dict[str, Any], note: str) -> None:
    audit.record(
        connection,
        action=action,
        section="complaints",
        actor=actor,
        subject_type="App\\Models\\ContactUnlock",
        subject_id=unlock["id"],
        subject_label=audit.label(unlock, "ContactUnlock", unlock["id"]),
        changes=None,
        note=note,
        ip=audit.client_ip(ctx.request),
    )


def _company(company_id: int) -> dict[str, Any] | None:
    rows = _rows("select * from companies where id = %s and deleted_at is null", [company_id])

    return rows[0] if rows else None


def accept(ctx: Context, actor: access.Admin, unlock: dict[str, Any], note: str) -> None:
    """ModerationService::acceptComplaint."""
    company = _company(unlock["company_id"])

    with transaction.atomic():
        wallets = (
            _rows("select * from wallets where company_id = %s limit 1", [company["id"]])
            if company is not None
            else []
        )

        if wallets and not unlock["refunded"]:
            wallet = wallets[0]

            if unlock["credits_spent"] > 0:
                settlement.grant(
                    wallet,
                    "credits",
                    int(unlock["credits_spent"]),
                    "complaint_refund",
                    ("ContactUnlock", unlock["id"]),
                    actor.id,
                )
            elif wallet["contacts_used_this_period"] > 0:
                # Model::decrement — с updated_at, без событий
                with allowed_writes("wallets"), connection.cursor() as cursor:
                    cursor.execute(
                        "update wallets set contacts_used_this_period = "
                        "contacts_used_this_period - 1, updated_at = %s where id = %s",
                        [_stamp(eloquent.now()), wallet["id"]],
                    )

        eloquent.save(
            ctx,
            "contact_unlocks",
            unlock,
            {
                "complaint_status": "accepted",
                "refunded": True,
                "moderator_note": note,
                "moderated_by": actor.id,
                "moderated_at": eloquent.now(),
            },
            section=None,
            model="ContactUnlock",
            casts={"refunded": "bool", "credits_spent": "int"},
        )

    if company is not None:
        _notify_company(
            ctx,
            company,
            "moderation",
            lambda locale: ui.t("messages.complaint.accepted_notice", locale),
            "success",
            "/cabinet/contacts",
            note,
        )

    _log(ctx, actor, "refunded", unlock, note)


def decline(ctx: Context, actor: access.Admin, unlock: dict[str, Any], note: str) -> None:
    """ModerationService::declineComplaint."""
    eloquent.save(
        ctx,
        "contact_unlocks",
        unlock,
        {
            "complaint_status": "declined",
            "moderator_note": note,
            "moderated_by": actor.id,
            "moderated_at": eloquent.now(),
        },
        section=None,
        model="ContactUnlock",
        casts={"refunded": "bool", "credits_spent": "int"},
    )
    company = _company(unlock["company_id"])

    if company is not None:
        _notify_company(
            ctx,
            company,
            "moderation",
            lambda locale: ui.t("messages.complaint.declined_notice", locale),
            "warning",
            "/cabinet/contacts",
            note,
        )

    _log(ctx, actor, "rejected", unlock, note)


class NoteForm(forms.Form):
    note = forms.CharField(
        label="Формулировка решения", min_length=15, widget=forms.Textarea(attrs={"rows": 3})
    )


class Pending(OpenFilter):
    title = "ждут решения"
    open_label = "Ждут решения"
    all_label = "Все жалобы"
    open_q = Q(complaint_status="pending")


class StatusFilter(admin.SimpleListFilter):
    title = "решение"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(COMPLAINT_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Complaint]) -> QuerySet[Complaint]:
        return queryset.filter(complaint_status=self.value()) if self.value() else queryset


@register(Complaint, section="complaints")
class ComplaintAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\ContactUnlock"
    title_list = "Жалобы на контакты"

    list_display = ("who", "reason", "spent", "state", "filed")
    list_filter = (Pending, StatusFilter)
    list_select_related = ("company", "target_company", "moderated_by")
    search_fields = ("company__name",)
    ordering = ("-complained_at", "-id")
    list_per_page = 50
    list_display_links = None

    def get_queryset(self, request: HttpRequest) -> QuerySet[Complaint]:
        queryset: QuerySet[Complaint] = super().get_queryset(request)

        return queryset.filter(complaint_status__isnull=False)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_decide(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("complaints.edit")

    # ── Список ──

    @admin.display(description="жалуется", ordering="company__name")
    def who(self, obj: Complaint) -> str:
        target = obj.target_company
        name = target.name if target.deleted_at is None else "компания удалена"

        return format_html("{}<br><small>на: {}</small>", obj.company.name, name)

    @admin.display(description="суть жалобы")
    def reason(self, obj: Complaint) -> str:
        return _limit(obj.complaint_reason or "", 160)

    @admin.display(description="списано")
    def spent(self, obj: Complaint) -> str:
        # Ноль — не «бесплатно», а «из месячного лимита тарифа»
        return f"{obj.credits_spent} кред." if obj.credits_spent > 0 else "из лимита тарифа"

    @admin.display(description="решение", ordering="complaint_status")
    def state(self, obj: Complaint) -> str:
        status = obj.complaint_status or ""
        badge = _badge(COMPLAINT_STATUSES.get(status, "Отказано"), STATUS_TONES.get(status, "gray"))
        who = obj.moderated_by.name if obj.moderated_by is not None else ""
        buttons = ""

        if status == "pending" and self._can_decide:
            buttons = format_html(
                '<br><a class="button" href="{}">Вернуть списанное</a> '
                '<a class="button" href="{}">Отказать</a>',
                reverse("savdex_admin:finance_complaint_accept", args=[obj.pk]),
                reverse("savdex_admin:finance_complaint_decline", args=[obj.pk]),
            )

        return format_html("{}<br><small>{}</small>{}", badge, who, buttons)

    @admin.display(description="подана", ordering="complained_at")
    def filed(self, obj: Complaint) -> str:
        moment = obj.complained_at

        return timezone.localtime(moment).strftime("%d.%m.%Y %H:%M") if moment else ""

    _can_decide = False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_decide = self.has_decide(request)

        return super().changelist_view(request, extra_context)

    # ── Решения ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/accept/",
                self.admin_site.admin_view(self.accept_view),
                name="finance_complaint_accept",
            ),
            path(
                "<path:object_id>/decline/",
                self.admin_site.admin_view(self.decline_view),
                name="finance_complaint_decline",
            ),
            *super().get_urls(),
        ]

    def _decide(self, request: HttpRequest, object_id: str, *, accepted: bool) -> HttpResponse:
        if not self.has_decide(request):
            raise PermissionDenied

        rows = _rows(
            "select * from contact_unlocks where id = %s and complaint_status = 'pending'",
            [int(object_id)],
        )
        back = reverse("savdex_admin:finance_complaint_changelist")

        if not rows:
            self.message_user(request, "Решение по жалобе уже принято.", messages.WARNING)

            return HttpResponseRedirect(back)

        form = NoteForm(request.POST or None)

        if accepted:
            form.fields["note"].help_text = "Компания увидит это как ответ на жалобу."
        else:
            form.fields[
                "note"
            ].help_text = "Отказ без причины покупатель прочитает как «деньги забрали молча»."

        if request.method == "POST" and form.is_valid():
            ctx = context_of(request)
            decide = accept if accepted else decline
            decide(ctx, _admin_of(request), rows[0], form.cleaned_data["note"])
            self.message_user(
                request,
                "Списанное возвращено" if accepted else "Жалоба отклонена",
                messages.SUCCESS,
            )

            return HttpResponseRedirect(back)

        return TemplateResponse(
            request,
            "admin/finance/form.html",
            {
                **self.admin_site.each_context(request),
                "title": "Признать жалобу обоснованной?" if accepted else "Отклонить жалобу?",
                "description": "Кредит вернётся на счёт компании, а израсходованный контакт по "
                "тарифу — в месячный лимит. Сам контакт останется открытым: показанное "
                "обратно не забрать."
                if accepted
                else "Возврата не будет. Компания получит объяснение.",
                "form": form,
                "submit": "Вернуть списанное" if accepted else "Отказать",
                "danger": not accepted,
                "list_url": back,
                "list_title": "Жалобы на контакты",
                "opts": self.model._meta,
            },
        )

    def accept_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self._decide(request, object_id, accepted=True)

    def decline_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self._decide(request, object_id, accepted=False)
