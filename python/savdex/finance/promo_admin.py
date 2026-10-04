"""
«Промокоды» в админке Django (этап 7, шаг 57) — вместо ресурса Filament
PromoCodes.

Коды не придумывают руками, а выпускают пачкой — «Выпустить коды» в
шапке списка: код, набранный человеком, предсказуем, а угаданный код —
это выданный бесплатно месяц тарифа. Вид выбирается при выпуске: код на
бесплатный период выдаёт тариф сразу, скидочный выставляет счёт на
остаток цены. Срок и тариф выпущенного кода не меняются — он уже роздан
под конкретную акцию; в списке правится только выключатель, и
погашенный код включать и выключать нечего.

Отличие от Filament: «Активировать до» — конец выбранного дня по
Ташкенту. У Filament дата разбиралась в UTC, и код работал до пяти утра
следующего дня, а не «со следующего дня — нет», как обещает подсказка.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, time
from typing import Any, cast
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex.adminsite import PerRequest, SavdexModelAdmin, _admin_of, register
from savdex.billing.models import Plan
from savdex.crm.admin import _badge
from savdex.finance.models import PromoCode
from savdex.guards import allowed_writes
from savdex.moderation.services import context_of
from savdex.text import numeric
from savdex.web import eloquent, orders
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _stamp

#: PromoCode::ALPHABET и ::RANDOM_LENGTH: без похожих I, L, O, 0, 1
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
RANDOM_LENGTH = 8

#: Сколько кодов выпускают за раз: больше пачки трудно раздать
MAX_BATCH = 500

STATUS_TONES = {"Действует": "success", "Просрочен": "warning", "Отключён": "danger"}


def generate_code(prefix: str = "SVDX") -> str:
    """PromoCode::generateCode: SVDX-7КЗНАКОВ, случайность криптостойкая."""
    random = "".join(secrets.choice(ALPHABET) for _ in range(RANDOM_LENGTH))

    return orders.normalize(random if prefix == "" else f"{prefix}-{random}")


def _expired(code: PromoCode) -> bool:
    return code.expires_at is not None and code.expires_at < datetime.now(UTC)


def status(code: PromoCode) -> str:
    """Статус, а не голый флажок: погашенный код с «Действует» читался как рабочий."""
    if code.used_at is not None:
        return "Погашен"

    if not code.is_active:
        return "Отключён"

    return "Просрочен" if _expired(code) else "Действует"


class IssueForm(forms.Form):
    kind = forms.ChoiceField(
        label="Вид промокода",
        choices=[
            ("free", "Бесплатный период — тариф выдаётся сразу, без оплаты"),
            ("discount", "Скидка в процентах — остаток цены оплачивается онлайн"),
        ],
        initial="free",
    )
    count = forms.IntegerField(label="Сколько кодов", initial=10, min_value=1, max_value=MAX_BATCH)
    plan = forms.ChoiceField(label="Тариф")
    days = forms.IntegerField(
        label="Срок доступа, дней",
        initial=30,
        min_value=1,
        max_value=365,
        required=False,
        help_text="Для бесплатного периода: сколько дней тарифа получит компания",
    )
    discount_percent = forms.IntegerField(
        label="Скидка, %",
        initial=30,
        min_value=1,
        max_value=99,
        required=False,
        help_text="Для скидочного: активация выставит счёт на остаток цены тарифа и уведёт "
        "покупателя на онлайн-оплату (Uzum). Срок доступа — стандартный период тарифа",
    )
    expires_at = forms.DateField(
        label="Активировать до (включительно)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Пусто — код не сгорает. В указанный день код ещё работает, со следующего — нет",
    )
    # Не «prefix»: это служебный атрибут формы Django
    code_prefix = forms.CharField(
        label="Префикс кода",
        initial="SVDX",
        max_length=8,
        required=False,
        help_text="Видно в коде: SVDX-A7K2M9PQ. По нему в списке ищут коды одной акции",
    )
    note = forms.CharField(
        label="Для кого / повод",
        max_length=255,
        required=False,
        help_text="Останется в списке рядом с кодом. Через месяц никто не вспомнит, "
        "куда ушла пачка",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Бесплатный тариф дарить нечего, а скидка от нулевой цены — счёт на ноль
        plans = Plan.objects.filter(is_active=True).exclude(code="free").order_by("sort", "id")
        cast(forms.ChoiceField, self.fields["plan"]).choices = [(str(p.pk), p.name) for p in plans]
        premium = next((p for p in plans if p.code == "premium"), None)

        if premium is not None:
            self.fields["plan"].initial = str(premium.pk)

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}

        if data.get("kind") == "free" and data.get("days") is None:
            self.add_error("days", "Укажите срок доступа.")

        if data.get("kind") == "discount" and data.get("discount_percent") is None:
            self.add_error("discount_percent", "Укажите скидку.")

        return data


class Redeemable(admin.SimpleListFilter):
    title = "состояние"
    parameter_name = "state"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("free", "Свободные"), ("used", "Активированные"), ("discount", "Скидочные")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[PromoCode]) -> QuerySet[PromoCode]:
        if self.value() == "free":
            return queryset.filter(is_active=True, used_at__isnull=True).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=datetime.now(UTC))
            )

        if self.value() == "used":
            return queryset.filter(used_at__isnull=False)

        if self.value() == "discount":
            return queryset.filter(discount_percent__isnull=False)

        return queryset


@register(PromoCode, section="promocodes")
class PromoCodeAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\PromoCode"
    title_list = "Промокоды"
    change_list_template = "admin/finance/promocode/change_list.html"

    list_display = ("code_text", "plan_text", "used", "expires", "state", "issued")
    list_filter = (Redeemable, "plan")
    list_select_related = ("plan", "used_by_company", "created_by")
    search_fields = ("code",)
    ordering = ("-created_at", "-id")
    list_per_page = 50
    list_display_links = None
    actions = ("disable_selected",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_edit(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("promocodes.edit")

    def has_disable_permission(self, request: HttpRequest) -> bool:
        return self.has_edit(request)

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return super(SavdexModelAdmin, self).get_actions(request)

    # ── Список ──

    @admin.display(description="код", ordering="code")
    def code_text(self, obj: PromoCode) -> str:
        return format_html("<b>{}</b><br><small>{}</small>", obj.code, obj.note or "")

    @admin.display(description="тариф", ordering="plan__name")
    def plan_text(self, obj: PromoCode) -> str:
        if obj.discount_percent is not None:
            return format_html(
                "{}<br><small>скидка {}%</small>",
                _badge(obj.plan.name, "warning"),
                obj.discount_percent,
            )

        return format_html(
            "{}<br><small>на {} дн. бесплатно</small>", _badge(obj.plan.name, "primary"), obj.days
        )

    @admin.display(description="активирован", ordering="used_at")
    def used(self, obj: PromoCode) -> str:
        if obj.used_at is None:
            return "—"

        company = obj.used_by_company.name if obj.used_by_company is not None else ""

        return format_html(
            "{}<br><small>{}</small>",
            timezone.localtime(obj.used_at).strftime("%d.%m.%Y %H:%M"),
            company,
        )

    @admin.display(description="активировать до", ordering="expires_at")
    def expires(self, obj: PromoCode) -> str:
        if obj.expires_at is None:
            return "бессрочно"

        text = timezone.localtime(obj.expires_at).strftime("%d.%m.%Y")

        # Просроченный — нерабочий, а не «дата в прошлом, ну и что»
        return _badge(text, "danger") if _expired(obj) and obj.used_at is None else text

    @admin.display(description="статус")
    def state(self, obj: PromoCode) -> str:
        label = status(obj)
        badge = _badge(label, STATUS_TONES.get(label, "gray"))

        if obj.used_at is not None or not self._can_edit:
            return badge

        return format_html(
            '{}<br><button type="submit" class="button" formaction="{}" formmethod="post" '
            "onclick=\"return confirm('{}?')\">{}</button>",
            badge,
            reverse("savdex_admin:finance_promocode_toggle", args=[obj.pk]),
            "Отключить код" if obj.is_active else "Включить код",
            "Отключить" if obj.is_active else "Включить",
        )

    @admin.display(description="выпущен", ordering="created_at")
    def issued(self, obj: PromoCode) -> str:
        date = timezone.localtime(obj.created_at).strftime("%d.%m.%Y") if obj.created_at else ""
        who = obj.created_by.name if obj.created_by is not None else ""

        return format_html("{}<br><small>{}</small>", date, who)

    _can_edit = PerRequest()

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_edit = self.has_edit(request)

        return super().changelist_view(
            request, {"can_issue": self._can_edit, **(extra_context or {})}
        )

    # ── Отключить ──

    def _toggle(self, request: HttpRequest, pk: int, value: bool | None = None) -> bool:
        """Выключатель одного кода; погашенный не трогается."""
        rows = _rows("select * from promo_codes where id = %s", [pk])

        if not rows or rows[0]["used_at"] is not None:
            return False

        row = rows[0]
        eloquent.save(
            context_of(request),
            "promo_codes",
            row,
            {"is_active": (not row["is_active"]) if value is None else value},
            section="promocodes",
            model="PromoCode",
            casts={"is_active": "bool", "discount_percent": "int"},
        )

        return True

    @admin.action(description="Отключить выбранные", permissions=["disable"])
    def disable_selected(self, request: HttpRequest, queryset: QuerySet[PromoCode]) -> None:
        # Погашенные пропускаются, но не молча
        used = [c for c in queryset if c.used_at is not None]
        done = sum(self._toggle(request, c.pk, False) for c in queryset if c.used_at is None)
        note = (
            f" Погашенных пропущено: {len(used)}. Активированный код отключать не нужно — "
            "повторно он не сработает."
            if used
            else ""
        )
        self.message_user(
            request,
            f"Отключено кодов: {done}.{note}",
            messages.SUCCESS if done else messages.WARNING,
        )

    # ── Выпуск ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "issue/",
                self.admin_site.admin_view(self.issue_view),
                name="finance_promocode_issue",
            ),
            path(
                "<path:object_id>/toggle/",
                self.admin_site.admin_view(self.toggle_view),
                name="finance_promocode_toggle",
            ),
            *super().get_urls(),
        ]

    def _list(self) -> str:
        return reverse("savdex_admin:finance_promocode_changelist")

    def toggle_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.has_edit(request):
            raise PermissionDenied

        if numeric(object_id) and self._toggle(request, int(object_id)):
            self.message_user(request, "Сохранено.", messages.SUCCESS)

        return HttpResponseRedirect(request.headers.get("Referer") or self._list())

    def issue(self, request: HttpRequest, data: dict[str, Any]) -> list[str]:
        """
        Выпуск пачки. Совпадения обходятся повтором, а не пропуском: молча
        выпустить 9 кодов вместо 10 значит недодать один обещанный.
        """
        prefix = (data.get("code_prefix") or "").strip()
        discount = data["kind"] == "discount"
        expires = None

        if data.get("expires_at") is not None:
            # Конец выбранного дня по Ташкенту — в базе UTC
            local = datetime.combine(
                data["expires_at"], time(23, 59, 59), tzinfo=ZoneInfo(settings.TIME_ZONE)
            )
            expires = local.astimezone(UTC)

        staff = _admin_of(request)
        ctx = context_of(request)
        codes: list[str] = []

        for _ in range(int(data["count"])):
            code = generate_code(prefix)

            while _rows("select 1 from promo_codes where code = %s", [code]):
                code = generate_code(prefix)

            moment = eloquent.now()
            row: dict[str, Any] = {
                "code": code,
                "plan_id": int(data["plan"]),
                "days": 0 if discount else int(data["days"]),
                "discount_percent": int(data["discount_percent"]) if discount else None,
                "expires_at": _stamp(expires) if expires is not None else None,
                "is_active": True,
                "note": data.get("note") or None,
                "created_by": staff.id,
                "updated_at": _stamp(moment),
                "created_at": _stamp(moment),
            }
            columns = list(row)

            with allowed_writes("promo_codes"), connection.cursor() as cursor:
                cursor.execute(
                    f"insert into promo_codes ({', '.join(columns)}) "
                    f"values ({', '.join(['%s'] * len(columns))}) returning id",
                    list(row.values()),
                )
                row["id"] = cursor.fetchone()[0]

            eloquent.journal(ctx, "created", "promocodes", "PromoCode", row, {"after": row})
            codes.append(code)

        return codes

    def issue_view(self, request: HttpRequest) -> HttpResponse:
        if not self.has_edit(request):
            raise PermissionDenied

        form = IssueForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            codes = self.issue(request, form.cleaned_data)
            self.message_user(
                request,
                f"Выпущено кодов: {len(codes)}. Скопируйте их из списка — код показывается "
                "полностью.",
                messages.SUCCESS,
            )

            return HttpResponseRedirect(self._list())

        return TemplateResponse(
            request,
            "admin/finance/form.html",
            {
                **self.admin_site.each_context(request),
                "title": "Выпустить коды",
                "form": form,
                "submit": "Выпустить",
                "list_url": self._list(),
                "list_title": "Промокоды",
                "opts": self.model._meta,
            },
        )
