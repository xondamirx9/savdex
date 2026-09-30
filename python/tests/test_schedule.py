"""
Ежедневные задачи Django (savdex/schedule.py, manage.py schedule).

Чистка «Кто смотрел» (audience-views:prune у Laravel): старше 90 дней —
прочь, остальное — как было; то же, что оставляет запрос Laravel.
Первый запуск после часа задачи день пропускает — его уже сделал
Laravel; пройденный день пишется в файл.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def компании() -> list[int]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->count(2)->create(); echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    return [r[0] for r in sql("select id from companies order by id")]


def просмотры(компании: list[int]) -> None:
    sql("truncate audience_views restart identity")

    for days in (400, 91, 90.9, 89, 1):
        sql(
            "insert into audience_views (target_company_id, viewer_company_id, created_at, "
            "updated_at) values (%s, %s, now() at time zone 'utc' - make_interval(secs => %s), "
            "now())",
            [компании[0], компании[1], days * 86400],
        )


def schedule(*args: str, state: Path, timeout: float | None = None) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "schedule", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "SAVDEX_SCHEDULE_STATE": str(state)},
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )

    return out.stdout


def test_чистка_как_у_laravel(компании, tmp_path):
    просмотры(компании)
    php(
        "App\\Models\\AudienceView::query()->where('created_at', '<', now()->subDays(90))"
        "->delete(); echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    л = sql("select id from audience_views order by id")

    просмотры(компании)
    вывод = schedule("--once", "audience_views_prune", state=tmp_path / "state")
    д = sql("select id from audience_views order by id")

    assert д == л == [(4,), (5,)]
    assert "Удалено просмотров: 3." in вывод


def test_первый_запуск_после_часа_день_пропускает(компании, tmp_path):
    now = datetime.now(UTC)

    if now.hour < 6:
        pytest.skip("проверка для времени после 06:00 UTC")

    просмотры(компании)
    state = tmp_path / "state"

    with pytest.raises(subprocess.TimeoutExpired):
        schedule("--every", "1", state=state, timeout=4)

    # Обе задачи дня отмечены пройденными, а не выполнены второй раз
    assert json.loads(state.read_text()) == {
        "audience_views_prune": now.date().isoformat(),
        "expire_listings": now.date().isoformat(),
    }
    assert sql("select count(*) from audience_views") == [(5,)]


def test_список_задач(компании, tmp_path):
    вывод = schedule("--list", state=tmp_path / "state")

    assert "audience_views_prune\t04:00" in вывод and "expire_listings\t06:00" in вывод
