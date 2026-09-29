from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Пользователи: поиск, отключение, восстановление и удаление навсегда."""

    name = "savdex.accounts"
    label = "accounts"
    verbose_name = "Пользователи"
