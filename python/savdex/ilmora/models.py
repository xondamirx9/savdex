"""
Заявка на регистрацию в ILMORA — ilmora_registrations глазами админки.

Таблицу заводит миграция 2026_10_26_100000, пишет только форма сайта
(savdex/ilmora/views.py) — обычной вставкой. Админка заявку не правит
и не удаляет: время подписания договора — юридическое подтверждение.
Столбцы offer_* названы так, когда документ ещё был «офертой».
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.catalog import UTCDateTimeField

PERSON_TYPES = {"individual": "Физическое лицо", "legal": "Юридическое лицо"}


class Registration(models.Model):
    created_at = UTCDateTimeField("дата")
    person_type = models.CharField("тип лица", max_length=16, choices=list(PERSON_TYPES.items()))
    phone = models.CharField("телефон", max_length=16)
    full_name = models.CharField("ФИО", max_length=150)
    pinfl = models.CharField("ПИНФЛ", max_length=14, null=True)
    tin = models.CharField("ИНН", max_length=9, null=True)
    offer_accepted_at = UTCDateTimeField("ознакомился с договором")
    offer_signed_at = UTCDateTimeField("подписал договор")
    offer_version = models.CharField("версия договора", max_length=32)
    locale = models.CharField("язык", max_length=8, null=True)
    ip = models.CharField("IP-адрес", max_length=45, null=True)
    user_agent = models.CharField("браузер", max_length=500, null=True)

    class Meta:
        managed = False
        db_table = "ilmora_registrations"
        verbose_name = "заявка ILMORA"
        verbose_name_plural = "ILMORA — регистрации"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"Заявка ILMORA #{self.pk}"

    @property
    def number(self) -> str | None:
        """ПИНФЛ физлица или ИНН юрлица."""
        return self.pinfl if self.person_type == "individual" else self.tin

    def save(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Заявки ILMORA пишет только форма сайта.")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise RuntimeError("Заявки ILMORA не удаляются.")
