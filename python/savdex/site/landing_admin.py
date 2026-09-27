"""
Раздел «Главная страница» админки на Django — вместо Filament
LandingBlockResource.

Что изменилось против Filament:

- правка доходит до сайта. Раньше главная брала тексты из словаря,
  а Filament правил таблицу, которую сайт не читал;
- решение заказчика: правятся тексты, вопросы и видимость секций,
  а порядок — как в макете. Секции не заводятся, не удаляются и не
  переставляются; первый экран не скрывается (на нём поиск);
- у каждой секции — только её поля: у «Поставщиков» один заголовок,
  у «Как это работает» — ещё шаги, у призыва — кнопка и подпись;
- языки — свои поля и машинный перевод, как у страниц
  (savdex/site/pages_admin.py).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.html import format_html, format_html_join

from savdex.adminsite import SavdexModelAdmin, register
from savdex.catalog import LOCALES
from savdex.site.models import LandingBlock
from savdex.site.pages_admin import (
    OTHER_LOCALES,
    OwnTranslationsForm,
    _language_fields,
    _language_fieldsets,
)

ITEMS_HINT = "Название первой строкой, пояснение — следующей; пункты разделяйте пустой строкой."

#: Поля каждой секции: подпись и подсказка. Чего нет в списке, того
#: у секции на сайте нет
LANDING_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "hero": {
        "heading": ("Заголовок", "Крупно на фотографии первого экрана."),
        "subheading": ("Подзаголовок", "Под заголовком, над кнопками."),
    },
    "stats": {},
    "categories": {"heading": ("Заголовок секции", "")},
    "vip": {"heading": ("Заголовок секции", "")},
    "requests": {"heading": ("Заголовок секции", "")},
    "suppliers": {"heading": ("Заголовок секции", "")},
    "how": {
        "eyebrow": ("Надзаголовок", "Мелко над заголовком."),
        "heading": ("Заголовок секции", ""),
        "subheading": ("Подзаголовок", ""),
        "body": ("Шаги", f"{ITEMS_HINT} В ряд помещаются четыре шага."),
    },
    "reviews": {"heading": ("Заголовок секции", "")},
    "faq": {
        "heading": ("Заголовок секции", ""),
        "body": (
            "Вопросы и ответы",
            "Вопрос первой строкой, ответ — следующей; вопросы разделяйте пустой строкой. "
            "Шесть вопросов ложатся в сетку ровно. Те же вопросы видит Google.",
        ),
    },
    "news": {
        "eyebrow": ("Надзаголовок", "Мелко над заголовком."),
        "heading": ("Заголовок секции", ""),
    },
    "cta": {
        "heading": ("Заголовок", ""),
        "subheading": ("Подзаголовок", ""),
        "button": ("Кнопка", "Ведёт на регистрацию."),
        "body": ("Подпись под кнопкой", "Можно пусто."),
    },
}

#: Секции, у которых текст — пункты «название + пояснение»
WITH_ITEMS = frozenset({"how", "faq"})

#: Что обязательно: без заголовка секция на сайте выглядит сломанной
REQUIRED = frozenset({"heading", "button"})

_CHUNKS = re.compile(r"\n\s*\n")

_LANDING_TEXT: dict[str, forms.Field] = {
    "eyebrow": forms.CharField(label="Надзаголовок", max_length=190),
    "heading": forms.CharField(label="Заголовок", max_length=190),
    "subheading": forms.CharField(label="Подзаголовок", widget=forms.Textarea(attrs={"rows": 2})),
    "button": forms.CharField(label="Кнопка", max_length=190),
    "body": forms.CharField(label="Текст", widget=forms.Textarea(attrs={"rows": 12})),
}


def _items_error(text: str) -> str | None:
    """Пункт без пояснения — сообщение для формы; всё верно — None."""
    for chunk in _CHUNKS.split(text.replace("\r\n", "\n").strip()):
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]

        if len(lines) == 1:
            return f"У пункта «{lines[0]}» нет пояснения — оно пишется следующей строкой."

    return None


class LandingBlockFormBase(OwnTranslationsForm):
    TRANSLATED = ("eyebrow", "heading", "subheading", "button", "body")

    class Meta:
        model = LandingBlock
        fields = ("eyebrow", "heading", "subheading", "button", "body", "is_visible")
        widgets: ClassVar[dict[str, Any]] = {
            "subheading": forms.Textarea(attrs={"rows": 2}),
            "body": forms.Textarea(attrs={"rows": 12}),
        }
        help_texts: ClassVar[dict[str, str]] = {
            "is_visible": "Скрытая секция пропадает с главной; порядок секций — как в макете",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        meaning = LANDING_FIELDS.get(self.instance.key, {})

        for name, (label, hint) in meaning.items():
            for field in [name, *(f"{name}_{code}" for code in OTHER_LOCALES)]:
                if field in self.fields:
                    self.fields[field].label = label

            if name in self.fields:
                self.fields[name].help_text = hint
                self.fields[name].required = name in REQUIRED or (
                    name == "body" and self.instance.key in WITH_ITEMS
                )

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}

        for name in self.translated():
            value = data.get(name)
            data[name] = str(value).strip() or None if value is not None else None

        if self.instance.key in WITH_ITEMS:
            for field in ["body", *(f"body_{code}" for code in OTHER_LOCALES)]:
                error = _items_error(str(data.get(field) or ""))

                if error and field in self.fields:
                    self.add_error(field, error)

        return data


LandingBlockForm = type(
    "LandingBlockForm", (LandingBlockFormBase,), _language_fields(_LANDING_TEXT)
)


@register(LandingBlock, section="content")
class LandingBlockAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\LandingBlock"
    title_list = "Главная страница"
    title_change = "Секция главной"

    form = LandingBlockForm
    list_display = ("name", "texts", "languages", "state")
    ordering = ("sort", "id")
    list_per_page = 50

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        fields = tuple(LANDING_FIELDS.get(obj.key, {}) if obj is not None else ())
        main: tuple[str, ...] = fields

        if obj is not None and obj.can_hide:
            main = (*main, "is_visible")

        if not fields:
            return (("Показ", {"fields": main}),)

        return (
            ("Русский", {"fields": main}),
            *_language_fieldsets(fields),
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:  # noqa: ANN401
        super().save_related(request, form, formsets, change)

        stale = form.stale_languages()

        if stale:
            what = "; ".join(f"{label} — {', '.join(langs)}" for label, langs in stale)
            messages.warning(
                request,
                "Русский текст изменён, а свой перевод остался прежним — проверьте его "
                f"или очистите поле, чтобы сайт показал машинный перевод. {what}.",
            )

    # ── Колонки ──

    @admin.display(description="Что правится")
    def texts(self, obj: LandingBlock) -> str:
        fields = LANDING_FIELDS.get(obj.key, {})

        return ", ".join(label.lower() for label, _ in fields.values()) or "только показ"

    @admin.display(description="Свои языки")
    def languages(self, obj: LandingBlock) -> Any:  # noqa: ANN401
        """Какие языки заполнены своим текстом; остальные — машинный перевод."""
        if not LANDING_FIELDS.get(obj.key):
            return "—"

        own: set[str] = set()

        for column in ("heading_i18n", "body_i18n"):
            own |= set((getattr(obj, column) or {}).keys())

        return format_html_join(
            " ",
            '<span style="{}" title="{}">{}</span>',
            (
                (
                    "font-weight:600" if code == "ru" or code in own else "color:#9ca3af",
                    "свой текст" if code == "ru" or code in own else "машинный перевод",
                    code,
                )
                for code in LOCALES
            ),
        )

    @admin.display(description="Видимость", ordering="is_visible")
    def state(self, obj: LandingBlock) -> Any:  # noqa: ANN401
        if obj.is_visible or not obj.can_hide:
            return format_html('<span style="color:#16a34a;font-weight:600">{}</span>', "Видна")

        return format_html('<span style="color:#6b7280;font-weight:600">{}</span>', "Скрыта")
