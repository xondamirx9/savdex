"""
Данные площадки в админке Django (этап 6) — вместо разделов Filament
группы «Данные».

Объявления: список без пустых черновиков мастера, отбор по статусу,
типу, источнику и корзине; решения модератора на странице объявления —
«Одобрить» (и отклонённое: отказ окончателен для автора, не для
модератора), «Вернуть на исправление» и «Отклонить» с причиной не короче
10 знаков, владельцу — уведомление; правка формой с текстами по языкам
(пустые переводы не хранятся); фотографии — загрузить, обложка,
удалить; удаление в корзину, вернуть и удалить насовсем — с правом
удалять. Решает модератор, а загруженное из Excel — и тот, кто вправе
загружать. «Загрузить» — книги Excel с фотографиями в строках товаров
(savdex/data/workbook.py, как ListingWorkbookImport), право listings.import;
«Выгрузить» — ListingExporter, право listings.export.

IT-задачи: список с отбором по статусу и виду услуги, правка (создаются
только из кабинета — задача от имени заказчика), «Снять» с витрины для
спама и нарушений (заказчик увидит её в кабинете архивной), «На сайте» у
открытой, удаление — с правом удалять.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.admin import _badge
from savdex.data.models import (
    IT_STATUSES,
    LIFETIME_DAYS,
    LISTING_MAX,
    LISTING_SOURCES,
    LISTING_STATUSES,
    LISTING_TEXTS,
    SERVICE_TYPES,
    ItTask,
    Listing,
)
from savdex.guards import allowed_writes
from savdex.web import locales


class StackField(forms.CharField):
    """TagsInput: теги через запятую — список в JSON."""

    def prepare_value(self, value: Any) -> Any:  # noqa: ANN401
        if isinstance(value, list):
            return ", ".join(str(tag) for tag in value)

        return value

    def to_python(self, value: Any) -> Any:  # noqa: ANN401
        text = super().to_python(value) or ""
        tags = [tag.strip() for tag in str(text).split(",") if tag.strip()]

        return tags or None


class ItTaskForm(forms.ModelForm):  # type: ignore[type-arg]
    stack = StackField(label="Стек", required=False, help_text="Через запятую: Laravel, React…")

    class Meta:
        model = ItTask
        fields = (
            "title",
            "description",
            "service_type",
            "stack",
            "budget_type",
            "budget_from",
            "budget_to",
            "currency",
            "deadline_at",
            "status",
        )

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        for name in ("budget_from", "budget_to"):
            value = data.get(name)

            if value is not None and value < 0:
                self.add_error(name, "Не меньше нуля.")

        return data


class ItStatus(admin.SimpleListFilter):
    title = "статус"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(IT_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(status=self.value()) if self.value() else queryset


class ServiceType(admin.SimpleListFilter):
    title = "вид услуги"
    parameter_name = "service"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(SERVICE_TYPES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(service_type=self.value()) if self.value() else queryset


@register(ItTask, section="ittasks")
class ItTaskAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\ItTask"
    title_list = "IT-задачи"
    title_change = "IT-задача"

    form = ItTaskForm
    fieldsets = (
        ("Задача", {"fields": ("title", "description", "service_type", "stack")}),
        (
            "Условия",
            {"fields": ("budget_type", "budget_from", "budget_to", "currency", "deadline_at")},
        ),
        ("Статус", {"fields": ("status",)}),
    )
    list_display = ("task", "service", "responses_count", "state", "published", "row_actions")
    list_filter = (ItStatus, ServiceType)
    list_select_related = ("company",)
    search_fields = ("title",)
    ordering = ("-created_at", "-id")
    list_per_page = 50
    actions = ("delete_selected",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Задача — от имени заказчика: заводится только в кабинете
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление — как DeleteBulkAction: только с правом удалять
        return super(SavdexModelAdmin, self).get_actions(request)

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Поиск и просмотры — не правка администратора: в журнал не идут."""
        attributes = self.attributes(obj)

        for column in ("search_text", "views_count"):
            attributes.pop(column, None)

        return attributes

    @admin.display(description="задача", ordering="title")
    def task(self, obj: ItTask) -> str:
        title = obj.title if len(obj.title) <= 80 else obj.title[:80].rstrip() + "..."
        company = obj.company

        return format_html(
            "{}<br><small>{}</small>",
            title,
            company.name if company is not None and company.deleted_at is None else "",
        )

    @admin.display(description="вид услуги", ordering="service_type")
    def service(self, obj: ItTask) -> str:
        return SERVICE_TYPES.get(obj.service_type, obj.service_type)

    @admin.display(description="статус", ordering="status")
    def state(self, obj: ItTask) -> str:
        return _badge(
            IT_STATUSES.get(obj.status, obj.status), "success" if obj.status == "active" else "gray"
        )

    @admin.display(description="опубликована", ordering="published_at")
    def published(self, obj: ItTask) -> str:
        return timezone.localtime(obj.published_at).strftime("%d.%m.%Y") if obj.published_at else ""

    @admin.display(description="")
    def row_actions(self, obj: ItTask) -> str:
        """«На сайте» и «Снять» — у открытой задачи."""
        if obj.status != "active":
            return ""

        link = (
            format_html(
                '<a href="/it-services/{}" target="_blank" rel="noopener">На сайте</a> ', obj.slug
            )
            if obj.slug
            else ""
        )
        button = (
            format_html(
                '<button type="submit" class="button" formaction="{}" formmethod="post" '
                "onclick=\"return confirm('Снять задачу с витрины? Заказчик увидит её в кабинете "
                "архивной.')\">Снять</button>",
                reverse("savdex_admin:data_ittask_archive", args=[obj.pk]),
            )
            if self._can_archive
            else ""
        )

        return format_html("{}{}", link, button)

    _can_archive = False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_archive = self.has_change_permission(request)

        return super().changelist_view(request, extra_context)

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/archive/",
                self.admin_site.admin_view(self.archive_view),
                name="data_ittask_archive",
            ),
            *super().get_urls(),
        ]

    def archive_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """«Снять»: в архив и дата закрытия — для спама и нарушений."""
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied

        task = self.get_object(request, object_id)

        if not isinstance(task, ItTask):
            raise PermissionDenied

        if task.status == "active":
            before = self.snapshot(task)
            task.status = "archived"
            task.closed_at = timezone.now().replace(microsecond=0)
            task.save()
            after = self.snapshot(task)
            changed = {k: v for k, v in after.items() if before.get(k) != v}
            self.journal(
                request,
                "updated",
                task,
                {"before": {k: before.get(k) for k in changed}, "after": changed},
            )
            messages.success(request, "Задача снята с витрины.")

        return HttpResponseRedirect(reverse("savdex_admin:data_ittask_changelist"))


# ── Объявления ───────────────────────────────────────────────────────


#: Причина решения — не отписка (у Filament minLength 10)
MIN_REASON = 10

#: Языки, кроме русского: переводы — в столбцах *_i18n
OTHER_LOCALES = tuple(code for code in locales.CODES if code != locales.DEFAULT)

#: Currencies::ALL — подписи по-русски
CURRENCY_LABELS = {
    "UZS": "сум",
    "USD": "доллар США",
    "EUR": "евро",
    "CNY": "юань",
    "TRY": "турецкая лира",
    "RUB": "рубль",
    "KZT": "тенге",
}

LISTING_TONES = {
    "active": "success",
    "moderation": "warning",
    "needs_changes": "warning",
    "rejected": "danger",
}


def _category_choices() -> list[tuple[int, str]]:
    """Активные категории, «Раздел → Подраздел», по алфавиту подписи."""
    from savdex.catalogs.models import Category

    labels = {}

    for category in Category.objects.filter(is_active=True).select_related("parent"):
        parent = category.parent
        labels[category.pk] = (
            f"{parent.name()} → {category.name()}" if parent is not None else category.name()
        )

    return sorted(labels.items(), key=lambda item: item[1])


def _city_choices() -> list[tuple[int, str]]:
    """Активные города со страной в подписи: «Триполи» без страны — загадка."""
    from savdex.geo.models import City

    return [
        (city.pk, f"{city.country.name()} → {city.name()}")
        for city in City.objects.filter(is_active=True)
        .select_related("country")
        .order_by("country_id", "sort", "id")
    ]


class ListingFormBase(forms.ModelForm):  # type: ignore[type-arg]
    """
    ListingForm: модератор скорее читает, чем правит, — но мелкую правку
    (опечатка, не та валюта) сделать можно. Статуса в форме нет: решения
    уходят уведомлением владельцу — это кнопки, а не список рядом с ценой.
    Тексты — по языку: русский в самих столбцах, остальные в *_i18n.
    """

    category_id = forms.TypedChoiceField(label="Категория", coerce=int, choices=())
    owner = forms.CharField(
        label="Компания",
        max_length=190,
        help_text=(
            "Название или ИНН компании из раздела «Компании». Смените, чтобы передать "
            "объявление настоящему владельцу: оно появится в его кабинете, отклики "
            "пойдут ему."
        ),
    )
    city_id = forms.TypedChoiceField(
        label="Город", coerce=int, choices=(), required=False, empty_value=None
    )
    title = forms.CharField(label="Заголовок", min_length=10, max_length=LISTING_MAX["title"])
    description = forms.CharField(
        label="Описание",
        min_length=30,
        max_length=LISTING_MAX["description"],
        widget=forms.Textarea(attrs={"rows": 8}),
    )
    delivery_terms = forms.CharField(
        label="Условия поставки",
        required=False,
        max_length=LISTING_MAX["delivery_terms"],
        empty_value=None,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    payment_terms = forms.CharField(
        label="Условия оплаты",
        required=False,
        max_length=LISTING_MAX["payment_terms"],
        empty_value=None,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    currency = forms.ChoiceField(label="Валюта", choices=list(CURRENCY_LABELS.items()))
    expires_at = forms.DateTimeField(
        label="Действует до",
        required=False,
        help_text="После этой даты объявление уходит в «истёкшие»",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Listing
        fields = (
            "type",
            "category_id",
            "title",
            "description",
            "delivery_terms",
            "payment_terms",
            "price_negotiable",
            "price",
            "bundle_price",
            "currency",
            "unit",
            "min_order",
            "city_id",
            "expires_at",
            "moderation_note",
        )
        help_texts: ClassVar[dict[str, str]] = {
            "bundle_price": "Необязательно: для товаров, продающихся набором",
            "moderation_note": "Текст виден владельцу объявления. Заполняется при отказе.",
            "unit": "шт, тонна, м³",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if "title" not in self.fields:
            return

        if "owner" in self.fields:
            owner = getattr(self.instance, "company", None) if self.instance.pk else None
            self.fields["owner"].initial = owner.name if owner is not None else ""

        category = self.fields["category_id"]
        assert isinstance(category, forms.TypedChoiceField)
        category.choices = [("", "—"), *_category_choices()]
        city = self.fields["city_id"]
        assert isinstance(city, forms.TypedChoiceField)
        city.choices = [("", "—"), *_city_choices()]

        for name in LISTING_TEXTS:
            stored = getattr(self.instance, f"{name}_i18n", None) or {}

            for code in OTHER_LOCALES:
                self.fields[f"{name}_{code}"].initial = stored.get(code, "")

    def clean_owner(self) -> int:
        from savdex.data.workbook import company_id

        name = str(self.cleaned_data.get("owner") or "").strip()
        current = getattr(self.instance, "company", None)

        # Название не трогали — компания та же (даже если у двух компаний
        # одинаковые названия, объявление не перескочит к другой)
        if current is not None and name == current.name:
            return int(current.pk)

        found = company_id(name)

        if found is None:
            raise forms.ValidationError(
                f"Компании «{name}» нет в разделе «Компании» — проверьте название или ИНН."
            )

        return found

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        for name in ("price", "bundle_price", "min_order"):
            value = data.get(name)

            if value is not None and value < 0:
                self.add_error(name, "Не меньше нуля.")

        # Пустая цена — только вместе с «договорной»: иначе на витрине пусто
        if not data.get("price_negotiable") and data.get("price") is None:
            self.add_error("price", "Укажите цену или отметьте «Цена договорная».")

        return data

    def save(self, commit: bool = True) -> Any:  # noqa: ANN401
        if self.cleaned_data.get("owner"):
            self.instance.company_id = self.cleaned_data["owner"]

        # Договорная цена: поле цены в Filament выключено и не пишется
        if self.cleaned_data.get("price_negotiable"):
            self.instance.price = self.initial.get("price", self.instance.price)

        # EditListing::mutateFormDataBeforeSave: пустые переводы не хранятся
        for name in LISTING_TEXTS:
            values = {
                code: text
                for code in OTHER_LOCALES
                if (text := str(self.cleaned_data.get(f"{name}_{code}") or "").strip())
            }
            setattr(self.instance, f"{name}_i18n", values or None)

        return super().save(commit)


def _language_fields() -> dict[str, forms.Field]:
    """Поля «заголовок_en» и т. п. — копии русских, необязательные."""
    fields: dict[str, forms.Field] = {}

    for name in LISTING_TEXTS:
        base = ListingFormBase.base_fields[name]

        for code in OTHER_LOCALES:
            fields[f"{name}_{code}"] = forms.CharField(
                label=base.label,
                required=False,
                max_length=LISTING_MAX[name],
                widget=base.widget.__class__(attrs=dict(base.widget.attrs)),
            )

    return fields


ListingForm = type("ListingForm", (ListingFormBase,), _language_fields())


#: ListingExporter — подписи статусов (прочее — «Снято»)
EXPORT_STATUSES = {
    "active": "Активно",
    "moderation": "На проверке",
    "draft": "Черновик",
    "rejected": "Отклонено",
    "expired": "Истекло",
}


def _category_names() -> dict[int, str]:
    from savdex.catalogs.models import Category

    return {category.pk: category.name() for category in Category.objects.all()}


class _Books(forms.ClearableFileInput):
    allow_multiple_selected = True


class BooksField(forms.FileField):
    """Несколько книг за раз: каталог удобнее резать на файлы по разделам."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("widget", _Books(attrs={"accept": XLSX_TYPE}))
        super().__init__(**kwargs)

    def clean(self, data: Any, initial: Any = None) -> Any:  # noqa: ANN401
        single = super().clean

        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]

        return [single(data, initial)]


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Фотографии лежат внутри книги, поэтому файл тяжелее таблицы на порядок
MAX_WORKBOOK_BYTES = 50 * 1024 * 1024


class WorkbooksForm(forms.Form):
    """
    Окно importWorkbook у ListingsTable: книги, «заменить фотографии»,
    компания для строк без компании и тип новых объявлений.
    """

    workbooks = BooksField(label="Книги Excel")
    replace = forms.BooleanField(
        label="Заменить фотографии, если они уже есть",
        required=False,
        help_text=(
            "Обычно снимки добавляются только объявлениям без фотографий — "
            "повторная загрузка того же файла не плодит одинаковые."
        ),
    )
    publish = forms.BooleanField(
        label="Сразу опубликовать",
        required=False,
        help_text=(
            "Новые объявления из книги сразу появятся на сайте, без проверки. "
            "Ждавшие проверки с прошлой загрузки тоже опубликуются; отклонённые — нет."
        ),
    )
    default_company = forms.CharField(
        label="Компания для строк без компании",
        required=False,
        max_length=190,
        help_text=(
            "Название или ИНН компании из раздела «Компании». Ей достанутся строки, где "
            "столбец «Компания» пуст или компании нет в справочнике. Оставьте пустым — "
            "они достанутся служебной компании (Anjir Group); передать настоящему "
            "владельцу — действием «Передать компании…» в списке объявлений."
        ),
    )
    default_type = forms.ChoiceField(
        label="Тип новых объявлений",
        choices=[("supply", "Предложение (продаю)"), ("demand", "Запрос (куплю)")],
        initial="supply",
        required=False,
        help_text="Когда в книге нет столбца «Тип» или ячейка в нём пуста.",
    )

    def clean_default_company(self) -> int | None:
        from savdex.data.workbook import company_id

        name = str(self.cleaned_data.get("default_company") or "").strip()

        if name == "":
            return None

        found = company_id(name)

        if found is None:
            raise forms.ValidationError(
                f"Компании «{name}» нет в разделе «Компании» — проверьте название или ИНН."
            )

        return found

    def clean_workbooks(self) -> list[Any]:
        from savdex.data.workbook import MAX_WORKBOOKS

        books = list(self.cleaned_data["workbooks"] or [])

        if len(books) > MAX_WORKBOOKS:
            raise forms.ValidationError(f"За раз — не больше {MAX_WORKBOOKS} книг.")

        for book in books:
            if not str(book.name).lower().endswith(".xlsx"):
                raise forms.ValidationError(f"{book.name}: нужна книга Excel в формате XLSX.")

            if book.size > MAX_WORKBOOK_BYTES:
                raise forms.ValidationError(f"{book.name}: файл больше 50 МБ.")

        return books


class TransferForm(forms.Form):
    """Кому передать отмеченные объявления."""

    company = forms.CharField(
        label="Компания",
        max_length=190,
        help_text="Название или ИНН компании из раздела «Компании» — настоящего владельца.",
    )

    def clean_company(self) -> int:
        from savdex.data.workbook import company_id

        name = str(self.cleaned_data.get("company") or "").strip()
        found = company_id(name)

        if found is None:
            raise forms.ValidationError(
                f"Компании «{name}» нет в разделе «Компании» — проверьте название или ИНН."
            )

        return found


class ListingState(admin.SimpleListFilter):
    title = "статус"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(LISTING_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(status=self.value()) if self.value() else queryset


class ListingType(admin.SimpleListFilter):
    title = "тип"
    parameter_name = "type"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("supply", "Предложение"), ("demand", "Запрос")]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(type=self.value()) if self.value() else queryset


class ListingSource(admin.SimpleListFilter):
    title = "источник"
    parameter_name = "source"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(LISTING_SOURCES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(source=self.value()) if self.value() else queryset


class Trashed(admin.SimpleListFilter):
    """Удалённые (в корзине) — отдельно: вернуть или удалить насовсем."""

    title = "корзина"
    parameter_name = "trashed"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "В корзине")]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        if self.value() == "1":
            return queryset.filter(deleted_at__isnull=False)

        return queryset.filter(deleted_at__isnull=True)


@register(Listing, section="listings")
class ListingAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Listing"
    title_list = "Объявления"
    title_change = "Объявление"
    change_form_template = "admin/data/listing/change_form.html"
    change_list_template = "admin/data/listing/change_list.html"

    form = ListingForm
    list_display = (
        "listing",
        "company_name",
        "kind",
        "state",
        "views_count",
        "unlocks_count",
        "until",
    )
    list_filter = (ListingState, ListingType, ListingSource, Trashed)
    list_select_related = ("company",)
    search_fields = ("title", "company__name")
    ordering = ("-created_at", "-id")
    list_per_page = 50
    actions = ("delete_selected", "approve_selected", "transfer_to_company")

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        languages = tuple(
            (
                f"Тексты — {locales.ALL[code]['label']}",
                {
                    "fields": tuple(f"{name}_{code}" for name in LISTING_TEXTS),
                    "classes": ("collapse",),
                    "description": "Необязательно: без перевода объявление на этом языке "
                    "показывается по-русски, пока его не переведёт машинный переводчик.",
                },
            )
            for code in OTHER_LOCALES
        )

        return (
            ("Что предлагают", {"fields": ("owner", "type", "category_id")}),
            ("Тексты — Русский", {"fields": LISTING_TEXTS}),
            *languages,
            (
                "Цена и условия",
                {
                    "fields": (
                        "price_negotiable",
                        "price",
                        "bundle_price",
                        "currency",
                        "unit",
                        "min_order",
                    )
                },
            ),
            ("Публикация", {"fields": ("city_id", "expires_at", "moderation_note")}),
        )

    def get_queryset(self, request: HttpRequest) -> Any:  # noqa: ANN401
        # Пустые черновики скрыты: их заводит сам мастер объявления и
        # переиспользует — удалять их отсюда бессмысленно
        return super().get_queryset(request).exclude(status="draft", title="")

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Объявление — от имени компании: заводится в кабинете или загрузкой
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массовое удаление — как DeleteBulkAction: только с правом удалять
        return super(SavdexModelAdmin, self).get_actions(request)

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Поиск и счётчики — не правка администратора: в журнал не идут."""
        attributes = self.attributes(obj)

        for column in (
            "search_text",
            "views_count",
            "impressions_count",
            "unlocks_count",
            "favorites_count",
        ):
            attributes.pop(column, None)

        return attributes

    # ── Список ──

    @admin.display(description="объявление", ordering="title")
    def listing(self, obj: Listing) -> str:
        title = obj.title if len(obj.title) <= 60 else obj.title[:60].rstrip() + "..."

        return format_html("{}<br><small>{}</small>", title, self._category_name(obj.category_id))

    @staticmethod
    def _category_name(category_id: int | None) -> str:
        from savdex.catalogs.models import Category

        category = Category.objects.filter(pk=category_id).first() if category_id else None

        return category.name() if category is not None else "Без категории"

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: Listing) -> str:
        return obj.company.name if obj.company is not None else "—"

    @admin.display(description="тип", ordering="type")
    def kind(self, obj: Listing) -> str:
        return _badge(
            "Запрос" if obj.type == "demand" else "Предложение",
            "warning" if obj.type == "demand" else "info",
        )

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Listing) -> str:
        return _badge(
            LISTING_STATUSES.get(obj.status, obj.status), LISTING_TONES.get(obj.status, "gray")
        )

    @admin.display(description="до", ordering="expires_at")
    def until(self, obj: Listing) -> str:
        return timezone.localtime(obj.expires_at).strftime("%d.%m.%Y") if obj.expires_at else "—"

    # ── Удаление: в корзину; вернуть и насовсем — суперадмин ──

    def delete_model(self, request: HttpRequest, obj: Any) -> None:  # noqa: ANN401
        """SoftDeletes: deleted_at и updated_at; строка журнала «удалено»."""
        stamp = timezone.now().replace(microsecond=0)

        with allowed_writes("listings"):
            Listing.objects.filter(pk=obj.pk).update(deleted_at=stamp, updated_at=stamp)

        self.journal(request, "deleted", obj)
        request._savdex_done = f"Удалено: {obj}"  # type: ignore[attr-defined]

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        for obj in list(queryset):
            self.delete_model(request, obj)

    # ── Публикация пачкой ──

    @admin.action(description="Опубликовать отмеченные (одобрить)")
    def approve_selected(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        """
        «Одобрить» для всех отмеченных сразу — как кнопка на странице
        объявления: на проверке или отклонённые, и только те, что этому
        сотруднику можно одобрять (can_moderate). Остальные пропускаются.
        """
        from savdex.data import services

        approved = skipped = 0

        for listing in queryset:
            allowed = {code for code, _, _ in self.decisions(listing)}

            if "approve" not in allowed or not self.can_moderate(request, listing):
                skipped += 1

                continue

            services.approve_listing(request, listing)
            approved += 1

        self.message_user(
            request,
            f"Опубликовано: {approved}."
            + (f" Пропущено {skipped} — уже опубликованы или нет права." if skipped else ""),
            messages.SUCCESS if approved else messages.WARNING,
        )

    # ── Передача настоящему владельцу ──

    @admin.action(description="Передать компании…", permissions=["change"])
    def transfer_to_company(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        """
        Отмеченные объявления — другой компании: заявки, загруженные без
        продавца (у служебной компании), переходят к настоящему владельцу.
        Первый шаг — страница с выбором компании, второй (apply) — передача;
        каждая — строка журнала «изменено» с компанией до и после.
        """
        from django.template.response import TemplateResponse

        form = TransferForm(request.POST if "apply" in request.POST else None)

        if "apply" in request.POST and form.is_valid():
            target = int(form.cleaned_data["company"])
            stamp = timezone.now().replace(microsecond=0)
            moved = 0

            for listing in queryset.select_related("company"):
                if listing.company_id == target:
                    continue

                before = listing.company_id

                with allowed_writes("listings"):
                    Listing.objects.filter(pk=listing.pk).update(
                        company_id=target, updated_at=stamp
                    )

                listing.company_id = target
                self.journal(
                    request,
                    "updated",
                    listing,
                    {"before": {"company_id": before}, "after": {"company_id": target}},
                )
                moved += 1

            from savdex.data.workbook import company_name

            self.message_user(
                request, f"Передано компании «{company_name(target)}»: {moved}.", messages.SUCCESS
            )

            return None

        return TemplateResponse(
            request,
            "admin/data/listing/transfer.html",
            {
                **self.admin_site.each_context(request),
                "title": "Передать объявления компании",
                "opts": self.model._meta,
                "form": form,
                "listings": queryset.select_related("company")[:200],
                "count": queryset.count(),
                "ids": [str(pk) for pk in queryset.values_list("pk", flat=True)],
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            },
        )

    # ── Решения модератора ──

    def can_moderate(self, request: HttpRequest, listing: Listing) -> bool:
        """
        Модератору — всё; тому, кто загружает книги, — загруженное: иначе
        администратор загружал бы то, что опубликовать не может.
        """
        staff = _admin_of(request)

        return bool(
            staff.can("listings.moderate")
            or (listing.source == "import" and staff.can("listings.import"))
        )

    def decisions(self, listing: Listing) -> list[tuple[str, str, bool]]:
        found = []

        # И отклонённое тоже: отказ окончателен для автора, не для модератора
        if listing.status in ("moderation", "rejected"):
            found.append(("approve", "Одобрить", False))

        if listing.status in ("moderation", "active", "rejected"):
            found.append(("return", "Вернуть на исправление", True))

        if listing.status in ("moderation", "active"):
            found.append(("reject", "Отклонить", True))

        return found

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/decide/",
                self.admin_site.admin_view(self.decide_view),
                name="data_listing_decide",
            ),
            path(
                "<path:object_id>/photos/",
                self.admin_site.admin_view(self.photos_view),
                name="data_listing_photos",
            ),
            path(
                "<path:object_id>/trash/",
                self.admin_site.admin_view(self.trash_view),
                name="data_listing_trash",
            ),
            path(
                "export/",
                self.admin_site.admin_view(self.export_view),
                name="data_listing_export",
            ),
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="data_listing_import",
            ),
            path(
                "import/template/",
                self.admin_site.admin_view(self.template_view),
                name="data_listing_template",
            ),
            *super().get_urls(),
        ]

    # ── Выгрузка ──

    def export_view(self, request: HttpRequest) -> HttpResponse:
        """
        ListingExporter: список с теми же отборами, что на экране, — в
        XLSX или CSV; право listings.export, строка журнала «Выгрузка».
        """
        if not _admin_of(request).can("listings.export"):
            raise PermissionDenied

        from savdex import admin_export

        query = request.GET.copy()
        file_format = query.pop("format", ["xlsx"])[-1]
        request.GET = query  # type: ignore[assignment]
        records = (
            self.get_changelist_instance(request)
            .get_queryset(request)
            .select_related("company")
            .order_by("-created_at", "-id")
        )
        categories = _category_names()

        return admin_export.respond(
            request,
            section="listings",
            filename="listings",
            file_format="csv" if file_format == "csv" else "xlsx",
            columns=[
                ("Номер", lambda r: r.pk),
                ("Заголовок", lambda r: r.title),
                ("Компания", lambda r: r.company.name if r.company else None),
                ("Категория", lambda r: categories.get(r.category_id)),
                ("Тип", lambda r: "Запрос" if r.type == "demand" else "Предложение"),
                ("Цена", lambda r: r.price),
                ("Валюта", lambda r: r.currency),
                ("Единица", lambda r: r.unit),
                ("Статус", lambda r: EXPORT_STATUSES.get(r.status, "Снято")),
                ("Показы", lambda r: r.impressions_count),
                ("Просмотры", lambda r: r.views_count),
                ("Раскрытий контакта", lambda r: r.unlocks_count),
                ("Опубликовано", lambda r: r.published_at),
                ("Действует до", lambda r: r.expires_at),
            ],
            records=records.iterator(),
        )

    # ── Загрузка книгами Excel ──

    def import_view(self, request: HttpRequest) -> HttpResponse:
        """
        importWorkbook у ListingsTable: книги Excel с фотографиями в строках
        (savdex/data/workbook.py), отчёт — строки, новые, обновлённые,
        фотографии, ошибки и заметки; право listings.import, строка журнала
        «Загрузка» с итогами.
        """
        if not _admin_of(request).can("listings.import"):
            raise PermissionDenied

        from django.template.response import TemplateResponse

        from savdex import audit
        from savdex.data import workbook
        from savdex.web.listing_image_actions import MAX_IMAGES

        result = None
        form = WorkbooksForm(request.POST or None, request.FILES or None)

        if request.method == "POST" and form.is_valid():
            books = [(str(book.name), book.read()) for book in form.cleaned_data["workbooks"]]

            try:
                result = workbook.import_workbooks(
                    books,
                    admin_id=_admin_of(request).id,
                    replace=bool(form.cleaned_data["replace"]),
                    publish=bool(form.cleaned_data.get("publish")),
                    ip=audit.client_ip(request),
                    default_company=form.cleaned_data["default_company"],
                    default_type=str(form.cleaned_data.get("default_type") or "supply"),
                )
            except workbook.UnreadableWorkbookError as error:
                form.add_error(
                    "workbooks",
                    f"Книгу не открыть: {error}. Загруженное из книг до неё осталось.",
                )
            else:
                messages.success(
                    request,
                    "Загрузка завершена"
                    + (" с ошибками" if result["errors"] else "")
                    + f". Обработано строк: {result['rows']}. Создано: {result['created']}, "
                    f"обновлено: {result['updated']}, фотографий добавлено: {result['photos']}.",
                )

        return TemplateResponse(
            request,
            "admin/data/listing/import.html",
            {
                **self.admin_site.each_context(request),
                "title": "Загрузка товаров из Excel",
                "opts": self.model._meta,
                "form": form,
                "result": result,
                "max_workbooks": workbook.MAX_WORKBOOKS,
                "max_images": MAX_IMAGES,
            },
        )

    def template_view(self, request: HttpRequest) -> HttpResponse:
        """«Скачать образец»: книга с листами по языкам и примером строки."""
        if not _admin_of(request).can("listings.import"):
            raise PermissionDenied

        from savdex.data import workbook

        response = HttpResponse(workbook.template_bytes(), content_type=XLSX_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{workbook.TEMPLATE_NAME}"'

        return response

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        query = request.GET.urlencode()

        return super().changelist_view(
            request,
            {
                "can_import": _admin_of(request).can("listings.import"),
                "import_url": reverse("savdex_admin:data_listing_import"),
                "can_export": _admin_of(request).can("listings.export"),
                "export_url": reverse("savdex_admin:data_listing_export")
                + (f"?{query}" if query else ""),
                "export_sep": "&" if query else "?",
                **(extra_context or {}),
            },
        )

    def get_object(self, request: HttpRequest, object_id: str, from_field: Any = None) -> Any:  # noqa: ANN401
        """Запись — и из корзины: её можно вернуть или удалить насовсем."""
        queryset = Listing.objects.all()

        try:
            return queryset.get(pk=int(object_id))
        except (Listing.DoesNotExist, ValueError):
            return None

    def decide_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        listing = self.get_object(request, object_id)

        if request.method != "POST" or not isinstance(listing, Listing):
            raise PermissionDenied

        if not self.can_moderate(request, listing):
            raise PermissionDenied

        page = reverse("savdex_admin:data_listing_change", args=[listing.pk])
        decision = request.POST.get("decision", "")
        allowed = {code: needs for code, _, needs in self.decisions(listing)}
        reason = (request.POST.get("note") or "").strip()

        if decision not in allowed:
            messages.warning(request, "Это решение по объявлению уже недоступно.")

            return HttpResponseRedirect(page)

        if allowed[decision] and len(reason) < MIN_REASON:
            messages.error(
                request,
                f"Напишите, что исправить или почему отказ, — не короче {MIN_REASON} знаков: "
                "текст увидит владелец.",
            )

            return HttpResponseRedirect(page)

        from savdex.data import services

        if decision == "approve":
            services.approve_listing(request, listing)
            messages.success(request, "Объявление опубликовано.")
        elif decision == "return":
            services.return_listing(request, listing, reason)
            messages.warning(request, "Объявление возвращено автору.")
        else:
            services.reject_listing(request, listing, reason)
            messages.warning(request, "Объявление отклонено.")

        return HttpResponseRedirect(page)

    # ── Фотографии ──

    def photos_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """Загрузить, сделать обложкой, удалить — как ImagesRelationManager."""
        listing = self.get_object(request, object_id)

        if (
            request.method != "POST"
            or not isinstance(listing, Listing)
            or not self.has_change_permission(request, listing)
        ):
            raise PermissionDenied

        from savdex.data import services

        page = reverse("savdex_admin:data_listing_change", args=[listing.pk])
        todo = request.POST.get("photo_action", "")

        if todo == "upload":
            saved = services.add_photos(listing.pk, request.FILES.getlist("photos"))
            (messages.success if saved else messages.warning)(
                request, f"Загружено фотографий: {saved}"
            )
        elif todo in ("cover", "remove"):
            image_id = request.POST.get("image", "")

            if image_id.isdigit() and services.photo_action(listing.pk, int(image_id), todo):
                messages.success(
                    request, "Обложка обновлена." if todo == "cover" else "Фотография удалена."
                )

        return HttpResponseRedirect(page)

    def trash_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """Из корзины: вернуть (RestoreAction) или удалить насовсем (ForceDeleteAction)."""
        listing = self.get_object(request, object_id)

        if (
            request.method != "POST"
            or not isinstance(listing, Listing)
            or listing.deleted_at is None
            or not self.has_delete_permission(request, listing)
        ):
            raise PermissionDenied

        if request.POST.get("trash_action") == "restore":
            stamp = timezone.now().replace(microsecond=0)

            with allowed_writes("listings"):
                Listing.objects.filter(pk=listing.pk).update(deleted_at=None, updated_at=stamp)

            self.journal(request, "restored", listing)
            messages.success(request, "Объявление восстановлено.")

            return HttpResponseRedirect(
                reverse("savdex_admin:data_listing_change", args=[listing.pk])
            )

        from savdex.data import services

        services.force_delete_listing(listing)
        self.journal(request, "force_deleted", listing)
        messages.success(request, "Объявление удалено насовсем.")

        return HttpResponseRedirect(reverse("savdex_admin:data_listing_changelist") + "?trashed=1")

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        listing = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(listing, Listing):
            extra["decisions"] = (
                self.decisions(listing) if self.can_moderate(request, listing) else []
            )
            extra["min_note"] = MIN_REASON
            extra["photos"] = list(listing.images.order_by("sort", "id"))
            extra["can_photos"] = self.has_change_permission(request, listing)
            extra["trashed"] = listing.deleted_at is not None
            extra["can_trash"] = listing.deleted_at is not None and self.has_delete_permission(
                request, listing
            )
            extra["status_label"] = LISTING_STATUSES.get(listing.status, listing.status)
            extra["source_label"] = LISTING_SOURCES.get(listing.source, listing.source)
            extra["lifetime_days"] = LIFETIME_DAYS

        return super().change_view(request, object_id, form_url, extra)


# Раздел «Компании» — в своём модуле; импорт его регистрирует
from savdex.data import companies_admin  # noqa: E402, F401
