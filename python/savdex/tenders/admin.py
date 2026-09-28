"""
Раздел «Закупки» в админке Django (этап 5).

Список с отбором по статусу и госзакупкам, правка закупки и загрузка
файлом (Excel или CSV, см. importer.py) с признаком «госзакупка» — на
весь файл галочкой или по столбцу. Права — раздел tenders в AdminAccess;
каждая созданная и изменённая закупка — строка журнала admin_actions,
как у Laravel.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse

from savdex.adminsite import SavdexModelAdmin, register
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
    list_display = ("title", "customer", "government", "state", "deadline_at", "views_count")
    list_filter = ("is_government", "status", "currency")
    search_fields = ("title", "customer", "source_url")
    list_per_page = 50
    raw_id_fields = ()

    @admin.display(description="госзакупка", boolean=True, ordering="is_government")
    def government(self, obj: Tender) -> bool:
        return obj.is_government

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Tender) -> str:
        return STATUSES.get(obj.status, obj.status)

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
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="tenders_tender_import",
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        return super().changelist_view(
            request,
            {
                "can_import": self.has_add_permission(request),
                "import_url": reverse("savdex_admin:tenders_tender_import"),
                **(extra_context or {}),
            },
        )

    def import_view(self, request: HttpRequest) -> HttpResponse:
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
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
