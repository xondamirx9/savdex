from __future__ import annotations

from django.apps import AppConfig


class SiteConfig(AppConfig):
    """Настройки площадки (этап 2): контакты, реквизиты, оформление, валюты."""

    name = "savdex.site"
    label = "site"
    # Как группа этого раздела в меню (adminsite.MENU_GROUPS) — в «хлебных крошках»
    verbose_name = "Контент"
