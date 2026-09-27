from __future__ import annotations

from django.apps import AppConfig


class GeoConfig(AppConfig):
    """География: страны (этап 2), позже — города."""

    name = "savdex.geo"
    label = "geo"
    verbose_name = "География"
