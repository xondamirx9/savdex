"""
Карта таблиц хода переноса совпадает с настоящей схемой базы.

Новая таблица Laravel без места в карте не попала бы ни в один этап —
и страница хода переноса молча считала бы без неё.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from savdex import progress

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база


def test_карта_совпадает_со_схемой():
    свежая_база()
    real = {t for (t,) in sql("select tablename from pg_tables where schemaname = 'public'")}
    mapped = set(progress.MOVING) | set(progress.SHARED)

    assert sorted(real - mapped) == [], "таблицы без места в карте переноса"
    assert sorted(mapped - real) == [], "в карте переноса таблицы, которых нет в базе"


def test_ход_переноса_на_главной_админки():
    """Любой сотрудник с доступом к разделам на Python видит ход переноса."""
    свежая_база()
    _, главная = django(сотрудник("content_manager"), ("get", "/py/admin/", None))
    total = progress.summary()

    assert главная["status"] == 200
    assert "Ход переноса на Python" in главная["body"]
    assert f"{total['tables_done']} из {total['tables_total']}" in главная["body"]
    assert "Этап 2. Справочники и содержимое" in главная["body"]
