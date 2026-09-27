"""
Страны и города — первые таблицы, хозяином которых стал Django (этап 2).

Модели описывают таблицы, созданные миграциями Laravel
(database/migrations/2026_07_28_100000_create_countries_and_cities_tables.php):
managed = False, схему по-прежнему меняет только Laravel.

Правила, которые в Laravel жили в моделях App\\Models\\Country и City
и которые иначе обошёл бы новый код (раздел 5 документа переноса):

- код страны — всегда строчными и без пробелов по краям: уникальность
  в базе регистрозависима, и «UZ» рядом с «uz» уже однажды завёл
  второй Узбекистан, в который уехала половина компаний;
- страна не удаляется, пока на неё ссылаются города, компании,
  тендеры или резюме, город — пока на него ссылаются компании,
  объявления или резюме: внешние ключи удалению не мешают, а увели бы
  города каскадом и молча обнулили бы ссылку у остальных.

Общее у всех справочников (время правки, названия, запрет удаления) —
в savdex/catalog.py.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from savdex.catalog import LOCALES, Catalog, RecordIsReferencedError, Reference, Translation

__all__ = [
    "LOCALES",
    "City",
    "CityTranslation",
    "Country",
    "CountryTranslation",
    "RecordIsReferencedError",
]


class Country(Catalog):
    #: Резюме в PHP-версии не учитывались — удаление страны обнуляло её
    #: у резюме молча; исправлено в обеих половинах
    REFERENCES: ClassVar[tuple[Reference, ...]] = (
        Reference("cities", "country_id", "города"),
        Reference("companies", "country_id", "компании"),
        Reference("tenders", "country_id", "тендеры"),
        Reference("resumes", "country_id", "резюме"),
    )
    NAME_FALLBACK = "code"
    HELD_AS = "на страну"
    INSTEAD = "Выключите её вместо удаления."

    code = models.CharField("код страны", max_length=2, unique=True)
    phone_code = models.CharField("телефонный код", max_length=8)
    currency_code = models.CharField("валюта", max_length=3)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("показывать при регистрации", default=True)

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
        super().save(*args, **kwargs)


class CountryTranslation(Translation):
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="translations", db_column="country_id"
    )

    class Meta:
        managed = False
        db_table = "country_translations"
        unique_together = (("country", "locale"),)
        verbose_name = "название"
        verbose_name_plural = "названия на языках"


class City(Catalog):
    """Город — копия правил App\\Models\\City."""

    #: Резюме в PHP-версии не учитывались — удаление города молча
    #: обнуляло его у резюме; исправлено в обеих половинах
    REFERENCES: ClassVar[tuple[Reference, ...]] = (
        Reference("companies", "city_id", "компании"),
        Reference("listings", "city_id", "объявления"),
        Reference("resumes", "city_id", "резюме"),
    )
    NAME_FALLBACK = "slug"
    HELD_AS = "на город"
    INSTEAD = "Выключите его вместо удаления."

    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name="cities",
        db_column="country_id",
        verbose_name="страна",
    )
    slug = models.CharField("адрес (slug)", max_length=190)
    lat = models.DecimalField("широта", max_digits=10, decimal_places=7, null=True, blank=True)
    lng = models.DecimalField("долгота", max_digits=10, decimal_places=7, null=True, blank=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("показывать при регистрации", default=True)

    class Meta:
        managed = False
        db_table = "cities"
        ordering = ("sort", "slug")
        verbose_name = "город"
        verbose_name_plural = "города"

    def __str__(self) -> str:
        return self.name() if self.pk else "новый город"


class CityTranslation(Translation):
    city = models.ForeignKey(
        City, on_delete=models.CASCADE, related_name="translations", db_column="city_id"
    )

    class Meta:
        managed = False
        db_table = "city_translations"
        unique_together = (("city", "locale"),)
        verbose_name = "название"
        verbose_name_plural = "названия на языках"
