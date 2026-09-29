from __future__ import annotations

from django.apps import AppConfig


class JournalConfig(AppConfig):
    """Журнал действий администраторов — только чтение (этап 6)."""

    name = "savdex.journal"
    label = "journal"
    verbose_name = "Система"
