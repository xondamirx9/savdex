from __future__ import annotations

from django.apps import AppConfig


class SiteConfig(AppConfig):
    """Настройки площадки (этап 2): контакты, реквизиты, оформление, валюты."""

    name = "savdex.site"
    label = "site"
    verbose_name = "Площадка"
