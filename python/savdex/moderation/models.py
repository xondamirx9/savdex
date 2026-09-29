"""
Модерация — отзывы о компаниях (reviews) и о площадке (platform_reviews)
глазами Django (этап 6). Схема — у Laravel (managed = False). Таблицы
этапа 5: пишут в них и кабинет (ответ, спор, новый отзыв — web/), и этот
раздел, поэтому запись — в блоке allowed_writes (SHARED_WRITES).

Правила моделей:

- Review::saved — рейтинг компании пересчитывается, когда отзыв создан
  или сменились оценка, статус или компания (у прежней компании тоже);
  Review::deleted — тоже пересчёт (сам пересчёт — web/review_actions.py);
- происхождение (origin) и кто завёл (created_by) ставит раздел, в
  форме их нет: поле, которым заведённый отзыв выдаётся за
  покупательский, обесценило бы пометку;
- у отзыва о площадке событий и журнала нет.
"""

from __future__ import annotations

from django.db import models

from savdex.accounts.models import User
from savdex.catalog import Timestamped, UTCDateTimeField
from savdex.crm.models import Company

PUBLISHED = "published"
MODERATION = "moderation"
HIDDEN = "hidden"

#: Статус на витрине — подписи в списке
SHOWCASE = {PUBLISHED: "Виден", MODERATION: "Ждёт проверки", HIDDEN: "Скрыт"}

#: Review::ORIGINS
ORIGINS = {"buyer": "От покупателя", "admin": "Заведён вручную", "import": "Загружен файлом"}

#: ReviewsTable::DISPUTES
DISPUTES = {"pending": "На рассмотрении", "accepted": "Удовлетворён", "declined": "Отклонён"}

#: Review::CRITERIA
CRITERIA = {
    "rating_description": "Соответствие описанию",
    "rating_response": "Скорость ответа",
    "rating_deadlines": "Соблюдение сроков",
    "rating_quality": "Качество товара",
}


def _ref(
    model: type[models.Model], verbose: str, *, null: bool = True, column: str | None = None
) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        model,
        verbose_name=verbose,
        null=null,
        blank=null,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column=column,
        related_name="+",
    )


class Listing(models.Model):
    """Объявление — только для выбора и подписи."""

    title = models.CharField(max_length=255)
    company_id = models.BigIntegerField(null=True)
    deleted_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "listings"
        ordering = ("title", "id")

    def __str__(self) -> str:
        return self.title


class Review(Timestamped):
    """App\\Models\\Review: отзыв компании о компании."""

    company = _ref(Company, "о какой компании", null=False)
    author_company = _ref(Company, "от какой компании", null=False)
    author_user_id = models.BigIntegerField(null=True, editable=False)
    contact_unlock_id = models.BigIntegerField(null=True, editable=False)
    listing = _ref(Listing, "по какому объявлению")
    rating = models.PositiveSmallIntegerField("общая оценка")
    rating_description = models.PositiveSmallIntegerField(
        CRITERIA["rating_description"], null=True, blank=True
    )
    rating_response = models.PositiveSmallIntegerField(
        CRITERIA["rating_response"], null=True, blank=True
    )
    rating_deadlines = models.PositiveSmallIntegerField(
        CRITERIA["rating_deadlines"], null=True, blank=True
    )
    rating_quality = models.PositiveSmallIntegerField(
        CRITERIA["rating_quality"], null=True, blank=True
    )
    body = models.TextField("отзыв")
    deal_confirmed = models.BooleanField(
        "сделка подтверждена",
        default=False,
        help_text="Отмечается, когда за отзывом стоит оплаченное раскрытие контакта",
    )
    reply = models.TextField(
        "ответ компании",
        null=True,
        blank=True,
        help_text="Необязательно. Обычно пишет сама компания из кабинета",
    )
    replied_at = UTCDateTimeField(null=True, editable=False)
    dispute_status = models.CharField(max_length=255, null=True, editable=False)
    dispute_reason = models.TextField(null=True, editable=False)
    status = models.CharField(
        "статус",
        max_length=255,
        default=PUBLISHED,
        choices=[(PUBLISHED, "Опубликован"), (MODERATION, "На проверке"), (HIDDEN, "Скрыт")],
        help_text="Опубликованный сразу попадает на витрину и в рейтинг компании",
    )
    moderator_note = models.TextField(null=True, editable=False)
    moderated_by = _ref(User, "решение принял", column="moderated_by")
    moderated_at = UTCDateTimeField(null=True, editable=False)
    screening_flags = models.CharField(max_length=255, null=True, editable=False)
    origin = models.CharField(max_length=255, default="buyer", editable=False)
    created_by = _ref(User, "завёл", column="created_by")

    class Meta:
        managed = False
        db_table = "reviews"
        verbose_name = "отзыв"
        verbose_name_plural = "отзывы"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"Review #{self.pk}"


class PlatformReview(Timestamped):
    """App\\Models\\PlatformReview: отзыв о площадке."""

    user = _ref(User, "автор")
    company = _ref(Company, "компания")
    rating = models.PositiveSmallIntegerField("оценка")
    rating_usability = models.PositiveSmallIntegerField(null=True)
    rating_search = models.PositiveSmallIntegerField(null=True)
    rating_support = models.PositiveSmallIntegerField(null=True)
    body = models.TextField("отзыв")
    status = models.CharField("на витрине", max_length=255, default=MODERATION)
    screening_flags = models.CharField(max_length=255, null=True)
    moderator_note = models.TextField(null=True)
    moderated_by = _ref(User, "решение принял", column="moderated_by")
    moderated_at = UTCDateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "platform_reviews"
        verbose_name = "отзыв о площадке"
        verbose_name_plural = "отзывы о площадке"
        ordering = ("-updated_at", "-id")

    def __str__(self) -> str:
        return f"PlatformReview #{self.pk}"
