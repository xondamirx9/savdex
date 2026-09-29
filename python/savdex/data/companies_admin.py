"""
Компании в админке Django (этап 6) — вместо раздела Filament «Компании».

Форма правит то, что компания пишет о себе сама (поддержка поправляет
ИНН, дописывает адрес, чистит описание). Уровень верификации, партнёрство
и блокировка — не поля, а решения: они на странице компании отдельными
кнопками, уходят владельцу уведомлением (верификация) и пишутся в журнал.

- «Верификация» — уровень руками модератора: бейдж «Проверена» купить
  нельзя ни на одном тарифе;
- «Партнёрство» — вид и порядок на странице «Партнёры»;
- «Логотип» и «Обложка» — загрузить (ImageStore) или снять;
- «Эмблема» — плашка с инициалами в цвете региона вместо логотипа
  (CompanyEmblem), массово — только компаниям без логотипа;
- «Заблокировать» с причиной (объявления уходят из выдачи) и
  «Разблокировать»;
- список: вкладки «Поставщики» и «Покупатели» — отбором «роль», менеджер
  направления открывает список сразу на своей;
- удаление в корзину, вернуть и удалить насовсем — с правом удалять;
- выгрузка — CompanyExporter, право companies.export; загрузка таблицей —
  CompanyImporter (savdex/data/company_import.py), право companies.import.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex import audit
from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.admin import _badge
from savdex.data.models import (
    FALLBACK_TYPES,
    LEGAL_FORMS,
    LEVELS,
    PARTNER_TIERS,
    CompanyRecord,
)
from savdex.guards import allowed_writes

MIN_BLOCK_REASON = 10


def _type_choices() -> list[tuple[str, str]]:
    """Company::typeOptions: справочник типов, пока пуст — запасной список."""
    from savdex.catalogs.models import CompanyType

    found = [(t.code, t.name()) for t in CompanyType.objects.filter(is_active=True)]

    return found or list(FALLBACK_TYPES.items())


def _country_choices() -> list[tuple[int, str]]:
    """Со снятыми с публикации: иначе поле у старой компании обнулилось бы."""
    from savdex.geo.models import Country

    return [(c.pk, c.name()) for c in Country.objects.order_by("sort", "id")]


def _city_choices(country_id: int | None) -> list[tuple[int, str]]:
    from savdex.geo.models import City

    if country_id is None:
        return []

    return [
        (c.pk, c.name()) for c in City.objects.filter(country_id=country_id).order_by("sort", "id")
    ]


class CompanyForm(forms.ModelForm):  # type: ignore[type-arg]
    type = forms.ChoiceField(label="Тип", required=False)
    country_id = forms.TypedChoiceField(
        label="Страна", coerce=int, required=False, empty_value=None
    )
    city_id = forms.TypedChoiceField(
        label="Город",
        coerce=int,
        required=False,
        empty_value=None,
        help_text="Город — той же страны; сменили страну — выберите город заново",
    )

    class Meta:
        model = CompanyRecord
        fields = (
            "name",
            "legal_form",
            "legal_name",
            "tin",
            "type",
            "primary_role",
            "founded_year",
            "country_id",
            "city_id",
            "address",
            "phone",
            "email",
            "website",
            "contact_person",
            "telegram",
            "whatsapp",
            "description",
            "source_note",
            "employees_range",
            "response_time_hours",
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if "name" not in self.fields:
            return

        kind = self.fields["type"]
        assert isinstance(kind, forms.ChoiceField)
        kind.choices = [("", "—"), *_type_choices()]
        country = self.fields["country_id"]
        assert isinstance(country, forms.TypedChoiceField)
        country.choices = [("", "—"), *_country_choices()]
        # Города — страны формы (присланной или сохранённой)
        chosen = self.data.get("country_id") if self.is_bound else self.instance.country_id
        city = self.fields["city_id"]
        assert isinstance(city, forms.TypedChoiceField)
        city.choices = [
            ("", "—"),
            *_city_choices(int(str(chosen)) if str(chosen or "").isdigit() else None),
        ]

    def clean_type(self) -> str | None:
        return self.cleaned_data.get("type") or None

    def clean_founded_year(self) -> int | None:
        year = self.cleaned_data.get("founded_year")

        if year is not None and not 1800 <= year <= date.today().year:
            raise forms.ValidationError(f"От 1800 до {date.today().year}.")

        return year

    def clean_response_time_hours(self) -> int | None:
        hours = self.cleaned_data.get("response_time_hours")

        if hours is not None and hours < 0:
            raise forms.ValidationError("Не меньше нуля.")

        return hours


class ImportForm(forms.Form):
    file = forms.FileField(
        label="Файл",
        help_text="Excel (.xlsx) или CSV. Первая строка — заголовки столбцов, язык любой.",
    )


class RoleTab(admin.SimpleListFilter):
    """Вкладки «Все», «Поставщики», «Покупатели»: у «оба» — в обеих."""

    title = "вкладка"
    parameter_name = "tab"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("all", "Все"), ("suppliers", "Поставщики"), ("buyers", "Покупатели")]

    def value(self) -> str | None:
        value = super().value()

        if value is not None:
            return value

        # Менеджер направления открывает список сразу на своей вкладке
        role = _admin_of(self.request).role if hasattr(self, "request") else None

        return {"supplier_manager": "suppliers", "buyer_manager": "buyers"}.get(role or "", "all")

    def __init__(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        self.request = request
        super().__init__(request, *args, **kwargs)

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        if self.value() == "suppliers":
            return queryset.filter(primary_role__in=("supplier", "both"))

        if self.value() == "buyers":
            return queryset.filter(primary_role__in=("buyer", "both"))

        return queryset

    def choices(self, changelist: Any) -> Any:  # noqa: ANN401
        for code, label in self.lookups(self.request, None):
            yield {
                "selected": self.value() == code,
                "query_string": changelist.get_query_string({self.parameter_name: code}),
                "display": label,
            }


def _simple(title_: str, name: str, options: dict[Any, str], cast: Any = str) -> type:  # noqa: ANN401
    class Choice(admin.SimpleListFilter):
        title = title_
        parameter_name = name

        def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
            return [(str(k), v) for k, v in options.items()]

        def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
            value = self.value()

            return queryset.filter(**{name: cast(value)}) if value else queryset

    return Choice


class Trashed(admin.SimpleListFilter):
    title = "корзина"
    parameter_name = "trashed"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "В корзине"), ("with", "Вместе с удалёнными")]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        if self.value() == "1":
            return queryset.filter(deleted_at__isnull=False)

        if self.value() == "with":
            return queryset

        return queryset.filter(deleted_at__isnull=True)


LEVEL_TONES = {3: "warning", 2: "success"}
PARTNER_TONES = {"general": "warning", "multi": "success"}
LEGAL_TONES = {"individual": "info", "freelancer": "warning"}


@register(CompanyRecord, section="companies")
class CompanyAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Company"
    title_list = "Компании"
    title_add = "Новая компания"
    title_change = "Компания"
    change_form_template = "admin/data/companyrecord/change_form.html"
    change_list_template = "admin/data/companyrecord/change_list.html"

    form = CompanyForm
    fieldsets = (
        (
            "Компания",
            {
                "fields": (
                    "name",
                    "legal_form",
                    "legal_name",
                    "tin",
                    "type",
                    "primary_role",
                    "founded_year",
                )
            },
        ),
        ("Где находится", {"fields": ("country_id", "city_id", "address")}),
        (
            "Контакты",
            {
                "fields": ("phone", "email", "website", "contact_person", "telegram", "whatsapp"),
                "description": "Основные контакты карточки. Развёрнутый список компания ведёт "
                "у себя в кабинете.",
            },
        ),
        (
            "О компании",
            {"fields": ("description", "source_note", "employees_range", "response_time_hours")},
        ),
    )
    list_display = (
        "company",
        "form_kind",
        "city",
        "level",
        "partner",
        "listings",
        "stars",
        "state",
    )
    list_filter = (
        RoleTab,
        _simple("верификация", "verification_level", LEVELS, int),
        _simple("партнёрство", "partner_tier", PARTNER_TIERS),
        _simple("форма", "legal_form", LEGAL_FORMS),
        _simple("статус", "status", {"active": "Активна", "blocked": "Заблокирована"}),
        Trashed,
    )
    search_fields = ("name",)
    ordering = ("-created_at", "-id")
    list_per_page = 50
    actions = ("emblems_selected", "delete_selected")

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление — как DeleteBulkAction: только с правом удалять
        return super(SavdexModelAdmin, self).get_actions(request)

    @admin.action(description="Сгенерировать эмблемы", permissions=["change"])
    def emblems_selected(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        """Компаниям без логотипа — плашка с инициалами; настоящий логотип дороже."""
        from savdex.data import emblem

        done = skipped = 0

        for company in queryset:
            if company.logo_path is not None:
                skipped += 1
                continue

            emblem.assign(company.pk, admin_id=_admin_of(request).id, request=request)
            done += 1

        messages.success(
            request,
            f"Эмблем установлено: {done}."
            + (f" Пропущено с логотипом: {skipped}." if skipped else ""),
        )

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        attributes = self.attributes(obj)
        attributes.pop("search_text", None)

        return attributes

    # ── Список ──

    @admin.display(description="компания", ordering="name")
    def company(self, obj: CompanyRecord) -> str:
        return format_html(
            "{}<br><small>{}</small>", obj.name, f"ИНН {obj.tin}" if obj.tin else "ИНН не указан"
        )

    @admin.display(description="форма", ordering="legal_form")
    def form_kind(self, obj: CompanyRecord) -> str:
        return _badge(
            LEGAL_FORMS.get(obj.legal_form or "legal", obj.legal_form),
            LEGAL_TONES.get(obj.legal_form, "gray"),
        )

    @admin.display(description="город")
    def city(self, obj: CompanyRecord) -> str:
        from savdex.geo.models import City

        city = City.objects.filter(pk=obj.city_id).first() if obj.city_id else None

        return city.name() if city is not None else "—"

    @admin.display(description="верификация", ordering="verification_level")
    def level(self, obj: CompanyRecord) -> str:
        level = int(obj.verification_level or 0)

        return _badge(LEVELS.get(level, str(level)), LEVEL_TONES.get(level, "gray"))

    @admin.display(description="партнёрство", ordering="partner_tier")
    def partner(self, obj: CompanyRecord) -> str:
        if obj.partner_tier is None:
            return "—"

        return _badge(
            PARTNER_TIERS.get(obj.partner_tier, "—"), PARTNER_TONES.get(obj.partner_tier, "info")
        )

    @admin.display(description="объявлений")
    def listings(self, obj: CompanyRecord) -> int:
        from savdex.data.models import Listing

        return Listing.objects.filter(company_id=obj.pk, deleted_at__isnull=True).count()

    @admin.display(description="рейтинг", ordering="rating")
    def stars(self, obj: CompanyRecord) -> str:
        return f"{obj.rating:.1f}" if obj.rating else "—"

    @admin.display(description="статус", ordering="status")
    def state(self, obj: CompanyRecord) -> str:
        active = obj.status == "active"

        return _badge("Активна" if active else "Заблокирована", "success" if active else "danger")

    # ── Удаление ──

    def delete_model(self, request: HttpRequest, obj: Any) -> None:  # noqa: ANN401
        """SoftDeletes: deleted_at и updated_at; строка журнала «удалено»."""
        stamp = timezone.now().replace(microsecond=0)

        with allowed_writes("companies"):
            CompanyRecord.objects.filter(pk=obj.pk).update(deleted_at=stamp, updated_at=stamp)

        self.journal(request, "deleted", obj)
        request._savdex_done = f"Удалено: {obj}"  # type: ignore[attr-defined]

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        for obj in list(queryset):
            self.delete_model(request, obj)

    # ── Решения и файлы ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/act/",
                self.admin_site.admin_view(self.act_view),
                name="data_companyrecord_act",
            ),
            path(
                "export/",
                self.admin_site.admin_view(self.export_view),
                name="data_companyrecord_export",
            ),
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="data_companyrecord_import",
            ),
            *super().get_urls(),
        ]

    def get_object(self, request: HttpRequest, object_id: str, from_field: Any = None) -> Any:  # noqa: ANN401
        """Запись — и из корзины: её можно вернуть или удалить насовсем."""
        try:
            return CompanyRecord.objects.get(pk=int(object_id))
        except (CompanyRecord.DoesNotExist, ValueError):
            return None

    def _changed(
        self, request: HttpRequest, company: CompanyRecord, before: dict[str, Any]
    ) -> None:
        """AuditObserver::updated у Company: только то, что поменялось."""
        after = self.snapshot(company)
        changed = {k: v for k, v in after.items() if before.get(k) != v and k != "updated_at"}

        if changed:
            self.journal(
                request,
                audit.update_action(before, changed),
                company,
                {"before": {k: before.get(k) for k in changed}, "after": changed},
            )

    def act_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        company = self.get_object(request, object_id)

        if (
            request.method != "POST"
            or not isinstance(company, CompanyRecord)
            or not self.has_change_permission(request, company)
        ):
            raise PermissionDenied

        from savdex.data import company_actions

        page = reverse("savdex_admin:data_companyrecord_change", args=[company.pk])
        todo = request.POST.get("act", "")
        before = self.snapshot(company)

        if todo == "verify":
            level = request.POST.get("level", "")

            if not level.isdigit() or int(level) not in LEVELS:
                messages.error(request, "Выберите уровень.")

                return HttpResponseRedirect(page)

            company_actions.verify(request, company, int(level))
            messages.success(request, "Уровень обновлён.")
        elif todo == "partner":
            tier = request.POST.get("tier", "none")
            sort = request.POST.get("sort", "0")
            company_actions.partner(
                company, tier if tier in PARTNER_TIERS else None, int(sort) if sort.isdigit() else 0
            )
            messages.success(
                request,
                "Компания убрана из партнёров."
                if company.partner_tier is None
                else f"Сохранено: {PARTNER_TIERS[company.partner_tier]}",
            )
        elif todo == "emblem":
            from savdex.data import emblem

            emblem.assign(company.pk, admin_id=_admin_of(request).id, request=request)
            messages.success(request, "Эмблема установлена.")
            # Строку «изменено» пишет сама эмблема, как Eloquent-сохранение
            return HttpResponseRedirect(page)
        elif todo in ("logo", "cover"):
            upload = request.FILES.get("file")
            outcome = company_actions.picture(company, todo, upload)
            (messages.success if outcome.endswith(".") else messages.error)(request, outcome)
        elif todo == "block":
            if company.status == "active":
                reason = (request.POST.get("reason") or "").strip()

                if len(reason) < MIN_BLOCK_REASON:
                    messages.error(
                        request,
                        f"Напишите причину блокировки — не короче {MIN_BLOCK_REASON} знаков: "
                        "компания увидит её в кабинете.",
                    )

                    return HttpResponseRedirect(page)

                company_actions.block(company, reason)
                messages.success(request, "Компания заблокирована.")
            else:
                company_actions.unblock(company)
                messages.success(request, "Компания разблокирована.")
        elif todo in ("restore", "force") and company.deleted_at is not None:
            if not self.has_delete_permission(request, company):
                raise PermissionDenied

            if todo == "restore":
                company_actions.restore(company)
                self.journal(request, "restored", company)
                messages.success(request, "Компания восстановлена.")
            else:
                company_actions.force_delete(company)
                self.journal(request, "force_deleted", company)
                messages.success(request, "Компания удалена насовсем.")

                return HttpResponseRedirect(
                    reverse("savdex_admin:data_companyrecord_changelist") + "?trashed=1"
                )

            return HttpResponseRedirect(page)
        else:
            raise PermissionDenied

        company.refresh_from_db()
        self._changed(request, company, before)

        return HttpResponseRedirect(page)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        company = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(company, CompanyRecord):
            extra["can_act"] = self.has_change_permission(request, company)
            extra["levels"] = list(LEVELS.items())
            extra["tiers"] = list(PARTNER_TIERS.items())
            extra["trashed"] = company.deleted_at is not None
            extra["can_trash"] = company.deleted_at is not None and self.has_delete_permission(
                request, company
            )
            extra["min_block"] = MIN_BLOCK_REASON

        return super().change_view(request, object_id, form_url, extra)

    # ── Выгрузка ──

    def export_view(self, request: HttpRequest) -> HttpResponse:
        """CompanyExporter: список с отборами экрана, право companies.export."""
        if not _admin_of(request).can("companies.export"):
            raise PermissionDenied

        from savdex import admin_export
        from savdex.data.company_actions import export_columns

        query = request.GET.copy()
        file_format = query.pop("format", ["xlsx"])[-1]
        request.GET = query  # type: ignore[assignment]
        records = self.get_changelist_instance(request).get_queryset(request).order_by("-id")

        return admin_export.respond(
            request,
            section="companies",
            filename="companies",
            file_format="csv" if file_format == "csv" else "xlsx",
            columns=export_columns(),
            records=records.iterator(),
        )

    def import_view(self, request: HttpRequest) -> HttpResponse:
        """
        CompanyImporter: таблица компаний сразу, отчёт с номерами строк;
        право companies.import, строка журнала «Загрузка».
        """
        if not _admin_of(request).can("companies.import"):
            raise PermissionDenied

        from django.db import connection
        from django.template.response import TemplateResponse

        from savdex import audit
        from savdex.data import company_import
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
                audit.record(
                    connection,
                    action="imported",
                    section="companies",
                    actor=_admin_of(request),
                    ip=audit.client_ip(request),
                )
                report = company_import.import_companies(
                    table, admin_id=_admin_of(request).id, request=request
                )
                messages.success(request, report.summary())

        return TemplateResponse(
            request,
            "admin/data/companyrecord/import.html",
            {
                **self.admin_site.each_context(request),
                "title": "Загрузка компаний из файла",
                "opts": self.model._meta,
                "form": form,
                "report": report,
                "columns": company_import.COLUMNS,
            },
        )

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        query = request.GET.urlencode()

        return super().changelist_view(
            request,
            {
                "can_import": _admin_of(request).can("companies.import"),
                "import_url": reverse("savdex_admin:data_companyrecord_import"),
                "can_export": _admin_of(request).can("companies.export"),
                "export_url": reverse("savdex_admin:data_companyrecord_export")
                + (f"?{query}" if query else ""),
                "export_sep": "&" if query else "?",
                **(extra_context or {}),
            },
        )
