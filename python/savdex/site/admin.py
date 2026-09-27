"""
Разделы «Настройки площадки» и «Баннеры» админки на Django — вместо
Filament SettingResource и BannerResource. Про баннеры — у BannerAdmin ниже.

Настройки.

Поле значения меняется под тип: число — числовой ввод, флаг —
переключатель, картинка — загрузка файла на публичный диск Laravel.
Один универсальный текстовый ввод однажды пропустил бы «два часа»
в числовую настройку.

Всё, что было в Filament, и то, что там было неправильно:

- флаг премодерации отзывов (тип «boolean», как его завела миграция)
  в форме Filament не показывался вовсе — поле знало только «bool»;
- системную настройку можно было удалить: так пропал фон первого
  экрана, а с ним и способ сменить картинку. Теперь настройки,
  которые читает код, не удаляются;
- ключ новой настройки проверяется на вид.

Кнопка «Логотип площадки» над списком ведёт прямо к знаку, как в Filament.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex import images, laravel_storage
from savdex.adminsite import SavdexModelAdmin, register
from savdex.catalog import LOCALES
from savdex.site.models import (
    DISMISS_DAYS,
    GROUPS,
    PLACEMENTS,
    TYPES,
    Banner,
    BannerImage,
    Setting,
)

#: Currencies::ALL
CURRENCIES: dict[str, str] = {
    "UZS": "сум",
    "USD": "доллар США",
    "EUR": "евро",
    "CNY": "юань",
    "TRY": "турецкая лира",
    "RUB": "рубль",
    "KZT": "тенге",
}

#: PriceDisplay::KEY_PREFIX
CURRENCY_PREFIX = "display_currency_"

#: OfficeLocation::KEY_COORDS и COORDS_PATTERN
COORDS_KEY = "office_coords"
COORDS = re.compile(r"^\s*-?\d{1,2}(\.\d+)?\s*,\s*-?\d{1,3}(\.\d+)?\s*$")

#: Appearance::KEY_LOGO и LOGO_HINT
LOGO_KEY = "logo_image"
LOGO_HINT = (
    "Знак в шапке, в подвале, на вкладке браузера и в админке. Квадратный, от 512 px; "
    "лучше SVG или PNG с прозрачным фоном — знак стоит и на белом, и на тёмно-синем. "
    "Пустое поле возвращает знак по умолчанию"
)
HERO_HINT = (
    "До 8 МБ. Для фона первого экрана берите широкую горизонтальную картинку от "
    "1920 px: она обрезается по центру и затемняется, чтобы читался белый текст"
)

#: Ключ новой настройки: как у всех, что заводит код, — support_phone
KEY = re.compile(r"[a-z][a-z0-9_]*")


def _image_url(path: str) -> str:
    return f"/storage/{path}"


class SettingForm(forms.ModelForm):  # type: ignore[type-arg]
    """Настройка: поле значения — под её тип."""

    # Объявлены здесь, чтобы админка приняла их в набор полей формы;
    # настоящее поле значения подставляется в __init__ по типу
    value_input = forms.CharField(required=False)
    value_clear = forms.BooleanField(required=False)

    class Meta:
        model = Setting
        fields = ("label", "key", "group", "type", "description", "sort")
        labels: ClassVar[dict[str, str]] = {"description": "Пояснение"}
        help_texts: ClassVar[dict[str, str]] = {
            "key": "По нему настройка читается из кода. После создания не меняется",
            "type": "После создания не меняется: код ждёт значение определённого типа",
            "description": "Подсказка для того, кто будет менять настройку после вас",
        }
        widgets: ClassVar[dict[str, Any]] = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        setting: Setting = self.instance
        kind = setting.type if setting.pk else str(self.data.get("type") or "string")
        key = setting.key if setting.pk else str(self.data.get("key") or "")
        self._kind, self._key = kind, key

        self.fields["value_input"] = self._value_field(kind, key)

        if setting.pk and kind == "image":
            self.fields["value_clear"].label = "Убрать картинку — вернуть по умолчанию"
        else:
            self.fields.pop("value_clear", None)

            if setting.pk:
                self.initial["value_input"] = setting.value

        if not setting.pk:
            self.fields["value_input"].help_text = (
                "Поле значения подстраивается под тип после сохранения: число, "
                "переключатель, загрузка картинки"
            )

    @staticmethod
    def _value_field(kind: str, key: str) -> forms.Field:
        if kind in ("bool", "boolean"):
            return forms.BooleanField(label="Включено", required=False)

        if kind == "number":
            return forms.DecimalField(label="Значение", required=False)

        if kind == "text":
            return forms.CharField(
                label="Значение", required=False, widget=forms.Textarea(attrs={"rows": 4})
            )

        if kind == "image":
            is_logo = key == LOGO_KEY

            return forms.FileField(
                label="Логотип" if is_logo else "Изображение",
                required=False,
                help_text=LOGO_HINT if is_logo else HERO_HINT,
            )

        if key.startswith(CURRENCY_PREFIX):
            # Код, которого витрина не знает, молча заменялся бы валютой
            # по умолчанию — поэтому список, а не строка
            return forms.ChoiceField(
                label="Валюта", choices=[(c, f"{c} — {n}") for c, n in CURRENCIES.items()]
            )

        help_text = (
            "Широта и долгота через запятую, например: 41.311081, 69.240562"
            if key == COORDS_KEY
            else ""
        )

        return forms.CharField(
            label="Значение", required=False, max_length=500, help_text=help_text
        )

    def clean_key(self) -> str:
        key = str(self.cleaned_data.get("key") or "").strip()

        if not KEY.fullmatch(key):
            raise forms.ValidationError(
                "Латиница в нижнем регистре, цифры и подчёркивание: support_phone."
            )

        return key

    def clean_description(self) -> str | None:
        # Пустое пояснение — null, как хранит Filament: иначе первое же
        # сохранение записало бы в журнал «правку» пояснения
        return str(self.cleaned_data.get("description") or "").strip() or None

    def clean_value_input(self) -> Any:  # noqa: ANN401
        value = self.cleaned_data.get("value_input")

        if self._kind == "image":
            if value:
                try:
                    return laravel_storage.save_image(
                        value, "appearance", allow_svg=self._key == LOGO_KEY
                    )
                except laravel_storage.NotAnImageError as error:
                    raise forms.ValidationError(str(error)) from error

            return None

        if self._kind == "number" and value is not None:
            number = Decimal(value)

            return int(number) if number == number.to_integral_value() else float(number)

        if self._kind == "number":
            return None

        if self._key == COORDS_KEY and value and not COORDS.match(str(value)):
            # Строка «41,31 69,24» не разбирается, и карта на странице
            # «О компании» пропадает — молча и уже после сохранения
            raise forms.ValidationError(
                "Ожидается широта и долгота через запятую, например: 41.311081, 69.240562"
            )

        return value if value is not None else ""

    def save(self, commit: bool = True) -> Any:  # noqa: ANN401
        setting: Setting = self.instance
        value = self.cleaned_data.get("value_input")

        if self._kind == "image":
            if self.cleaned_data.get("value_clear"):
                setting.value = ""
            elif value:
                setting.value = value
            elif not setting.pk:
                setting.value = ""
        else:
            setting.value = value

        return super().save(commit)


@register(Setting, section="settings")
class SettingAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Setting"
    title_list = "Настройки площадки"
    title_add = "Новая настройка"
    title_change = "Настройка"
    change_list_template = "admin/site/setting/change_list.html"

    form = SettingForm
    list_display = ("title", "group_name", "shown_value", "sort")
    list_filter = ("group",)
    search_fields = ("label", "key")
    ordering = ("group", "sort", "key")
    list_per_page = 100

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        value = ["value_input"] + (
            ["value_clear"] if obj is not None and obj.type == "image" else []
        )
        about = (
            ("label", "group", "sort")
            if obj is not None
            else ("label", "key", "group", "type", "sort")
        )

        return (
            ("Настройка", {"fields": about}),
            ("Значение", {"fields": (*value, "description")}),
            ("Удаление", {"fields": ("held",)}),
        )

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        # Ключ и тип после создания не меняются: по ним настройку читает код
        return ("key", "type", "held") if obj is not None else ("held",)

    def get_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        return [f for _, box in self.get_fieldsets(request, obj) for f in box["fields"]]

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> Any:  # noqa: ANN401
        logo = Setting.objects.filter(key=LOGO_KEY).values_list("pk", flat=True).first()
        link = reverse("savdex_admin:site_setting_change", args=[logo]) if logo else None

        return super().changelist_view(request, {"logo_link": link, **(extra_context or {})})

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        """Настройку, которую читает код, не удаляют."""
        if not super().has_delete_permission(request, obj):
            return False

        return obj is None or not obj.is_system

    # ── Колонки ──

    @admin.display(description="Настройка", ordering="label")
    def title(self, obj: Setting) -> str:
        return f"{obj.label} · {obj.key}"

    @admin.display(description="Раздел", ordering="group")
    def group_name(self, obj: Setting) -> str:
        return GROUPS.get(obj.group, obj.group)

    @admin.display(description="Значение")
    def shown_value(self, obj: Setting) -> Any:  # noqa: ANN401
        value = obj.value

        if obj.type == "image":
            if not value:
                return "по умолчанию"

            return format_html(
                '<img src="{}" alt="" style="max-height:40px;max-width:120px">',
                _image_url(str(value)),
            )

        if obj.is_flag:
            return "Да" if value else "Нет"

        text = "" if value is None else str(value)

        return text if len(text) <= 80 else text[:80] + "…"

    @admin.display(description="Можно ли удалить")
    def held(self, obj: Setting | None) -> str:
        if obj is None or obj.pk is None:
            return "—"

        if obj.is_system:
            return "Нельзя: настройку читает код площадки."

        return "Можно: код площадки её не читает."

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        setting = Setting.objects.filter(pk=object_id).first()
        context = dict(extra_context or {})

        if setting is not None and setting.type == "image" and setting.value:
            # Текущая картинка видна в форме: иначе не понять, меняешь
            # ты её или ставишь впервые
            context["subtitle"] = format_html(
                'Сейчас: <img src="{}" alt="" style="max-height:80px;vertical-align:middle">',
                _image_url(str(setting.value)),
            )

        return super().change_view(request, object_id, form_url, context)


__all__ = ["TYPES", "SettingAdmin", "SettingForm"]


# ── Баннеры ─────────────────────────────────────────────────────────


def _image_field(label: str, help_text: str, *, required: bool) -> forms.FileField:
    return forms.FileField(
        label=label,
        required=required,
        help_text=help_text,
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )


def _prepared(form: forms.Form, field: str, frame: images.Frame) -> bytes | None:
    """Картинка из поля — проверенная и пересобранная, но ещё не на диске."""
    upload = form.cleaned_data.get(field)

    if not upload:
        return None

    try:
        return images.prepare(upload, frame)
    except images.NotAnImageError as error:
        raise forms.ValidationError(str(error)) from error


class BannerImagesMixin:
    """Картинки для компьютера и для телефона — общее у баннера и его языков."""

    cleaned_data: dict[str, Any]
    instance: Any

    def clean_image_upload(self) -> bytes | None:
        prepared = _prepared(self, "image_upload", images.BANNER)  # type: ignore[arg-type]

        if prepared is None and not self.instance.image_path:
            raise forms.ValidationError("Нужна картинка для компьютера.")

        return prepared

    def clean_image_mobile_upload(self) -> bytes | None:
        return _prepared(self, "image_mobile_upload", images.BANNER_MOBILE)  # type: ignore[arg-type]

    def put_images(self) -> None:
        """Записать новые картинки на диск; прежние удалит модель после записи."""
        desktop = self.cleaned_data.get("image_upload")
        mobile = self.cleaned_data.get("image_mobile_upload")

        if desktop:
            self.instance.image_path = images.write(desktop, "banners")

        if mobile:
            self.instance.image_mobile_path = images.write(mobile, "banners")
        elif self.cleaned_data.get("image_mobile_clear"):
            self.instance.image_mobile_path = None


class BannerForm(BannerImagesMixin, forms.ModelForm):  # type: ignore[type-arg]
    image_upload = _image_field(
        "Картинка для компьютера",
        "JPG, PNG или WebP до 8 МБ. Лучше широкая, например 2400×800",
        required=False,
    )
    image_mobile_upload = _image_field(
        "Картинка для телефона",
        "Необязательно, но с ней телефон выглядит заметно лучше. Например 1000×1200",
        required=False,
    )
    image_mobile_clear = forms.BooleanField(label="Убрать картинку для телефона", required=False)
    url = forms.URLField(
        label="Куда ведёт",
        required=False,
        max_length=500,
        assume_scheme="https",
        help_text="Можно оставить пустым — тогда баннер не кликается",
    )

    class Meta:
        model = Banner
        fields = (
            "name",
            "placement",
            "url",
            "alt",
            "starts_at",
            "ends_at",
            "sort",
            "is_active",
            "is_dismissible",
            "focal_x",
            "focal_y",
        )
        help_texts: ClassVar[dict[str, str]] = {
            "name": "На сайте не показывается. Нужно, чтобы отличать акции в этом списке",
            "placement": "На одном месте одновременно висит один баннер — "
            "тот, у кого меньше «порядок»",
            "alt": "Текстом: «Скидка 30% на годовой тариф до 1 октября». "
            "Нужно незрячим и поисковикам",
            "starts_at": "Время ташкентское. Пусто — показывать сразу. Акцию можно завести заранее",
            "ends_at": "Пусто — бессрочно. Снимать руками не нужно — пропадёт сам",
            "sort": "Меньше — важнее. При совпадении места показывается он",
            "is_active": "Выключает показ, не трогая даты",
            "is_dismissible": f"Закрытый вернётся через {DISMISS_DAYS} дня",
            "focal_x": "Что не обрезать, когда узкой картинки нет. "
            "0 — левый край, 100 — правый. Проще — щёлкнуть по картинке в предпросмотре",
            "focal_y": "0 — верх, 100 — низ",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if not self.instance.image_mobile_path:
            self.fields.pop("image_mobile_clear", None)

        # Одно поле с календарём браузера вместо разбитого на дату и время
        # поля админки; время — ташкентское (TIME_ZONE), в базу — UTC
        for name in ("starts_at", "ends_at"):
            old: Any = self.fields[name]
            self.fields[name] = forms.DateTimeField(
                label=old.label,
                required=False,
                help_text=old.help_text,
                input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"],
                widget=forms.DateTimeInput(
                    attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
                ),
            )

    def _within(self, field: str) -> int:
        value = self.cleaned_data.get(field)

        if value is None or not 0 <= value <= 100:
            raise forms.ValidationError("От 0 до 100.")

        return int(value)

    def clean_focal_x(self) -> int:
        return self._within("focal_x")

    def clean_focal_y(self) -> int:
        return self._within("focal_y")

    def clean_url(self) -> str | None:
        return self.cleaned_data.get("url") or None

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")

        if starts and ends and ends <= starts:
            self.add_error("ends_at", "Конец должен быть позже начала.")

        return cleaned

    def save(self, commit: bool = True) -> Any:  # noqa: ANN401
        self.put_images()

        return super().save(commit)


class BannerImageForm(BannerImagesMixin, forms.ModelForm):  # type: ignore[type-arg]
    image_upload = _image_field("Для компьютера", "", required=False)
    image_mobile_upload = _image_field("Для телефона", "", required=False)
    image_mobile_clear = forms.BooleanField(label="Убрать для телефона", required=False)

    class Meta:
        model = BannerImage
        fields = ("locale",)

    def save(self, commit: bool = True) -> Any:  # noqa: ANN401
        self.put_images()

        return super().save(commit)


class BannerImagesInline(admin.TabularInline):  # type: ignore[type-arg]
    """Картинки под отдельные языки: права — права на баннер."""

    model = BannerImage
    form = BannerImageForm
    fields = ("locale", "current", "image_upload", "image_mobile_upload", "image_mobile_clear")
    readonly_fields = ("current",)
    extra = 0
    max_num = len(LOCALES)
    verbose_name = "картинка под язык"
    verbose_name_plural = (
        "Картинки под отдельные языки — необязательно: русская полоса на китайской "
        "версии выглядит недоделкой. Не загрузили — везде показывается основная"
    )

    @admin.display(description="Сейчас")
    def current(self, obj: BannerImage) -> Any:  # noqa: ANN401
        if not obj or not obj.image_path:
            return "—"

        return format_html(
            '<img src="{}" alt="" style="max-height:40px;max-width:160px">',
            _image_url(obj.image_path),
        )

    def _parent_perm(self, request: HttpRequest, action: str) -> bool:
        return bool(request.user.has_perm(f"site.{action}_banner"))

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "view")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change" if obj else "add")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change" if obj else "add")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change" if obj else "add")


class LiveFilter(admin.SimpleListFilter):
    """«Висит сейчас» — не то же, что «включён»: включённый может ждать даты."""

    title = "висит сейчас"
    parameter_name = "live"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("yes", "Да"), ("no", "Нет")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        now = timezone.now()
        live = (
            Q(is_active=True)
            & (Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            & (Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        )

        if self.value() == "yes":
            return queryset.filter(live)
        if self.value() == "no":
            return queryset.exclude(live)

        return queryset


@register(Banner, section="content")
class BannerAdmin(SavdexModelAdmin):
    """
    Раздел «Баннеры» — вместо Filament BannerResource.

    Сверх Filament — предпросмотр: как баннер выглядит на компьютере
    и на телефоне, с обрезкой по точке фокуса и под каждый язык. Он
    обновляется сразу, ещё до сохранения: при выборе файла и смене
    точки фокуса; точку можно поставить щелчком по картинке.
    """

    laravel_model = "App\\Models\\Banner"
    title_list = "Баннеры"
    title_add = "Новый баннер"
    title_change = "Баннер"
    change_form_template = "admin/site/banner/change_form.html"

    form = BannerForm
    inlines = (BannerImagesInline,)
    fieldsets = (
        ("Что и куда", {"fields": ("name", "placement", "url", "alt")}),
        (
            "Срок акции",
            {
                "fields": ("starts_at", "ends_at", "sort", "is_active", "is_dismissible"),
                "description": "По окончании баннер исчезает сам.",
            },
        ),
        (
            "Картинка",
            {
                "fields": (
                    "image_upload",
                    "image_mobile_upload",
                    "image_mobile_clear",
                    "focal_x",
                    "focal_y",
                ),
                "description": "Широкая — для компьютера, узкая — для телефона. "
                "Без узкой широкая обрезается по точке фокуса.",
            },
        ),
    )
    list_display = ("thumb", "title", "countdown", "starts", "ends", "languages")
    list_display_links = ("thumb", "title")
    list_filter = ("placement", "is_active", LiveFilter)
    search_fields = ("name",)
    ordering = ("sort", "-id")

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        sets = super().get_fieldsets(request, obj)

        if obj is None or not obj.image_mobile_path:
            what, box = sets[2]
            sets = (
                *sets[:2],
                (
                    what,
                    {**box, "fields": tuple(f for f in box["fields"] if f != "image_mobile_clear")},
                ),
            )

        return sets

    def get_queryset(self, request: HttpRequest) -> QuerySet[Banner]:
        queryset: QuerySet[Banner] = super().get_queryset(request)

        return queryset.prefetch_related("images")

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Поля баннера и его языковые картинки: их замена — тоже правка."""
        by_language = {f"image:{i.locale}": i.image_path for i in obj.images.order_by("locale")}

        return {**self.attributes(obj), **by_language}

    # ── Предпросмотр ──

    def _preview(self, obj: Banner | None) -> dict[str, Any]:
        languages = {
            i.locale: {
                "label": LOCALES.get(i.locale, i.locale),
                "image": _image_url(i.image_path),
                "mobile": _image_url(i.image_mobile_path) if i.image_mobile_path else None,
            }
            for i in (obj.images.order_by("locale") if obj is not None else [])
        }

        return {
            "image": _image_url(obj.image_path) if obj and obj.image_path else None,
            "mobile": _image_url(obj.image_mobile_path) if obj and obj.image_mobile_path else None,
            "languages": languages,
        }

    def add_view(self, request: HttpRequest, form_url: str = "", extra_context: Any = None) -> Any:  # noqa: ANN401
        return super().add_view(
            request, form_url, {"banner_preview": self._preview(None), **(extra_context or {})}
        )

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        banner = Banner.objects.filter(pk=object_id).first()

        return super().change_view(
            request,
            object_id,
            form_url,
            {"banner_preview": self._preview(banner), **(extra_context or {})},
        )

    # ── Колонки ──

    @admin.display(description="Баннер")
    def thumb(self, obj: Banner) -> Any:  # noqa: ANN401
        return format_html(
            '<img src="{}" alt="" style="height:40px;max-width:160px;object-fit:cover">',
            _image_url(obj.image_path),
        )

    @admin.display(description="Название", ordering="name")
    def title(self, obj: Banner) -> Any:  # noqa: ANN401
        return format_html(
            "{}<br><small>{}</small>", obj.name, PLACEMENTS.get(obj.placement, obj.placement)
        )

    @admin.display(description="Осталось")
    def countdown(self, obj: Banner) -> Any:  # noqa: ANN401
        text = obj.countdown()
        live = obj.is_live()
        colour = "#6b7280" if not live else "#16a34a"

        if live and obj.ends_at is not None and (obj.ends_at - timezone.now()).days < 3:
            colour = "#d97706"

        return format_html('<span style="color:{};font-weight:600">{}</span>', colour, text)

    @admin.display(description="С", ordering="starts_at")
    def starts(self, obj: Banner) -> str:
        return (
            timezone.localtime(obj.starts_at).strftime("%d.%m.%Y %H:%M")
            if obj.starts_at
            else "сразу"
        )

    @admin.display(description="По", ordering="ends_at")
    def ends(self, obj: Banner) -> str:
        return (
            timezone.localtime(obj.ends_at).strftime("%d.%m.%Y %H:%M")
            if obj.ends_at
            else "бессрочно"
        )

    @admin.display(description="Языков")
    def languages(self, obj: Banner) -> str:
        count = len(obj.images.all())

        return "одна на все" if count == 0 else f"+{count}"
