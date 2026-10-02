from __future__ import annotations

from django.apps import AppConfig


class TendersConfig(AppConfig):
    """Закупки: раздел админки, загрузка файлом, госзакупки."""

    name = "savdex.tenders"
    label = "tenders"
    # Как группа этого раздела в меню (adminsite.MENU_GROUPS) — в «хлебных крошках»
    verbose_name = "Данные"
