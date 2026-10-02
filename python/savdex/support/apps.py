from __future__ import annotations

from django.apps import AppConfig


class SupportConfig(AppConfig):
    """Обращения в поддержку (этап 6)."""

    name = "savdex.support"
    label = "support"
    # Как группа этого раздела в меню (adminsite.MENU_GROUPS) — в «хлебных крошках»
    verbose_name = "CRM"
