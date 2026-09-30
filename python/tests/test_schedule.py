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
import time
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
        "App\\Models\\Company::factory()->count(4)->create(); echo 'ok';",
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


#: Суточные задачи, которые Laravel делал раньше Django
ДНЕВНЫЕ = {"audience_views_prune", "expire_listings", "ratings_recalculate", "reviews_ask"}


def test_первый_запуск_после_часа_день_пропускает(компании, tmp_path):
    now = datetime.now(UTC)

    if now.hour < 6:
        pytest.skip("проверка для времени после 06:00 UTC")

    просмотры(компании)
    state = tmp_path / "state"

    # Цикл без конца: ждём, пока он отметит задачи дня (запуск Django
    # под нагрузкой — секунды), и останавливаем
    loop = subprocess.Popen(
        [sys.executable, "manage.py", "schedule", "--every", "1"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "SAVDEX_SCHEDULE_STATE": str(state)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        for _ in range(120):
            if state.exists() and set(json.loads(state.read_text() or "{}")) >= ДНЕВНЫЕ:
                break

            time.sleep(0.5)

        # Второй проход цикла ничего не меняет
        time.sleep(2)
    finally:
        loop.terminate()
        loop.wait(timeout=10)

    # Суточные задачи дня отмечены пройденными, а не выполнены второй раз
    # (повторяющиеся — раз в час и т. п. — проходят сразу, их безвредно повторить)
    отмечено = json.loads(state.read_text())
    assert {k: v for k, v in отмечено.items() if k in ДНЕВНЫЕ} == {
        "audience_views_prune": now.date().isoformat(),
        "expire_listings": now.date().isoformat(),
        "ratings_recalculate": now.date().isoformat(),
        "reviews_ask": now.date().isoformat(),
    }
    assert sql("select count(*) from audience_views") == [(5,)]


def рейтинги(компании: list[int]) -> None:
    sql(
        "update companies set deleted_at = null, rating = 0, reviews_count = 0, "
        "search_text = 'stale', updated_at = '2026-01-01 00:00:00'"
    )
    sql("truncate reviews restart identity cascade")
    a, b, c, d = компании
    # (о ком, от кого, оценка, статус)
    for company, author, rating, status in (
        (a, b, 5, "published"),
        (a, c, 4, "published"),
        (a, d, 1, "moderation"),
        (b, a, 3, "published"),
        (d, a, 5, "published"),
        (d, b, 5, "published"),
    ):
        sql(
            "insert into reviews (company_id, author_company_id, rating, body, status, "
            "created_at, updated_at) values (%s, %s, %s, 'Отзыв', %s, now(), now())",
            [company, author, rating, status],
        )
    # Удалённую компанию Laravel не пересчитывает (SoftDeletes)
    sql("update companies set deleted_at = now() where id = %s", [d])


def рейтинги_снимок() -> list[tuple]:
    return sql(
        "select id, rating::text, reviews_count, search_text, "
        "updated_at > '2026-01-01 00:00:00' from companies order by id"
    )


def test_рейтинги_как_у_laravel(компании, tmp_path):
    рейтинги(компании)
    php(
        "Illuminate\\Support\\Facades\\Artisan::call('ratings:recalculate'); echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    л = рейтинги_снимок()

    рейтинги(компании)
    вывод = schedule("--once", "ratings_recalculate", state=tmp_path / "state")
    д = рейтинги_снимок()

    assert д == л, (д, л)
    # Среднее по площадке — (5 + 4 + 3 + 5 + 5) / 5 = 4,4: у a (5×4,4+9)/7
    assert д[0][1:3] == ("4.43", 2) and д[2][1:3] == ("0.00", 0)
    assert "Пересчитано компаний: 3." in вывод


def test_список_задач(компании, tmp_path):
    вывод = schedule("--list", state=tmp_path / "state")

    assert "ratings_recalculate\t03:00" in вывод
    assert "audience_views_prune\t04:00" in вывод and "expire_listings\t06:00" in вывод
    assert "reviews_ask\t06:00" in вывод
