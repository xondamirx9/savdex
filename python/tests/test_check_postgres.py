"""
Проверка базы против настоящего PostgreSQL.

SQLite здесь не подходит: проверяются ровно те вещи, которых у него
нет, — `show server_version`, `has_table_privilege`, права ролей.

Адрес берётся из SAVDEX_TEST_PG_URL. В CI его даёт служебный
контейнер, у разработчика — локальный сервер. Без переменной проверки
пропускаются: поднятая база не должна быть условием для того, чтобы
прогнать остальные семьдесят.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import psycopg
import pytest
from django.conf import settings
from django.db import connections

from savdex.checks import NOTE, OK, inspect

АДРЕС = os.environ.get("SAVDEX_TEST_PG_URL")

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_TEST_PG_URL — проверка требует настоящего PostgreSQL",
)

# Урезанный слепок схемы Laravel: столько, сколько нужно, чтобы
# пройти по всем ветвям отчёта. Гонять сюда все 74 миграции значило бы
# требовать установленного PHP ради проверки Python-кода
СХЕМА = """
drop schema public cascade;
create schema public;

create table migrations (id serial primary key, migration varchar, batch int);
insert into migrations (migration, batch) values
    ('2026_07_28_100000_create_countries_and_cities_tables', 1),
    ('2026_09_18_150000_unique_company_wide_review', 2);

create table companies (id serial primary key, name varchar);
create table listings (id serial primary key, title varchar);
"""


def _строки(отчёт) -> dict[str, tuple[str, str]]:
    """Отчёт в вид «что → (значок, состояние)» — так проверки читаются."""
    return {what: (mark, value) for mark, what, value in отчёт.rows}


@pytest.fixture
def чистая_база():
    """
    Схема пересоздаётся под каждую проверку.

    `drop schema public cascade` стирает всё, поэтому только в базе,
    названной проверочной: переменную окружения легко перепутать,
    и цена ошибки — боевая база.
    """
    if "test" not in urlparse(АДРЕС).path.lstrip("/"):
        pytest.fail(
            "SAVDEX_TEST_PG_URL ведёт в базу без «test» в имени. "
            "Проверка стирает схему целиком — отказываюсь."
        )

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        соединение.execute(СХЕМА)

    yield


@pytest.fixture
def подключение(чистая_база, django_db_blocker):
    """
    Соединение Django с проверочной базой.

    Отдельное подключение, а не подмена основного: предохранители
    вешаются на каждое соединение, и проверять их обход на том же,
    которым идёт настройка, было бы нечестно.
    """
    import dj_database_url

    settings.DATABASES["проверка"] = dict(dj_database_url.parse(АДРЕС))

    connections.settings = connections.configure_settings(settings.DATABASES)

    # Запрет pytest-django снимается точечно: он бережёт от похода
    # в базу там, где его не ждали, а здесь база и есть предмет проверки
    try:
        with django_db_blocker.unblock():
            yield connections["проверка"]
    finally:
        connections["проверка"].close()
        del connections["проверка"]
        del settings.DATABASES["проверка"]
        connections.settings = connections.configure_settings(settings.DATABASES)


class TestОтчёт:
    def test_база_описана(self, подключение):
        строки = _строки(inspect(подключение))

        значок, значение = строки["Соединение"]

        assert значок == OK
        assert значение.startswith("PostgreSQL 1")

    def test_схема_посчитана(self, подключение):
        """Три таблицы: migrations, companies, listings."""
        assert _строки(inspect(подключение))["Схема"] == (OK, "3 таблицы")

    def test_счёт_таблиц_совпадает_с_базой(self, подключение):
        """
        Сторожевая проверка.

        Первая версия переноса пробовала права созданием временной
        таблицы — и та доживала до подсчёта схемы в том же соединении,
        давая на одну больше, чем PHP-версия. Само число ничем
        не выдавало подделку; нашлось только сверкой двух выводов.
        """
        отчёт = inspect(подключение)

        with подключение.cursor() as курсор:
            курсор.execute(
                "select count(*) from information_schema.tables where table_schema = 'public'"
            )
            настоящих = курсор.fetchone()[0]

        assert _строки(отчёт)["Схема"][1].startswith(f"{настоящих} ")

    def test_видна_последняя_миграция_laravel(self, подключение):
        """
        Главный признак «Django смотрит не туда».

        Устаревшая копия базы проходит все остальные проверки: она
        доступна, схема на месте, данные есть. Расхождение видно
        только по хвосту списка миграций.
        """
        значок, значение = _строки(inspect(подключение))["Миграции Laravel"]

        assert значок == OK
        assert "2 применено" in значение
        assert "2026_09_18_150000_unique_company_wide_review" in значение

    def test_пустая_база_замечена_но_не_блокирует(self, подключение):
        """Для только что созданной базы пустота — норма, а не сбой."""
        отчёт = inspect(подключение)

        assert _строки(отчёт)["Данные"] == (NOTE, "база пуста")
        assert отчёт.blocked is False

    def test_данные_посчитаны_со_склонением(self, подключение):
        with psycopg.connect(АДРЕС, autocommit=True) as соединение:
            соединение.execute("insert into companies (name) values ('Цемент Трейд')")
            соединение.execute("insert into listings (title) values ('Цемент М400'), ('Песок')")

        assert _строки(inspect(подключение))["Данные"] == (
            OK,
            "1 компания, 2 объявления",
        )


class TestПраваРоли:
    def test_право_записи_замечено(self, подключение):
        """
        У обычной роли право записи есть, и это замечание, а не норма.

        На этапах 0 и 1 Django нужно только чтение: запись мимо правил
        Eloquent расходит данные молча.
        """
        значок, значение = _строки(inspect(подключение))["Запись"]

        assert значок == NOTE
        assert "INSERT" in значение

    def test_чтение_разрешено(self, подключение):
        assert _строки(inspect(подключение))["Чтение"] == (OK, "разрешено")

    def test_роль_без_записи_проходит_как_надо(self, подключение):
        """
        Ровно то состояние, к которому ведёт этап 0.

        Роль заводится настоящая, а не подделанная заглушкой: смысл
        проверки в том, что отчёт правильно читает права PostgreSQL.
        """
        with psycopg.connect(АДРЕС, autocommit=True) as соединение:
            соединение.execute("drop role if exists savdex_readonly")
            соединение.execute("create role savdex_readonly")
            соединение.execute("grant select on all tables in schema public to savdex_readonly")
            соединение.execute("grant usage on schema public to savdex_readonly")

        with подключение.cursor() as курсор:
            курсор.execute("set role savdex_readonly")

            try:
                отчёт = inspect(подключение)
            finally:
                курсор.execute("reset role")

        значок, значение = _строки(отчёт)["Запись"]

        assert значок == OK
        assert "только на чтение" in значение
