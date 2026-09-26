"""
Консольная часть прозвона Uzum.

Вся содержательная часть — в `savdex.payments.uzum`; здесь печать
и код возврата.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from savdex.payments.uzum import UzumConfig, probe


class Command(BaseCommand):
    help = "Проверить доступ к API Uzum Checkout и ключи, не проводя платёж"

    def handle(self, *args: Any, **options: Any) -> None:
        config = UzumConfig.from_env()

        self.stdout.write("Конфигурация:")

        for строка in config.lines():
            self.stdout.write(f"  {строка}")

        self.stdout.write("")

        if not config.enabled:
            self.stderr.write("Провайдер выключен: задайте PAYMENTS_UZUM_ENABLED=true")

            raise SystemExit(1)

        итог = probe(config)

        if not итог.ok:
            self.stderr.write(f"СБОЙ: {итог.message}")

            raise SystemExit(1)

        self.stdout.write(f"OK: {итог.message}")

        if not config.checkout:
            self.stdout.write(
                "Кнопка «Оплатить» пока выключена: задайте PAYMENTS_UZUM_CHECKOUT_ENABLED=true"
            )
