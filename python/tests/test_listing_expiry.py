"""
Этап 4: снятие истёкших объявлений на Django (задача expire_listings в
manage.py schedule) вместо расписания Laravel listings:expire.

Проверки Django: истёкшие активные — «истёкшие» с пересчитанным search_text,
компании — событие в ленте и уведомление каждому сотруднику (удалённой
компании — нет), за три дня — предупреждение; архивные, удалённые и
живые объявления не трогаются. Повторный проход ничего не повторяет,
первый запуск после 06:00 свой день пропускает.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from .factories import Выражение, компания, объявление, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база


@pytest.fixture(scope="module")
def компании() -> dict[str, int]:
    свежая_база()

    for slug in ("a", "gone"):
        c = компания(slug=slug)
        пользователь(company_id=c)
        пользователь(company_id=c)

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

    for company, title, status, shift, trashed in строки:
        объявление(
            company_id=company,
            title=title,
            description=f"Описание: {title}",
            status=status,
            expires_at=Выражение(f"now() + interval '{shift}'") if shift else None,
            **({"deleted_at": Выражение("now()")} if trashed else {}),
        )

    # Устаревший индекс поиска: сохранение модели обязано его пересчитать
    sql("update listings set search_text = 'stale' where title = 'Цемент М500'")
    sql("update companies set deleted_at = now() where id = %s", [gone])


def снимок() -> dict[str, Any]:
    return {
        "listings": sql(
            "select title, status, search_text, deleted_at is not null from listings order by id"
        ),
        "events": sorted(sql("select company_id, type, tone, message, url from activity_events")),
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
        [sys.executable, "manage.py", "schedule", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "SAVDEX_SCHEDULE_STATE": str(state)},
        capture_output=True,
        text=True,
        check=True,
    )

    return out.stdout


def test_снятие_истёкших(компании, tmp_path):
    from savdex.web.search_text import index

    подготовка(компании)
    вывод = django("--once", "expire_listings", state=tmp_path / "state")
    д = снимок()

    assert "Снято с публикации: 3. Предупреждений отправлено: 2." in вывод
    статусы = {title: status for title, status, *_ in д["listings"]}
    assert статусы == {
        "Цемент М500": "expired",
        "Арматура А500С": "expired",
        "Щебень гранитный": "expired",
        "Кирпич облицовочный": "archived",
        "Песок речной": "active",
        "Газоблок D500": "active",
        "Доска обрезная": "active",
        "Утеплитель": "active",
        "Бессрочное": "active",
    }
    # Сохранение пересчитало устаревший индекс поиска
    поиск = {title: text for title, _, text, _ in д["listings"]}
    assert поиск["Цемент М500"] == index("Цемент М500 Описание: Цемент М500")

    # Лента и уведомления — только у живой компании: два снятия и одно
    # предупреждение, уведомление каждому из двух сотрудников
    a = компании["a"]
    снято = "снято: истёк срок размещения"
    assert д["events"] == [
        (
            a,
            "listing_expiring",
            "warning",
            f"Объявление «Арматура А500С» {снято}",
            "/cabinet/listings?status=expired",
        ),
        (
            a,
            "listing_expiring",
            "warning",
            "Объявление «Газоблок D500» истекает через 3 дня",
            "/cabinet/listings",
        ),
        (
            a,
            "listing_expiring",
            "warning",
            f"Объявление «Цемент М500» {снято}",
            "/cabinet/listings?status=expired",
        ),
    ]
    сотрудники = {uid for (uid,) in sql("select id from users where company_id = %s", [a])}
    assert len(д["notifications"]) == 6
    assert {n[0] for n in д["notifications"]} == сотрудники
    assert {n[1] for n in д["notifications"]} == {a}
    assert all(n[7] is None for n in д["notifications"])
    assert sorted({(n[3], n[4]) for n in д["notifications"]}) == [
        (
            f"Объявление «Арматура А500С» {снято}",
            "Продлите его в кабинете — показы возобновятся сразу.",
        ),
        (
            "Объявление «Газоблок D500» истекает через 3 дня",
            "После истечения показы прекращаются. Продлите в один клик.",
        ),
        (
            f"Объявление «Цемент М500» {снято}",
            "Продлите его в кабинете — показы возобновятся сразу.",
        ),
    ]


def test_день_не_повторяется(компании, tmp_path):
    from datetime import UTC, datetime

    state = tmp_path / "state"
    state.write_text(json.dumps({"expire_listings": datetime.now(UTC).date().isoformat()}))
    подготовка(компании)

    # Бесконечный режим с проходом сегодня уже сделанным: одна проверка
    # и ни одной записи. Прерываем через таймаут — это цикл
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(
            [sys.executable, "manage.py", "schedule", "--every", "1"],
            cwd=PYTHON,
            env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "SAVDEX_SCHEDULE_STATE": str(state)},
            capture_output=True,
            timeout=4,
        )

    assert sql("select count(*) from listings where status = 'expired'") == [(0,)]
    assert sql("select count(*) from user_notifications") == [(0,)]
