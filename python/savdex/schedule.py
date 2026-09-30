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


JOBS: tuple[Job, ...] = (
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
