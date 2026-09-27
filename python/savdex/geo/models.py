"""
Страны — первая таблица, хозяином которой стал Django (этап 2).

Модели описывают таблицы, созданные миграциями Laravel
(database/migrations/2026_07_28_100000_create_countries_and_cities_tables.php):
managed = False, схему по-прежнему меняет только Laravel.

Правила, которые в Laravel жили в модели App\\Models\\Country и которые
иначе обошёл бы новый код (раздел 5 документа переноса):

- код страны — всегда строчными и без пробелов по краям: уникальность
  в базе регистрозависима, и «UZ» рядом с «uz» уже однажды завёл
  второй Узбекистан, в который уехала половина компаний;
- страна не удаляется, пока на неё ссылаются города, компании,
  тендеры или резюме: внешние ключи удалению не мешают, а увели бы
  города каскадом и молча обнулили бы страну у остальных.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import connection, models
from django.utils import timezone

#: Языки площадки — App\\Support\\Locales::ALL
LOCALES: dict[str, str] = {
    "ru": "Русский",
    "uz": "O‘zbekcha",
    "en": "English",
    "zh": "中文",
    "tr": "Türkçe",
}

#: Что удерживает страну от удаления: таблица → как назвать в подсказке.
#: Резюме в PHP-версии не учитывались — удаление страны обнуляло её
#: у резюме молча; исправлено в обеих половинах
REFERENCES: dict[str, str] = {
    "cities": "города",
    "companies": "компании",
    "tenders": "тендеры",
    "resumes": "резюме",
}


class RecordIsReferencedError(RuntimeError):
    """App\\Exceptions\\RecordIsReferenced: на запись ссылаются, удалять нельзя."""


def _now() -> datetime:
    # Как Laravel: время в UTC, до секунды (столбцы timestamp(0))
    return timezone.now().replace(microsecond=0)


class Country(models.Model):
    code = models.CharField("код страны", max_length=2, unique=True)
    phone_code = models.CharField("телефонный код", max_length=8)
    currency_code = models.CharField("валюта", max_length=3)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("показывать при регистрации", default=True)
    created_at = models.DateTimeField(null=True, editable=False)
    updated_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "countries"
        ordering = ("sort", "code")
        verbose_name = "страна"
        verbose_name_plural = "страны"

    def __str__(self) -> str:
        return f"{self.name()} ({self.code.upper()})" if self.pk else "новая страна"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Country::booted(): код строчными и без пробелов — всегда, кто бы ни сохранял
        self.code = (self.code or "").strip().lower()
        now = _now()

        if self._state.adding and self.created_at is None:
            self.created_at = now

        self.updated_at = now
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """
        RefusesDeletionWhenReferenced: проверка в модели, а не в кнопке —
        кнопку обходит любой будущий код, а модель нет.
        """
        references = self.references()

        if references:
            parts = ", ".join(f"{what} — {count}" for what, count in references.items())

            raise RecordIsReferencedError(f"Удалить нельзя, на страну ссылаются: {parts}.")

        return super().delete(*args, **kwargs)

    def name(self, locale: str = "ru") -> str:
        """Country::name(): название на языке, с откатом на русский и на код."""
        names = {t.locale: t.name for t in self.translations.all()}

        return names.get(locale) or names.get("ru") or self.code

    def references(self) -> dict[str, int]:
        """Country::references(): кто ссылается на страну; пусто — удалять можно."""
        if self.pk is None:
            return {}

        counts: dict[str, int] = {}

        with connection.cursor() as cursor:
            for table, label in REFERENCES.items():
                cursor.execute(f"select count(*) from {table} where country_id = %s", [self.pk])
                row = cursor.fetchone()

                if row and row[0]:
                    counts[label] = int(row[0])

        return counts


class CountryTranslation(models.Model):
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="translations", db_column="country_id"
    )
    locale = models.CharField("язык", max_length=5, choices=list(LOCALES.items()))
    name = models.CharField("название", max_length=190)
    created_at = models.DateTimeField(null=True, editable=False)
    updated_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "country_translations"
        unique_together = (("country", "locale"),)
        verbose_name = "название"
        verbose_name_plural = "названия на языках"

    def __str__(self) -> str:
        return f"{self.locale}: {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        now = _now()

        if self._state.adding and self.created_at is None:
            self.created_at = now

        self.updated_at = now
        super().save(*args, **kwargs)
