from __future__ import annotations

from django.apps import AppConfig


class ModerationConfig(AppConfig):
    """Модерация: отзывы о компаниях и о площадке (этап 6)."""

    name = "savdex.moderation"
    label = "moderation"
    verbose_name = "Модерация"
