"""
Раздел «Тендеры» в админке Django (этап 5; с этапа 6 — вместо раздела
Filament).

Список с отбором по статусу и госзакупкам, правка закупки и загрузка
файлом (Excel или CSV, см. importer.py) с признаком «госзакупка» — на
весь файл галочкой или по столбцу. Права — раздел tenders в AdminAccess;
каждая созданная и изменённая закупка — строка журнала admin_actions,
как у Laravel.

Из Filament (TendersTable): «Опубликовать» — кнопкой в строке и над
отмеченными (дата публикации остаётся или ставится), «В архив» над
отмеченными, удаление — с правом удалять (суперадмин), «На сайте» у
опубликованной; загрузка пишет строку журнала «Загрузка», как
ImportAction::before.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex import audit
from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.tenders import importer
from savdex.tenders.models import STATUSES, Tender

#: Файл больше — не загрузка закупок, а ошибка (или не тот файл)
MAX_UPLOAD = 10 * 1024 * 1024


class ImportForm(forms.Form):
    file = forms.FileField(
        label="Файл",
        help_text="Excel (.xlsx) или CSV. Первая строка — заголовки столбцов, язык любой.",
    )
    all_government = forms.BooleanField(
        label="Все закупки в файле — госзакупки",
        required=False,
        help_text="Иначе — по столбцу «Госзакупка» (да/нет), если он есть.",
    )


@register(Tender, section="tenders")
class TenderAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Tender"
    title_list = "Закупки"
    title_add = "Новая закупка"
    title_change = "Закупка"
    change_list_template = "admin/tenders/tender/change_list.html"

    fieldsets = (
        ("Что закупают", {"fields": ("title", "description", "category", "customer")}),
        ("Госзакупка", {"fields": ("is_government",)}),
        (
            "Условия",
            {"fields": ("budget", "currency", "deadline_at", "country", "location", "source_url")},
        ),
        ("Контакты заказчика", {"fields": ("contact_name", "contact_phone", "contact_email")}),
        ("Публикация", {"fields": ("status", "published_at")}),
    )
    list_display = (
        "tender",
        "category_name",
        "money",
        "deadline",
        "government",
        "state",
        "published",
        "row_actions",
    )
    list_select_related = ("category", "country")
    list_filter = ("is_government", "status", "currency")
    actions = ("publish_selected", "archive_selected", "delete_selected")
    ordering = ("-created_at", "-id")
    search_fields = ("title", "customer", "source_url")
    list_per_page = 50
    raw_id_fields = ()

    @admin.display(description="госзакупка", boolean=True, ordering="is_government")
    def government(self, obj: Tender) -> bool:
        return obj.is_government

    @admin.display(description="тендер", ordering="title")
    def tender(self, obj: Tender) -> str:
        title = obj.title if len(obj.title) <= 80 else obj.title[:80].rstrip() + "..."

        return format_html("{}<br><small>{}</small>", title, obj.customer or "")

    @admin.display(description="категория")
    def category_name(self, obj: Tender) -> str:
        category = obj.category

        return str(category.name()) if category is not None else "—"

    @admin.display(description="бюджет", ordering="budget")
    def money(self, obj: Tender) -> str:
        if obj.budget is None:
            return "—"

        # number_format(…, 0, ',', ' ') и валюта
        return f"{int(obj.budget + Decimal('0.5')):,}".replace(",", " ") + f" {obj.currency}"

    @admin.display(description="приём до", ordering="deadline_at")
    def deadline(self, obj: Tender) -> str:
        if obj.deadline_at is None:
            return "—"

        text = timezone.localtime(obj.deadline_at).strftime("%d.%m.%Y")

        # Tender::isClosed — приём закончился: серым
        if obj.deadline_at < timezone.now():
            return format_html('<span style="color:#6b7280">{}</span>', text)

        return text

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Tender) -> str:
        color = {"published": "#15803d", "archived": "#6b7280"}.get(obj.status, "#b45309")

        return format_html(
            '<b style="color:{}">{}</b>', color, STATUSES.get(obj.status, obj.status)
        )

    @admin.display(description="опубликован", ordering="published_at")
    def published(self, obj: Tender) -> str:
        return timezone.localtime(obj.published_at).strftime("%d.%m.%Y") if obj.published_at else ""

    @admin.display(description="")
    def row_actions(self, obj: Tender) -> str:
        """«На сайте» у опубликованной, «Опубликовать» — у остальных."""
        if obj.status == "published":
            if not obj.slug:
                return ""

            return format_html(
                '<a href="/tenders/{}" target="_blank" rel="noopener">На сайте</a>', obj.slug
            )

        if not self._can_publish:
            return ""

        return format_html(
            '<button type="submit" class="button" formaction="{}" formmethod="post">'
            "Опубликовать</button>",
            reverse("savdex_admin:tenders_tender_publish", args=[obj.pk]),
        )

    _can_publish = False

    # ── Опубликовать, в архив, удалить ──

    def has_publish_permission(self, request: HttpRequest) -> bool:
        return self.has_change_permission(request)

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление — как DeleteBulkAction: только с правом удалять
        return super(SavdexModelAdmin, self).get_actions(request)

    def publish(self, request: HttpRequest, tender: Tender) -> bool:
        """TendersTable::publish: статус и дата публикации, если её не было."""
        if tender.status == "published":
            return False

        before = self.snapshot(tender)
        tender.status = "published"
        tender.published_at = tender.published_at or timezone.now().replace(microsecond=0)
        tender.save()
        self._journal_change(request, tender, before)

        return True

    def _journal_change(self, request: HttpRequest, tender: Tender, before: dict[str, Any]) -> None:
        """AuditObserver::updated у Tender: только изменившиеся поля."""
        after = self.snapshot(tender)
        changed = {k: v for k, v in after.items() if before.get(k) != v}

        if {k for k in changed if k != "updated_at"}:
            self.journal(
                request,
                "updated",
                tender,
                {"before": {k: before.get(k) for k in changed}, "after": changed},
            )

    @admin.action(description="Опубликовать выбранные", permissions=["publish"])
    def publish_selected(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        count = sum(self.publish(request, tender) for tender in queryset)
        messages.success(request, f"Опубликовано: {count}.")

    @admin.action(description="В архив", permissions=["publish"])
    def archive_selected(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        count = 0

        for tender in queryset:
            if tender.status == "archived":
                continue

            before = self.snapshot(tender)
            tender.status = "archived"
            tender.save()
            self._journal_change(request, tender, before)
            count += 1

        messages.success(request, f"В архиве: {count}.")

    def publish_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.has_publish_permission(request):
            raise PermissionDenied

        tender = self.get_object(request, object_id)

        if not isinstance(tender, Tender):
            raise PermissionDenied

        if self.publish(request, tender):
            messages.success(request, "Тендер опубликован.")

        return HttpResponseRedirect(reverse("savdex_admin:tenders_tender_changelist"))

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:  # noqa: ANN401
        """Категории — разделом и подразделом по порядку, страны — по порядку справочника."""
        if db_field.name == "category":
            from savdex.catalogs.models import Category

            kwargs["queryset"] = Category.objects.order_by(
                "parent_id", "sort", "id"
            ).select_related("parent")
        elif db_field.name == "country":
            from savdex.geo.models import Country

            kwargs["queryset"] = Country.objects.order_by("sort", "id")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Перевод, поиск и просмотры — не правка администратора: в журнал не идут."""
        attributes = self.attributes(obj)

        for column in ("title_i18n", "description_i18n", "search_text", "views_count"):
            attributes.pop(column, None)

        return attributes

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        if not change:
            obj.author_id = getattr(request, "admin", None) and request.admin.id  # type: ignore[attr-defined]

        if obj.status == "published" and obj.published_at is None:
            from django.utils import timezone

            obj.published_at = timezone.now().replace(microsecond=0)

        super().save_model(request, obj, form, change)

    # ── Загрузка файлом ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/publish/",
                self.admin_site.admin_view(self.publish_view),
                name="tenders_tender_publish",
            ),
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="tenders_tender_import",
            ),
            *super().get_urls(),
        ]

    def can_import(self, request: HttpRequest) -> bool:
        """
        Загрузка — тому, кто заводит и правит закупки (решение владельца
        для госзакупок, этап 5); у Filament было отдельное tenders.import.
        """
        return self.has_add_permission(request) and self.has_change_permission(request)

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_publish = self.has_publish_permission(request)

        return super().changelist_view(
            request,
            {
                "can_import": self.can_import(request),
                "import_url": reverse("savdex_admin:tenders_tender_import"),
                **(extra_context or {}),
            },
        )

    def import_view(self, request: HttpRequest) -> HttpResponse:
        if not self.can_import(request):
            raise PermissionDenied

        report = None
        form = ImportForm(request.POST or None, request.FILES or None)

        if request.method == "POST" and form.is_valid():
            upload = form.cleaned_data["file"]

            if upload.size > MAX_UPLOAD:
                form.add_error("file", "Файл больше 10 МБ.")
            else:
                try:
                    table = importer.read_table(upload.name, upload.read())
                except Exception:
                    form.add_error("file", "Не удалось прочитать файл: нужен .xlsx или .csv.")
                    table = None

                if table is not None:
                    # ImportAction::before: след загрузки пачкой — строка журнала
                    audit.record(
                        connection,
                        action="imported",
                        section="tenders",
                        actor=_admin_of(request),
                        subject_type=None,
                        subject_id=None,
                        subject_label=None,
                        changes=None,
                        ip=audit.client_ip(request),
                    )
                    report = importer.import_tenders(
                        table,
                        author_id=request.admin.id,  # type: ignore[attr-defined]
                        all_government=form.cleaned_data["all_government"],
                        on_saved=lambda t, adding, before: self._journal_import(
                            request, t, adding, before
                        ),
                    )
                    messages.success(
                        request,
                        f"Загружено: новых {len(report.created)}, обновлено {len(report.updated)}, "
                        f"без изменений {report.unchanged}, не загружено {len(report.failed)}.",
                    )

        return TemplateResponse(
            request,
            "admin/tenders/tender/import.html",
            {
                **self.admin_site.each_context(request),
                "title": "Загрузка закупок из файла",
                "opts": self.model._meta,
                "form": form,
                "report": report,
                "columns": [
                    ("Заголовок", "обязательно"),
                    ("Описание", ""),
                    ("Заказчик", ""),
                    ("Госзакупка", "да / нет"),
                    ("Категория", "название или «Раздел → Подраздел»"),
                    ("Страна", "название или код (uz)"),
                    ("Город", ""),
                    ("Бюджет", "250 000 000, «от 100 до 200 млн»"),
                    ("Валюта", "UZS, USD, сум, $ …"),
                    ("Приём заявок до", "30.10.2026 или «30 октября 2026»"),
                    ("Ссылка на источник", "по ней повторная загрузка обновляет закупку"),
                    ("Контактное лицо, Телефон, Почта", ""),
                    ("Опубликовать", "да — сразу на сайт, иначе черновик"),
                ],
            },
        )

    def _journal_import(
        self, request: HttpRequest, tender: Tender, adding: bool, before: dict[str, Any]
    ) -> None:
        after = self.snapshot(tender)

        if adding:
            self.journal(request, "created", tender, {"after": after})

            return

        previous = self.snapshot(_Frozen(before, tender))
        changed = {k: v for k, v in after.items() if previous.get(k) != v}

        if {k for k in changed if k not in ("updated_at",)}:
            self.journal(
                request,
                "updated",
                tender,
                {"before": {k: previous.get(k) for k in changed}, "after": changed},
            )


class _Frozen:
    """Снимок закупки до загрузки — в виде, который понимает attributes()."""

    def __init__(self, values: dict[str, Any], model: Tender) -> None:
        self._meta = model._meta

        for field in model._meta.concrete_fields:
            setattr(self, field.attname, values.get(field.attname, getattr(model, field.attname)))
