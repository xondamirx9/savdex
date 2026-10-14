"""
Демо-наполнение тестового сервера (savdex/demo.py, manage.py demo):
компании с владельцами, объявлениями и отзывами на пустой базе со
справочниками; повторный запуск ничего не дублирует; на боевом — отказ;
почты — только в зоне .test, куда сайт писем не шлёт.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from savdex import demo
from savdex.web import mail

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база


def manage(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=PYTHON,
        # Справочники и демо-данные пишет владелец базы — как разовый
        # запуск migrate на сервере
        env={
            **ОКРУЖЕНИЕ,
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "PYTHONPATH": str(PYTHON),
            "APP_ENV": "staging",
            **env,
        },
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def база() -> None:
    свежая_база()
    seed = manage("seed")
    assert seed.returncode == 0, seed.stderr[-2000:]


def test_демо_данные(база):
    итог = manage("demo")
    assert итог.returncode == 0, итог.stderr[-3000:]
    assert "компаний 24" in итог.stdout

    [(компаний, видимых)] = sql(
        "select count(*), count(*) filter (where status = 'active' and deleted_at is null) "
        "from companies where source_note = %s",
        [demo.MARK],
    )
    assert компаний == видимых == len(demo.COMPANIES)

    # У каждой — владелец с подтверждённой почтой-заглушкой
    владельцы = sql(
        "select u.email, u.email_verified_at is not null, u.company_role from users u "
        "join companies c on c.id = u.company_id where c.source_note = %s",
        [demo.MARK],
    )
    assert len(владельцы) == len(demo.COMPANIES)
    assert all(
        mail.undeliverable(email) and ok and role == "owner" for email, ok, role in владельцы
    )
    [(почт_компаний,)] = sql(
        "select count(*) from companies where source_note = %s and email not like %s",
        [demo.MARK, f"%@%.{demo.EMAIL_DOMAIN}"],
    )
    assert почт_компаний == 0

    # Объявления опубликованы, с адресом и поиском; есть и закупки
    объявления = sql(
        "select l.type, l.slug is not null, l.search_text <> '', "
        "l.published_at < now(), l.expires_at > now() from listings l "
        "join companies c on c.id = l.company_id where c.source_note = %s",
        [demo.MARK],
    )
    assert len(объявления) >= 50
    assert all(slug and поиск and вышло and живо for _, slug, поиск, вышло, живо in объявления)
    assert {вид for вид, *_ in объявления} == {"supply", "demand"}

    # Отзывы опубликованы, рейтинг пересчитан
    [(отзывов,)] = sql("select count(*) from reviews where status = 'published'")
    assert отзывов == len(demo.REVIEWS)
    [(с_рейтингом,)] = sql(
        "select count(*) from companies where source_note = %s and reviews_count > 0 "
        "and rating > 0",
        [demo.MARK],
    )
    assert с_рейтингом == len({target for target, *_ in demo.REVIEWS})

    # Повторный запуск ничего не дублирует
    ещё = manage("demo")
    assert ещё.returncode == 0 and "уже есть" in ещё.stdout
    [(всего,)] = sql("select count(*) from companies where source_note = %s", [demo.MARK])
    assert всего == len(demo.COMPANIES)


def test_на_боевом_отказ(база):
    итог = manage("demo", APP_ENV="production")

    assert итог.returncode != 0
    assert "Боевой сайт" in итог.stderr
