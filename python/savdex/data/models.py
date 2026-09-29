"""
Данные площадки глазами админки Django (этап 6). Схема — у Laravel
(managed = False); таблицы этапов 4–5, в них пишет и кабинет, поэтому
запись — в блоке allowed_writes (SHARED_WRITES).

IT-задача (App\\Models\\ItTask):

- ItTask::saving — search_text из заголовка, описания и стека;
- адрес (slug) ставит кабинет при создании; из админки задачи не
  создаются — только правка, снятие и удаление.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.catalog import LaravelJSONField, Timestamped, UTCDateTimeField
from savdex.crm.models import Company
from savdex.guards import allowed_writes

#: ItTask::STATUSES
IT_STATUSES = {
    "active": "Открыта",
    "closed": "Закрыта",
    "completed": "Выполнена",
    "archived": "В архиве",
}

#: ItTask::SERVICE_TYPES
SERVICE_TYPES = {
    "web": "Сайты и веб-приложения",
    "mobile": "Мобильные приложения",
    "erp": "1С, учёт и ERP",
    "integration": "Интеграции и API",
    "design": "Дизайн и UX",
    "automation": "Автоматизация и боты",
    "support": "Поддержка и администрирование",
    "logistics": "Логистика и перевозки",
    "hr": "Подбор персонала",
    "customs": "Декларирование и ВЭД",
    "accounting": "Бухгалтерские услуги",
    "other": "Другое",
}

BUDGET_TYPES = {"negotiable": "Договорной", "fixed": "Фиксированный", "range": "Диапазон"}

#: ItTask::CURRENCIES
IT_CURRENCIES = ("UZS", "USD")


class ItTask(Timestamped):
    """App\\Models\\ItTask: задача заказчика исполнителям."""

    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
        editable=False,
    )
    user_id = models.BigIntegerField(null=True, editable=False)
    slug = models.CharField(max_length=255, null=True, editable=False)
    title = models.CharField("название", max_length=120)
    description = models.TextField("описание", max_length=8000)
    service_type = models.CharField(
        "вид услуги", max_length=255, choices=list(SERVICE_TYPES.items())
    )
    stack = LaravelJSONField("стек", null=True, blank=True)
    budget_type = models.CharField("бюджет", max_length=255, choices=list(BUDGET_TYPES.items()))
    budget_from = models.DecimalField(
        "от / сумма", max_digits=16, decimal_places=2, null=True, blank=True
    )
    budget_to = models.DecimalField("до", max_digits=16, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        "валюта", max_length=3, choices=[(c, c) for c in IT_CURRENCIES], default="UZS"
    )
    deadline_at = models.DateField("срок сдачи", null=True, blank=True)
    status = models.CharField("статус", max_length=255, choices=list(IT_STATUSES.items()))
    published_at = UTCDateTimeField("опубликована", null=True, editable=False)
    closed_at = UTCDateTimeField(null=True, editable=False)
    responses_count = models.IntegerField("откликов", default=0, editable=False)
    views_count = models.IntegerField(default=0, editable=False)
    search_text = models.TextField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "it_tasks"
        verbose_name = "IT-задача"
        verbose_name_plural = "IT-задачи"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """ItTask::saving: search_text заново."""
        from savdex.web.it_task_actions import _search_text

        self.search_text = _search_text(
            {"title": self.title, "description": self.description, "stack": self.stack}
        )["search_text"]

        with allowed_writes("it_tasks"):
            super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        with allowed_writes("it_tasks"):
            return super().delete(*args, **kwargs)
