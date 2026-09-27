"""
Типы компаний — справочник, перешедший к Django (этап 2).

Таблицы созданы миграцией Laravel
(database/migrations/2026_07_29_100700_create_company_types_table.php):
managed = False, схему по-прежнему меняет только Laravel.

Компания хранит не номер типа, а его код (companies.type), поэтому:

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
