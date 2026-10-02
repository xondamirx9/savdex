from __future__ import annotations

from django.apps import AppConfig


class DataConfig(AppConfig):
    """Данные площадки в админке: заказы на услуги, объявления, компании (этап 6)."""

    name = "savdex.data"
    label = "data"
    verbose_name = "Данные"
