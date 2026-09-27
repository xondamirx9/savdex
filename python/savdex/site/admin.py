"""
Раздел «Настройки площадки» админки на Django — вместо Filament SettingResource.

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
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from savdex import laravel_storage
from savdex.adminsite import SavdexModelAdmin, register
from savdex.site.models import GROUPS, TYPES, Setting

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
