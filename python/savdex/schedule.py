"""
Задачи по расписанию Django — вместо расписания Laravel (routes/console.php):
раз в сутки в свой час или каждые N часов.

У Laravel задачу раз в сутки запускает schedule:work; здесь — команда
manage.py schedule (цикл в docker/render-entrypoint.sh), проверка раз в
минуту. Какой день каждая задача уже прошла, помнит файл
(SAVDEX_SCHEDULE_STATE, иначе storage/app/schedule.json):

- перезапуск контейнера проход не повторяет;
- контейнер, поднявшийся после назначенного часа, свой день догоняет;
- самый первый запуск задачи после её часа день пропускает — в этот
  день её уже сделало расписание Laravel.

Время — UTC, как у Laravel (часы приложения — UTC).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection

from savdex.guards import allowed_writes


@dataclass(frozen=True)
class Job:
    name: str
    #: dailyAt у Laravel; у повторяющихся — минута часа
    at: time
    #: (сейчас, назначенный момент) → строка для журнала
    run: Callable[[datetime, datetime], str]
    #: Повтор каждые N часов (hourly — 1, everyFourHours — 4), от полуночи;
    #: None — раз в сутки
    every: int | None = None

    def due(self, now: datetime) -> datetime:
        """Последний назначенный момент (у суточной — сегодняшний, даже будущий)."""
        if self.every is None:
            return datetime.combine(now.date(), self.at)

        slot = datetime.combine(now.date(), time(now.hour - now.hour % self.every, self.at.minute))

        return slot if slot <= now else slot - timedelta(hours=self.every)

    def mark(self, due: datetime) -> str:
        """Запись пройденного: у суточной — день, у повторяющейся — момент."""
        if self.every is None:
            return due.date().isoformat()

        return due.isoformat(timespec="minutes")


# ── Задачи ───────────────────────────────────────────────────────────


def expire_listings(now: datetime, due: datetime) -> str:
    """listings:expire (06:00): снять истёкшие объявления, предупредить за три дня."""
    from savdex.web import listing_expiry

    expired, warned = listing_expiry.run(now, anchor=due)

    return f"Снято с публикации: {expired}. Предупреждений отправлено: {warned}."


def expire_tenders(now: datetime, due: datetime) -> str:
    """Каждый час: тендеры из кабинета — предупредить за три дня, по сроку — «Истёк»."""
    from savdex import tender_expiry

    expired, warned = tender_expiry.run(now)

    return f"Тендеров истекло: {expired}. Предупреждений: {warned}."


def prune_audience_views(now: datetime, due: datetime) -> str:
    """
    audience-views:prune (04:00): «Кто смотрел» старше 90 дней — прочь.
    Кабинет показывает месяц, ещё два — про запас.
    """
    from datetime import timedelta

    with allowed_writes("audience_views"), connection.cursor() as cursor:
        cursor.execute(
            "delete from audience_views where created_at < %s", [now - timedelta(days=90)]
        )
        deleted = cursor.rowcount

    return f"Удалено просмотров: {deleted}."


def recalculate_ratings(now: datetime, due: datetime) -> str:
    """
    ratings:recalculate (03:00): байесовский рейтинг каждой компании —
    (5 × среднее по площадке + сумма оценок) / (5 + число отзывов), только
    опубликованные. Среднее меняется у всех с каждым новым отзывом, поэтому
    целиком. Сохранение — как forceFill()->save(): search_text заново,
    updated_at, только если что-то изменилось; журнала нет (не администратор).
    """
    from savdex.web import eloquent
    from savdex.web.cabinet import _rows
    from savdex.web.company_profile_actions import _search_text
    from savdex.web.review_actions import COMPANY_CASTS, WEIGHT, _php_round

    average = _rows("select avg(rating) as a from reviews where status = 'published'")[0]["a"]
    # Отзывов нет вообще — нейтральная середина, а не «5» первой же компании
    global_average = float(average or 0) or 4.0
    stats = {
        row["company_id"]: (int(row["total"]), float(row["sum_rating"] or 0))
        for row in _rows(
            "select company_id, count(*) as total, sum(rating) as sum_rating from reviews "
            "where status = 'published' group by company_id"
        )
    }
    companies = _rows("select * from companies where deleted_at is null order by id")

    for company in companies:
        count, total = stats.get(company["id"], (0, 0.0))
        rating = (WEIGHT * global_average + total) / (WEIGHT + count) if count > 0 else 0.0
        eloquent.save(
            None,
            "companies",
            company,
            {"rating": _php_round(rating, 2), "reviews_count": count},
            section=None,
            model="Company",
            saving=_search_text,
            casts=COMPANY_CASTS,
        )

    return (
        f"Пересчитано компаний: {len(companies)}. "
        f"Среднее по площадке: {_php_round(global_average, 2)}"
    )


def ask_for_reviews(now: datetime, due: datetime, limit: int = 300) -> str:
    """
    reviews:ask (06:00): просьба оставить отзыв — в колокольчик, по одной
    на повод. О площадке — через неделю после регистрации; о компании —
    через 3–30 дней после раскрытия её контактов, если отзыва от компании
    ещё нет и на контакты не жаловались. Повтор отсекается по уже
    отправленному уведомлению того же вида (и адреса — для компании).
    Язык — профиля человека, без него — русский (app.locale у Laravel).
    """
    from datetime import timedelta

    from savdex.web import ui
    from savdex.web.cabinet import _rows

    def deliver(user: dict[str, Any], type_: str, title: str, body: str, url: str) -> None:
        """Notifier::user → UserNotification::deliver."""
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")

        with allowed_writes("user_notifications"), connection.cursor() as cursor:
            cursor.execute(
                "insert into user_notifications (user_id, company_id, type, title, body, tone, "
                "url, created_at, updated_at) values (%s, %s, %s, %s, %s, 'info', %s, %s, %s)",
                [user["id"], user["company_id"], type_, title, body, url, stamp, stamp],
            )

    users = _rows(
        "select id, company_id, locale from users u where deleted_at is null "
        "and status = 'active' and is_admin = false and email_verified_at is not null "
        "and created_at <= %s "
        # Сотрудника заблокированной компании об отзыве не просим
        "and not exists (select 1 from companies c where c.id = u.company_id "
        "and c.status = 'blocked') "
        "and not exists (select 1 from platform_reviews p where p.user_id = u.id) "
        "and not exists (select 1 from user_notifications n where n.user_id = u.id "
        "and n.type = 'platform_review_ask') order by id limit %s",
        [now - timedelta(days=7), limit],
    )

    for user in users:
        locale = user["locale"] or "ru"
        deliver(
            user,
            "platform_review_ask",
            ui.t("platform_reviews.ask_title", locale),
            ui.t("platform_reviews.ask_body", locale),
            "/reviews/new",
        )

    unlocks = _rows(
        "select cu.user_id, cu.target_company_id, u.company_id, u.locale, t.slug, t.name "
        "from contact_unlocks cu "
        "join users u on u.id = cu.user_id and u.deleted_at is null and u.status = 'active' "
        "and not exists (select 1 from companies c where c.id = u.company_id "
        "and c.status = 'blocked') "
        "join companies t on t.id = cu.target_company_id and t.deleted_at is null "
        "and t.status = 'active' "
        "where cu.user_id is not null and cu.complaint_status is null "
        "and cu.created_at between %s and %s "
        "and not exists (select 1 from reviews r where r.company_id = cu.target_company_id "
        "and r.author_company_id = cu.company_id) order by cu.id",
        [now - timedelta(days=30), now - timedelta(days=3)],
    )
    seen: set[tuple[int, int]] = set()
    sent = 0

    for unlock in unlocks:
        # ->unique(user_id:target_company_id): первое раскрытие пары
        pair = (unlock["user_id"], unlock["target_company_id"])

        if pair in seen:
            continue

        seen.add(pair)

        if sent >= limit:
            break

        url = f"/company/{unlock['slug']}#reviews"

        if _rows(
            "select 1 from user_notifications where user_id = %s and type = 'review_ask' "
            "and url = %s limit 1",
            [unlock["user_id"], url],
        ):
            continue

        locale = unlock["locale"] or "ru"
        deliver(
            {"id": unlock["user_id"], "company_id": unlock["company_id"]},
            "review_ask",
            ui.t("platform_reviews.ask_company_title", locale, name=unlock["name"]),
            ui.t("platform_reviews.ask_company_body", locale),
            url,
        )
        sent += 1

    return f"Просьб о площадке: {len(users)}, о компаниях: {sent}."


def finish_promotions(now: datetime, due: datetime) -> str:
    """promotions:finish (каждый час): истёкшие продвижения — завершить, слоты свободны."""
    from savdex.payments import periods

    return f"Завершено продвижений: {periods.finish_promotions(now)}."


def reset_billing_periods(now: datetime, due: datetime) -> str:
    """billing:reset-periods (00:30): счета на продление, конец подписок, сброс лимитов."""
    from savdex.payments import periods

    issued, expired, wallets = periods.reset_periods(now)

    return (
        f"Выставлено счетов на продление: {issued}. Закрыто подписок: {expired}. "
        f"Сброшено кошельков: {wallets}."
    )


def refresh_rates(now: datetime, due: datetime) -> str:
    """cbu-rates:refresh (каждые четыре часа): курсы ЦБ заранее, а не первым посетителем."""
    from savdex.web.currency import refresh

    return "Курсы ЦБ обновлены." if refresh() else "Курсы ЦБ: ЦБ недоступен, остались прежние."


def probe_uzum(now: datetime, due: datetime) -> str:
    """uzum-probe (каждый час): доступен ли Uzum Checkout и приняты ли ключи."""
    import logging

    from savdex.payments.uzum import UzumConfig, probe

    config = UzumConfig.from_env()

    if not config.enabled or not config.checkout:
        return "Uzum Checkout выключен — прозвон не нужен."

    result = probe(config)
    log = logging.getLogger("savdex.payments")

    if result.ok:
        log.info("payment.uzum.probe_ok: %s", result.message)
    else:
        log.error("payment.uzum.probe_failed: %s", result.message)

    return f"Uzum: {'доступен' if result.ok else 'СБОЙ'} — {result.message}"


JOBS: tuple[Job, ...] = (
    Job("ratings_recalculate", time(3, 0), recalculate_ratings),
    Job("audience_views_prune", time(4, 0), prune_audience_views),
    Job("expire_listings", time(6, 0), expire_listings),
    Job("expire_tenders", time(0, 5), expire_tenders, every=1),
    Job("reviews_ask", time(6, 0), ask_for_reviews),
    # Деньги (шаг 72) и курсы с прозвоном (шаг 71) — вместо routes/console.php
    Job("billing_reset_periods", time(0, 30), reset_billing_periods),
    Job("promotions_finish", time(0, 0), finish_promotions, every=1),
    Job("cbu_rates", time(0, 0), refresh_rates, every=4),
    Job("uzum_probe", time(0, 0), probe_uzum, every=1),
)


def job(name: str) -> Job:
    for candidate in JOBS:
        if candidate.name == name:
            return candidate

    raise KeyError(name)


# ── Пройденные дни ───────────────────────────────────────────────────


def state_path() -> Path:
    configured = os.environ.get("SAVDEX_SCHEDULE_STATE")

    if configured:
        return Path(configured)

    return Path(settings.LARAVEL_ROOT) / "storage/app/schedule.json"


def load() -> dict[str, str]:
    try:
        data = json.loads(state_path().read_text())
    except (OSError, ValueError):
        return {}

    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def remember(name: str, day: date | str) -> None:
    state = load()
    state[name] = day if isinstance(day, str) else day.isoformat()
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True))


def adopt(now: datetime) -> None:
    """
    Суточные задачи без записи, чей час сегодня уже прошёл, — сделаны
    Laravel. Повторяющиеся (раз в час, раз в четыре часа) безвредно
    повторить: первый проход — сразу.
    """
    state = load()

    for item in JOBS:
        if item.every is None and item.name not in state and now >= item.due(now):
            remember(item.name, now.date())


def pending(now: datetime) -> list[Job]:
    """Задачи, чей назначенный момент настал, а пройден ещё не был."""
    state = load()

    return [
        item
        for item in JOBS
        if now >= item.due(now) and state.get(item.name) != item.mark(item.due(now))
    ]
