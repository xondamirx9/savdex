"""
Пользователь — таблица users глазами админки Django.

Таблица и её правила — у Laravel (App\\Models\\User, managed = False):
Django её не сохраняет через ORM. Раздел «Пользователи» только ищет,
показывает и выполняет три действия удаления в два шага (admin.py) —
прямыми запросами, как SoftDeletes и forceDelete у Eloquent.
"""

from __future__ import annotations

from django.db import models

from savdex.catalog import LaravelJSONField, UTCDateTimeField

#: Статус аккаунта (status); отключённый (deleted_at) — поверх него
STATUSES = {"active": "Активен", "blocked": "Заблокирован"}


class User(models.Model):
    name = models.CharField("имя", max_length=255)
    email = models.CharField("почта", max_length=255)
    phone = models.CharField("телефон", max_length=32, null=True, blank=True)
    company_id = models.BigIntegerField("компания", null=True, blank=True)
    company_role = models.CharField("роль в компании", max_length=32, null=True, blank=True)
    is_admin = models.BooleanField("администратор", default=False)
    admin_role = models.CharField("роль в админке", max_length=32, null=True, blank=True)
    status = models.CharField("статус", max_length=32, default="active")
    email_verified_at = UTCDateTimeField("почта подтверждена", null=True, blank=True)
    last_login_at = UTCDateTimeField("последний вход", null=True, blank=True)
    created_at = UTCDateTimeField("зарегистрирован", null=True, blank=True)
    updated_at = UTCDateTimeField("изменён", null=True, blank=True)
    deleted_at = UTCDateTimeField("отключён", null=True, blank=True)
    locale = models.CharField("язык интерфейса", max_length=8, default="ru")
    must_change_password = models.BooleanField("требовать смену пароля при входе", default=False)
    admin_permissions = LaravelJSONField("личные права", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "users"
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"

    @property
    def disabled(self) -> bool:
        return self.deleted_at is not None
