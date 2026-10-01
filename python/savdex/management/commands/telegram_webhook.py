"""
Регистрация бота у Telegram одной командой — копия telegram:webhook
(app/Console/Commands/TelegramWebhook.php).

Токен и секрет берутся из переменных окружения, адрес собирается из
APP_URL, а ответ Telegram пересказывается по-русски: подставлять их
в адрес руками — ровно тот случай, когда в строку уезжает «<ТОКЕН>»,
Telegram отвечает «Not Found», и ошибку ищут в сайте.

  manage.py telegram_webhook            сообщить Telegram адрес бота
  manage.py telegram_webhook --info     что Telegram знает о боте сейчас
  manage.py telegram_webhook --delete   снять адрес
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from savdex.web import messaging


class Command(BaseCommand):
    help = "Сообщить Telegram адрес, на который присылать сообщения боту"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--info", action="store_true", help="Показать, что Telegram знает о боте сейчас"
        )
        parser.add_argument(
            "--delete", action="store_true", help="Снять адрес, бот перестанет получать сообщения"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not messaging.telegram_configured():
            self.stderr.write("Бот не настроен.")
            self.stderr.write(
                "  Задайте TELEGRAM_BOT_TOKEN (выдаёт @BotFather) и TELEGRAM_BOT_USERNAME "
                "(имя бота без «@»)."
            )

            raise SystemExit(1)

        if options["delete"]:
            self._report(
                *messaging.delete_webhook(), "Адрес снят: бот больше не получает сообщения."
            )

            return

        if options["info"]:
            self._info()

            return

        if messaging.webhook_secret() == "":
            self.stderr.write("Не задан TELEGRAM_WEBHOOK_SECRET.")
            self.stderr.write(
                "  Это любая случайная строка из 8–64 знаков (латиница, цифры, «-», «_»)."
            )
            self.stderr.write(
                "  Она становится частью адреса — без неё писать боту от чужого имени "
                "мог бы кто угодно."
            )

            raise SystemExit(1)

        self.stdout.write(f"  Адрес: {messaging.webhook_url()}")
        self._report(
            *messaging.register_webhook(),
            "Готово: Telegram будет присылать сообщения на этот адрес.",
        )

    def _report(self, ok: bool, message: str, success: str) -> None:
        if ok:
            self.stdout.write(success)

            return

        self.stderr.write(message)

        raise SystemExit(1)

    def _info(self) -> None:
        info = messaging.webhook_info()

        if info is None:
            self.stderr.write(
                "Telegram не ответил. Проверьте TELEGRAM_BOT_TOKEN и доступ в интернет "
                "с этого сервера."
            )

            raise SystemExit(1)

        url = str(info.get("url") or "")

        self.stdout.write(f"Адрес у Telegram: {url or 'не задан'}")
        self.stdout.write(f"Ожидает доставки: {info.get('pending_update_count') or 0}")

        if info.get("last_error_message"):
            self.stdout.write(f"Последняя ошибка: {info['last_error_message']}")

        expected = messaging.webhook_url()

        if expected is not None and url != expected:
            self.stdout.write("")
            self.stdout.write(f"Адрес отличается от нынешних настроек: {expected}")
            self.stdout.write(
                "  Выполните «manage.py telegram_webhook», чтобы привести их в соответствие."
            )
