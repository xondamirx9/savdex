"""
Закупка — копия правил App\\Models\\Tender для админки Django.

Таблица заведена миграциями Laravel (managed = False). Что делает
модель при записи, как Eloquent:

- saving: search_text — заголовок, описание, заказчик и переводы
  заголовка в обеих графиках (SearchText::index);
- created: адрес из заголовка и номера (Tender::makeSlug), если его нет;
- перевод опубликованной закупки ставить в очередь не нужно: его
  добирает фоновый обработчик Python (manage.py translate).

Столбцы перевода (*_i18n) и счётчик просмотров пишут другие —
обработчик перевода и страница закупки. Обычное сохранение из админки
их не трогает, чтобы не затереть записанное, пока форма была открыта.

is_government — госзакупка (этап 5): на сайте у неё значок «Госзакупка».
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.catalog import LaravelJSONField, Timestamped, UTCDateTimeField
from savdex.guards import allowed_writes
from savdex.tenders.slug import make_slug
from savdex.web.search_text import index

STATUSES = {
    "draft": "Черновик",
    "published": "Опубликован",
    "archived": "Завершён / в архиве",
    "expired": "Истёк",
}

#: Чем закончился тендер — отмечает владелец кнопкой «Завершить» в кабинете
OUTCOMES = {
    "contract": "Сделка состоялась",
    "no_deal": "Сделка не состоялась",
    "cancelled": "Закупка отменена",
}

#: Откуда тендер: из кабинета компании (живёт 30 дней) или от администратора
SOURCES = {"cabinet": "Компания (кабинет)", "admin": "Администратор / Excel"}

#: Tender::CURRENCIES
CURRENCIES = ("UZS", "USD", "EUR", "RUB", "CNY", "KZT")

#: Кто пишет эти столбцы помимо админки — обычное сохранение их не трогает
FOREIGN_COLUMNS = (
    "title_i18n",
    "description_i18n",
    "views_count",
    # Пишут кабинет и проход сроков (savdex/tender_expiry.py)
    "source",
    "finished_at",
    "expiry_warned_at",
    "extended_at",
)


class Tender(Timestamped):
    slug = models.CharField("адрес", max_length=255, unique=True, null=True, blank=True)
    title = models.CharField("заголовок", max_length=190)
    title_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    description = models.TextField("описание", null=True, blank=True)
    description_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    customer = models.CharField("заказчик", max_length=190, null=True, blank=True)
    is_government = models.BooleanField(
        "госзакупка",
        default=False,
        help_text="На сайте у закупки появится значок «Госзакупка».",
    )
    category = models.ForeignKey(
        "catalogs.Category",
        verbose_name="категория",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    country = models.ForeignKey(
        "geo.Country",
        verbose_name="страна",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    location = models.CharField("город / место поставки", max_length=190, null=True, blank=True)
    budget = models.DecimalField("бюджет", max_digits=16, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        "валюта", max_length=3, default="UZS", choices=[(c, c) for c in CURRENCIES]
    )
    deadline_at = UTCDateTimeField("приём заявок до", null=True, blank=True)
    source_url = models.URLField("ссылка на источник", max_length=255, null=True, blank=True)
    contact_name = models.CharField("контактное лицо", max_length=190, null=True, blank=True)
    contact_phone = models.CharField("телефон", max_length=40, null=True, blank=True)
    contact_email = models.EmailField("почта", max_length=190, null=True, blank=True)
    status = models.CharField(
        "статус", max_length=20, default="draft", choices=list(STATUSES.items())
    )
    published_at = UTCDateTimeField("дата публикации", null=True, blank=True)
    views_count = models.IntegerField(default=0, editable=False)
    search_text = models.TextField(null=True, blank=True, editable=False)
    # Ссылка на users без модели: таблица пользователей — Laravel
    author_id = models.BigIntegerField(null=True, blank=True, editable=False)
    source = models.CharField(
        "откуда", max_length=16, default="admin", choices=list(SOURCES.items()), editable=False
    )
    outcome = models.CharField(
        "итог", max_length=16, null=True, blank=True, choices=list(OUTCOMES.items())
    )
    outcome_party = models.CharField("договор с кем", max_length=255, null=True, blank=True)
    outcome_amount = models.DecimalField(
        "сумма договора", max_digits=16, decimal_places=2, null=True, blank=True
    )
    finished_at = UTCDateTimeField("завершён", null=True, blank=True, editable=False)
    expiry_warned_at = UTCDateTimeField(null=True, blank=True, editable=False)
    extended_at = UTCDateTimeField("продлён", null=True, blank=True, editable=False)

    class Meta:
        managed = False
        db_table = "tenders"
        ordering = ("-id",)
        verbose_name = "закупка"
        verbose_name_plural = "закупки"

    def __str__(self) -> str:
        return self.title if self.pk else "новая закупка"

    def reindex(self) -> None:
        """Событие saving у Tender: search_text заново."""
        parts = [
            self.title,
            self.description or "",
            self.customer or "",
            *(self.title_i18n.values() if isinstance(self.title_i18n, dict) else []),
        ]
        self.search_text = index(" ".join(str(p) for p in parts if p not in (None, "", "0")))

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.reindex()
        # Пустой адрес — null, а не «»: столбец уникальный
        self.slug = self.slug or None
        adding = self._state.adding

        if not adding and "update_fields" not in kwargs:
            kwargs["update_fields"] = [
                f.name
                for f in self._meta.concrete_fields
                if not f.primary_key and f.column not in FOREIGN_COLUMNS
            ]

        with allowed_writes("tenders"):
            super().save(*args, **kwargs)

            # Событие created: адрес из заголовка и номера — только после вставки
            if adding and not self.slug:
                self.slug = make_slug(self.title, self.pk)
                super().save(update_fields=["slug"])

    def delete(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        with allowed_writes("tenders"):
            return super().delete(*args, **kwargs)
