"""
Модерация отзывов в админке Django (этап 6) — вместо разделов Filament
«Отзывы» и «Отзывы о площадке». Право — раздел reviews: одна работа
одного модератора.

Отзывы о компаниях:

- очередь «Ждут решения» (включена по умолчанию) — премодерация и споры
  одним списком: это одна работа, и вторую вкладку модератор забудет;
- решения на странице отзыва: «Опубликовать», «Не пропускать», «Скрыть
  отзыв» и «Оставить отзыв» (по спору), «Вернуть на витрину»; где нужна
  формулировка — не короче 15 знаков, её дословно получают стороны;
- правка и заведение вручную (origin — «Заведён вручную», кто завёл —
  сам), загрузка файлом с отдельным правом reviews.import (origin —
  «Загружен файлом»); одна пара «автор — компания — объявление»;
- удаление — только суперадмин (скрытие — не удаление), рейтинг
  пересчитывается.

Отзывы о площадке — только решения: заводят их сами пользователи.

Отличие от Filament: решать по отзывам о компаниях может только тот, у
кого есть правка раздела (у Filament кнопки решений видел каждый, кому
открыт список, — и поддержка с правом «смотреть»).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.crm.admin import OpenFilter, _badge
from savdex.crm.models import Company
from savdex.guards import allowed_writes
from savdex.moderation import services
from savdex.moderation.models import (
    DISPUTES,
    DOC_APPROVED,
    DOC_PENDING,
    DOC_REJECTED,
    DOC_STATUSES,
    HIDDEN,
    MODERATION,
    ORIGINS,
    PUBLISHED,
    RESUME_BLOCKED,
    RESUME_PUBLISHED,
    RESUME_STATUSES,
    SHOWCASE,
    VERIFICATION_TYPES,
    CompanyDocument,
    Listing,
    PlatformReview,
    Resume,
    Review,
)
from savdex.tenders import importer
from savdex.text import numeric
from savdex.web import ui

#: Формулировка решения — не отписка
MIN_NOTE = 15

#: Файл больше — не загрузка отзывов, а ошибка (или не тот файл)
MAX_UPLOAD = 10 * 1024 * 1024

SHOWCASE_TONES = {PUBLISHED: "success", MODERATION: "warning", HIDDEN: "gray"}
DISPUTE_TONES = {"pending": "warning", "accepted": "success"}

RATINGS = [
    (5, "5 — отлично"),
    (4, "4 — хорошо"),
    (3, "3 — нормально"),
    (2, "2 — плохо"),
    (1, "1 — очень плохо"),
]


def _rating(value: int) -> str:
    tone = "success" if value >= 4 else "warning" if value == 3 else "danger"

    return _badge(f"{value} из 5", tone)


def _short(text: str | None, limit: int) -> str:
    """->limit(N): обрезка с многоточием."""
    text = text or ""

    return text if len(text) <= limit else text[:limit].rstrip() + "..."


class Waiting(OpenFilter):
    """«Ждут решения» — премодерация и споры одной очередью, по умолчанию."""

    # Не «all»: так ChangeList называет «показать всё без страниц»
    parameter_name = "queue"
    title = "очередь"
    open_label = "Ждут решения"
    all_label = "Все отзывы"
    open_q = Q(status=MODERATION) | Q(dispute_status="pending")


class Flagged(admin.SimpleListFilter):
    title = "проверка"
    parameter_name = "flagged"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "С отметками проверки")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(screening_flags__isnull=False) if self.value() == "1" else queryset


class Showcase(admin.SimpleListFilter):
    title = "на витрине"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(SHOWCASE.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(status=self.value()) if self.value() else queryset


class Stars(admin.SimpleListFilter):
    title = "оценка"
    parameter_name = "rating"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [(str(n), str(n)) for n in (5, 4, 3, 2, 1)]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        value = self.value()

        return queryset.filter(rating=int(value)) if value and numeric(value) else queryset


class Origin(admin.SimpleListFilter):
    title = "откуда отзыв"
    parameter_name = "origin"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(ORIGINS.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Review]) -> QuerySet[Review]:
        return queryset.filter(origin=self.value()) if self.value() else queryset


# ── Форма отзыва ─────────────────────────────────────────────────────


def _companies() -> QuerySet[Company]:
    return Company.objects.filter(deleted_at__isnull=True).order_by("name", "id")


class ReviewForm(forms.ModelForm):  # type: ignore[type-arg]
    rating = forms.TypedChoiceField(label="Общая оценка", choices=RATINGS, coerce=int)
    body = forms.CharField(
        label="Отзыв", widget=forms.Textarea(attrs={"rows": 5}), min_length=10, max_length=5000
    )
    reply = forms.CharField(
        label="Ответ компании",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        max_length=5000,
        empty_value=None,
        help_text="Необязательно. Обычно пишет сама компания из кабинета",
    )

    class Meta:
        model = Review
        fields = (
            "company",
            "author_company",
            "listing",
            "rating",
            "rating_description",
            "rating_response",
            "rating_deadlines",
            "rating_quality",
            "deal_confirmed",
            "body",
            "reply",
            "status",
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Только просмотр (право «смотреть»): полей в форме нет
        if "company" not in self.fields:
            return

        for name in ("company", "author_company"):
            field = self.fields[name]
            assert isinstance(field, forms.ModelChoiceField)
            field.queryset = _companies()

        self.fields["author_company"].help_text = "Компания не может отозваться о себе"
        listing = self.fields["listing"]
        assert isinstance(listing, forms.ModelChoiceField)
        listing.queryset = Listing.objects.filter(deleted_at__isnull=True).order_by("title", "id")
        listing.help_text = "Необязательно: отзыв может быть о работе с компанией вообще"

        for name in ("rating_description", "rating_response", "rating_deadlines", "rating_quality"):
            label = self.fields[name].label
            self.fields[name] = forms.TypedChoiceField(
                label=label,
                choices=[("", "—"), *((n, str(n)) for n in range(1, 6))],
                coerce=int,
                required=False,
                empty_value=None,
            )

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}
        company, author = data.get("company"), data.get("author_company")

        if company is None or author is None:
            return data

        if company.pk == author.pk:
            self.add_error("author_company", "Компания не может отозваться о себе.")

            return data

        # Повтор пары ловится здесь, а не базой: у отзыва о компании
        # объявления нет, а NULL в индексе не равен NULL
        listing = data.get("listing")
        twins = Review.objects.filter(company=company, author_company=author)
        twins = twins.filter(listing=listing) if listing else twins.filter(listing__isnull=True)

        if self.instance.pk is not None:
            twins = twins.exclude(pk=self.instance.pk)

        if twins.exists():
            self.add_error(
                "author_company", "Отзыв этой компании об этой уже есть — откройте и поправьте его."
            )

        return data


class ImportForm(forms.Form):
    file = forms.FileField(
        label="Файл",
        help_text="Excel (.xlsx) или CSV. Первая строка — заголовки столбцов.",
    )


# ── Отзывы о компаниях ───────────────────────────────────────────────


@register(Review, section="reviews")
class ReviewAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\Review"
    title_list = "Отзывы"
    title_add = "Завести отзыв"
    title_change = "Отзыв"
    change_form_template = "admin/moderation/review/change_form.html"
    change_list_template = "admin/moderation/review/change_list.html"

    form = ReviewForm
    fieldsets = (
        (
            "Кто о ком",
            {
                "fields": ("company", "author_company", "listing"),
                "description": "Один отзыв на пару «автор — компания — объявление». Повтор "
                "той же пары не заводится: правьте существующий.",
            },
        ),
        (
            "Оценка",
            {
                "fields": (
                    "rating",
                    "rating_description",
                    "rating_response",
                    "rating_deadlines",
                    "rating_quality",
                    "deal_confirmed",
                )
            },
        ),
        ("Текст", {"fields": ("body", "reply", "status")}),
    )
    list_display = ("about", "stars", "text", "showcase", "dispute", "source", "left")
    list_filter = (Waiting, Origin, Flagged, Showcase, Stars)
    list_select_related = ("company", "author_company", "created_by")
    search_fields = ("company__name", "body")
    ordering = ("-created_at", "-id")
    list_per_page = 50

    # ── Список ──

    @admin.display(description="о компании", ordering="company__name")
    def about(self, obj: Review) -> str:
        author = obj.author_company
        name = author.name if author is not None and author.deleted_at is None else "удалён"

        return format_html(
            "{}<br><small>автор: {}</small>", obj.company.name if obj.company else "—", name
        )

    @admin.display(description="оценка", ordering="rating")
    def stars(self, obj: Review) -> str:
        return _rating(obj.rating)

    @admin.display(description="отзыв")
    def text(self, obj: Review) -> str:
        return _short(obj.body, 120)

    @admin.display(description="на витрине", ordering="status")
    def showcase(self, obj: Review) -> str:
        # Что насторожило автоматическую проверку — сразу под статусом
        return format_html(
            "{}<br><small>{}</small>",
            _badge(SHOWCASE.get(obj.status, "Скрыт"), SHOWCASE_TONES.get(obj.status, "gray")),
            obj.screening_flags or "",
        )

    @admin.display(description="спор", ordering="dispute_status")
    def dispute(self, obj: Review) -> str:
        if obj.dispute_status is None:
            return "—"

        return format_html(
            "{}<br><small>{}</small>",
            _badge(
                DISPUTES.get(obj.dispute_status, "—"), DISPUTE_TONES.get(obj.dispute_status, "gray")
            ),
            obj.dispute_reason or "",
        )

    @admin.display(description="откуда", ordering="origin")
    def source(self, obj: Review) -> str:
        creator = obj.created_by

        return format_html(
            "{}<br><small>{}</small>",
            _badge(
                ORIGINS.get(obj.origin, obj.origin),
                "success" if obj.origin == "buyer" else "warning",
            ),
            creator.name if creator is not None else "",
        )

    @admin.display(description="оставлен", ordering="created_at")
    def left(self, obj: Review) -> str:
        return obj.created_at.strftime("%d.%m.%Y") if obj.created_at else ""

    # ── Запись ──

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        # CreateReview: происхождение и автор — кодом, а не формой
        if not change:
            obj.origin = "admin"
            obj.created_by_id = _admin_of(request).id

        with allowed_writes("reviews"):
            super().save_model(request, obj, form, change)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:  # noqa: ANN401
        super().save_related(request, form, formsets, change)

        # Review::saved: новый — пересчёт; правка — если сменились оценка,
        # статус или компания (у прежней компании тоже)
        before: dict[str, Any] = getattr(form, "_savdex_before", {})
        obj = form.instance
        watched = ("rating", "status", "company_id")

        if not change or any(before.get(k) != getattr(obj, k) for k in watched):
            services.recalculate_companies(
                services.context_of(request), before.get("company_id"), obj.company_id
            )

    def delete_model(self, request: HttpRequest, obj: Any) -> None:  # noqa: ANN401
        """Насовсем (SoftDeletes у отзыва нет); Review::deleted — пересчёт."""
        pk, company_id = obj.pk, obj.company_id

        with transaction.atomic():
            with allowed_writes("reviews"):
                Review.objects.filter(pk=pk).delete()

            self.journal(request, "deleted", obj)
            services.recalculate_companies(services.context_of(request), company_id)

        request._savdex_done = f"Удалено: отзыв №{pk}"  # type: ignore[attr-defined]

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        for obj in list(queryset):
            self.delete_model(request, obj)

    # ── Решения ──

    def can_decide(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("reviews.edit")

    def decisions(self, review: Review) -> list[tuple[str, str, bool]]:
        """(код, подпись, нужна ли формулировка) — какие решения доступны."""
        found = []

        if review.status == MODERATION:
            found += [("approve", "Опубликовать", False), ("reject", "Не пропускать", True)]

        if review.dispute_status == "pending":
            found += [("accept", "Скрыть отзыв", True), ("decline", "Оставить отзыв", True)]

        if review.status == HIDDEN:
            found.append(("restore", "Вернуть на витрину", False))

        return found

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/decide/",
                self.admin_site.admin_view(self.decide_view),
                name="moderation_review_decide",
            ),
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="moderation_review_import",
            ),
            *super().get_urls(),
        ]

    def decide_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.can_decide(request):
            raise PermissionDenied

        review = self.get_object(request, object_id)

        if not isinstance(review, Review):
            raise PermissionDenied

        page = reverse("savdex_admin:moderation_review_change", args=[review.pk])
        decision = request.POST.get("decision", "")
        allowed = {code: needs for code, _, needs in self.decisions(review)}

        if decision not in allowed:
            self.message_user(request, "Это решение по отзыву уже недоступно.", messages.WARNING)

            return HttpResponseRedirect(page)

        note = (request.POST.get("note") or "").strip()

        if allowed[decision] and len(note) < MIN_NOTE:
            self.message_user(
                request,
                f"Напишите формулировку решения — не короче {MIN_NOTE} знаков: её получат стороны.",
                messages.ERROR,
            )

            return HttpResponseRedirect(page)

        done = {
            "approve": lambda: services.approve_review(request, review),
            "reject": lambda: services.reject_review(request, review, note),
            "accept": lambda: services.accept_dispute(request, review, note),
            "decline": lambda: services.decline_dispute(request, review, note),
            "restore": lambda: services.restore_review(request, review),
        }
        done[decision]()
        self.message_user(
            request,
            {
                "approve": "Отзыв опубликован.",
                "reject": "Отзыв отклонён.",
                "accept": "Отзыв скрыт, рейтинг пересчитан.",
                "decline": "Спор отклонён.",
                "restore": "Отзыв снова виден.",
            }[decision],
            messages.SUCCESS,
        )

        return HttpResponseRedirect(page)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        review = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(review, Review):
            extra["review"] = review
            extra["decisions"] = self.decisions(review) if self.can_decide(request) else []
            extra["min_note"] = MIN_NOTE
            extra["origin_label"] = ORIGINS.get(review.origin, review.origin)
            extra["dispute_label"] = DISPUTES.get(review.dispute_status or "", "")

        return super().change_view(request, object_id, form_url, extra)

    # ── Загрузка файлом ──

    def can_import(self, request: HttpRequest) -> bool:
        """Загрузка создаёт записи пачкой мимо формы — право отдельное."""
        return _admin_of(request).can("reviews.import")

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        return super().changelist_view(
            request,
            {
                "can_import": self.can_import(request),
                "import_url": reverse("savdex_admin:moderation_review_import"),
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
            table = None

            if upload.size > MAX_UPLOAD:
                form.add_error("file", "Файл больше 10 МБ.")
            else:
                try:
                    table = importer.read_table(upload.name, upload.read())
                except Exception:
                    form.add_error("file", "Не удалось прочитать файл: нужен .xlsx или .csv.")

            if table is not None:
                report = self.import_reviews(request, table)
                messages.success(
                    request,
                    f"Загружено отзывов: {report['done']}."
                    + (
                        f" Пропущено строк: {len(report['failed'])}. Обычно это ненайденная "
                        "компания — проверьте написание названий."
                        if report["failed"]
                        else ""
                    ),
                )

        return TemplateResponse(
            request,
            "admin/moderation/review/import.html",
            {
                **self.admin_site.each_context(request),
                "title": "Загрузка отзывов из файла",
                "opts": self.model._meta,
                "form": form,
                "report": report,
                "columns": [(label, hint) for label, _, hint in IMPORT_COLUMNS],
            },
        )

    def import_reviews(self, request: HttpRequest, table: list[dict[str, Any]]) -> dict[str, Any]:
        """
        ReviewImporter: строка — отзыв. Компании ищутся по названию без
        учёта регистра; не нашлась — строка пропускается (завести отзыв о
        несуществующей компании хуже, чем не завести). Совпавшая пара
        «автор — компания» без объявления обновляет существующий отзыв.
        """
        headers = list(table[0]) if table else []
        mapping = import_columns(headers)
        failed: list[tuple[int, str]] = []
        done = 0

        for number, row in enumerate(table, start=2):
            data: dict[str, Any] = {key: row.get(header) for key, header in mapping.items()}
            problem = _import_problem(data)

            if problem is not None:
                failed.append((number, problem))
                continue

            about = _company_named(data["company"])
            author = _company_named(data["author_company"])

            if about is None or author is None or about.pk == author.pk:
                failed.append((number, "компания не найдена или отзыв о себе"))
                continue

            review = Review.objects.filter(
                company=about, author_company=author, listing__isnull=True
            ).first()
            adding = review is None
            before = self.snapshot(review) if review is not None else {}

            if review is None:
                review = Review(company=about, author_company=author, status=PUBLISHED)

            review.origin = "import"
            review.created_by_id = _admin_of(request).id
            review.rating = data["rating"]
            review.body = data["body"]
            review.reply = data.get("reply")

            with transaction.atomic():
                with allowed_writes("reviews"):
                    review.save()

                after = self.snapshot(review)

                if adding:
                    self.journal(request, "created", review, {"after": after})
                else:
                    changed = {k: v for k, v in after.items() if before.get(k) != v}

                    if {k for k in changed if k != "updated_at"}:
                        self.journal(
                            request,
                            "updated",
                            review,
                            {"before": {k: before.get(k) for k in changed}, "after": changed},
                        )

                if adding or any(before.get(k) != after.get(k) for k in ("rating", "status")):
                    services.recalculate_companies(services.context_of(request), about.pk)

            done += 1

        return {"done": done, "failed": failed}


#: ReviewImporter::getColumns — (подпись, ключ, подсказка)
IMPORT_COLUMNS = [
    ("О какой компании", "company", "обязательно, название как на площадке"),
    ("От какой компании", "author_company", "обязательно"),
    ("Оценка", "rating", "обязательно: цифра от 1 до 5 («5 звёзд», «4/5»)"),
    ("Текст отзыва", "body", "обязательно, от 10 до 5000 знаков"),
    ("Ответ компании", "reply", ""),
]


def import_columns(headers: list[str]) -> dict[str, str]:
    """Столбец загрузки → заголовок файла: подпись или имя столбца, без регистра."""
    mapping: dict[str, str] = {}

    for label, key, _ in IMPORT_COLUMNS:
        for header in headers:
            if header not in mapping.values() and importer.normalize(header) in (
                importer.normalize(label),
                key,
                key.replace("_", " "),
            ):
                mapping[key] = header
                break

    return mapping


def _import_problem(data: dict[str, Any]) -> str | None:
    """Правила столбцов ReviewImporter после приведения ячеек."""
    for key in ("company", "author_company"):
        data[key] = importer.text(data.get(key), 190)

    if not data["company"] or not data["author_company"]:
        return "не указана компания"

    found = re.search(r"[1-5]", str(data.get("rating") or ""))
    data["rating"] = int(found.group(0)) if found else None

    if data["rating"] is None:
        return "нет оценки от 1 до 5"

    data["body"] = importer.text(data.get("body"), 5000)

    if not data["body"] or len(data["body"]) < 10:
        return "текст отзыва короче 10 знаков"

    data["reply"] = importer.text(data.get("reply"), 5000)

    return None


def _company_named(name: str) -> Company | None:
    """Компания по названию, без учёта регистра и лишних пробелов."""
    return (
        Company.objects.filter(deleted_at__isnull=True, name__iexact=name.strip())
        .order_by("id")
        .first()
    )


# ── Отзывы о площадке ────────────────────────────────────────────────


class PlatformWaiting(OpenFilter):
    parameter_name = "queue"
    title = "очередь"
    open_label = "Ждут решения"
    all_label = "Все отзывы"
    open_q = Q(status=MODERATION)


@register(PlatformReview, section="reviews")
class PlatformReviewAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\PlatformReview"
    title_list = "Отзывы о площадке"
    title_change = "Отзыв о площадке"
    change_form_template = "admin/moderation/platformreview/change_form.html"

    list_display = ("author", "stars", "text", "showcase", "sent")
    list_filter = (PlatformWaiting, Showcase, Stars)
    list_select_related = ("user", "company", "moderated_by")
    search_fields = ("user__name", "body")
    ordering = ("-updated_at", "-id")
    list_per_page = 50

    fields = ("author", "stars", "body", "showcase", "sent")
    readonly_fields = fields

    # Заводят и правят их только сами пользователи
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    @admin.display(description="автор", ordering="user__name")
    def author(self, obj: PlatformReview) -> str:
        user = obj.user
        company = obj.company

        return format_html(
            "{}<br><small>{}</small>",
            user.name if user is not None and user.deleted_at is None else "учётная запись удалена",
            company.name if company is not None and company.deleted_at is None else "",
        )

    @admin.display(description="оценка", ordering="rating")
    def stars(self, obj: PlatformReview) -> str:
        return _rating(obj.rating)

    @admin.display(description="отзыв")
    def text(self, obj: PlatformReview) -> str:
        return _short(obj.body, 160)

    @admin.display(description="на витрине", ordering="status")
    def showcase(self, obj: PlatformReview) -> str:
        return format_html(
            "{}<br><small>{}</small>",
            _badge(SHOWCASE.get(obj.status, "Скрыт"), SHOWCASE_TONES.get(obj.status, "gray")),
            obj.screening_flags or obj.moderator_note or "",
        )

    @admin.display(description="отправлен", ordering="updated_at")
    def sent(self, obj: PlatformReview) -> str:
        return obj.updated_at.strftime("%d.%m.%Y") if obj.updated_at else ""

    def can_decide(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("reviews.edit")

    def decisions(self, review: PlatformReview) -> list[tuple[str, str, bool]]:
        found = []

        if review.status == MODERATION:
            found.append(("approve", "Опубликовать", False))

        if review.status != HIDDEN:
            label = "Снять с витрины" if review.status == PUBLISHED else "Не пропускать"
            found.append(("reject", label, True))
        else:
            found.append(("restore", "Вернуть на витрину", False))

        return found

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/decide/",
                self.admin_site.admin_view(self.decide_view),
                name="moderation_platformreview_decide",
            ),
            *super().get_urls(),
        ]

    def decide_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.can_decide(request):
            raise PermissionDenied

        review = self.get_object(request, object_id)

        if not isinstance(review, PlatformReview):
            raise PermissionDenied

        page = reverse("savdex_admin:moderation_platformreview_change", args=[review.pk])
        decision = request.POST.get("decision", "")
        allowed = {code: needs for code, _, needs in self.decisions(review)}
        note = (request.POST.get("note") or "").strip()

        if decision not in allowed:
            self.message_user(request, "Это решение по отзыву уже недоступно.", messages.WARNING)

            return HttpResponseRedirect(page)

        if allowed[decision] and len(note) < MIN_NOTE:
            self.message_user(
                request,
                f"Напишите формулировку решения — не короче {MIN_NOTE} знаков: её получит автор.",
                messages.ERROR,
            )

            return HttpResponseRedirect(page)

        if decision == "approve":
            services.approve_platform(request, review)
            self.message_user(request, "Отзыв опубликован.", messages.SUCCESS)
        elif decision == "reject":
            services.reject_platform(request, review, note)
            self.message_user(request, "Отзыв отклонён.", messages.WARNING)
        else:
            services.restore_platform(request, review)
            self.message_user(request, "Отзыв снова виден.", messages.SUCCESS)

        return HttpResponseRedirect(page)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        review = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(review, PlatformReview):
            extra["decisions"] = self.decisions(review) if self.can_decide(request) else []
            extra["min_note"] = MIN_NOTE

        return super().change_view(request, object_id, form_url, extra)


# ── Документы на проверку ────────────────────────────────────────────


def doc_type(code: str) -> str:
    """CompanyDocument::typeLabel."""
    label = ui.t(f"cabinet.files.types.{code}", "ru")

    return code if label.startswith("ui.") else label


class DocPending(OpenFilter):
    parameter_name = "queue"
    title = "очередь"
    open_label = "Ждут проверки"
    all_label = "Все документы"
    open_q = Q(moderation_status=DOC_PENDING)


class DocStatus(admin.SimpleListFilter):
    title = "проверка"
    parameter_name = "state"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(DOC_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(moderation_status=self.value()) if self.value() else queryset


class DocType(admin.SimpleListFilter):
    title = "тип"
    parameter_name = "type"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [(code, doc_type(code)) for code in VERIFICATION_TYPES]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(type=self.value()) if self.value() else queryset


@register(CompanyDocument, section="documents")
class CompanyDocumentAdmin(SavdexModelAdmin):
    """
    Очередь документов: принять или отклонить с причиной. Ни создать, ни
    править: подменять чужой файл — подделывать основание проверки.
    Материалы (презентации, прайсы) сюда не попадают — публикуются сразу.
    """

    laravel_model = "App\\Models\\CompanyDocument"
    title_list = "Документы на проверку"
    title_change = "Документ"
    change_form_template = "admin/moderation/companydocument/change_form.html"

    list_display = ("company_name", "document", "size", "valid", "verdict", "public", "loaded")
    list_filter = (DocPending, DocStatus, DocType)
    list_select_related = ("company",)
    search_fields = ("company__name", "title")
    ordering = ("-created_at", "-id")
    list_per_page = 50

    fields = ("company_name", "document", "size", "valid", "verdict", "public", "loaded", "file")
    readonly_fields = fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[CompanyDocument]:
        queryset: QuerySet[CompanyDocument] = super().get_queryset(request)

        return queryset.filter(type__in=VERIFICATION_TYPES)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    @admin.display(description="компания", ordering="company__name")
    def company_name(self, obj: CompanyDocument) -> str:
        company = obj.company
        level = _verification_level(obj.company_id)

        return format_html(
            "{}<br><small>уровень проверки: {}</small>",
            company.name if company is not None else "—",
            level,
        )

    @admin.display(description="документ", ordering="title")
    def document(self, obj: CompanyDocument) -> str:
        return format_html("{}<br><small>{}</small>", obj.title, doc_type(obj.type))

    @admin.display(description="размер")
    def size(self, obj: CompanyDocument) -> str:
        return obj.size_label() or "—"

    @admin.display(description="действует до", ordering="valid_until")
    def valid(self, obj: CompanyDocument) -> str:
        if obj.valid_until is None:
            return "бессрочно"

        text = obj.valid_until.strftime("%d.%m.%Y")

        # Просроченный документ ничего не подтверждает — видно до открытия
        return _badge(text, "danger") if obj.valid_until < date.today() else text

    @admin.display(description="проверка", ordering="moderation_status")
    def verdict(self, obj: CompanyDocument) -> str:
        tone = {DOC_APPROVED: "success", DOC_REJECTED: "danger"}.get(
            obj.moderation_status, "warning"
        )

        return format_html(
            "{}<br><small>{}</small>",
            _badge(DOC_STATUSES.get(obj.moderation_status, "Ждёт"), tone),
            obj.moderation_note or "",
        )

    @admin.display(description="на визитке", boolean=True)
    def public(self, obj: CompanyDocument) -> bool:
        return obj.is_public

    @admin.display(description="загружен", ordering="created_at")
    def loaded(self, obj: CompanyDocument) -> str:
        return obj.created_at.strftime("%d.%m.%Y") if obj.created_at else ""

    @admin.display(description="файл")
    def file(self, obj: CompanyDocument) -> str:
        # Решать, не открыв документ, нельзя — ссылка на скачивание
        return format_html(
            '<a href="/files/{}" target="_blank" rel="noopener">Открыть файл</a>', obj.pk
        )

    # ── Решения ──

    def can_decide(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("documents.moderate")

    def decisions(self, document: CompanyDocument) -> list[tuple[str, str, bool]]:
        found = []

        if document.moderation_status != DOC_APPROVED:
            found.append(("approve", "Принять", False))

        if document.moderation_status != DOC_REJECTED:
            found.append(("reject", "Отклонить", True))

        return found

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/decide/",
                self.admin_site.admin_view(self.decide_view),
                name="moderation_companydocument_decide",
            ),
            *super().get_urls(),
        ]

    def decide_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.can_decide(request):
            raise PermissionDenied

        document = self.get_object(request, object_id)

        if not isinstance(document, CompanyDocument):
            raise PermissionDenied

        page = reverse("savdex_admin:moderation_companydocument_change", args=[document.pk])
        decision = request.POST.get("decision", "")
        allowed = {code: needs for code, _, needs in self.decisions(document)}
        note = (request.POST.get("note") or "").strip()

        if decision not in allowed:
            self.message_user(request, "Это решение по документу уже недоступно.", messages.WARNING)

            return HttpResponseRedirect(page)

        if allowed[decision] and len(note) < MIN_NOTE:
            self.message_user(
                request,
                f"Напишите причину отказа — не короче {MIN_NOTE} знаков: её увидит компания.",
                messages.ERROR,
            )

            return HttpResponseRedirect(page)

        if decision == "approve":
            services.approve_document(request, document)
            self.message_user(request, "Документ принят.", messages.SUCCESS)
        else:
            services.reject_document(request, document, note)
            self.message_user(request, "Документ отклонён.", messages.WARNING)

        return HttpResponseRedirect(page)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        document = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(document, CompanyDocument):
            extra["decisions"] = self.decisions(document) if self.can_decide(request) else []
            extra["min_note"] = MIN_NOTE

        return super().change_view(request, object_id, form_url, extra)


def _verification_level(company_id: int | None) -> Any:  # noqa: ANN401
    if company_id is None:
        return ""

    with connection.cursor() as cursor:
        cursor.execute("select verification_level from companies where id = %s", [company_id])
        row = cursor.fetchone()

    return row[0] if row else ""


# ── Резюме ───────────────────────────────────────────────────────────

#: Причина снятия — не отписка (у Filament minLength 10)
MIN_RESUME_NOTE = 10


class ResumeStatus(admin.SimpleListFilter):
    title = "состояние"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(RESUME_STATUSES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(status=self.value()) if self.value() else queryset


class ResumeField(admin.SimpleListFilter):
    title = "сфера"
    parameter_name = "field"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        from savdex.web.resumes import FIELDS

        return [(code, ui.t(f"resume.field_{code}", "ru")) for code in FIELDS]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(field=self.value()) if self.value() else queryset


class Fresh(admin.SimpleListFilter):
    """Свежие — резюме публикуются сразу, беглый просмотр заменяет очередь."""

    title = "свежие"
    parameter_name = "fresh"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("1", "Опубликованы за неделю")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.value() != "1":
            return queryset

        from savdex.catalog import now

        return queryset.filter(
            status=RESUME_PUBLISHED, published_at__gte=now() - timedelta(weeks=1)
        )


def _experience(months: int) -> str:
    if months == 0:
        return "без опыта"

    years, rest = divmod(months, 12)

    return ((f"{years} г. " if years else "") + (f"{rest} мес." if rest else "")).strip()


@register(Resume, section="resumes")
class ResumeAdmin(SavdexModelAdmin):
    """
    Резюме — работа модератора: остаётся в разделе или снимается с
    причиной, которую соискатель видит в кабинете. Формы правки нет —
    модератор не переписывает чужую биографию. Удаление — крайняя мера.
    """

    laravel_model = "App\\Models\\Resume"
    title_list = "Резюме"
    title_change = "Резюме"
    change_form_template = "admin/moderation/resume/change_form.html"

    list_display = ("position", "sphere", "experience", "city", "state", "views", "published")
    list_filter = (ResumeStatus, ResumeField, Fresh)
    list_select_related = ("user",)
    search_fields = ("title",)
    ordering = ("-published_at", "-id")
    list_per_page = 50

    fields = ("position", "sphere", "experience", "city", "state", "views", "published", "page")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    @admin.display(description="должность", ordering="title")
    def position(self, obj: Resume) -> str:
        user = obj.user

        return format_html(
            "{}<br><small>{}</small>",
            obj.title,
            obj.contact_name or (user.name if user is not None else "—"),
        )

    @admin.display(description="сфера", ordering="field")
    def sphere(self, obj: Resume) -> str:
        return ui.t(f"resume.field_{obj.field}", "ru") if obj.field else "—"

    @admin.display(description="опыт", ordering="experience_months")
    def experience(self, obj: Resume) -> str:
        return _experience(int(obj.experience_months or 0))

    @admin.display(description="город")
    def city(self, obj: Resume) -> str:
        if obj.city_id is None:
            return "—"

        from savdex.geo.models import City

        city = City.objects.filter(pk=obj.city_id).first()

        return city.name() if city is not None else "—"

    @admin.display(description="состояние", ordering="status")
    def state(self, obj: Resume) -> str:
        tone = {RESUME_PUBLISHED: "success", RESUME_BLOCKED: "danger"}.get(obj.status, "gray")

        # Причина снятия — сразу под состоянием
        return format_html(
            "{}<br><small>{}</small>",
            _badge(RESUME_STATUSES.get(obj.status, obj.status), tone),
            obj.moderation_note or "",
        )

    @admin.display(description="просмотров", ordering="views_count")
    def views(self, obj: Resume) -> int:
        return int(obj.views_count or 0)

    @admin.display(description="опубликовано", ordering="published_at")
    def published(self, obj: Resume) -> str:
        return obj.published_at.strftime("%d.%m.%Y") if obj.published_at else "—"

    @admin.display(description="на сайте")
    def page(self, obj: Resume) -> str:
        if obj.status != RESUME_PUBLISHED:
            return "—"

        return format_html(
            '<a href="/resume/{}" target="_blank" rel="noopener">Открыть</a>', obj.slug
        )

    # ── Снять, вернуть, удалить ──

    def can_decide(self, request: HttpRequest) -> bool:
        return _admin_of(request).can("resumes.moderate")

    def decisions(self, resume: Resume) -> list[tuple[str, str, bool]]:
        if resume.status == RESUME_BLOCKED:
            return [("restore", "Вернуть", False)]

        return [("block", "Снять", True)]

    def delete_model(self, request: HttpRequest, obj: Any) -> None:  # noqa: ANN401
        """SoftDeletes: deleted_at и updated_at; строка журнала «удалено»."""
        from savdex.catalog import now

        stamp = now()

        with allowed_writes("resumes"):
            Resume.everything.filter(pk=obj.pk).update(deleted_at=stamp, updated_at=stamp)

        self.journal(request, "deleted", obj)
        request._savdex_done = f"Удалено: {obj}"  # type: ignore[attr-defined]

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        for obj in list(queryset):
            self.delete_model(request, obj)

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/decide/",
                self.admin_site.admin_view(self.decide_view),
                name="moderation_resume_decide",
            ),
            *super().get_urls(),
        ]

    def decide_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST" or not self.can_decide(request):
            raise PermissionDenied

        resume = self.get_object(request, object_id)

        if not isinstance(resume, Resume):
            raise PermissionDenied

        page = reverse("savdex_admin:moderation_resume_change", args=[resume.pk])
        decision = request.POST.get("decision", "")
        allowed = {code: needs for code, _, needs in self.decisions(resume)}
        note = (request.POST.get("note") or "").strip()

        if decision not in allowed:
            self.message_user(request, "Это решение по резюме уже недоступно.", messages.WARNING)

            return HttpResponseRedirect(page)

        if allowed[decision] and len(note) < MIN_RESUME_NOTE:
            self.message_user(
                request,
                f"Напишите причину — не короче {MIN_RESUME_NOTE} знаков: её видит соискатель.",
                messages.ERROR,
            )

            return HttpResponseRedirect(page)

        # Причина блокировки резюме хранится в 255 знаках — длиннее не записать
        if decision == "block" and len(note) > 255:
            self.message_user(
                request, "Причина — не длиннее 255 знаков: сократите формулировку.", messages.ERROR
            )

            return HttpResponseRedirect(page)

        if decision == "block":
            services.block_resume(request, resume, note)
            self.message_user(request, "Резюме снято с публикации.", messages.SUCCESS)
        else:
            services.restore_resume(request, resume)
            self.message_user(request, "Резюме вернулось в раздел.", messages.SUCCESS)

        return HttpResponseRedirect(page)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        resume = self.get_object(request, object_id)
        extra = dict(extra_context or {})

        if isinstance(resume, Resume):
            extra["decisions"] = self.decisions(resume) if self.can_decide(request) else []
            extra["min_note"] = MIN_RESUME_NOTE

        return super().change_view(request, object_id, form_url, extra)
