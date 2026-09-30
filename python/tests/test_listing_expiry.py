"""
Этап 4: снятие истёкших объявлений на Django (manage.py expire_listings)
вместо расписания Laravel listings:expire.

На одних данных команда Django оставляет ту же базу, что команда
Laravel: истёкшие активные — «истёкшие» с пересчитанным search_text,
компании — событие в ленте и уведомление каждому сотруднику (удалённой
компании — нет), за три дня — предупреждение; архивные, удалённые и
живые объявления не трогаются. Повторный проход ничего не повторяет,
первый запуск после 06:00 свой день пропускает.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def компании() -> dict[str, int]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=CategorySeeder", "--force"],
        cwd=str(КОРЕНЬ),
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "foreach (['a', 'gone'] as $s) { $c = App\\Models\\Company::factory()->create("
        "['slug' => $s]); App\\Models\\User::factory()->count(2)->create("
        "['company_id' => $c->id]); } echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    return {r[0]: r[1] for r in sql("select slug, id from companies")}


def подготовка(компании: dict[str, int]) -> None:
    sql("update companies set deleted_at = null")
    sql("truncate listings, activity_events, user_notifications restart identity cascade")
    a, gone = компании["a"], компании["gone"]
    строки = [
        # (компания, заголовок, статус, срок от «сейчас», удалено)
        (a, "Цемент М500", "active", "-1 hour", False),
        (a, "Арматура А500С", "active", "-3 days", False),
        (gone, "Щебень гранитный", "active", "-1 day", False),
        (a, "Кирпич облицовочный", "archived", "-2 days", False),
        (a, "Песок речной", "active", "-5 days", True),
        (a, "Газоблок D500", "active", "+3 days 12 hours", False),
        (gone, "Доска обрезная", "active", "+3 days 12 hours", False),
        (a, "Утеплитель", "active", "+10 days", False),
        (a, "Бессрочное", "active", None, False),
    ]
    code = []

    for company, title, status, shift, trashed in строки:
        expires = f"now()->modify('{shift}')" if shift else "null"
        code.append(
            f"$l = App\\Models\\Listing::factory()->create(['company_id' => {company}, "
            f"'title' => '{title}', 'description' => 'Описание: {title}', "
            f"'status' => '{status}', 'expires_at' => {expires}]);"
            + ("$l->delete();" if trashed else "")
        )

    php("".join(code) + "echo 'ok';", БЕЗ_ПЕРЕВОДА)
    # Устаревший индекс поиска: сохранение модели обязано его пересчитать
    sql("update listings set search_text = 'stale' where title = 'Цемент М500'")
    sql("update companies set deleted_at = now() where id = %s", [gone])


def снимок() -> dict[str, Any]:
    return {
        "listings": sql(
            "select title, status, search_text, deleted_at is not null from listings order by id"
        ),
        "events": sorted(
            sql("select company_id, type, tone, message, url from activity_events")
        ),
        "notifications": sorted(
            sql(
                "select user_id, company_id, type, title, body, tone, url, read_at "
                "from user_notifications"
            ),
            key=repr,
        ),
    }


def django(*args: str, state: Path) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "expire_listings", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "LISTINGS_EXPIRE_STATE": str(state)},
        capture_output=True,
        text=True,
        check=True,
    )

    return out.stdout


def test_как_у_laravel(компании, tmp_path):
    подготовка(компании)
    php("Illuminate\\Support\\Facades\\Artisan::call('listings:expire'); echo 'ok';", БЕЗ_ПЕРЕВОДА)
    л = снимок()

    подготовка(компании)
    вывод = django("--once", state=tmp_path / "state")
    д = снимок()

    assert д == л, (д, л)
    assert "Снято с публикации: 3. Предупреждений отправлено: 2." in вывод
    # Проверка самих данных, а не только равенства с Laravel
    статусы = {title: status for title, status, *_ in д["listings"]}
    assert статусы["Цемент М500"] == "expired" and статусы["Щебень гранитный"] == "expired"
    assert статусы["Кирпич облицовочный"] == "archived" and статусы["Песок речной"] == "active"
    assert статусы["Газоблок D500"] == "active" and статусы["Бессрочное"] == "active"
    assert "stale" not in {text for _, _, text, _ in д["listings"]}
    # Две компании-снятия и одно предупреждение — только у живой компании
    assert len(д["events"]) == 3 and len(д["notifications"]) == 6


def test_день_не_повторяется(компании, tmp_path):
    from datetime import UTC, datetime

    state = tmp_path / "state"
    state.write_text(datetime.now(UTC).date().isoformat())
    подготовка(компании)

    # Бесконечный режим с проходом сегодня уже сделанным: одна проверка
    # и ни одной записи. Прерываем через таймаут — это цикл
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(
            [sys.executable, "manage.py", "expire_listings", "--every", "1"],
            cwd=PYTHON,
            env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "LISTINGS_EXPIRE_STATE": str(state)},
            capture_output=True,
            timeout=4,
        )

    assert sql("select count(*) from listings where status = 'expired'") == [(0,)]
    assert sql("select count(*) from user_notifications") == [(0,)]
