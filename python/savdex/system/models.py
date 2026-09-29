"""
Система — рассылки (broadcasts) глазами админки Django (этап 6). Схема —
у Laravel; таблица этапа 5, запись — в блоке allowed_writes.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.accounts.models import User
from savdex.catalog import Timestamped, UTCDateTimeField
from savdex.guards import allowed_writes

#: Broadcast::AUDIENCES
AUDIENCES = {
    "all": "Все пользователи",
    "plan": "Компании на тарифе",
    "verified": "Проверенные компании",
    "unverified": "Непроверенные компании",
    "no_company": "Без компании",
}

TONES = {
    "info": "Обычное",
    "success": "Хорошая новость",
    "warning": "Предупреждение",
    "danger": "Важно",
}


class Broadcast(Timestamped):
    """App\\Models\\Broadcast: рассылка уведомлений по сегменту."""

    sent_by = models.ForeignKey(
        User,
        verbose_name="автор",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="sent_by",
        related_name="+",
        editable=False,
    )
    title = models.CharField(
        "заголовок", max_length=190, help_text="Видно в списке уведомлений и в колокольчике"
    )
    body = models.TextField("текст", max_length=2000)
    url = models.CharField(
        "ссылка",
        max_length=190,
        null=True,
        blank=True,
        help_text="Куда ведёт нажатие. Например /news/oplata-click-uzum",
    )
    tone = models.CharField("тон", max_length=255, default="info", choices=list(TONES.items()))
    audience = models.CharField(
        "получатели", max_length=255, default="all", choices=list(AUDIENCES.items())
    )
    audience_value = models.CharField("тариф", max_length=255, null=True, blank=True)
    recipients_count = models.IntegerField("получили", default=0, editable=False)
    sent_at = UTCDateTimeField("отправлена", null=True, editable=False)

    class Meta:
        managed = False
        db_table = "broadcasts"
        verbose_name = "рассылка"
        verbose_name_plural = "рассылки"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.title

    def audience_label(self) -> str:
        """Broadcast::audienceLabel."""
        label = AUDIENCES.get(self.audience, self.audience)

        return (
            f"{label} {self.audience_value}"
            if self.audience == "plan" and self.audience_value
            else label
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        with allowed_writes("broadcasts"):
            super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        with allowed_writes("broadcasts"):
            return super().delete(*args, **kwargs)
