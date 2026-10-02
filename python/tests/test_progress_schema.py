"""
Карта таблиц хода переноса совпадает с настоящей схемой базы.

Новая таблица Laravel без места в карте не попала бы ни в один этап —
и страница хода переноса молча считала бы без неё.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
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


def test_главная_админки_без_хода_переноса():
    """Перенос закончен: на главной админки хода переноса больше нет."""
    свежая_база()
    _, главная = django(сотрудник("content_manager"), ("get", "/py/admin/", None))

    assert главная["status"] == 200
    assert "Ход переноса" not in главная["body"]
    assert "Python" not in главная["body"]
