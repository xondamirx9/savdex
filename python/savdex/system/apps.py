from __future__ import annotations

from django.apps import AppConfig


class SystemConfig(AppConfig):
    """Система: рассылки, роли и права (этап 6)."""

    name = "savdex.system"
    label = "system"
    verbose_name = "Система"
