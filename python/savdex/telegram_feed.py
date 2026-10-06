"""
Рассылка в Telegram: новые объявления и тендеры по категориям компании.

Фоновый проход (manage.py notify, раз в минуту, после писем по
уведомлениям) берёт опубликованное, что ещё не разбиралось
(telegram_feed_items), и шлёт каждому, кто привязал бота:

- объявление — после публикации (прошло модерацию: status active),
  тендер — когда он опубликован на сайте;
- если раздел объявления или тендера — категория его компании или её
  подраздел (company_category: категории общие на компанию и меняются на
  сайте);
- кроме объявлений его же компании, заблокированных и удалённых учётных
  записей и тех, кто поставил рассылку на паузу (notification_preferences,
  событие category_feed, telegram = false).

Каждая запись разбирается один раз: insert … on conflict do nothing —
два прохода (старый и новый контейнер во время деплоя) одно и то же не
разошлют дважды. Старше FRESH — разбирается без отправки: бот, лежавший
сутки, не должен потом завалить людей вчерашним.

До SINGLE новинок человеку за проход — отдельными сообщениями с кнопкой
«Открыть на SAVDEX»; больше (загрузили сотню объявлений из Excel) —
одним списком. Человек заблокировал бота — чат у учётной записи
снимается: писать ему больше некуда.

Бесплатно всем; платный доступ появится позже — место для него _eligible.
"""

from __future__ import annotations

import html
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection

from savdex.guards import allowed_writes
from savdex.telegram_bot import FEED_EVENT
from savdex.web import locales, messaging, ui
from savdex.web.it_tasks import number_format
from savdex.web.listing_actions import _now
from savdex.web.messaging import Button

log = logging.getLogger("savdex.telegram_feed")

#: Записей за проход (каждого вида)
LIMIT = 300

#: Опубликованное раньше — разбирается без отправки
FRESH = timedelta(days=1)

#: Новинок человеку за проход отдельными сообщениями; больше — одним списком
SINGLE = 5

#: Строк в списке
SUMMARY_LINES = 10

#: Пауза между сообщениями: Telegram пускает около 30 в секунду
PAUSE = 0.04


@dataclass
class Report:
    items: int = 0
    messages: int = 0
    people: int = 0
    blocked: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"новинок {self.items}, сообщений {self.messages} ({self.people} чел.), "
            f"заблокировали бота {self.blocked}, не ушло {self.failed}"
        )


@dataclass
class Item:
    kind: str
    row: dict[str, Any]
    categories: set[int]


def _rows(query: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


# ── Что нового ───────────────────────────────────────────────────────


def _claim(kind: str, now: datetime, limit: int) -> list[int]:
    """Занять ещё не разобранные опубликованные записи вида kind."""
    if kind == "listing":
        source = (
            "select 'listing', l.id, %s from listings l join companies c on c.id = l.company_id "
            "where l.status = 'active' and l.deleted_at is null "
            "and l.published_at is not null and l.published_at <= %s "
            "and c.status = 'active' and c.deleted_at is null "
            "and not exists (select 1 from telegram_feed_items f "
            "  where f.kind = 'listing' and f.item_id = l.id) "
            "order by l.published_at, l.id limit %s"
        )
    else:
        source = (
            "select 'tender', t.id, %s from tenders t "
            "where t.status = 'published' and (t.published_at is null or t.published_at <= %s) "
            "and not exists (select 1 from telegram_feed_items f "
            "  where f.kind = 'tender' and f.item_id = t.id) "
            "order by t.id limit %s"
        )

    with allowed_writes("telegram_feed_items"), connection.cursor() as cursor:
        cursor.execute(
            "insert into telegram_feed_items (kind, item_id, processed_at) "
            + source
            + " on conflict do nothing returning item_id",
            # Время в базе округлено до секунды и бывает чуть впереди часов
            # процесса: запас в минуту, чтобы только что опубликованное
            # не ждало следующего прохода
            [now, now + timedelta(minutes=1), limit],
        )

        return [row[0] for row in cursor.fetchall()]


def _ancestors(parents: dict[int, int | None], category_id: int | None) -> set[int]:
    """Раздел и все разделы над ним: объявление в «Диваны» — новость и для «Мебели»."""
    found: set[int] = set()

    while category_id is not None and category_id not in found:
        found.add(category_id)
        category_id = parents.get(category_id)

    return found


def _items(now: datetime, limit: int) -> tuple[list[Item], int]:
    """Свежие новинки и сколько всего записей разобрано за проход."""
    listing_ids = _claim("listing", now, limit)
    tender_ids = _claim("tender", now, limit)
    parents = {r["id"]: r["parent_id"] for r in _rows("select id, parent_id from categories", [])}
    items: list[Item] = []

    if listing_ids:
        for row in _rows(
            "select id, slug, title, title_i18n, type, price, currency, unit, price_negotiable, "
            "category_id, city_id, company_id, published_at from listings "
            "where id = any(%s) and published_at > %s order by published_at, id",
            [listing_ids, now - FRESH],
        ):
            items.append(Item("listing", row, _ancestors(parents, row["category_id"])))

    if tender_ids:
        for row in _rows(
            "select id, slug, title, title_i18n, budget, currency, customer, location, "
            "deadline_at, category_id, published_at from tenders "
            "where id = any(%s) and coalesce(published_at, updated_at, created_at) > %s "
            "order by id",
            [tender_ids, now - FRESH],
        ):
            items.append(Item("tender", row, _ancestors(parents, row["category_id"])))

    return items, len(listing_ids) + len(tender_ids)


# ── Кому ─────────────────────────────────────────────────────────────


def _recipients() -> list[dict[str, Any]]:
    """Привязавшие бота, со своими категориями компании; пауза — не получатель."""
    people = _rows(
        "select u.id, u.telegram_chat_id, u.locale, u.company_id from users u "
        "join companies c on c.id = u.company_id "
        "where u.telegram_chat_id is not null and u.deleted_at is null "
        "and u.status = 'active' and c.deleted_at is null and c.status = 'active' "
        "and not exists (select 1 from notification_preferences p where p.user_id = u.id "
        "  and p.event = %s and p.telegram = false) "
        "order by u.id",
        [FEED_EVENT],
    )

    if not people:
        return []

    chosen: dict[int, set[int]] = defaultdict(set)

    for link in _rows(
        "select company_id, category_id from company_category where company_id = any(%s)",
        [list({p["company_id"] for p in people})],
    ):
        chosen[link["company_id"]].add(link["category_id"])

    for person in people:
        person["categories"] = chosen.get(person["company_id"], set())

    return [p for p in people if p["categories"] and _eligible(p)]


def _eligible(person: dict[str, Any]) -> bool:
    """Пока рассылка бесплатна всем; платный доступ — проверка здесь."""
    return True


def _wanted(person: dict[str, Any], item: Item) -> bool:
    if not (person["categories"] & item.categories):
        return False

    # Своё объявление человеку не новость
    return not (item.kind == "listing" and item.row["company_id"] == person["company_id"])


# ── Текст ────────────────────────────────────────────────────────────


def _e(value: object) -> str:
    return html.escape(str(value), quote=False)


def _locale(person: dict[str, Any]) -> str:
    return person["locale"] if locales.supports(person["locale"]) else locales.DEFAULT


def _t(locale: str, key: str, **replace: object) -> str:
    return ui.t(f"messages.bot.{key}", locale, **replace)


def _url(locale: str, path: str) -> str:
    root = (os.environ.get("APP_URL") or "http://localhost").rstrip("/")

    return root + locales.prefix(locale) + path


def _title(row: dict[str, Any], locale: str) -> str:
    titles = row["title_i18n"] if isinstance(row["title_i18n"], dict) else {}
    own = titles.get(locale)

    return str(own).strip() if isinstance(own, str) and own.strip() else str(row["title"])


def _money(value: object, currency: object) -> str:
    amount = float(value)  # type: ignore[arg-type]

    return f"{number_format(amount, 0 if amount == int(amount) else 2)} {currency or 'UZS'}"


def _link(item: Item, locale: str) -> str:
    row = item.row
    key = row["slug"] or row["id"]

    return _url(locale, f"/listing/{key}" if item.kind == "listing" else f"/tenders/{key}")


def _date(value: datetime) -> str:
    local = value.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(settings.TIME_ZONE))

    return local.strftime("%d.%m.%Y")


class _Names:
    """Названия разделов и городов на языке человека — один запрос на язык."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], dict[int, str]] = {}

    def get(self, table: str, locale: str, key: int | None) -> str | None:
        from savdex.web.directory import _named

        if key is None:
            return None

        if (table, locale) not in self._cache:
            self._cache[(table, locale)] = _named(table, locale)

        return self._cache[(table, locale)].get(key)


def _text(item: Item, locale: str, names: _Names) -> str:
    row = item.row
    category = names.get("categories", locale, row["category_id"])

    if item.kind == "listing":
        kind = _t(locale, "type_demand" if row["type"] == "demand" else "type_supply")
        lines = [f"<b>{_e(_t(locale, 'feed_listing'))} · {_e(kind)}</b>"]
    else:
        lines = [f"<b>{_e(_t(locale, 'feed_tender'))}</b>"]

    if category:
        lines.append(_e(category))

    lines += ["", f"<b>{_e(_title(row, locale))}</b>"]

    if item.kind == "listing":
        if row["price"] is not None:
            price = _money(row["price"], row["currency"])
            lines.append(f"{_e(_t(locale, 'price'))}: {_e(price)}")
        elif row["price_negotiable"]:
            lines.append(f"{_e(_t(locale, 'price'))}: {_e(_t(locale, 'negotiable'))}")

        city = names.get("cities", locale, row["city_id"])

        if city:
            lines.append(f"{_e(_t(locale, 'city'))}: {_e(city)}")
    else:
        if row["budget"] is not None:
            budget = _money(row["budget"], row["currency"])
            lines.append(f"{_e(_t(locale, 'budget'))}: {_e(budget)}")

        if row["customer"]:
            lines.append(f"{_e(_t(locale, 'customer'))}: {_e(row['customer'])}")

        if row["location"]:
            lines.append(f"{_e(_t(locale, 'region'))}: {_e(row['location'])}")

        if row["deadline_at"] is not None:
            lines.append(f"{_e(_t(locale, 'deadline'))}: {_date(row['deadline_at'])}")

    return "\n".join(lines)


def _summary(items: list[Item], locale: str) -> str:
    lines = [f"<b>{_e(_t(locale, 'summary', count=len(items)))}</b>", ""]

    for item in items[:SUMMARY_LINES]:
        label = _t(locale, "feed_listing" if item.kind == "listing" else "feed_tender")
        link = html.escape(_link(item, locale), quote=True)
        lines.append(f'• <a href="{link}">{_e(_title(item.row, locale))}</a> — {_e(label)}')

    if len(items) > SUMMARY_LINES:
        lines.append(_e(_t(locale, "more", count=len(items) - SUMMARY_LINES)))

    return "\n".join(lines)


# ── Отправка ─────────────────────────────────────────────────────────


def _forget_chat(person: dict[str, Any]) -> None:
    """Человек заблокировал бота: чат у учётной записи снимается."""
    with allowed_writes("users"), connection.cursor() as cursor:
        cursor.execute(
            "update users set telegram_chat_id = null, telegram_username = null, "
            "telegram_linked_at = null where id = %s and telegram_chat_id = %s",
            [person["id"], person["telegram_chat_id"]],
        )


def _send(person: dict[str, Any], text: str, buttons: list[list[Button]]) -> messaging.Sent:
    sent = messaging.telegram_send(str(person["telegram_chat_id"]), text, buttons)

    # Telegram просит подождать — один повтор после паузы
    if not sent.ok and sent.retry_after:
        time.sleep(min(sent.retry_after, 30))
        sent = messaging.telegram_send(str(person["telegram_chat_id"]), text, buttons)

    time.sleep(PAUSE)

    return sent


def run(now: datetime | None = None, limit: int = LIMIT) -> Report:
    """Один проход рассылки."""
    report = Report()

    if not messaging.telegram_configured():
        return report

    now = now or _now()
    items, report.items = _items(now, limit)

    if not items:
        return report

    names = _Names()

    for person in _recipients():
        mine = [item for item in items if _wanted(person, item)]

        if not mine:
            continue

        locale = _locale(person)

        if len(mine) <= SINGLE:
            messages = [
                (
                    _text(item, locale, names),
                    [[Button(_t(locale, "btn_open"), _link(item, locale))]],
                )
                for item in mine
            ]
        else:
            path = "/tenders" if all(i.kind == "tender" for i in mine) else "/catalog"
            messages = [
                (_summary(mine, locale), [[Button(_t(locale, "btn_all"), _url(locale, path))]])
            ]

        delivered = False

        for text, buttons in messages:
            sent = _send(person, text, buttons)

            if sent.blocked:
                _forget_chat(person)
                report.blocked += 1
                break

            if sent.ok:
                report.messages += 1
                delivered = True
            else:
                report.failed += 1

        if delivered:
            report.people += 1

    return report
