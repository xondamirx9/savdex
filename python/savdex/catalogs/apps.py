from __future__ import annotations

from django.apps import AppConfig


class CatalogsConfig(AppConfig):
    """Справочники площадки, кроме географии (этап 2): типы компаний и дальше."""

    name = "savdex.catalogs"
    label = "catalogs"
    verbose_name = "Справочники"
