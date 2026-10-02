from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Пользователи: поиск, отключение, восстановление и удаление навсегда."""

    name = "savdex.accounts"
    label = "accounts"
    # Как группа этого раздела в меню (adminsite.MENU_GROUPS) — в «хлебных крошках»
    verbose_name = "Система"
