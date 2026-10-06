"""
Потенциальные клиенты и рассылки по базе в админке Django (раздел CRM).
Логика — savdex/crm/prospects.py.

Список — вся база отдела продаж, общая для всех (у раздела нет «только
свои»): вкладки «Ещё не писали», «Писали», «В лидах», «Не писать» со
счётчиками, поиск по названию, контакту, ИНН, телефону, почте, городу и
отрасли. Пустое поле — «—»: у физлица и фрилансера данных бывает мало,
и видно, чего именно нет.

Действия над отмеченными (галочка в шапке — вся страница, «Выбрать все»
— весь отбор, на всех страницах):

- «Отправить письмо…» — окно с темой и текстом; сколько получат и
  почему остальные нет (без почты, не писать, уже в лидах). Письма
  уходят фоном, ход — в «Рассылках по базе»;
- «Отметить рассылку…» — касание вне площадки (своя почта, Telegram,
  звонок): счётчик +1 сразу;
- «Перенести в лиды» — право заводить лиды; запись остаётся с отметкой;
- удаление — в корзину, с правом удалять.

Загрузка из Excel или CSV — кнопка «Загрузить из Excel» (право
prospects.import), рядом — образец файла.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.views.main import SEARCH_VAR
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from savdex import audit
from savdex.accounts.models import User
from savdex.adminsite import _admin_of, register, state_tabs
from savdex.crm import prospects
from savdex.crm.admin import CrmAdmin, _badge
from savdex.crm.models import (
    MAILING_CHANNELS,
    PROSPECT_KINDS,
    RECIPIENT_STATUSES,
    Prospect,
    ProspectMailing,
    ProspectRecipient,
)
from savdex.text import plural

#: Пустое поле в списке: данных нет — так и видно
EMPTY = "—"

#: Отбор вкладками над списком — без блока в правой колонке
HIDDEN_FILTER = "admin/data/companyrecord/hidden_filter.html"

#: Вкладки: что с записью сейчас
STATES = {
    "new": "Ещё не писали",
    "mailed": "Писали",
    "lead": "В лидах",
    "stop": "Не писать",
}

_STATE_Q = {
    "new": Q(mailings_count=0, converted_at__isnull=True, unsubscribed_at__isnull=True),
    "mailed": Q(mailings_count__gt=0, converted_at__isnull=True, unsubscribed_at__isnull=True),
    "lead": Q(converted_at__isnull=False),
    "stop": Q(unsubscribed_at__isnull=False),
}

#: Отбор по счётчику рассылок
_MAILED = {
    "1": ("1 рассылка", Q(mailings_count=1)),
    "2-3": ("2–3 рассылки", Q(mailings_count__in=(2, 3))),
    "4+": ("4 и больше", Q(mailings_count__gte=4)),
}

#: Кнопки-отборы под поиском: параметр и варианты (в группе выбран один)
CHIPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("email", (("yes", "Есть почта"), ("no", "Нет почты"))),
    ("kind", (*PROSPECT_KINDS.items(), ("none", "Кто — не указано"))),
    ("mailed", tuple((code, label) for code, (label, _) in _MAILED.items())),
    ("savdex", (("yes", "Уже на SavdEx"),)),
)

#: Получатель письма — цвет плашки
RECIPIENT_TONES = {
    "queued": "gray",
    "sending": "info",
    "sent": "success",
    "failed": "danger",
    "skipped": "warning",
}


def _date(value: datetime | None) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y") if value else EMPTY


def _moment(value: datetime | None) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else EMPTY


def _people(ids: set[int]) -> dict[int, str]:
    return dict(User.objects.filter(pk__in=ids).values_list("id", "name")) if ids else {}


# ── Фильтры ─────────────────────────────────────────────────────────


class State(admin.SimpleListFilter):
    title = "что с ним"
    parameter_name = "state"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(STATES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> QuerySet[Prospect]:
        value = self.value()

        return queryset.filter(_STATE_Q[value]) if value in _STATE_Q else queryset


class HasEmail(admin.SimpleListFilter):
    title = "почта"
    parameter_name = "email"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("yes", "Есть почта"), ("no", "Нет почты")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> QuerySet[Prospect]:
        empty = Q(email__isnull=True) | Q(email="")

        if self.value() == "yes":
            return queryset.exclude(empty)

        if self.value() == "no":
            return queryset.filter(empty)

        return queryset


class Kind(admin.SimpleListFilter):
    title = "кто это"
    parameter_name = "kind"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [*PROSPECT_KINDS.items(), ("none", "Не указано")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> QuerySet[Prospect]:
        if self.value() == "none":
            return queryset.filter(kind__isnull=True)

        if self.value() in PROSPECT_KINDS:
            return queryset.filter(kind=self.value())

        return queryset


class Mailed(admin.SimpleListFilter):
    title = "рассылок"
    parameter_name = "mailed"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [(code, label) for code, (label, _) in _MAILED.items()]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> QuerySet[Prospect]:
        found = _MAILED.get(self.value() or "")

        return queryset.filter(found[1]) if found else queryset


def filter_chips(request: HttpRequest) -> list[dict[str, Any]]:
    """
    Отборы кнопками под поиском, как у объявлений: колонка фильтров справа
    сдвигала таблицу за край экрана. Нажатие включает, повторное — снимает.
    """
    chips = []

    for parameter, options in CHIPS:
        current = request.GET.get(parameter, "")

        for value, label in options:
            query = request.GET.copy()

            for name in (parameter, "p", "e"):
                query.pop(name, None)

            if current != value:
                query[parameter] = value

            chips.append(
                {
                    "label": label,
                    "url": "?" + query.urlencode() if query else "?",
                    "active": current == value,
                    "group_start": value == options[0][0],
                }
            )

    return chips


class OnSavdex(admin.SimpleListFilter):
    title = "на SavdEx"
    parameter_name = "savdex"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("yes", "Уже есть на площадке"), ("no", "Ещё нет")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> QuerySet[Prospect]:
        if self.value() == "yes":
            return queryset.filter(company__isnull=False)

        if self.value() == "no":
            return queryset.filter(company__isnull=True)

        return queryset


# ── Формы ───────────────────────────────────────────────────────────


class ProspectForm(forms.ModelForm):  # type: ignore[type-arg]
    do_not_mail = forms.BooleanField(
        label="Не писать",
        required=False,
        help_text="Отписался по ссылке из письма или попросил не беспокоить: письма ему не уходят",
    )

    class Meta:
        model = Prospect
        fields = prospects.FIELDS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if isinstance(field, forms.CharField):
                # Пустое — NULL: в списке «—», а не пустая клетка
                field.empty_value = None

        if "kind" in self.fields:
            kind = self.fields["kind"]
            assert isinstance(kind, forms.ChoiceField)
            kind.choices = [("", "— не указано"), *PROSPECT_KINDS.items()]

        if "note" in self.fields:
            self.fields["note"].widget = forms.Textarea(attrs={"rows": 3})

        if "do_not_mail" in self.fields:
            self.fields["do_not_mail"].initial = self.instance.unsubscribed_at is not None

    def clean_tin(self) -> str | None:
        tin = self.cleaned_data.get("tin")

        return "".join(tin.split()) or None if tin else None

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        if not any(data.get(name) for name in prospects.IDENTITY):
            raise ValidationError(
                "Заполните хотя бы одно: название, контактное лицо, телефон, почту или ИНН."
            )

        twin = prospects.find(data, exclude=self.instance.pk)

        if twin is not None:
            raise ValidationError(
                format_html(
                    'Такой уже есть в базе: <a href="{}">{}</a>. Дополните ту запись.',
                    reverse("savdex_admin:crm_prospect_change", args=[twin.pk]),
                    twin.label(),
                )
            )

        return data


class ImportForm(forms.Form):
    file = forms.FileField(
        label="Файл",
        help_text="Excel (.xlsx) или CSV. Первая строка — заголовки столбцов, как в образце.",
    )
    source = forms.CharField(
        label="Откуда база",
        required=False,
        max_length=120,
        help_text="Например «Выставка UzBuild 2026». Пусто — имя файла. "
        "Столбец «Откуда» в файле важнее",
    )
    kind = forms.ChoiceField(
        label="Кто в файле",
        required=False,
        choices=[("", "— как в столбце «Кто это»"), *PROSPECT_KINDS.items()],
        help_text="Для строк, где «Кто это» пусто",
    )


class EmailForm(forms.Form):
    subject = forms.CharField(
        label="Тема", max_length=190, widget=forms.TextInput(attrs={"class": "vTextField"})
    )
    body = forms.CharField(
        label="Текст",
        max_length=20000,
        widget=forms.Textarea(attrs={"rows": 12, "class": "vLargeTextField"}),
        help_text="Метки: {имя} — контактное лицо (нет — название, нет и его — «коллеги»), "
        "{компания} — название. Ссылки пишите как есть: https://savdex.uz/… "
        "Внизу письма сама добавится ссылка «Больше не присылать письма».",
    )
    reply_to = forms.EmailField(
        label="Ответы — на почту",
        required=False,
        max_length=190,
        widget=forms.EmailInput(attrs={"class": "vTextField"}),
        help_text="Куда придут ответы клиентов. Письмо уходит с почты площадки",
    )
    include_converted = forms.BooleanField(label="Писать и тем, кто уже в лидах", required=False)


class MarkForm(forms.Form):
    channel = forms.ChoiceField(
        label="Как писали",
        choices=[(k, v) for k, v in MAILING_CHANNELS.items() if k != "email"],
    )
    note = forms.CharField(
        label="Что отправили",
        required=False,
        max_length=255,
        help_text="Например «Прайс на 2027 год» — видно в истории каждого",
    )


# ── Потенциальные клиенты ──────────────────────────────────────────


@register(Prospect, section="prospects")
class ProspectAdmin(CrmAdmin):
    laravel_model = prospects.MODEL
    title_list = "Потенциальные клиенты"
    title_add = "Новый потенциальный клиент"
    title_change = "Потенциальный клиент"
    change_list_template = "admin/crm/prospect/change_list.html"
    change_form_template = "admin/crm/prospect/change_form.html"

    form = ProspectForm
    fieldsets = (
        ("Кто", {"fields": ("name", "kind", "tin", "contact_person")}),
        ("Связь", {"fields": ("phone", "email", "website", "do_not_mail")}),
        ("О клиенте", {"fields": ("city", "industry", "source", "note")}),
    )
    list_display = (
        "who",
        "tin_",
        "contact",
        "reach",
        "place",
        "mailings",
        "state",
    )
    list_display_links = ("who",)
    list_filter = (State, Mailed, HasEmail, Kind, OnSavdex)
    search_fields = (
        "name",
        "contact_person",
        "tin",
        "phone",
        "email",
        "city",
        "industry",
        "source",
    )
    search_help_text = "Название, контакт, ИНН, телефон, почта, город, отрасль или откуда"
    ordering = ("-created_at", "-id")
    list_per_page = 100
    empty_value_display = EMPTY
    actions = ("send_email", "mark_mailing", "to_leads", "delete_selected")

    def get_search_results(
        self,
        request: HttpRequest,
        queryset: Any,  # noqa: ANN401
        search_term: str,
    ) -> tuple[Any, bool]:
        """
        Номер телефона — по цифрам: «901234567», «90 123 45 67» и
        «+998 (90) 123-45-67» находят одну запись, как ни записан номер в
        базе. Остальное — общим поиском (savdex/search.py).
        """
        digits = re.sub(r"\D", "", search_term)

        if len(digits) >= 7 and re.fullmatch(r"[\d\s()+\-.]+", search_term.strip()):
            tail = digits[-9:]

            return queryset.filter(
                Q(phone__regex=r"\D*".join(tail)) | Q(tin__contains=digits)
            ), False

        return super().get_search_results(request, queryset, search_term)

    # ── Права ──

    def has_lead_permission(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("leads.create")

    def has_import_permission(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("prospects.import")

    # ── Столбцы ──

    @admin.display(description="название / ФИО", ordering="name")
    def who(self, obj: Prospect) -> str:
        kind = PROSPECT_KINDS.get(obj.kind or "", "")

        return format_html(
            '<span class="sx-row-title">{}</span>{}',
            obj.name or EMPTY,
            format_html('<span class="sx-row-sub">{}</span>', kind) if kind else "",
        )

    @admin.display(description="ИНН", ordering="tin")
    def tin_(self, obj: Prospect) -> str | None:
        return obj.tin or None

    @admin.display(description="контактное лицо", ordering="contact_person")
    def contact(self, obj: Prospect) -> str | None:
        return obj.contact_person or None

    @admin.display(description="телефон / почта")
    def reach(self, obj: Prospect) -> str:
        """
        Каждый номер — своей строкой и без переноса («+998 90 / 123-45-67»
        не читается), под ними — почта; чего нет — «—».
        """
        phones = [p.strip() for p in re.split(r"[,;\n]", obj.phone or "") if p.strip()]

        return format_html(
            "{}<br>{}",
            format_html_join(
                "<br>", '<span style="white-space: nowrap">{}</span>', ((p,) for p in phones)
            )
            if phones
            else EMPTY,
            obj.email or EMPTY,
        )

    @admin.display(description="город / отрасль", ordering="city")
    def place(self, obj: Prospect) -> str:
        return format_html(
            '{}<span class="sx-row-sub">{}</span>', obj.city or EMPTY, obj.industry or EMPTY
        )

    @admin.display(description="рассылок", ordering="mailings_count")
    def mailings(self, obj: Prospect) -> str:
        """Сколько и когда последняя."""
        if not obj.mailings_count:
            return format_html('0<span class="sx-row-sub">{}</span>', EMPTY)

        return format_html(
            '<b>{}</b><span class="sx-row-sub">{}</span>',
            obj.mailings_count,
            _date(obj.last_mailed_at),
        )

    @admin.display(description="статус")
    def state(self, obj: Prospect) -> str:
        pills: list[str] = []

        if obj.lead_id is not None:
            pills.append(
                format_html(
                    '<a href="{}">{}</a>',
                    reverse("savdex_admin:crm_lead_change", args=[obj.lead_id]),
                    _badge("В лидах", "success"),
                )
            )

        if obj.unsubscribed_at is not None:
            pills.append(_badge("Не писать", "danger"))

        if obj.company_id is not None:
            pills.append(
                format_html(
                    '<a href="{}">{}</a>',
                    reverse("savdex_admin:data_companyrecord_change", args=[obj.company_id]),
                    _badge("На SavdEx", "info"),
                )
            )

        return format_html_join(" ", "{}", ((p,) for p in pills)) if pills else EMPTY

    @admin.display(description="не писать")
    def do_not_mail(self, obj: Prospect) -> str:
        return _moment(obj.unsubscribed_at) if obj.unsubscribed_at else "нет"

    # ── Список ──

    def _tabs(self, request: HttpRequest) -> list[dict[str, Any]]:
        rows = self.get_queryset(request)

        if term := request.GET.get(SEARCH_VAR):
            rows = self.get_search_results(request, rows, term)[0]

        counts = rows.aggregate(
            all=Count("id"), **{code: Count("id", filter=q) for code, q in _STATE_Q.items()}
        )

        return state_tabs(
            request,
            [
                ("state", "", "Все", counts["all"]),
                *(("state", code, label, counts[code]) for code, label in STATES.items()),
            ],
        )

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        return super().changelist_view(
            request,
            {
                "sx_tabs": self._tabs(request),
                "filter_chips": filter_chips(request),
                "can_import": self.has_import_permission(request),
                "import_url": reverse("savdex_admin:crm_prospect_import"),
                "sample_url": reverse("savdex_admin:crm_prospect_sample"),
                "mailings_url": reverse("savdex_admin:crm_prospectmailing_changelist"),
                **(extra_context or {}),
            },
        )

    # ── Карточка ──

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        if not change:
            obj.created_by = _admin_of(request).id

        stop = bool(form.cleaned_data.get("do_not_mail"))

        if stop and obj.unsubscribed_at is None:
            obj.unsubscribed_at = timezone.now().replace(microsecond=0)
        elif not stop:
            obj.unsubscribed_at = None

        if obj.company_id is None:
            obj.company_id = prospects.savdex_company(form.cleaned_data)

        super().save_model(request, obj, form, change)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        obj = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(obj, Prospect):
            history = list(
                ProspectRecipient.objects.filter(prospect_id=obj.pk)
                .select_related("mailing")
                .order_by("-id")[:100]
            )
            people = _people({r.mailing.sent_by_id for r in history if r.mailing.sent_by_id})
            extra["sx_history"] = [
                {
                    "when": _moment(r.sent_at or r.created_at),
                    "how": MAILING_CHANNELS.get(r.mailing.channel, r.mailing.channel),
                    "what": r.mailing.subject or r.mailing.note or EMPTY,
                    "who": people.get(r.mailing.sent_by_id or 0, EMPTY),
                    "status": _badge(
                        RECIPIENT_STATUSES.get(r.status, r.status),
                        RECIPIENT_TONES.get(r.status, "gray"),
                    ),
                    "error": r.error or "",
                    "url": reverse("savdex_admin:crm_prospectmailing_change", args=[r.mailing_id]),
                }
                for r in history
            ]
            extra["sx_facts"] = [
                ("Рассылок", str(obj.mailings_count)),
                ("Последняя", _moment(obj.last_mailed_at)),
                ("Завёл", _people({obj.created_by}).get(obj.created_by, EMPTY)
                 if obj.created_by else EMPTY),
                ("В базе с", _moment(obj.created_at)),
            ]  # fmt: skip
            extra["sx_lead_url"] = (
                reverse("savdex_admin:crm_lead_change", args=[obj.lead_id]) if obj.lead_id else ""
            )
            extra["sx_company_url"] = (
                reverse("savdex_admin:data_companyrecord_change", args=[obj.company_id])
                if obj.company_id
                else ""
            )
            extra["can_to_lead"] = (
                obj.converted_at is None
                and self.has_lead_permission(request)
                and self.has_change_permission(request, obj)
            )

        return super().change_view(request, object_id, form_url, extra)

    # ── Адреса ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="crm_prospect_import",
            ),
            path(
                "sample/",
                self.admin_site.admin_view(self.sample_view),
                name="crm_prospect_sample",
            ),
            path(
                "<path:object_id>/to-lead/",
                self.admin_site.admin_view(self.to_lead_view),
                name="crm_prospect_to_lead",
            ),
            *super().get_urls(),
        ]

    def sample_view(self, request: HttpRequest) -> HttpResponse:
        """Образец файла для загрузки — заголовки и три примера."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        response = HttpResponse(
            prospects.sample_workbook(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="savdex-prospects-sample.xlsx"'

        return response

    def import_view(self, request: HttpRequest) -> HttpResponse:
        """Загрузка из Excel или CSV: отчёт сразу, повторы склеиваются."""
        if not self.has_import_permission(request):
            raise PermissionDenied

        from savdex.tenders import importer

        report = None
        form = ImportForm(request.POST or None, request.FILES or None)

        if request.method == "POST" and form.is_valid():
            upload = form.cleaned_data["file"]
            table = None

            if upload.size > 10 * 1024 * 1024:
                form.add_error("file", "Файл больше 10 МБ.")
            else:
                try:
                    table = importer.read_table(upload.name, upload.read())
                except Exception:
                    form.add_error("file", "Не удалось прочитать файл: нужен .xlsx или .csv.")

            if table is not None:
                report = prospects.import_rows(
                    table,
                    staff=_admin_of(request),
                    source=form.cleaned_data["source"] or upload.name.rsplit(".", 1)[0][:120],
                    kind=form.cleaned_data["kind"] or None,
                    ip=audit.client_ip(request),
                    file_name=upload.name,
                )
                level = messages.ERROR if report.missing else messages.SUCCESS
                self.message_user(request, report.summary(), level)

        return TemplateResponse(
            request,
            "admin/crm/prospect/import.html",
            {
                **self.admin_site.each_context(request),
                "title": "Загрузка потенциальных клиентов",
                "opts": self.model._meta,
                "form": form,
                "report": report,
                "columns": prospects.COLUMNS,
                "sample_url": reverse("savdex_admin:crm_prospect_sample"),
            },
        )

    def to_lead_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.has_lead_permission(request):
            raise PermissionDenied

        obj = self.get_object(request, object_id)

        if not isinstance(obj, Prospect) or not self.has_change_permission(request, obj):
            raise PermissionDenied

        lead = prospects.to_lead(obj, staff=_admin_of(request), ip=audit.client_ip(request))

        if lead is None:
            self.message_user(request, "Уже в лидах.", messages.WARNING)

            return HttpResponseRedirect(reverse("savdex_admin:crm_prospect_change", args=[obj.pk]))

        self.message_user(
            request, "Лид создан, этап «Новый». Ответственный — вы.", messages.SUCCESS
        )

        return HttpResponseRedirect(reverse("savdex_admin:crm_lead_change", args=[lead.pk]))

    # ── Действия над отмеченными ──

    def _again(self, request: HttpRequest, action: str) -> dict[str, Any]:
        """
        Поля, с которыми окно действия отправляет выбор обратно. Отмеченные
        строки — и при «Выбрать все»: без них Django отвечает «записи не
        выбраны», а весь отбор берёт по select_across и адресу списка.
        """
        return {
            "action": action,
            "select_across": "1" if request.POST.get("select_across") == "1" else "0",
            "selected": request.POST.getlist(helpers.ACTION_CHECKBOX_NAME),
        }

    def _window(
        self, request: HttpRequest, template: str, title: str, context: dict[str, Any]
    ) -> TemplateResponse:
        return TemplateResponse(
            request,
            template,
            {
                **self.admin_site.each_context(request),
                "title": title,
                "opts": self.model._meta,
                "back_url": request.get_full_path(),
                **context,
            },
        )

    @admin.action(description="Отправить письмо…", permissions=["change"])
    def send_email(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> HttpResponse | None:
        staff = _admin_of(request)
        posted = request.POST.get("post") == "yes"
        form = EmailForm(request.POST if posted else None, initial={"reply_to": staff.email})
        include = posted and request.POST.get("include_converted") == "on"
        audience = prospects.email_audience(queryset, include_converted=include)
        ready = prospects.mail_ready()

        if posted and form.is_valid() and ready and audience.count:
            mailing = prospects.queue_email(
                audience.recipients,
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                reply_to=form.cleaned_data["reply_to"] or None,
                staff=staff,
                ip=audit.client_ip(request),
            )
            self.message_user(
                request,
                "Письмо в очереди: "
                + plural(audience.count, "получатель", "получателя", "получателей")
                + f". Уходит фоном, по {prospects.PER_PASS} в минуту.",
                messages.SUCCESS,
            )

            return HttpResponseRedirect(
                reverse("savdex_admin:crm_prospectmailing_change", args=[mailing.pk])
            )

        return self._window(
            request,
            "admin/crm/prospect/send.html",
            "Письмо потенциальным клиентам",
            {
                "form": form,
                "audience": audience,
                "ready": ready,
                "again": self._again(request, "send_email"),
                "per_pass": prospects.PER_PASS,
            },
        )

    @admin.action(description="Отметить рассылку (Telegram, звонок…)…", permissions=["change"])
    def mark_mailing(
        self, request: HttpRequest, queryset: QuerySet[Prospect]
    ) -> HttpResponse | None:
        posted = request.POST.get("post") == "yes"
        form = MarkForm(request.POST if posted else None)
        count = queryset.count()

        if posted and form.is_valid() and count:
            mailing = prospects.mark(
                queryset,
                channel=form.cleaned_data["channel"],
                note=form.cleaned_data["note"],
                staff=_admin_of(request),
                ip=audit.client_ip(request),
            )
            self.message_user(
                request,
                f"Отмечено: {mailing.total}. Счётчик рассылок у каждого +1.",
                messages.SUCCESS,
            )

            return None

        return self._window(
            request,
            "admin/crm/prospect/mark.html",
            "Отметить рассылку",
            {"form": form, "count": count, "again": self._again(request, "mark_mailing")},
        )

    @admin.action(description="Перенести в лиды", permissions=["lead"])
    def to_leads(self, request: HttpRequest, queryset: QuerySet[Prospect]) -> None:
        staff = _admin_of(request)
        ip = audit.client_ip(request)
        done = sum(
            prospects.to_lead(obj, staff=staff, ip=ip) is not None
            for obj in queryset.order_by("id")
        )
        self.message_user(
            request,
            f"В лиды перенесено: {done}. Они на доске лидов, этап «Новый»."
            if done
            else "Все отмеченные уже в лидах.",
            messages.SUCCESS if done else messages.WARNING,
        )


# ── Рассылки по базе ───────────────────────────────────────────────


class Channel(admin.SimpleListFilter):
    title = "как"
    parameter_name = "channel"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(MAILING_CHANNELS.items())

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[ProspectMailing]
    ) -> QuerySet[ProspectMailing]:
        return queryset.filter(channel=self.value()) if self.value() else queryset


@register(ProspectMailing, section="prospects")
class ProspectMailingAdmin(CrmAdmin):
    laravel_model = prospects.MAILING_MODEL
    title_list = "Рассылки по базе"
    title_change = "Рассылка по базе"
    change_form_template = "admin/crm/prospectmailing/change_form.html"

    fields = ("how", "subject", "text", "reply_to", "note", "author", "created", "finished")
    list_display = ("when", "what", "how", "author", "total", "sent_", "failed_", "progress")
    list_display_links = ("when", "what")
    list_filter = (Channel,)
    search_fields = ("subject", "note", "body")
    ordering = ("-created_at", "-id")
    empty_value_display = EMPTY

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        # Ушедшее не правится: только смотреть и останавливать очередь
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return {}

    def get_queryset(self, request: HttpRequest) -> QuerySet[ProspectMailing]:
        queryset: QuerySet[ProspectMailing] = super().get_queryset(request)

        return queryset.select_related("sent_by").annotate(
            waiting=Count("recipients", filter=Q(recipients__status__in=("queued", "sending"))),
            skipped=Count("recipients", filter=Q(recipients__status="skipped")),
        )

    @admin.display(description="когда", ordering="created_at")
    def when(self, obj: ProspectMailing) -> str:
        return _moment(obj.created_at)

    @admin.display(description="что")
    def what(self, obj: ProspectMailing) -> str:
        return obj.subject or obj.note or EMPTY

    @admin.display(description="как", ordering="channel")
    def how(self, obj: ProspectMailing) -> str:
        return MAILING_CHANNELS.get(obj.channel, obj.channel)

    @admin.display(description="кто")
    def author(self, obj: ProspectMailing) -> str:
        return obj.sent_by.name if obj.sent_by is not None else EMPTY

    @admin.display(description="отправлено", ordering="sent")
    def sent_(self, obj: ProspectMailing) -> int:
        return int(obj.sent)

    @admin.display(description="не ушло", ordering="failed")
    def failed_(self, obj: ProspectMailing) -> str:
        return format_html("<b>{}</b>", obj.failed) if obj.failed else "0"

    @admin.display(description="ход")
    def progress(self, obj: ProspectMailing) -> str:
        waiting = int(getattr(obj, "waiting", 0) or 0)

        if waiting:
            return _badge(f"в очереди {waiting}", "info")

        skipped = int(getattr(obj, "skipped", 0) or 0)

        return _badge(
            "закончена" + (f", пропущено {skipped}" if skipped else ""),
            "success" if not obj.failed else "warning",
        )

    @admin.display(description="текст")
    def text(self, obj: ProspectMailing) -> str:
        return format_html('<div style="white-space: pre-wrap">{}</div>', obj.body or EMPTY)

    @admin.display(description="создана")
    def created(self, obj: ProspectMailing) -> str:
        return _moment(obj.created_at)

    @admin.display(description="закончена")
    def finished(self, obj: ProspectMailing) -> str:
        return _moment(obj.finished_at)

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/stop/",
                self.admin_site.admin_view(self.stop_view),
                name="crm_prospectmailing_stop",
            ),
            *super().get_urls(),
        ]

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        obj = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(obj, ProspectMailing):
            rows = ProspectRecipient.objects.filter(mailing=obj)
            counts = dict(rows.values_list("status").annotate(n=Count("id")).order_by())
            extra["sx_counts"] = [
                (RECIPIENT_STATUSES[code], counts.get(code, 0), RECIPIENT_TONES[code])
                for code in RECIPIENT_STATUSES
                if counts.get(code)
            ]
            extra["sx_recipients"] = [
                {
                    "prospect": r.prospect,
                    "url": reverse("savdex_admin:crm_prospect_change", args=[r.prospect_id]),
                    "email": r.email or r.prospect.email or EMPTY,
                    "status": _badge(
                        RECIPIENT_STATUSES.get(r.status, r.status),
                        RECIPIENT_TONES.get(r.status, "gray"),
                    ),
                    "error": r.error or "",
                    "when": _moment(r.sent_at),
                }
                for r in rows.select_related("prospect").order_by("id")[:1000]
            ]
            extra["sx_total"] = obj.total
            extra["can_stop"] = bool(counts.get("queued")) and _admin_of(request).can(
                "prospects.edit"
            )

        return super().change_view(request, object_id, form_url, extra)

    def stop_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not _admin_of(request).can("prospects.edit"):
            raise PermissionDenied

        obj = self.get_object(request, object_id)

        if not isinstance(obj, ProspectMailing):
            raise PermissionDenied

        stopped = prospects.stop(obj, staff=_admin_of(request), ip=audit.client_ip(request))
        self.message_user(
            request,
            f"Рассылка остановлена: не отправлено {stopped}." if stopped else "Очередь уже пуста.",
            messages.SUCCESS if stopped else messages.WARNING,
        )

        return HttpResponseRedirect(
            reverse("savdex_admin:crm_prospectmailing_change", args=[obj.pk])
        )
