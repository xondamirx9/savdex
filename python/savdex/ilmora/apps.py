from __future__ import annotations

from django.apps import AppConfig


class IlmoraConfig(AppConfig):
    """Заявки на регистрацию в ILMORA с формы Savdex."""

    name = "savdex.ilmora"
    label = "ilmora"
    verbose_name = "ILMORA"
