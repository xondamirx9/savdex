from __future__ import annotations

from django.apps import AppConfig


class TendersConfig(AppConfig):
    """Закупки: раздел админки, загрузка файлом, госзакупки."""

    name = "savdex.tenders"
    label = "tenders"
    verbose_name = "Закупки"
