"""
Типы компаний и категории — справочники, перешедшие к Django (этап 2).

Таблицы созданы миграциями Laravel
(database/migrations/2026_07_29_100700_create_company_types_table.php,
2026_07_28_100400_create_categories_table.php):
managed = False, схему по-прежнему меняет только Laravel.

Типы компаний. Компания хранит не номер типа, а его код (companies.type), поэтому:

- код не меняется после создания — иначе у компаний останется тип,
  которого нет, и в карточке вместо названия появится сырой код;
- тип не удаляется, пока его выбрала хоть одна компания. В PHP запрет
  жил только в кнопке таблицы Filament; теперь он в модели в обеих
  половинах.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from savdex.catalog import Catalog, Reference, Translation


class CompanyType(Catalog):
    REFERENCES: ClassVar[tuple[Reference, ...]] = (
        Reference("companies", "type", "компании", field="code"),
    )
    NAME_FALLBACK = "code"
    HELD_AS = "на тип"
    INSTEAD = (
        "Выключите его вместо удаления — он исчезнет из выбора, но останется у тех, кто уже выбрал."
    )

    code = models.CharField("код", max_length=30, unique=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("доступен для выбора", default=True)

    class Meta:
        managed = False
        db_table = "company_types"
        ordering = ("sort", "code")
        verbose_name = "тип компании"
        verbose_name_plural = "типы компаний"

    def __str__(self) -> str:
        return self.name() if self.pk else "новый тип компании"


class CompanyTypeTranslation(Translation):
    company_type = models.ForeignKey(
        CompanyType,
        on_delete=models.CASCADE,
        related_name="translations",
        db_column="company_type_id",
    )

    class Meta:
        managed = False
        db_table = "company_type_translations"
        unique_together = (("company_type", "locale"),)
        verbose_name = "название"
        verbose_name_plural = "названия на языках"


class Category(Catalog):
    """
    Категория каталога — копия правил App\\Models\\Category.

    Дерево ровно на два уровня: раздел и подраздел. Третий уровень
    сломал бы фильтры каталога и мастер объявления.

    Удаление в Filament ничем не было защищено, а внешние ключи
    удалению не мешают: подкатегории раздела молча становились
    разделами, у объявлений, тендеров и продвижений категория
    обнулялась, а привязки компаний к категории стирались каскадом.
    Теперь удалить можно только категорию, на которую никто не
    ссылается, — в обеих половинах.
    """

    REFERENCES: ClassVar[tuple[Reference, ...]] = (
        Reference("categories", "parent_id", "подкатегории"),
        Reference("listings", "category_id", "объявления"),
        Reference("tenders", "category_id", "тендеры"),
        Reference("promotions", "category_id", "продвижения"),
        Reference("company_category", "category_id", "компании"),
    )
    NAME_FALLBACK = "slug"
    HELD_AS = "на категорию"
    INSTEAD = "Выключите её вместо удаления — она скроется из каталога и мастера объявлений."

    parent = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="children",
        db_column="parent_id",
        verbose_name="раздел",
    )
    slug = models.CharField("адрес (slug)", max_length=190, unique=True)
    icon = models.CharField("значок", max_length=64, null=True, blank=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("активна", default=True)

    class Meta:
        managed = False
        db_table = "categories"
        ordering = ("sort", "slug")
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def __str__(self) -> str:
        return self.name() if self.pk else "новая категория"


class CategoryTranslation(Translation):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="translations", db_column="category_id"
    )

    class Meta:
        managed = False
        db_table = "category_translations"
        unique_together = (("category", "locale"),)
        verbose_name = "название"
        verbose_name_plural = "названия на языках"
