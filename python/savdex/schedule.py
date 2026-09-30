"""
Ежедневные задачи Django — вместо расписания Laravel (routes/console.php)
для таблиц, хозяин которых перешёл к Django.

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
from datetime import date, datetime, time
from pathlib import Path

from django.conf import settings
from django.db import connection

from savdex.guards import allowed_writes


@dataclass(frozen=True)
class Job:
    name: str
    #: dailyAt у Laravel
    at: time
    #: (сейчас, назначенный момент сегодня) → строка для журнала
    run: Callable[[datetime, datetime], str]

    def due(self, now: datetime) -> datetime:
        return datetime.combine(now.date(), self.at)


# ── Задачи ───────────────────────────────────────────────────────────


def expire_listings(now: datetime, due: datetime) -> str:
    """listings:expire (06:00): снять истёкшие объявления, предупредить за три дня."""
    from savdex.web import listing_expiry

    expired, warned = listing_expiry.run(now, anchor=due)

    return f"Снято с публикации: {expired}. Предупреждений отправлено: {warned}."


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


JOBS: tuple[Job, ...] = (
    Job("ratings_recalculate", time(3, 0), recalculate_ratings),
    Job("audience_views_prune", time(4, 0), prune_audience_views),
    Job("expire_listings", time(6, 0), expire_listings),
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


def remember(name: str, day: date) -> None:
    state = load()
    state[name] = day.isoformat()
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True))


def adopt(now: datetime) -> None:
    """Задачи без записи, чей час сегодня уже прошёл, — сделаны Laravel."""
    state = load()

    for item in JOBS:
        if item.name not in state and now >= item.due(now):
            remember(item.name, now.date())


def pending(now: datetime) -> list[Job]:
    """Задачи, чей час сегодня настал, а день ещё не пройден."""
    state = load()

    return [
        item
        for item in JOBS
        if now >= item.due(now) and state.get(item.name) != now.date().isoformat()
    ]
