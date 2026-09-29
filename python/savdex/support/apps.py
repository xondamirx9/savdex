from __future__ import annotations

from django.apps import AppConfig


class SupportConfig(AppConfig):
    """Обращения в поддержку (этап 6)."""

    name = "savdex.support"
    label = "support"
    verbose_name = "Поддержка"
