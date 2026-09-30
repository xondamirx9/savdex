"""
«Возвраты» в админке Django (этап 7, шаг 58) — вместо ресурса Filament
Refunds. Решения — через savdex/finance/refunds.py (RefundService).

Заявленные сверху и по умолчанию: это деньги, по которым решение ещё не
принято. Формы правки и удаления нет: ошибочный возврат исправляется
обратной операцией, а не стиранием записи.

- «Заявить возврат» (refunds.create) — по оплаченному счёту из последних
  ста, сумма не больше остатка, причина от 10 знаков;
- «Провести» и «Отклонить» (refunds.edit) — у заявленного; отказ — с
  причиной от 10 знаков.

Отличие: итога по сумме под списком нет — он у отчётов (шаг 60).
"""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.timesince import timesince

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.admin import OpenFilter, _badge
from savdex.finance import refunds
from savdex.finance.models import REFUND_STATUSES, Refund
from savdex.moderation.services import context_of
from savdex.web.cabinet import _rows

STATUS_TONES = {"done": "success", "rejected": "gray", "requested": "warning"}


def _limit(text: str, length: int = 70) -> str:
    """Str::limit: обрезка по знакам с «...»."""
    return text if len(text) <= length else text[:length].rstrip() + "..."


class Requested(OpenFilter):
    title = "ждут решения"
    open_label = "Ждут решения"
    all_label = "Все возвраты"
    open_q = Q(status="requested")


class StatusFilter(admin.SimpleListFilter):
    title = "решение"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(REFUND_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Refund]) -> QuerySet[Refund]:
        return queryset.filter(status=self.value()) if self.value() else queryset


class RequestForm(forms.Form):
    payment = forms.ChoiceField(label="По какому счёту")
    amount = forms.IntegerField(
        label="Сумма возврата",
        min_value=1,
        help_text="Не больше остатка по счёту: частичные возвраты складываются",
    )
    reason = forms.CharField(
        label="Причина",
        min_length=10,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Обязательно: возврат без причины невозможно ни проверить, ни объяснить",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        rows = _rows(
            "select p.id, p.number, p.amount, p.currency, c.name from payments p "
            "left join companies c on c.id = p.company_id and c.deleted_at is null "
            "where p.status = 'paid' order by p.paid_at desc nulls last limit 100"
        )
        cast(forms.ChoiceField, self.fields["payment"]).choices = [
            (
                str(r["id"]),
                f"{r['number']} — {r['name'] or 'компания удалена'} — "
                f"{refunds.money(r['amount'], r['currency'])}",
            )
            for r in rows
        ]


class ApproveForm(forms.Form):
    note = forms.CharField(
        label="Комментарий к решению", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class RejectForm(forms.Form):
    """Отказ — только с формулировкой: без неё его не объяснить проверяющему."""

    note = forms.CharField(
        label="Почему отказ", min_length=10, widget=forms.Textarea(attrs={"rows": 3})
    )


@register(Refund, section="refunds")
class RefundAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Refund"
    title_list = "Возвраты"
    change_list_template = "admin/finance/refund/change_list.html"

    list_display = ("requested", "company_name", "amount_text", "reason_text", "state", "author")
    list_filter = (Requested, StatusFilter)
    list_select_related = ("payment", "company", "created_by", "decided_by")
    search_fields = ("company__name",)
    ordering = ("-created_at", "-id")
    list_per_page = 50
    list_display_links = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    # ── Список ──

    @admin.display(description="заявлен", ordering="created_at")
    def requested(self, obj: Refund) -> str:
        if obj.created_at is None:
            return ""

        return format_html(
            "{}<br><small>{} назад</small>",
            timezone.localtime(obj.created_at).strftime("%d.%m.%Y %H:%M"),
            timesince(obj.created_at, depth=1),
        )

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: Refund) -> str:
        company = obj.company

        name = company.name if company is not None and company.deleted_at is None else "удалена"

        return format_html("{}<br><small>{}</small>", name, obj.payment.number or "")

    @admin.display(description="сумма", ordering="amount")
    def amount_text(self, obj: Refund) -> str:
        # Часть или весь счёт: по частичному возврату счёт остаётся оплаченным
        partial = obj.amount < obj.payment.amount

        return format_html(
            "{}{}", obj.money(), format_html("<br><small>частичный</small>") if partial else ""
        )

    @admin.display(description="причина")
    def reason_text(self, obj: Refund) -> str:
        return _limit(obj.reason)

    @admin.display(description="решение", ordering="status")
    def state(self, obj: Refund) -> str:
        badge = _badge(
            REFUND_STATUSES.get(obj.status, obj.status), STATUS_TONES.get(obj.status, "warning")
        )
        who = obj.decided_by.name if obj.decided_by is not None else ""
        buttons = ""

        if obj.status == refunds.REQUESTED and self._can_decide:
            buttons = format_html(
                '<br><a class="button" href="{}">Провести</a> <a class="button" href="{}">'
                "Отклонить</a>",
                reverse("savdex_admin:finance_refund_approve", args=[obj.pk]),
                reverse("savdex_admin:finance_refund_reject", args=[obj.pk]),
            )

        return format_html("{}<br><small>{}</small>{}", badge, who, buttons)

    @admin.display(description="заявил")
    def author(self, obj: Refund) -> str:
        return obj.created_by.name if obj.created_by is not None else "—"

    _can_decide = False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        staff = _admin_of(request)
        self._can_decide = staff.can("refunds.edit")

        return super().changelist_view(
            request, {"can_request": staff.can("refunds.create"), **(extra_context or {})}
        )

    # ── Заявить, провести, отклонить ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "request/",
                self.admin_site.admin_view(self.request_view),
                name="finance_refund_request",
            ),
            path(
                "<path:object_id>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="finance_refund_approve",
            ),
            path(
                "<path:object_id>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="finance_refund_reject",
            ),
            *super().get_urls(),
        ]

    def _list(self) -> str:
        return reverse("savdex_admin:finance_refund_changelist")

    def _page(self, request: HttpRequest, **context: Any) -> TemplateResponse:
        return TemplateResponse(
            request,
            "admin/finance/form.html",
            {
                **self.admin_site.each_context(request),
                "list_url": self._list(),
                "list_title": "Возвраты",
                "opts": self.model._meta,
                **context,
            },
        )

    def request_view(self, request: HttpRequest) -> HttpResponse:
        staff = _admin_of(request)

        if not staff.can("refunds.create"):
            raise PermissionDenied

        form = RequestForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            payment = _rows(
                "select * from payments where id = %s", [int(form.cleaned_data["payment"])]
            )[0]

            try:
                refunds.request_refund(
                    context_of(request),
                    staff,
                    payment,
                    int(form.cleaned_data["amount"]),
                    form.cleaned_data["reason"],
                )
                self.message_user(request, "Возврат заявлен", messages.SUCCESS)
            except refunds.RefundError as error:
                self.message_user(request, f"Не получилось: {error}", messages.ERROR)

            return HttpResponseRedirect(self._list())

        return self._page(request, title="Заявить возврат", form=form, submit="Заявить")

    def _refund(self, request: HttpRequest, object_id: str) -> dict[str, Any]:
        if not _admin_of(request).can("refunds.edit"):
            raise PermissionDenied

        rows = _rows("select * from refunds where id = %s", [int(object_id)])

        if not rows:
            raise PermissionDenied

        return rows[0]

    def _decide(self, request: HttpRequest, object_id: str, *, approve: bool) -> HttpResponse:
        refund = self._refund(request, object_id)
        form = (ApproveForm if approve else RejectForm)(request.POST or None)

        if request.method == "POST" and form.is_valid():
            note = form.cleaned_data["note"] or None

            try:
                if approve:
                    refunds.approve(context_of(request), _admin_of(request), refund, note)
                else:
                    refunds.reject(context_of(request), _admin_of(request), refund, note or "")

                self.message_user(
                    request,
                    "Возврат проведён" if approve else "Возврат отклонён",
                    messages.SUCCESS,
                )
            except refunds.RefundError as error:
                self.message_user(request, f"Не получилось: {error}", messages.ERROR)

            return HttpResponseRedirect(self._list())

        return self._page(
            request,
            title="Провести возврат?" if approve else "Отклонить возврат?",
            description="Счёт получит статус «Возвращён», если возвращается вся сумма. "
            "Отменить проведение нельзя — только оформить обратную операцию."
            if approve
            else "",
            form=form,
            submit="Провести" if approve else "Отклонить",
            danger=not approve,
        )

    def approve_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self._decide(request, object_id, approve=True)

    def reject_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self._decide(request, object_id, approve=False)
