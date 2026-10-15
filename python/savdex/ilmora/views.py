"""
Страницы ILMORA на сайте Savdex.

- /register/ilmora-register — форма заявки (GET) и её отправка (POST,
  throttle:10,10,ilmora-register, капча — как у первого шага регистрации).
  Заявка сохраняется, затем — экран «Заявка принята» с кнопкой «Перейти
  в ILMORA». Аккаунт Savdex не заводится, вход не выполняется;
- /ilmora/offer — публичная оферта (текст — offer/<язык>.txt).

У ILMORA два языка — русский и узбекский: на /en, /zh и /tr страницы
показываются по-русски.

ПИНФЛ, ИНН, телефон и ФИО в журналы и логи не пишутся: в логе — только
номер заявки.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.audit import client_ip
from savdex.ilmora import site_url
from savdex.ilmora.form import PHONE_PREFIX, Application, validate
from savdex.web import captcha, eloquent, inertia
from savdex.web.actions import form
from savdex.web.forms import action, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.seo import Seo
from savdex.web.shared import Context

log = logging.getLogger("savdex.ilmora")

#: Языки ILMORA; остальные — по-русски
LOCALES = ("ru", "uz")

#: Какой текст оферты принимали. Опубликуют настоящий — сменить здесь
#: (например на «2026-11-01»): у старых заявок останется «draft»
OFFER_VERSION = "draft"

#: Тексты оферты: offer/ru.txt и offer/uz.txt. Пусто — «будет опубликован позже»
OFFER_DIR = Path(__file__).resolve().parent / "offer"

PATH = "/register/ilmora-register"
OFFER_PATH = "/ilmora/offer"
#: Метка в сессии после сохранения: следующий показ страницы — «Заявка
#: принята». Не флеш: на /en, /zh и /tr между отправкой и страницей бывает
#: ещё переход на запомненный язык, и флеш пропадал бы на нём
DONE = "ilmora.done"


def _ilmora(ctx: Context) -> Context:
    """Контекст на языке ILMORA: русский или узбекский."""
    return ctx if ctx.locale in LOCALES else replace(ctx, locale="ru")


def _seo(ctx: Context, title: str) -> Seo:
    from savdex.web.cabinet import _seo as noindex

    return noindex(ctx).title(title)


def page(request: HttpRequest) -> HttpResponse:
    """Форма заявки; сразу после отправки — экран «Заявка принята»."""
    from savdex.web.cabinet import _store
    from savdex.web.request import context

    found = context(request)

    if isinstance(found, HttpResponse):
        return found

    ctx = _ilmora(found)
    store = _store(ctx)
    done = store is not None and store.get(DONE) is True

    if done and store is not None:
        store.forget(DONE)

    return inertia.render(
        ctx,
        "ilmora/Register",
        {
            "done": done,
            "ilmoraUrl": site_url(),
            "phonePrefix": PHONE_PREFIX,
            "captcha": captcha.enabled(),
        },
        _seo(ctx, ctx.t("ilmora.title")),
    )


@form()
def submit(request: HttpRequest) -> HttpResponse:
    """Отправка заявки: проверка, капча, запись — и назад на страницу с «Заявка принята»."""
    from savdex.web.auth_actions import _session, _to

    ctx = _ilmora(
        action(
            request,
            auth=False,
            throttle=10,
            throttle_minutes=10,
            throttle_prefix="ilmora-register",
        )
    )
    data = input_of(request)
    application, errors = validate(ctx, data)

    if application is None:
        return invalid(ctx, errors)

    # Капча — после полей: с ошибкой в номере задание не гасится зря
    if (problem := captcha.verify(_session(ctx), "ilmora", data.get("captcha"))) is not None:
        return invalid(ctx, {"captcha": [ctx.t(f"captcha.errors.{problem}")]})

    number = save(ctx, application)
    log.info("ILMORA: заявка #%s (%s)", number, application.person_type)
    _session(ctx).put(DONE, True)

    return _to(ctx, PATH)


def save(ctx: Context, application: Application) -> int:
    """Заявка в ilmora_registrations: обе галочки — временем отправки."""
    now = _stamp(eloquent.now())
    agent = ctx.request.headers.get("User-Agent")

    with connection.cursor() as cursor:
        cursor.execute(
            "insert into ilmora_registrations (created_at, person_type, phone, full_name, pinfl, "
            "tin, offer_accepted_at, offer_signed_at, offer_version, locale, ip, user_agent) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
            [
                now,
                application.person_type,
                application.phone,
                application.full_name,
                application.pinfl,
                application.tin,
                now,
                now,
                OFFER_VERSION,
                ctx.locale,
                client_ip(ctx.request),
                agent[:500] if agent else None,
            ],
        )

        return int(cursor.fetchone()[0])


def offer_text(locale: str) -> list[str]:
    """Абзацы оферты (пустая строка между ними); файла или текста нет — []."""
    path = OFFER_DIR / f"{locale if locale in LOCALES else 'ru'}.txt"

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    return [" ".join(part.split()) for part in text.split("\n\n") if part.strip()]


def offer(request: HttpRequest) -> HttpResponse:
    """Публичная оферта ILMORA. Пока текста нет — «будет опубликован позже»."""
    from savdex.web.request import context

    found = context(request)

    if isinstance(found, HttpResponse):
        return found

    ctx = _ilmora(found)

    return inertia.render(
        ctx,
        "ilmora/Offer",
        {"paragraphs": offer_text(ctx.locale), "version": OFFER_VERSION},
        _seo(ctx, ctx.t("ilmora.offer.title")),
    )
