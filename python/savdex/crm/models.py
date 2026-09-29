"""
CRM — таблицы crm_* глазами Django (этап 6). Схема — у Laravel
(managed = False), хозяин записи — Django: кроме разделов админки в эти
таблицы никто не пишет.

Правила моделей App\\Models\\Crm\\*:

- SoftDeletes у всех, кроме коммуникаций: удаление — deleted_at и
  updated_at, строка остаётся; списки её не видят (менеджер Alive).
- Кто завёл контакт — created_by, ставит раздел при создании.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.catalog import Timestamped, UTCDateTimeField, now


class Alive(models.Manager):  # type: ignore[type-arg]
    """SoftDeletingScope: удалённые не видны."""

    def get_queryset(self) -> models.QuerySet[Any]:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleting(Timestamped):
    """SoftDeletes::runSoftDelete: deleted_at и updated_at — одно время."""

    deleted_at = UTCDateTimeField(null=True, editable=False)

    objects = Alive()
    everything = models.Manager()

    class Meta:
        abstract = True

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        stamp = now()
        type(self).everything.filter(pk=self.pk).update(deleted_at=stamp, updated_at=stamp)
        self.deleted_at = self.updated_at = stamp

        return 1, {self._meta.label: 1}


class Company(models.Model):
    """Компания площадки — только для выбора и подписи (таблица этапа 5)."""

    name = models.CharField("название", max_length=190)
    deleted_at = UTCDateTimeField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "companies"
        ordering = ("name", "id")

    def __str__(self) -> str:
        return self.name


class Contact(SoftDeleting):
    """App\\Models\\Crm\\Contact: человек у клиента."""

    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    name = models.CharField("имя", max_length=160)
    position = models.CharField("должность", max_length=120, null=True, blank=True)
    phone = models.CharField("телефон", max_length=40, null=True, blank=True)
    email = models.EmailField("почта", max_length=160, null=True, blank=True)
    telegram = models.CharField(
        "Telegram", max_length=80, null=True, blank=True, help_text="Без @, например ivanov"
    )
    note = models.TextField("заметка", null=True, blank=True)
    created_by = models.BigIntegerField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "crm_contacts"
        verbose_name = "контакт"
        verbose_name_plural = "контакты"
        ordering = ("name", "id")

    def __str__(self) -> str:
        """Contact::label: имя и должность."""
        return f"{self.name}, {self.position}" if self.position else self.name
