"""
Раздел «Страницы и FAQ» админки на Django — вместо Filament PageResource.

Что изменилось против Filament:

- правка доходит до сайта. Раньше «О компании», «Помощь»,
  «Инструкция» и «Правила» брали текст из словаря, а Filament правил
  таблицу, которую сайт не читал;
- у текста есть поля под каждый язык (решение заказчика: «свои поля +
  машинный»). Пустой язык сайт показывает машинным переводом
  русского текста. Если русский текст поменяли, а язык оставили
  прежним, раздел предупреждает: иначе перевод тихо разошёлся бы
  с оригиналом;
- набор страниц задан кодом (у каждой свой адрес и вёрстка): страницы
  не заводятся и не удаляются, ключ и адрес не правятся. Скрыть
  можно только «Помощь», «Инструкцию» и «Правила»;
- у текста есть простая разметка — шаги, список, предупреждение
  (App\\Support\\PageBody), вместо сплошных абзацев.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html, format_html_join

from savdex.adminsite import SavdexModelAdmin, register
from savdex.catalog import LOCALES
from savdex.site.models import FaqItem, Page

#: Языки со своими полями; русский — основные столбцы
OTHER_LOCALES: tuple[str, ...] = tuple(code for code in LOCALES if code != "ru")

MACHINE_HINT = "Пустое поле — сайт покажет машинный перевод русского текста."

MARKUP_HINT = (
    "Абзацы — через пустую строку. В начале строки: «## » — подзаголовок; "
    "«1. » — шаг (подсказка к нему — следующей строкой); «- » — пункт с галочкой; "
    "«! » — предупреждение (пояснение — следующей строкой)."
)

#: Что значат поля у каждой страницы: у «Контактов» текст — это раздел
#: офиса, у «Помощи» — вступление над вопросами
PAGE_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "about": {
        "excerpt": ("Подзаголовок", "Крупно под заголовком страницы."),
        "body": ("Текст «О нас»", "Под ним — счётчики и принципы площадки."),
    },
    "contacts": {
        "excerpt": ("Текст под заголовком", "Над карточками с телефоном и почтой. Можно пусто."),
        "body": (
            "Текст раздела «Офис на карте»",
            "Раздел виден, когда адрес офиса заполнен в настройках площадки.",
        ),
    },
    "help": {
        "excerpt": ("Подзаголовок", "Крупно под заголовком страницы."),
        "body": ("Вступление", "Над вопросами и ответами. Можно пусто."),
    },
    "guide": {
        "excerpt": ("Подзаголовок", "Крупно под заголовком страницы."),
        "body": ("Текст", ""),
    },
    "rules": {
        "excerpt": ("Подзаголовок", "Крупно под заголовком страницы."),
        "body": ("Текст", ""),
    },
}


def _language_fields(spec: dict[str, forms.Field]) -> dict[str, forms.Field]:
    """Поля «заголовок_uz» и т. п. — копии русских, необязательные."""
    fields: dict[str, forms.Field] = {}

    for name, field in spec.items():
        for code in OTHER_LOCALES:
            copy = forms.CharField(
                label=field.label,
                required=False,
                max_length=getattr(field, "max_length", None),
                widget=field.widget.__class__(attrs=dict(field.widget.attrs)),
            )
            fields[f"{name}_{code}"] = copy

    return fields


class OwnTranslationsForm(forms.ModelForm):  # type: ignore[type-arg]
    """Текст со своими полями под языки: {поле}_{язык} ↔ столбец {поле}_i18n."""

    TRANSLATED: ClassVar[tuple[str, ...]] = ()

    def translated(self) -> list[str]:
        """
        Поля с языками, которые есть в этой форме: у секции главной
        бывает только заголовок, и отсутствующее поле не должно стирать
        свои переводы.
        """
        return [name for name in self.TRANSLATED if name in self.fields]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for name in self.translated():
            stored = getattr(self.instance, f"{name}_i18n", None) or {}

            for code in OTHER_LOCALES:
                self.fields[f"{name}_{code}"].initial = stored.get(code, "")

    def save(self, commit: bool = True) -> Any:  # noqa: ANN401
        for name in self.translated():
            values = {
                code: text
                for code in OTHER_LOCALES
                if (text := str(self.cleaned_data.get(f"{name}_{code}") or "").strip())
            }
            setattr(self.instance, f"{name}_i18n", values or None)

        return super().save(commit)

    def stale_languages(self) -> list[tuple[str, list[str]]]:
        """
        Русский текст поменяли, а свой перевод языка оставили прежним:
        он теперь переводит старый текст.
        """
        stale = []

        for name in self.translated():
            if name not in self.changed_data:
                continue

            languages = [
                LOCALES[code]
                for code in OTHER_LOCALES
                if self.cleaned_data.get(f"{name}_{code}")
                and f"{name}_{code}" not in self.changed_data
            ]

            if languages:
                stale.append((str(self.fields[name].label), languages))

        return stale


_PAGE_TEXT: dict[str, forms.Field] = {
    "title": forms.CharField(label="Заголовок", max_length=190),
    "excerpt": forms.CharField(label="Подзаголовок", widget=forms.Textarea(attrs={"rows": 2})),
    "body": forms.CharField(label="Текст", widget=forms.Textarea(attrs={"rows": 12})),
}


class PageFormBase(OwnTranslationsForm):
    TRANSLATED = ("title", "excerpt", "body")

    class Meta:
        model = Page
        fields = ("title", "excerpt", "body", "is_published", "meta_title", "meta_description")
        widgets: ClassVar[dict[str, Any]] = {
            "excerpt": forms.Textarea(attrs={"rows": 2}),
            "body": forms.Textarea(attrs={"rows": 12}),
            "meta_description": forms.Textarea(attrs={"rows": 2, "maxlength": 255}),
        }
        help_texts: ClassVar[dict[str, str]] = {
            "is_published": "Скрытая страница не открывается и пропадает из оглавления",
            "meta_title": "Только по-русски, другие языки переводятся. "
            "Пусто — возьмём заголовок страницы",
            "meta_description": "Пусто — возьмём подзаголовок",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        meaning = PAGE_FIELDS.get(self.instance.key, {})

        for name, (label, hint) in meaning.items():
            for field in [name, *(f"{name}_{code}" for code in OTHER_LOCALES)]:
                if field in self.fields:
                    self.fields[field].label = label

            self.fields[name].help_text = hint

        if "body" in self.fields:
            body_hint = str(self.fields["body"].help_text or "")
            self.fields["body"].help_text = f"{body_hint} {MARKUP_HINT}".strip()

    def clean_excerpt(self) -> str | None:
        return str(self.cleaned_data.get("excerpt") or "").strip() or None

    def clean_body(self) -> str | None:
        return str(self.cleaned_data.get("body") or "").strip() or None

    def clean_meta_title(self) -> str | None:
        return str(self.cleaned_data.get("meta_title") or "").strip() or None

    def clean_meta_description(self) -> str | None:
        return str(self.cleaned_data.get("meta_description") or "").strip() or None


PageForm = type("PageForm", (PageFormBase,), _language_fields(_PAGE_TEXT))


class FaqItemFormBase(OwnTranslationsForm):
    TRANSLATED = ("question", "answer")

    class Meta:
        model = FaqItem
        fields = ("question", "answer", "is_published", "sort")
        widgets: ClassVar[dict[str, Any]] = {"answer": forms.Textarea(attrs={"rows": 3})}


FaqItemForm = type(
    "FaqItemForm",
    (FaqItemFormBase,),
    _language_fields(
        {
            "question": forms.CharField(label="Вопрос", max_length=190),
            "answer": forms.CharField(label="Ответ", widget=forms.Textarea(attrs={"rows": 3})),
        }
    ),
)


def _language_fieldsets(
    fields: tuple[str, ...], *, title: str = "{}"
) -> tuple[tuple[str, dict[str, Any]], ...]:
    return tuple(
        (
            title.format(LOCALES[code]),
            {
                "fields": tuple(f"{name}_{code}" for name in fields),
                "classes": ("collapse",),
                "description": MACHINE_HINT,
            },
        )
        for code in OTHER_LOCALES
    )


class FaqItemsInline(admin.StackedInline):  # type: ignore[type-arg]
    """Вопросы «Помощи» — часть страницы: права на них — права на страницу."""

    model = FaqItem
    form = FaqItemForm
    extra = 0
    ordering = ("sort", "id")
    verbose_name = "вопрос"
    verbose_name_plural = "Вопросы и ответы"
    fieldsets: ClassVar[Any] = (
        (None, {"fields": ("question", "answer", ("is_published", "sort"))}),
        *_language_fieldsets(("question", "answer")),
    )

    def _parent_perm(self, request: HttpRequest, action: str) -> bool:
        return bool(request.user.has_perm(f"site.{action}_page"))

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "view")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return self._parent_perm(request, "change")


@register(Page, section="content")
class PageAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Page"
    title_list = "Страницы и FAQ"
    title_change = "Страница"

    form = PageForm
    inlines = (FaqItemsInline,)
    readonly_fields = ("site_link",)
    list_display = ("title", "site_link", "languages", "faq", "state")
    list_filter = ("is_published",)
    ordering = ("sort", "id")

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        main: tuple[str, ...] = ("site_link", "title", "excerpt", "body")

        if obj is not None and obj.can_hide:
            main = (*main, "is_published")

        return (
            ("Русский", {"fields": main}),
            *_language_fieldsets(("title", "excerpt", "body")),
            (
                "Для поисковиков",
                {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)},
            ),
        )

    def get_inlines(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        # Вопросы и ответы сайт показывает только на «Помощи»
        return self.inlines if obj is not None and obj.key == "help" else ()

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        pages: QuerySet[Any] = super().get_queryset(request)

        counted: QuerySet[Any] = pages.annotate(
            _faq=Count("faq_items", filter=Q(faq_items__is_published=True))
        )

        return counted

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def snapshot(self, obj: Any) -> dict[str, Any]:  # noqa: ANN401
        """Вопросы помощи — часть страницы: их правка тоже идёт в журнал."""
        attributes = self.attributes(obj)

        if obj.pk is not None and obj.key == "help":
            attributes["faq"] = [
                {
                    "question": item.question,
                    "answer": item.answer,
                    "question_i18n": item.question_i18n,
                    "answer_i18n": item.answer_i18n,
                    "is_published": item.is_published,
                }
                for item in FaqItem.objects.filter(page=obj).order_by("sort", "id")
            ]

        return attributes

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:  # noqa: ANN401
        super().save_related(request, form, formsets, change)

        stale = form.stale_languages()

        for formset in formsets:
            for inline in formset.forms:
                if inline.has_changed() and not inline.cleaned_data.get("DELETE"):
                    stale += [
                        (f"{label} «{inline.instance.question}»", languages)
                        for label, languages in inline.stale_languages()
                    ]

        if stale:
            what = "; ".join(f"{label} — {', '.join(langs)}" for label, langs in stale)
            messages.warning(
                request,
                "Русский текст изменён, а свой перевод остался прежним — проверьте его "
                f"или очистите поле, чтобы сайт показал машинный перевод. {what}.",
            )

    # ── Колонки ──

    @admin.display(description="Адрес на сайте")
    def site_link(self, obj: Page) -> Any:  # noqa: ANN401
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{} ↗</a>', obj.address, obj.address
        )

    @admin.display(description="Свои языки")
    def languages(self, obj: Page) -> Any:  # noqa: ANN401
        """Какие языки заполнены своим текстом; остальные — машинный перевод."""
        own = set((obj.title_i18n or {}).keys()) | set((obj.body_i18n or {}).keys())

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

    @admin.display(description="Вопросов")
    def faq(self, obj: Page) -> str:
        return str(obj._faq) if obj.key == "help" else "—"  # type: ignore[attr-defined]

    @admin.display(description="Видимость", ordering="is_published")
    def state(self, obj: Page) -> Any:  # noqa: ANN401
        if obj.is_published or not obj.can_hide:
            return format_html('<span style="color:#16a34a;font-weight:600">{}</span>', "Открыта")

        return format_html('<span style="color:#6b7280;font-weight:600">{}</span>', "Скрыта")
