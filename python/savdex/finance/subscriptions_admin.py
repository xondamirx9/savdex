"""
«Подписки» в админке Django (этап 7, шаг 57) — вместо ресурса Filament
Subscriptions.

Кто на каком тарифе и ручная выдача. Формы правки нет намеренно:
подписка — не набор полей, а событие. Смена тарифа закрывает прежнюю,
начисляет единицы продвижения и обнуляет раскрытия, поэтому только
действия, идущие через SubscriptionService::assign (savdex/web/orders.py):

- «Назначить тариф» — компании, вручную, с основанием;
- «Сменить или продлить» — у строки, тоже вручную;
- «Отменить» — только действующую: статус, дата отмены, без автопродления.

Срок показан днями до конца (Subscription::daysLeft): скоро истекающие
выделены цветом — это повод позвонить.

Отличие от Filament: действия — только с правом subscriptions.edit.
У Filament кнопки видел любой, кто открыл раздел, и поддержка (раздел у
неё только на просмотр) могла выдать тариф бесплатно.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.billing.models import Plan
from savdex.crm.admin import _badge
from savdex.finance.models import SOURCES, SUBSCRIPTION_STATUSES, Subscription
from savdex.moderation.services import context_of
from savdex.web import eloquent, orders
from savdex.web.cabinet import _rows

SOURCE_TONES = {"manual": "warning", "promo": "info", "payment": "success"}
STATUS_TONES = {"active": "success", "cancelled": "gray"}


def _date(value: datetime | None) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y") if value is not None else ""


def days_left(ends_at: datetime | None) -> int | None:
    """Subscription::daysLeft: дни от сегодня до дня окончания, не меньше нуля."""
    if ends_at is None:
        return None

    today = datetime.now(UTC).date()

    return max(0, (ends_at.astimezone(UTC).date() - today).days)


class GrantForm(forms.Form):
    """Поля выдачи — общие для «Назначить» и «Сменить или продлить»."""

    company = forms.ChoiceField(label="Компания")
    plan = forms.ChoiceField(label="Тариф")
    days = forms.IntegerField(
        label="Срок, дней",
        required=False,
        min_value=0,
        help_text="Пусто — период тарифа. Ноль — бессрочно",
    )
    reason = forms.CharField(
        label="Основание",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Останется в карточке подписки. Через месяц никто не вспомнит, "
        "почему тариф выдали бесплатно",
    )

    def __init__(self, *args: Any, with_company: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cast(forms.ChoiceField, self.fields["plan"]).choices = [
            (str(p.pk), p.name) for p in Plan.objects.order_by("sort", "id")
        ]

        if with_company:
            cast(forms.ChoiceField, self.fields["company"]).choices = [
                (str(r["id"]), r["name"])
                for r in _rows(
                    "select id, name from companies where deleted_at is null order by name, id"
                )
            ]
        else:
            del self.fields["company"]


class ExpiringFilter(admin.SimpleListFilter):
    title = "срок"
    parameter_name = "expiring"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Истекают в ближайшую неделю")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[Subscription]
    ) -> QuerySet[Subscription]:
        if self.value() == "1":
            moment = datetime.now(UTC)

            return queryset.filter(
                status="active",
                ends_at__isnull=False,
                ends_at__range=(moment, moment + timedelta(days=7)),
            )

        return queryset


class StatusFilter(admin.SimpleListFilter):
    title = "статус"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(SUBSCRIPTION_STATUSES.items())

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[Subscription]
    ) -> QuerySet[Subscription]:
        return queryset.filter(status=self.value()) if self.value() else queryset


class SourceFilter(admin.SimpleListFilter):
    title = "откуда"
    parameter_name = "source"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(SOURCES.items())

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[Subscription]
    ) -> QuerySet[Subscription]:
        return queryset.filter(source=self.value()) if self.value() else queryset


@register(Subscription, section="subscriptions")
class SubscriptionAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Subscription"
    title_list = "Подписки"
    change_list_template = "admin/finance/subscription/change_list.html"

    list_display = ("company_name", "plan_name", "origin", "state", "left", "started")
    list_filter = ("plan", StatusFilter, SourceFilter, ExpiringFilter)
    list_select_related = ("company", "plan", "granted_by")
    search_fields = ("company__name",)
    ordering = ("-started_at", "-id")
    list_per_page = 50
    list_display_links = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_edit(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("subscriptions.edit")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Subscription]:
        queryset: QuerySet[Subscription] = super().get_queryset(request)

        return queryset.annotate(
            company_tin=RawSQL(
                "select tin from companies where companies.id = subscriptions.company_id", []
            )
        )

    # ── Список ──

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: Subscription) -> str:
        return format_html(
            "{}<br><small>{}</small>", obj.company.name, getattr(obj, "company_tin", "") or ""
        )

    @admin.display(description="тариф", ordering="plan__name")
    def plan_name(self, obj: Subscription) -> str:
        return _badge(obj.plan.name, "primary")

    @admin.display(description="откуда", ordering="source")
    def origin(self, obj: Subscription) -> str:
        badge = _badge(SOURCES.get(obj.source, "Оплачен"), SOURCE_TONES.get(obj.source, "success"))

        # Основание — у всех неоплаченных: у промокода это его код
        if obj.source == "payment":
            return badge

        who = obj.granted_by.name if obj.granted_by is not None else "администратор"

        return format_html("{}<br><small>{}: {}</small>", badge, who, obj.grant_reason or "—")

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Subscription) -> str:
        label = SUBSCRIPTION_STATUSES.get(obj.status, "Истекла")
        badge = _badge(label, STATUS_TONES.get(obj.status, "danger"))

        if not self._can_edit:
            return badge

        buttons = format_html(
            '<br><a class="button" href="{}">Сменить или продлить</a>',
            reverse("savdex_admin:finance_subscription_extend", args=[obj.pk]),
        )

        if obj.status == "active":
            buttons = format_html(
                '{} <a class="button" href="{}">Отменить</a>',
                buttons,
                reverse("savdex_admin:finance_subscription_cancel", args=[obj.pk]),
            )

        return format_html("{}{}", badge, buttons)

    @admin.display(description="осталось", ordering="ends_at")
    def left(self, obj: Subscription) -> str:
        if obj.status != "active":
            return "—"

        days = days_left(obj.ends_at)
        text = "бессрочно" if days is None else f"{days} дн."
        tone = "danger" if days is not None and days <= 7 else "gray"

        return format_html("{}<br><small>{}</small>", _badge(text, tone), _date(obj.ends_at))

    @admin.display(description="начало", ordering="started_at")
    def started(self, obj: Subscription) -> str:
        return _date(obj.started_at)

    _can_edit = False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_edit = self.has_edit(request)

        return super().changelist_view(
            request, {"can_grant": self._can_edit, **(extra_context or {})}
        )

    # ── Действия ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "grant/",
                self.admin_site.admin_view(self.grant_view),
                name="finance_subscription_grant",
            ),
            path(
                "<path:object_id>/extend/",
                self.admin_site.admin_view(self.extend_view),
                name="finance_subscription_extend",
            ),
            path(
                "<path:object_id>/cancel/",
                self.admin_site.admin_view(self.cancel_view),
                name="finance_subscription_cancel",
            ),
            *super().get_urls(),
        ]

    def _list(self) -> str:
        return reverse("savdex_admin:finance_subscription_changelist")

    def _page(self, request: HttpRequest, **context: Any) -> TemplateResponse:
        return TemplateResponse(
            request,
            "admin/finance/form.html",
            {
                **self.admin_site.each_context(request),
                "list_url": self._list(),
                "list_title": "Подписки",
                "opts": self.model._meta,
                **context,
            },
        )

    def _assign(
        self, request: HttpRequest, company_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """SubscriptionService::assign вручную, от имени сотрудника."""
        companies = _rows(
            "select * from companies where id = %s and deleted_at is null", [company_id]
        )

        if not companies:
            return None

        plan = _rows("select * from plans where id = %s", [int(data["plan"])])[0]
        staff = _admin_of(request)
        orders.assign(
            context_of(request),
            companies[0],
            plan,
            days=data["days"],
            source=orders.SOURCE_MANUAL,
            granted_by={"id": staff.id, "name": staff.name},
            reason=data["reason"],
        )

        return companies[0]

    def grant_view(self, request: HttpRequest) -> HttpResponse:
        """«Назначить тариф» в шапке списка."""
        if not self.has_edit(request):
            raise PermissionDenied

        form = GrantForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            company = self._assign(request, int(form.cleaned_data["company"]), form.cleaned_data)

            if company is not None:
                self.message_user(
                    request, f"Тариф назначен компании «{company['name']}»", messages.SUCCESS
                )

            return HttpResponseRedirect(self._list())

        return self._page(request, title="Назначить тариф", form=form, submit="Назначить")

    def _subscription(self, request: HttpRequest, object_id: str) -> Subscription:
        if not self.has_edit(request):
            raise PermissionDenied

        found = Subscription.objects.filter(pk=object_id).first()

        if found is None:
            raise PermissionDenied

        return found

    def extend_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """«Сменить или продлить»: новая подписка вручную, прежняя истекает."""
        subscription = self._subscription(request, object_id)
        form = GrantForm(
            request.POST or None,
            with_company=False,
            initial={"plan": str(subscription.plan_id)},
        )

        if request.method == "POST" and form.is_valid():
            if self._assign(request, subscription.company_id, form.cleaned_data) is None:
                self.message_user(request, "Компания удалена", messages.ERROR)
            else:
                self.message_user(request, "Подписка обновлена", messages.SUCCESS)

            return HttpResponseRedirect(self._list())

        return self._page(
            request,
            title="Сменить или продлить",
            description=f"Компания «{subscription.company.name}»: прежняя подписка закроется, "
            "новая начнётся сегодня.",
            form=form,
            submit="Сохранить",
        )

    def cancel_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """«Отменить»: компания сразу переходит на Free."""
        subscription = self._subscription(request, object_id)

        if subscription.status != "active":
            return HttpResponseRedirect(self._list())

        if request.method == "POST":
            row = _rows("select * from subscriptions where id = %s", [subscription.pk])[0]
            eloquent.save(
                context_of(request),
                "subscriptions",
                row,
                {"status": "cancelled", "cancelled_at": eloquent.now(), "auto_renew": False},
                section="subscriptions",
                model="Subscription",
                casts={"auto_renew": "bool"},
            )
            self.message_user(request, "Подписка отменена", messages.SUCCESS)

            return HttpResponseRedirect(self._list())

        return self._page(
            request,
            title="Отменить подписку?",
            description="Компания сразу перейдёт на Free: лимиты объявлений и раскрытий "
            "станут бесплатными. Опубликованные объявления останутся.",
            submit="Отменить подписку",
            danger=True,
        )
