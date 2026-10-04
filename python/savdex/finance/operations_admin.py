"""
«Финансовые операции» в админке Django (этап 7, шаг 61) — вместо
страницы Filament FinanceOperations.

Движения по кошелькам компаний: начисления, списания, возвраты. Их не
создают и не правят руками — это след покупки, раскрытия или возврата,
и с ним делают одно: читают. Здесь закрывается спор «у меня списали
лишнее»: остаток обязан выводиться из истории.

Видят те, у кого refunds.view (финансы, суперадмин), — как у Filament.
Под списком — «Итого» по отфильтрованному (сумма колонки «Сколько»).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import admin
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html

from savdex.adminsite import SavdexModelAdmin, register
from savdex.crm.admin import _badge
from savdex.finance.models import WALLET_KINDS, WALLET_REASONS, WalletTransaction
from savdex.finance.refunds_admin import _limit


def _signed(amount: int) -> str:
    """Знак — главное в колонке: начисление и списание различаются только им."""
    return ("+" if amount > 0 else "") + f"{amount:,}".replace(",", " ")


class ReasonFilter(admin.SimpleListFilter):
    title = "основание"
    parameter_name = "reason"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(WALLET_REASONS.items())

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[WalletTransaction]
    ) -> QuerySet[WalletTransaction]:
        return queryset.filter(reason=self.value()) if self.value() else queryset


class KindFilter(admin.SimpleListFilter):
    title = "что"
    parameter_name = "kind"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(WALLET_KINDS.items())

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[WalletTransaction]
    ) -> QuerySet[WalletTransaction]:
        return queryset.filter(kind=self.value()) if self.value() else queryset


class DirectionFilter(admin.SimpleListFilter):
    title = "направление"
    parameter_name = "direction"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("grants", "Только начисления"), ("spends", "Только списания")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[WalletTransaction]
    ) -> QuerySet[WalletTransaction]:
        if self.value() == "grants":
            return queryset.filter(amount__gt=0)

        if self.value() == "spends":
            return queryset.filter(amount__lt=0)

        return queryset


class MonthFilter(admin.SimpleListFilter):
    title = "период"
    parameter_name = "period"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("month", "За месяц")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[WalletTransaction]
    ) -> QuerySet[WalletTransaction]:
        if self.value() == "month":
            return queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))

        return queryset


@register(WalletTransaction, section="refunds")
class WalletTransactionAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\WalletTransaction"
    title_change = "Финансовая операция"
    title_list = "Финансовые операции"
    change_list_template = "admin/finance/wallettransaction/change_list.html"

    list_display = ("when", "company_name", "kind_badge", "signed", "balance", "reason_badge",
                    "who", "comment_text")  # fmt: skip
    list_filter = (ReasonFilter, KindFilter, DirectionFilter, MonthFilter)
    list_select_related = ("company", "user")
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

    @admin.display(description="когда", ordering="created_at")
    def when(self, obj: WalletTransaction) -> str:
        moment = obj.created_at

        return timezone.localtime(moment).strftime("%d.%m.%Y %H:%M") if moment else ""

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: WalletTransaction) -> str:
        company = obj.company

        return company.name if company.deleted_at is None else "удалена"

    @admin.display(description="что", ordering="kind")
    def kind_badge(self, obj: WalletTransaction) -> str:
        return _badge(WALLET_KINDS.get(obj.kind, obj.kind), "gray")

    @admin.display(description="сколько", ordering="amount")
    def signed(self, obj: WalletTransaction) -> str:
        colour = "#15803d" if obj.amount > 0 else "#b91c1c"

        return format_html('<b style="color:{}">{}</b>', colour, _signed(obj.amount))

    @admin.display(description="остаток после")
    def balance(self, obj: WalletTransaction) -> str:
        return f"{obj.balance_after:,}".replace(",", " ")

    @admin.display(description="основание", ordering="reason")
    def reason_badge(self, obj: WalletTransaction) -> str:
        return _badge(WALLET_REASONS.get(obj.reason, obj.reason), "info")

    @admin.display(description="кто провёл")
    def who(self, obj: WalletTransaction) -> str:
        # У Laravel связь withTrashed: отключённый сотрудник остаётся по имени
        return obj.user.name if obj.user is not None else "автоматически"

    @admin.display(description="комментарий")
    def comment_text(self, obj: WalletTransaction) -> str:
        return _limit(obj.comment, 60) if obj.comment else "—"

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        response = super().changelist_view(request, extra_context)

        if isinstance(response, TemplateResponse) and response.context_data is not None:
            cl = response.context_data.get("cl")

            if cl is not None:
                total = cl.queryset.aggregate(total=Sum("amount"))["total"] or 0
                response.context_data["total"] = f"{total:,}".replace(",", " ")

        return response
