from __future__ import annotations

from django.apps import AppConfig


class FinanceConfig(AppConfig):
    """Деньги в админке (этап 7): счета, подписки, промокоды, возвраты, отчёты."""

    name = "savdex.finance"
    label = "finance"
    verbose_name = "Монетизация"
