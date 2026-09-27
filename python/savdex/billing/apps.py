from __future__ import annotations

from django.apps import AppConfig


class BillingConfig(AppConfig):
    """Монетизация (этап 2): пакеты контактов, дальше — тарифы и промокоды."""

    name = "savdex.billing"
    label = "billing"
    verbose_name = "Монетизация"
