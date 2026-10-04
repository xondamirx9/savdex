"""
«Счета и оплаты» в админке Django (этап 7, шаг 56) — вместо страницы
Filament Invoices.

Оплата идёт переводом на расчётный счёт, поэтому зачисление подтверждает
человек: видит поступление в выписке и отмечает счёт оплаченным. В этот
момент — и только в этот — подписка активируется, а кредиты ложатся на
кошелёк. По умолчанию в списке — ждущие оплаты, свежие сверху.

- «Деньги пришли» — OrderService::confirm: та же выдача, что у колбэка
  кассы (savdex/web/settlement.py), кто отметил — confirmed_by, отметка
  для себя — admin_note, подписка — granted_by, кредиты — от его имени;
- «Отменить счёт» — OrderService::cancel с причиной: строка остаётся со
  статусом «Отменён», скидочный промокод — в оборот.

Отличие от Filament: кнопки — с правом payments.edit, а не просто с
доступом к странице. Сейчас это одно и то же (раздел «Счета» есть только
у финансов, с правкой), но подтверждение денег не должно держаться на
том, что ролей с одним просмотром пока нет.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme

from savdex.adminsite import PerRequest, SavdexModelAdmin, _admin_of, register
from savdex.catalog import now
from savdex.crm.admin import OpenFilter, _badge
from savdex.finance.models import PURPOSES, STATUSES, Payment
from savdex.moderation.services import context_of
from savdex.web import orders, settlement
from savdex.web.cabinet import _rows

#: Цвет статуса — как у Filament
STATUS_TONES = {"paid": "success", "pending": "warning"}


def _date(value: Any) -> str:  # noqa: ANN401
    """date('d.m.Y') в часовом поясе админки."""
    return timezone.localtime(value).strftime("%d.%m.%Y") if value is not None else ""


class Unpaid(OpenFilter):
    title = "ждут оплаты"
    open_label = "Ждут оплаты"
    all_label = "Все счета"
    open_q = Q(status="pending")


class Overdue(admin.SimpleListFilter):
    """Просрочены: ждут оплаты дольше OrderService::EXPIRES_DAYS."""

    title = "срок"
    parameter_name = "overdue"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Просрочены")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Payment]) -> QuerySet[Payment]:
        if self.value() == "1":
            return queryset.filter(
                status="pending", created_at__lt=now() - timedelta(days=orders.EXPIRES_DAYS)
            )

        return queryset


class Purpose(admin.SimpleListFilter):
    title = "за что"
    parameter_name = "purpose"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(PURPOSES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Payment]) -> QuerySet[Payment]:
        return queryset.filter(purpose=self.value()) if self.value() else queryset


@register(Payment, section="payments")
class PaymentAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Payment"
    title_list = "Счета и оплаты"
    title_change = "Счёт"

    list_display = ("invoice", "company_name", "description", "amount_text", "state", "paid")
    list_filter = (Unpaid, "status", Purpose, Overdue)
    list_select_related = ("company", "confirmed_by")
    search_fields = ("number", "company__name")
    ordering = ("-created_at", "-id")
    list_per_page = 50
    fields = (
        "number",
        "company",
        "description",
        "amount",
        "currency",
        "status",
        "provider",
        "external_id",
        "paid_at",
        "confirmed_by",
        "admin_note",
        "created_at",
    )
    readonly_fields = fields

    # Счёт выставляет компания в кассе, меняет — только «Деньги пришли»
    # и «Отменить»: ни формы, ни удаления
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_edit(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("payments.edit")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Payment]:
        queryset: QuerySet[Payment] = super().get_queryset(request)

        # ИНН — под названием компании, как у Filament; в модели компании его нет
        return queryset.annotate(
            company_tin=RawSQL(
                "select tin from companies where companies.id = payments.company_id", []
            )
        )

    # ── Список ──

    @admin.display(description="счёт", ordering="number")
    def invoice(self, obj: Payment) -> str:
        return format_html("<b>{}</b><br><small>{}</small>", obj, _date(obj.created_at))

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: Payment) -> str:
        tin = getattr(obj, "company_tin", None)

        return format_html("{}<br><small>{}</small>", obj.company.name, tin or "")

    @admin.display(description="сумма", ordering="amount")
    def amount_text(self, obj: Payment) -> str:
        return obj.amount_label()

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Payment) -> str:
        badge = _badge(STATUSES.get(obj.status, obj.status), STATUS_TONES.get(obj.status, "gray"))
        who = obj.confirmed_by.name if obj.confirmed_by is not None else ""
        buttons = ""

        if obj.status == "pending" and self._can_edit:
            buttons = format_html(
                '<br><a class="button" href="{}">Деньги пришли</a> '
                '<a class="button" href="{}">Отменить счёт</a>',
                reverse("savdex_admin:finance_payment_confirm", args=[obj.pk]),
                reverse("savdex_admin:finance_payment_cancel", args=[obj.pk]),
            )

        return format_html("{}<br><small>{}</small>{}", badge, who, buttons)

    @admin.display(description="оплачен", ordering="paid_at")
    def paid(self, obj: Payment) -> str:
        return _date(obj.paid_at) or "—"

    _can_edit = PerRequest()

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_edit = self.has_edit(request)
        extra_context = {
            **(extra_context or {}),
            "can_reports": _admin_of(request).can("finreports.view"),
        }

        return super().changelist_view(request, extra_context)

    # ── Деньги пришли, отменить ──

    def get_urls(self) -> list[Any]:
        from savdex.finance import reports_view

        return [
            # Отчёты и сверка — страницы, не разделы модели; права — finreports.view
            path(
                "reports/",
                self.admin_site.admin_view(reports_view.view),
                name="finance_reports",
            ),
            path(
                "reconciliation/",
                self.admin_site.admin_view(reports_view.reconciliation),
                name="finance_reconciliation",
            ),
            path(
                "<path:object_id>/confirm/",
                self.admin_site.admin_view(self.confirm_view),
                name="finance_payment_confirm",
            ),
            path(
                "<path:object_id>/cancel/",
                self.admin_site.admin_view(self.cancel_view),
                name="finance_payment_cancel",
            ),
            *super().get_urls(),
        ]

    def _pending(self, request: HttpRequest, object_id: str) -> dict[str, Any] | None:
        """Строка счёта, как её видят службы сайта; только ждущий оплаты."""
        if not self.has_edit(request):
            raise PermissionDenied

        try:
            pk = int(object_id)
        except ValueError:
            return None

        rows = _rows("select * from payments where id = %s", [pk])

        return rows[0] if rows and rows[0]["status"] == "pending" else None

    def _back(self, request: HttpRequest) -> HttpResponse:
        back = request.POST.get("back") or ""

        if not url_has_allowed_host_and_scheme(
            back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            back = reverse("savdex_admin:finance_payment_changelist")

        return HttpResponseRedirect(back)

    def _page(self, request: HttpRequest, payment: dict[str, Any], kind: str) -> TemplateResponse:
        company = _rows("select name from companies where id = %s", [payment["company_id"]])

        return TemplateResponse(
            request,
            "admin/finance/payment/decision.html",
            {
                **self.admin_site.each_context(request),
                "title": "Подтвердить поступление?" if kind == "confirm" else "Отменить счёт?",
                "kind": kind,
                "payment": payment,
                "company": company[0]["name"] if company else "",
                "amount": Payment(
                    amount=payment["amount"], currency=payment["currency"]
                ).amount_label(),
                "back": request.headers.get("Referer", ""),
                "opts": self.model._meta,
            },
        )

    def confirm_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """Деньги пришли: подписка активируется, кредиты ложатся на кошелёк."""
        payment = self._pending(request, object_id)

        if payment is None:
            self.message_user(request, "Счёт уже не ждёт оплаты.", messages.WARNING)

            return HttpResponseRedirect(reverse("savdex_admin:finance_payment_changelist"))

        if request.method != "POST":
            return self._page(request, payment, "confirm")

        staff = _admin_of(request)
        note = (request.POST.get("note") or "").strip() or None
        ok, message = settlement.confirm(
            context_of(request), payment, {"id": staff.id, "name": staff.name}, note
        )
        self.message_user(request, message, messages.SUCCESS if ok else messages.WARNING)

        return self._back(request)

    def cancel_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """Отменить счёт: строка остаётся — исчезнувший счёт выглядит как потерянный платёж."""
        payment = self._pending(request, object_id)

        if payment is None:
            self.message_user(request, "Счёт уже не ждёт оплаты.", messages.WARNING)

            return HttpResponseRedirect(reverse("savdex_admin:finance_payment_changelist"))

        if request.method != "POST":
            return self._page(request, payment, "cancel")

        staff = _admin_of(request)
        note = (request.POST.get("note") or "").strip() or None
        orders.cancel(context_of(request), payment, note, {"id": staff.id})
        self.message_user(request, "Счёт отменён", messages.SUCCESS)

        return self._back(request)


# Остальные разделы денег — в своих модулях; Django читает только admin.py
from savdex.finance import (  # noqa: E402, F401
    complaints_admin,
    operations_admin,
    promo_admin,
    refunds_admin,
    subscriptions_admin,
)
