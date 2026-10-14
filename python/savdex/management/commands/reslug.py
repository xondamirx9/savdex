"""
Адреса страниц латиницей для уже заведённых компаний и объявлений
(ТЗ-02 §4, savdex/reslug.py). Запускается при каждом деплое: трогает только
ещё плохие адреса, прежние остаются для 301.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from savdex import reslug


class Command(BaseCommand):
    help = "Переписать адреса /company/company и /listing/-N на латинские, старые — в 301"

    def handle(self, *args: Any, **options: Any) -> None:
        moved = reslug.run()
        self.stdout.write(f"Адреса: компаний {moved['company']}, объявлений {moved['listing']}")
