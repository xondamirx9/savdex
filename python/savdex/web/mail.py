"""
Письма площадки со стороны Django — как уведомления Laravel (MailMessage
в оформлении по умолчанию) и почтовик из MAIL_* (этап 5, шаг 45).

Оформление — снимок того, что собирал Laravel, на каждом языке площадки:
mail_templates/<письмо>.<язык>.subject|html|txt (ru, en, uz, tr, zh) с
метками __LANG__, __APP_URL__, __URL__ (в HTML — экранированный,
__URL_HTML__), __CODE__, __YEAR__. Разметка у языков одна, разнится
только текст. Язык письма — язык страницы, где его запросили
(ctx.locale: префикс адреса, затем users.locale, затем сессия);
неизвестный язык или письмо без перевода — русское (locales.DEFAULT).

Почтовик — MAIL_MAILER, как config/mail.php:
- smtp: MAIL_HOST, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD; порт 465 или
  MAIL_SCHEME=smtps — сразу TLS, иначе STARTTLS, как у Symfony Mailer;
- log: письмо целиком — в файл MAIL_LOG_PATH (по умолчанию
  storage/logs/python-mail.log), как log-почтовик Laravel;
- прочее (array) — никуда.

Сбой отправки пишется в журнал и не роняет запрос — как
User::sendEmailVerificationNotification.
"""

from __future__ import annotations

import html
import logging
import os
from datetime import UTC, datetime
from email.utils import formataddr
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from savdex.web import locales

log = logging.getLogger("savdex.mail")

_TEMPLATES = Path(__file__).with_name("mail_templates")
_PARTS = ("subject", "html", "txt")


def language(*candidates: object) -> str:
    """Первый язык площадки среди кандидатов (язык страницы, users.locale…), иначе ru."""
    for candidate in candidates:
        if locales.supports(candidate):
            return str(candidate)

    return locales.DEFAULT


def _template_language(name: str, lang: str) -> str:
    """Язык, на котором письмо есть целиком; нет перевода — русский."""
    if all((_TEMPLATES / f"{name}.{lang}.{ext}").is_file() for ext in _PARTS):
        return lang

    return locales.DEFAULT


def render(
    name: str, *, url: str, app_url: str, lang: str | None, code: str = ""
) -> tuple[str, str, str]:
    """Тема, HTML и текст письма на языке lang (неизвестный — русский)."""
    lang = _template_language(name, language(lang))
    year = str(datetime.now(UTC).year)

    def fill(text: str) -> str:
        return (
            text.replace("__URL_HTML__", html.escape(url, quote=True))
            .replace("__URL__", url)
            .replace("__APP_URL__", app_url)
            .replace("__CODE__", code)
            .replace("__YEAR__", year)
            .replace("__LANG__", lang)
        )

    subject, body_html, body_text = (
        fill((_TEMPLATES / f"{name}.{lang}.{ext}").read_text(encoding="utf-8")) for ext in _PARTS
    )

    return subject, body_html, body_text


def _sender() -> str:
    address = os.environ.get("MAIL_FROM_ADDRESS") or "hello@example.com"
    name = os.environ.get("MAIL_FROM_NAME") or os.environ.get("APP_NAME") or "Laravel"

    return formataddr((name, address))


def _log_path() -> Path:
    configured = os.environ.get("MAIL_LOG_PATH")

    if configured:
        return Path(configured)

    return Path(settings.LARAVEL_ROOT) / "storage/logs/python-mail.log"


def send(to: str, subject: str, body_html: str, body_text: str) -> bool:
    """Отправить письмо (текст и HTML); сбой — в журнал, False."""
    message = EmailMultiAlternatives(subject, body_text, _sender(), [to])
    message.attach_alternative(body_html, "text/html")
    mailer = os.environ.get("MAIL_MAILER") or "log"

    try:
        if mailer == "smtp":
            port = int(os.environ.get("MAIL_PORT") or 587)
            implicit = os.environ.get("MAIL_SCHEME") == "smtps" or port == 465
            connection = get_connection(
                "django.core.mail.backends.smtp.EmailBackend",
                host=os.environ.get("MAIL_HOST") or "127.0.0.1",
                port=port,
                username=os.environ.get("MAIL_USERNAME") or None,
                password=os.environ.get("MAIL_PASSWORD") or None,
                use_ssl=implicit,
                use_tls=not implicit,
                timeout=int(os.environ.get("MAIL_TIMEOUT") or 30),
            )
            connection.send_messages([message])
        elif mailer == "log":
            path = _log_path()
            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open("a", encoding="utf-8") as handle:
                handle.write(message.message().as_string() + "\n")
    except Exception:
        log.exception("Письмо на %s не отправлено", to)

        return False

    return True
