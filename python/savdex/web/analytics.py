"""
Google Analytics 4 на сайте (ТЗ-03): тег в <head> и события продукта.

Тег ставится только на боевом сайте (APP_ENV=production) или когда
GA4_MEASUREMENT_ID задан явно — так локальный запуск и проверки не
засоряют отчёты. В админку тег не попадает: у неё свои шаблоны.

События, которые подтверждает сервер (регистрация, публикация, отклик,
упёрся в лимит), копятся здесь и уходят на клиент вместе со страницей:
  queue(ctx, ...)       — после перенаправления: событие ложится в сессию
                          и показывается на следующей странице (POST → GET);
  queue(ctx, ..., now=True) — в этот же ответ (страница каталога, карточка).
Отправляет их resources/js/lib/analytics.ts — одной обёрткой track().

Персональных данных в событиях нет: ни почты, ни телефона, ни ИНН, ни
имени, ни названия компании — только коды, номера объявлений и признаки.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from savdex.web.shared import Context

#: Ресурс «Savdex», поток «Savdex - savdex.uz»
DEFAULT_ID = "G-E5YEXDTG4X"

#: Ключ сессии: события до следующей страницы (флеш живёт один запрос)
_SESSION_KEY = "analytics_events"
#: События этого ответа — на объекте запроса, не в сессии
_NOW_ATTR = "_analytics_now"

_ID = re.compile(r"^G-[A-Z0-9]{4,20}$")


def measurement_id() -> str:
    """Номер потока GA4 или пусто — тег на этой площадке не ставится."""
    configured = (os.environ.get("GA4_MEASUREMENT_ID") or "").strip()

    if configured:
        return configured if _ID.match(configured) else ""

    return DEFAULT_ID if os.environ.get("APP_ENV", "local") == "production" else ""


def head_tags(path: str) -> list[str]:
    """
    gtag.js сразу после <head>. Первый просмотр не считается тегом
    (send_page_view: false): его вместе со всеми переходами Inertia
    отправляет клиент — иначе первая страница считалась бы дважды.
    Без integrity: Google меняет gtag.js без смены адреса, и хеш
    ломал бы тег (так же в официальной инструкции Google).
    """
    ga = measurement_id()

    if not ga or path.startswith("/admin") or path.startswith("/py/admin"):
        return []

    return [
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga}"></script>',
        "<script>window.dataLayer=window.dataLayer||[];"
        "function gtag(){dataLayer.push(arguments);}"
        f"gtag('js',new Date());gtag('config','{ga}',{{send_page_view:false}});</script>",
    ]


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Только простые значения: GA4 не принимает вложенные объекты."""
    return {k: v for k, v in params.items() if isinstance(v, (str, int, float, bool)) or v is None}


def queue(
    ctx: Context, name: str, params: dict[str, Any] | None = None, *, now: bool = False
) -> None:
    """Событие для GA4: в этот ответ (now) или на следующую страницу."""
    event = {"name": name, "params": _clean(params or {})}

    if now:
        events = getattr(ctx, _NOW_ATTR, None)

        if events is None:
            events = []
            setattr(ctx, _NOW_ATTR, events)

        events.append(event)

        return

    from savdex.web.forms import flash

    pending = ctx.session.get(_SESSION_KEY)
    flash(ctx, _SESSION_KEY, [*(pending if isinstance(pending, list) else []), event])


def events(ctx: Context) -> list[dict[str, Any]]:
    """Что отправить с этой страницей: отложенное с прошлого запроса и своё."""
    pending = ctx.session.get(_SESSION_KEY)
    found = list(pending) if isinstance(pending, list) else []

    return found + list(getattr(ctx, _NOW_ATTR, None) or [])


def script_of(text: str) -> str:
    """Письменность запроса — для отчёта «что ищут», без самого запроса."""
    text = text.strip()

    if not text:
        return "none"

    if re.search(r"[一-鿿]", text):
        return "cjk"

    if re.search(r"[а-яёА-ЯЁўқғҳЎҚҒҲ]", text):
        return "cyrillic"

    if re.search(r"[A-Za-z]", text):
        return "latin"

    return "other"


def country_code(country_id: Any) -> str | None:  # noqa: ANN401
    """Код страны (uz, cn…) вместо номера справочника — так читается отчёт."""
    if not country_id:
        return None

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("select code from countries where id = %s", [country_id])
        row = cursor.fetchone()

    return str(row[0]) if row else None


def intended_plan(ctx: Context) -> str:
    """
    Тариф, с которым человек пришёл на регистрацию (кнопка «Выбрать» на
    /pricing → /register?plan=код): после регистрации его ждёт оплата.
    """
    from savdex.web.forms import _store

    store = _store(ctx)
    intended = str(store.get("url.intended") or "") if store is not None else ""
    found = re.search(r"[?&]plan=([a-z0-9_-]+)", intended)

    return found.group(1) if found else "free"


def tin_validation_failed(ctx: Context, country: str | None, reason: str) -> None:
    """
    GA4 (ТЗ-02): номер компании не прошёл проверку — страна (код) и причина
    (uz_length, cn_format, digits_only, taken…). Самого номера в событии нет.
    Много cn_format — китайцам непонятно, что вводить, и подсказку пора менять.
    """
    queue(ctx, "tin_validation_failed", {"country": country or "uz", "reason": reason})


def limit_reached(ctx: Context, limit_type: str, plan: str | None) -> None:
    """GA4: человек упёрся в лимит тарифа — listing, unlock или replies."""
    queue(ctx, "limit_reached", {"limit_type": limit_type, "plan": plan or "free"})


def listing_published(ctx: Context, listing: dict[str, Any]) -> None:
    """GA4: объявление опубликовано — тип, раздел, цена и фото, без текста."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "select (select slug from categories where id = %s), "
            "(select count(*) from listing_images where listing_id = %s)",
            [listing.get("category_id"), listing["id"]],
        )
        slug, photos = cursor.fetchone() or (None, 0)

    queue(
        ctx,
        "listing_published",
        {
            "type": listing.get("type"),
            "category_id": listing.get("category_id"),
            # «Другое» в справочнике — drugoe и <раздел>-drugoe
            "is_other_category": isinstance(slug, str)
            and (slug == "drugoe" or slug.endswith("-drugoe")),
            "has_price": listing.get("price") is not None and not listing.get("price_negotiable"),
            "currency": listing.get("currency"),
            "photos_count": int(photos or 0),
        },
    )
