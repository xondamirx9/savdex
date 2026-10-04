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

Заказы на услуги (в базе — it_tasks): состояние вкладками со
счётчиками над списком, отбор по направлению, правка (создаются
только из кабинета — заказ от имени заказчика), «Снять с витрины»
для спама и нарушений (заказчик увидит заказ в кабинете архивным),
«Открыть на сайте» у открытого, удаление — с правом удалять.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.views.main import SEARCH_VAR
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html

from savdex.adminsite import PerRequest, SavdexModelAdmin, _admin_of, register, state_tabs
from savdex.crm.admin import _badge
from savdex.data.models import (
    IT_STATUSES,
    LIFETIME_DAYS,
    LISTING_MAX,
    LISTING_SOURCES,
    LISTING_STATUSES,
    LISTING_TEXTS,
    LISTING_TYPES,
    SERVICE_TYPES,
    ItTask,
    Listing,
)
from savdex.guards import allowed_writes
from savdex.text import numeric, plural
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
    # Подписи те же, что в списке и на вкладках: раздел должен
    # называть состояние одинаково везде. Значения в базе прежние.
    # Список отложен в вызываемое: IT_STATES объявлен ниже формы
    status = forms.ChoiceField(
        label="Что сейчас с заказом",
        choices=lambda: [(code, label) for code, (label, _) in IT_STATES.items()],
    )

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


#: Состояние заказа словами о деле и цвет плашки.
#:
#: В базе лежит «active», «completed» — и так же они назывались
#: в списке: «Открыта», «Выполнена». Сотруднику поддержки эти слова
#: ничего не говорят: открыта — кем, выполнена — кем и что дальше.
#: Здесь то же состояние названо делом: заказ ищет исполнителя, работа
#: сдана, заказчик закрыл, мы сняли с витрины. Значения в базе
#: прежние — меняются только подписи, и те же слова стоят в форме
#: правки, чтобы раздел говорил на одном языке.
IT_STATES: dict[str, tuple[str, str]] = {
    "active": ("Ищет исполнителя", "success"),
    "closed": ("Закрыта заказчиком", "warning"),
    "completed": ("Работа сдана", "info"),
    "archived": ("Снята с витрины", "gray"),
}


class ItStatus(admin.SimpleListFilter):
    """
    Состояние: отбор тот же, но в правой колонке его нет — он стоит
    вкладками над списком (шаблон change_list.html раздела). Пустой
    шаблон вместо выброшенного фильтра: так адрес ?status=active
    остаётся законным для Django и вкладки работают его же отбором.
    """

    title = "статус"
    parameter_name = "status"
    template = "admin/data/ittask/status_filter.html"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [(code, label) for code, (label, _) in IT_STATES.items()]

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
    title_list = "Заказы на услуги"
    title_change = "Заказ на услугу"

    change_list_template = "admin/data/ittask/change_list.html"

    form = ItTaskForm
    fieldsets = (
        ("Задача", {"fields": ("title", "description", "service_type", "stack")}),
        (
            "Условия",
            {"fields": ("budget_type", "budget_from", "budget_to", "currency", "deadline_at")},
        ),
        ("Статус", {"fields": ("status",)}),
    )
    # Направление — строкой под названием, а не своей колонкой:
    # места в разделе ровно столько, сколько оставляют меню слева
    # и фильтр справа, и семь колонок в нём наезжали друг на друга
    list_display = ("task", "responses", "state", "published", "row_actions")
    list_filter = (ItStatus, ServiceType)
    list_select_related = ("company",)
    search_fields = ("title",)
    ordering = ("-created_at", "-id")
    list_per_page = 50
    actions = ("delete_selected",)
    # Пусто — значит пусто: прочерк Django в колонке действий читался
    # как «данных нет», хотя с закрытым заказом просто нечего делать
    empty_value_display = ""

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Заказ — от имени заказчика: заводится только в кабинете
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

    @admin.display(description="что нужно сделать и кому", ordering="title")
    def task(self, obj: ItTask) -> str:
        """
        Название, под ним заказчик — и предупреждение, если заказ висит
        впустую.

        Открытый заказ без единого отклика — единственное, что в этом
        списке требует вмешательства: либо описание не объясняет, что
        нужно, либо направление выбрано не то. Раньше это приходилось
        вылавливать глазами по колонке с нулём.
        """
        title = obj.title if len(obj.title) <= 80 else obj.title[:80].rstrip() + "..."
        company = obj.company
        stale = obj.status == "active" and obj.responses_count == 0

        return format_html(
            '<span class="sx-row-title">{}</span>'
            '<span class="sx-row-meta"><small class="sx-row-sub">{}</small>'
            '<span class="sx-chip">{}</span></span>{}',
            title,
            company.name if company is not None and company.deleted_at is None else "",
            SERVICE_TYPES.get(obj.service_type, obj.service_type),
            format_html(
                '<small class="sx-row-care">Висит без откликов — стоит проверить описание</small>'
            )
            if stale
            else "",
        )

    @admin.display(description="отклики", ordering="responses_count")
    def responses(self, obj: ItTask) -> str:
        """
        Число со словом: «6 откликов». Голая цифра в колонке «Откликов»
        читалась как номер чего-то, а ноль — как пустая клетка.
        """
        if obj.responses_count == 0:
            return format_html('<span class="sx-row-sub">нет откликов</span>')

        number, word = plural(obj.responses_count, "отклик", "отклика", "откликов").split(" ", 1)

        return format_html('<span class="sx-count"><b>{}</b>{}</span>', number, word)

    @admin.display(description="что сейчас с заказом", ordering="status")
    def state(self, obj: ItTask) -> str:
        label, tone = IT_STATES.get(obj.status, (IT_STATUSES.get(obj.status, obj.status), "gray"))

        return _badge(label, tone)

    @admin.display(description="на витрине", ordering="published_at")
    def published(self, obj: ItTask) -> str:
        """Дата словами: «23 мая 2026». «23.05.2026» — это из отчёта."""
        if obj.published_at is None:
            return ""

        return date_format(timezone.localtime(obj.published_at), "j E Y")

    @admin.display(description="")
    def row_actions(self, obj: ItTask) -> str:
        """
        «На сайте» и «Снять» — у открытой задачи. У остальных колонка
        пустая: прочерк в ней читался как «данных нет», хотя делать
        с закрытой задачей попросту нечего.
        """
        if obj.status != "active":
            return ""

        link = (
            format_html(
                '<a class="sx-row-link" href="/it-services/{}" target="_blank" '
                'rel="noopener">На сайте</a>',
                obj.slug,
            )
            if obj.slug
            else ""
        )
        button = (
            format_html(
                '<button type="submit" class="button sx-quiet" formaction="{}" formmethod="post" '
                "onclick=\"return confirm('Снять задачу с витрины? Заказчик увидит её в кабинете "
                "архивной.')\">Снять</button>",
                reverse("savdex_admin:data_ittask_archive", args=[obj.pk]),
            )
            if self._can_archive
            else ""
        )

        return format_html('<span class="sx-row-actions">{}{}</span>', link, button)

    _can_archive = PerRequest()

    def _tabs(self, request: HttpRequest) -> list[dict[str, Any]]:
        """Вкладки состояний: считается то, что откроется при нажатии."""
        rows = self.get_queryset(request)

        if service := request.GET.get(ServiceType.parameter_name):
            rows = rows.filter(service_type=service)

        if term := request.GET.get(SEARCH_VAR):
            rows = rows.filter(title__icontains=term)

        # order_by() обязателен: со списочной сортировкой Django кладёт
        # поле сортировки в GROUP BY, и каждый заказ считается отдельной
        # группой — вкладки показывали единицы вместо десятков
        counts = dict(rows.order_by().values_list("status").annotate(total=Count("pk")))
        parameter = ItStatus.parameter_name

        return state_tabs(
            request,
            [
                (parameter, "", "Все", sum(counts.values())),
                *(
                    (parameter, code, label, counts.get(code, 0))
                    for code, (label, _) in IT_STATES.items()
                ),
            ],
            # Заказ, который ищет исполнителя, — то, ради чего сюда и
            # заходят: пусть счётчик видно и с другой вкладки
            alert=("active",),
        )

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        self._can_archive = self.has_change_permission(request)

        return super().changelist_view(
            request, {"sx_tabs": self._tabs(request), **(extra_context or {})}
        )

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

#: Цвет метки статуса в списке: тона бейджей → классы sx-pill
PILL_CLASSES = {"success": "ok", "warning": "warn", "danger": "bad"}

#: Откуда объявление — как скажет человек, а не как названо в коде
SOURCE_LABELS = {"cabinet": "Добавила компания", "import": "Загружено из Excel"}

#: Вкладки над списком: (параметр, значение, подпись); «Ждут проверки»
#: подсвечиваются, когда там что-то есть
LISTING_TABS = (
    ("status", "", "Все"),
    ("status", "active", "Активные"),
    ("status", "moderation", "Ждут проверки"),
    ("status", "needs_changes", "На исправлении"),
    ("status", "rejected", "Отклонены"),
    ("status", "draft", "Черновики"),
    ("status", "expired", "Истекли"),
    ("status", "archived", "Сняты"),
    ("trashed", "1", "Корзина"),
)

#: Heroicons (outline), как значки меню
ICON_EXTERNAL = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" '
    'd="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 '
    '18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>'
)
ICON_EDIT = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" '
    'd="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 '
    "1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 "
    '0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10"/></svg>'
)

#: Осталось дней — «скоро»: подсвечиваем, чтобы продлили вовремя
EXPIRES_SOON_DAYS = 7

#: Сколько дней объявление может лежать на проверке, прежде чем это
#: станет просрочкой: за двое суток продавец успевает решить, что
#: площадка о нём забыла
WAITING_TOO_LONG_DAYS = 2


def _days_word(days: int) -> str:
    """1 день, 2 дня, 5 дней."""
    if days % 10 == 1 and days % 100 != 11:
        return "день"

    if 2 <= days % 10 <= 4 and not 12 <= days % 100 <= 14:
        return "дня"

    return "дней"


def _initials(name: str) -> str:
    """Две буквы для значка компании: без ООО, LLC и кавычек."""
    words = [
        w
        for w in name.replace("«", " ").replace("»", " ").replace('"', " ").split()
        if w.upper().strip(".") not in {"ООО", "OOO", "LLC", "ИП", "АО", "ЧП", "MCHJ", "XK"}
    ]

    return "".join(w[0] for w in words[:2]).upper() or "?"


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


def _readonly_displays(cls: type) -> type:
    """
    Поля формы, которых нет в модели (переводы, «Компания»), для роли без
    права правки показываются только чтением — по имени поля. Без своих
    подписей и значений там стояло «Title en:» и пусто.
    """
    for name in LISTING_TEXTS:
        label = str(ListingFormBase.base_fields[name].label)

        for code in OTHER_LOCALES:

            def text(self: Any, obj: Listing, name: str = name, code: str = code) -> str:  # noqa: ANN401
                return (getattr(obj, f"{name}_i18n", None) or {}).get(code) or "—"

            setattr(
                cls,
                f"{name}_{code}",
                admin.display(description=f"{label} ({code})")(text),
            )

    def owner(self: Any, obj: Listing) -> str:  # noqa: ANN401
        return obj.company.name if obj.company_id is not None and obj.company else "—"

    cls.owner = admin.display(description="Компания")(owner)  # type: ignore[attr-defined]

    return cls


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
        help_text=(
            "Когда в книге нет столбца «Тип» или ячейка в нём пуста, а заголовок не "
            "начинается с «Куплю», «Требуется», «Ищем» или «Продам», «Предлагаем» — "
            "по таким тип ставится сам."
        ),
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


#: Фильтр без блока в боковой колонке: им управляют вкладки и кнопки
#: над списком — колонка справа отнимала 240 px у таблицы
HIDDEN_FILTER = "admin/data/listing/hidden_filter.html"


class ListingState(admin.SimpleListFilter):
    title = "статус"
    parameter_name = "status"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(LISTING_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(status=self.value()) if self.value() else queryset


class ListingType(admin.SimpleListFilter):
    title = "продаю или покупаю"
    parameter_name = "type"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("supply", "Продаю"), ("demand", "Покупаю")]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(type=self.value()) if self.value() else queryset


class ListingSource(admin.SimpleListFilter):
    title = "откуда"
    parameter_name = "source"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [(code, SOURCE_LABELS.get(code, label)) for code, label in LISTING_SOURCES.items()]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        return queryset.filter(source=self.value()) if self.value() else queryset


class Trashed(admin.SimpleListFilter):
    """Удалённые (в корзине) — отдельно: вернуть или удалить насовсем."""

    title = "корзина"
    parameter_name = "trashed"
    template = HIDDEN_FILTER

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "В корзине")]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:  # noqa: ANN401
        if self.value() == "1":
            return queryset.filter(deleted_at__isnull=False)

        return queryset.filter(deleted_at__isnull=True)


@register(Listing, section="listings")
@_readonly_displays
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
        "state",
        "views",
        "contacts",
        "until",
        "row_actions",
    )
    list_filter = (ListingState, ListingType, ListingSource, Trashed)
    list_select_related = ("company",)
    search_fields = ("title", "company__name")
    ordering = ("-created_at", "-id")
    list_per_page = 50
    actions = (
        "delete_selected",
        "approve_selected",
        "transfer_to_company",
        "mark_demand",
        "mark_supply",
    )

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
        # Под названием — продаёт компания или покупает, и категория:
        # отдельная колонка «Тип» с «Предложение/Запрос» была непонятна
        kind = (
            '<span class="sx-kind sx-kind-buy">Покупаю</span>'
            if obj.type == "demand"
            else '<span class="sx-kind sx-kind-sell">Продаю</span>'
        )

        return format_html(
            '<span class="sx-title">{}</span><span class="sx-sub">{}{}</span>{}',
            obj.title,
            format_html(kind),
            self._category_name(obj.category_id),
            self._waiting(obj),
        )

    @staticmethod
    def _waiting(obj: Listing) -> str:
        """
        Объявление, которое ждёт уже нас.

        Очередь проверки видна на вкладке, но внутри неё всё выглядит
        одинаково, а разница есть: поданное час назад подождёт, а то,
        что лежит третий день, — уже просрочка, продавец ждёт ответа
        и не понимает, почему его нет.
        """
        if obj.status != "moderation" or obj.created_at is None:
            return ""

        days = (timezone.localdate() - timezone.localtime(obj.created_at).date()).days

        if days < WAITING_TOO_LONG_DAYS:
            return ""

        return format_html(
            '<span class="sx-sub sx-waiting">Ждёт проверки {} {} — продавец ждёт ответа</span>',
            days,
            _days_word(days),
        )

    @staticmethod
    def _category_name(category_id: int | None) -> str:
        from savdex.catalogs.models import Category

        category = Category.objects.filter(pk=category_id).first() if category_id else None

        return category.name() if category is not None else "Без категории"

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: Listing) -> str:
        name = obj.company.name if obj.company is not None else "—"
        source = SOURCE_LABELS.get(obj.source, LISTING_SOURCES.get(obj.source, ""))

        return format_html(
            '<span class="sx-company"><span class="sx-avatar" aria-hidden="true">{}</span>'
            '<span class="sx-company-text"><span class="sx-company-name">{}</span>'
            '<span class="sx-sub">{}</span></span></span>',
            _initials(name) if obj.company is not None else "—",
            name,
            source,
        )

    @admin.display(description="статус", ordering="status")
    def state(self, obj: Listing) -> str:
        tone = PILL_CLASSES.get(LISTING_TONES.get(obj.status, ""), "gray")

        return format_html(
            '<span class="sx-pill sx-pill-{}">{}</span>',
            tone,
            LISTING_STATUSES.get(obj.status, obj.status),
        )

    @admin.display(description="просмотры", ordering="views_count")
    def views(self, obj: Listing) -> int:
        return obj.views_count

    @admin.display(description="открыли контакты", ordering="unlocks_count")
    def contacts(self, obj: Listing) -> int:
        return obj.unlocks_count

    @admin.display(description="активно до", ordering="expires_at")
    def until(self, obj: Listing) -> str:
        if obj.expires_at is None:
            return "—"

        date = timezone.localtime(obj.expires_at)
        days = (date.date() - timezone.localdate()).days

        if obj.status != "active":
            note, soon = "", False
        elif days < 0:
            note, soon = "срок вышел", True
        elif days == 0:
            note, soon = "последний день", True
        else:
            note, soon = f"осталось {days} {_days_word(days)}", days <= EXPIRES_SOON_DAYS

        return format_html(
            '<span class="sx-until{}"><span>{}</span><span class="sx-sub">{}</span></span>',
            " is-soon" if soon else "",
            # Словами, как в «Заказах на услуги»: «22.09.2026» сверяют
            # с календарём, «22 сентября 2026» читают
            date_format(date, "j E Y"),
            note,
        )

    @admin.display(description="")
    def row_actions(self, obj: Listing) -> str:
        """«Открыть на сайте» — у опубликованных; «Изменить» — всегда."""
        edit = reverse("savdex_admin:data_listing_change", args=[obj.pk])
        site = (
            format_html(
                '<a href="/listing/{}" class="sx-icon-btn" target="_blank" rel="noopener" '
                'title="Открыть на сайте" aria-label="Открыть на сайте">{}</a>',
                obj.slug,
                format_html(ICON_EXTERNAL),
            )
            if obj.status == "active" and obj.slug and obj.deleted_at is None
            else ""
        )

        return format_html(
            '<span class="sx-row-actions">{}<a href="{}" class="sx-icon-btn" title="Изменить" '
            'aria-label="Изменить">{}</a></span>',
            site,
            edit,
            format_html(ICON_EDIT),
        )

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

    @admin.action(description="Одобрить")
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

    # ── Тип пачкой: исправить загруженное с неверным типом ──

    def _set_type(self, request: HttpRequest, queryset: Any, kind: str) -> None:  # noqa: ANN401
        """
        Отмеченным — «Покупаю» (demand) или «Продаю» (supply). Книги заявок
        без столбца «Тип» раньше загружались «Предложениями»; так их
        исправляют пачкой. Каждая смена — строка журнала «изменено».
        """
        stamp = timezone.now().replace(microsecond=0)
        changed = 0

        for listing in queryset:
            if listing.type == kind:
                continue

            before = listing.type

            with allowed_writes("listings"):
                Listing.objects.filter(pk=listing.pk).update(type=kind, updated_at=stamp)

            listing.type = kind
            self.journal(
                request, "updated", listing, {"before": {"type": before}, "after": {"type": kind}}
            )
            changed += 1

        label = "Покупаю" if kind == "demand" else "Продаю"
        self.message_user(
            request,
            f"Тип «{label}»: {changed}." if changed else f"Все отмеченные уже «{label}».",
            messages.SUCCESS if changed else messages.INFO,
        )

    @admin.action(description="Сделать «Покупаю»", permissions=["change"])
    def mark_demand(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        self._set_type(request, queryset, "demand")

    @admin.action(description="Сделать «Продаю»", permissions=["change"])
    def mark_supply(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        self._set_type(request, queryset, "supply")

    # ── Передача настоящему владельцу ──

    @admin.action(description="Передать другой компании", permissions=["change"])
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
        ListingExporter, право listings.export, строка журнала «Выгрузка».

        Из окна «Выгрузка» (pick=1) — по категориям, мебельным словам,
        статусу и типу (savdex/data/listing_export.py); иначе — список с
        теми же отборами, что на экране. Формат — XLSX, CSV или JSON; в
        каждой строке ссылки на объявление на сайте и в админке.
        """
        if not _admin_of(request).can("listings.export"):
            raise PermissionDenied

        from savdex import admin_export
        from savdex.data import listing_export as le

        query = request.GET.copy()
        file_format = query.pop("format", ["xlsx"])[-1]
        file_format = file_format if file_format in le.FORMATS else "xlsx"

        if query.get("pick") == "1":
            categories = [int(i) for i in query.getlist("category") if numeric(i)]
            with_keywords = query.get("keywords") == "1"
            status = "all" if query.get("status") == "all" else "active"
            kind = query.get("type", "")
            records = le.select(
                categories=categories, with_keywords=with_keywords, status=status, kind=kind
            )
            labels = le.category_labels()
            note = self._export_note(file_format, categories, labels, with_keywords, status, kind)
        else:
            request.GET = query  # type: ignore[assignment]
            records = (
                self.get_changelist_instance(request)
                .get_queryset(request)
                .select_related("company")
                .order_by("-created_at", "-id")
            )
            labels = le.category_labels()
            note = f"Формат: {le.FORMATS[file_format]}; отборы списка"

        cities = le.city_names()
        records = records.prefetch_related("images")

        return admin_export.respond(
            request,
            section="listings",
            filename="listings",
            file_format=file_format,
            note=note,
            as_json=lambda r: le.as_json(r, categories=labels, cities=cities, internal=True),
            columns=[
                ("Номер", lambda r: r.pk),
                ("Заголовок", lambda r: r.title),
                ("Ссылка на сайте", le.listing_url),
                ("Компания", lambda r: r.company.name if r.company else None),
                ("Категория", lambda r: le.category_path(labels.get(r.category_id))),
                ("Тип", lambda r: "Запрос" if r.type == "demand" else "Предложение"),
                ("Цена", lambda r: r.price),
                ("Валюта", lambda r: r.currency),
                ("Единица", lambda r: r.unit),
                ("Город", lambda r: cities.get(r.city_id)),
                ("Статус", lambda r: EXPORT_STATUSES.get(r.status, "Снято")),
                ("Показы", lambda r: r.impressions_count),
                ("Просмотры", lambda r: r.views_count),
                ("Раскрытий контакта", lambda r: r.unlocks_count),
                ("Опубликовано", lambda r: r.published_at),
                ("Действует до", lambda r: r.expires_at),
                ("Описание", lambda r: r.description),
                ("Фото", lambda r: "\n".join(le.photo_urls(r))),
                ("Ссылка в админке", le.admin_url),
            ],
            records=records.iterator(chunk_size=500),
        )

    @staticmethod
    def _export_note(
        file_format: str,
        categories: list[int],
        labels: dict[int, dict[str, Any]],
        with_keywords: bool,
        status: str,
        kind: str,
    ) -> str:
        """Что выгрузили — строкой журнала: «Формат: JSON; категории: Мебель; …»."""
        from savdex.data import listing_export as le

        names = [le.category_path(labels.get(i)) or str(i) for i in categories]
        parts = [
            f"Формат: {le.FORMATS[file_format]}",
            "категории: " + (", ".join(names) if names else "все"),
        ]

        if with_keywords:
            parts.append("плюс мебельные слова")

        parts.append(le.STATUSES[status].lower())

        if kind in LISTING_TYPES:
            parts.append(LISTING_TYPES[kind].lower())

        return "; ".join(parts)

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

    def status_tabs(self, request: HttpRequest) -> list[dict[str, Any]]:
        """Вкладки над списком: статус или корзина, с числом объявлений."""
        base = Listing.objects.exclude(status="draft", title="")
        alive = base.filter(deleted_at__isnull=True)
        counts = dict(alive.values_list("status").annotate(n=Count("pk")))
        counts[""] = sum(counts.values())
        counts["trashed"] = base.filter(deleted_at__isnull=False).count()

        return state_tabs(
            request,
            [
                (
                    parameter,
                    value,
                    label,
                    counts.get("trashed" if parameter == "trashed" else value, 0),
                )
                for parameter, value, label in LISTING_TABS
            ],
            alert=("moderation",),
        )

    @staticmethod
    def filter_chips(request: HttpRequest) -> list[dict[str, Any]]:
        """
        Кнопки-отборы над списком: «Продаю / Покупаю» и откуда объявление.
        Нажатие включает отбор, повторное — снимает; в группе выбран один.
        """
        groups = (
            ("type", [("supply", "Продаю"), ("demand", "Покупаю")]),
            ("source", list(SOURCE_LABELS.items())),
        )
        chips = []

        for parameter, options in groups:
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

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        from savdex.data import listing_export as le

        query = request.GET.urlencode()
        can_export = _admin_of(request).can("listings.export")

        return super().changelist_view(
            request,
            {
                "status_tabs": self.status_tabs(request),
                "filter_chips": self.filter_chips(request),
                "can_import": _admin_of(request).can("listings.import"),
                "import_url": reverse("savdex_admin:data_listing_import"),
                "can_export": can_export,
                "export_url": reverse("savdex_admin:data_listing_export")
                + (f"?{query}" if query else ""),
                "export_sep": "&" if query else "?",
                # Окно «Выгрузка»: дерево категорий и мебельные слова
                "export_base": reverse("savdex_admin:data_listing_export"),
                "export_tree": le.category_tree() if can_export else [],
                "export_furniture": le.furniture_ids() if can_export else [],
                "export_keywords": ", ".join(le.keywords()) if can_export else "",
                "export_keywords_url": le.keywords_url(_admin_of(request)) if can_export else "",
                "export_formats": le.FORMATS,
                "export_statuses": le.STATUSES,
                "export_types": LISTING_TYPES,
                "meyos_url": reverse("savdex_admin:integrations_meyos")
                if _admin_of(request).can("integrations.view")
                else "",
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

        # Фотографии — в журнал, как логотип и обложка компании: кто и что сделал
        if todo == "upload":
            saved = services.add_photos(listing.pk, request.FILES.getlist("photos"))
            (messages.success if saved else messages.warning)(
                request, f"Загружено фотографий: {saved}"
            )

            if saved:
                self.journal(request, "updated", listing, {"after": {"фото добавлено": saved}})
        elif todo in ("cover", "remove"):
            image_id = request.POST.get("image", "")

            if numeric(image_id) and services.photo_action(listing.pk, int(image_id), todo):
                messages.success(
                    request, "Обложка обновлена." if todo == "cover" else "Фотография удалена."
                )
                change = "обложка" if todo == "cover" else "фото удалено"
                self.journal(request, "updated", listing, {"after": {change: int(image_id)}})

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
