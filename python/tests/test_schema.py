"""
Шаг 73: схема базы без PHP — manage.py schema на пустой базе даёт ровно
то, что оставляют миграции Laravel (migrate:fresh): таблицы, индексы,
строки миграций и права роли savdex_django. После неё php artisan migrate
ничего не делает. Снимок savdex/bootstrap/ не отстал от миграций.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from savdex import schema

from .pg_admin import PYTHON, АДРЕС, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

ВЛАДЕЛЕЦ = {**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)}


#: Строки, которые заводят сами миграции, несут время их выполнения
ВРЕМЯ = re.compile(r"'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?'")


def без_времени(text: str) -> str:
    return ВРЕМЯ.sub("'<время>'", text)


def дамп(*args: str) -> str:
    return без_времени(schema._pg_dump(АДРЕС, *args))


def manage(*args: str) -> str:
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=PYTHON,
        env=ВЛАДЕЛЕЦ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def artisan(*args: str) -> str:
    return subprocess.run(
        ["php", "artisan", *args, "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_снимок_не_отстал(tmp_path: Path):
    свежая_база()
    subprocess.run(
        [
            sys.executable, "-c",
            "import django; django.setup(); from pathlib import Path; from savdex import schema; "
            f"schema.export(directory=Path({str(tmp_path)!r}))",
        ],
        cwd=PYTHON,
        env={**ВЛАДЕЛЕЦ, "DJANGO_SETTINGS_MODULE": "savdex.settings"},
        check=True,
        capture_output=True,
    )  # fmt: skip

    for name in ("baseline.sql", "grants.sql"):
        assert без_времени((tmp_path / name).read_text()) == без_времени(
            (schema.DIRECTORY / name).read_text()
        ), f"Миграции Laravel изменились, снимок {name} — нет: manage.py schema --export"


def test_пустая_база_как_после_миграций():
    свежая_база()
    л_схема, л_права = дамп("--no-privileges", "--inserts"), дамп("--schema-only")

    artisan("db:wipe")
    assert manage("schema", "--status").strip() == "empty"
    assert "создана" in manage("schema")

    assert дамп("--no-privileges", "--inserts") == л_схема
    assert дамп("--schema-only") == л_права
    assert manage("schema", "--status").strip() == "ready"
    # Снимок несёт таблицу migrations целиком — Laravel нечего применять
    assert "Nothing to migrate" in artisan("migrate")
    # Повторный запуск базу не трогает
    assert "не пустая" in manage("schema")


def test_миграции_sql_один_раз(tmp_path: Path):
    """Этап 8: новые изменения схемы — файлы SQL, каждый один раз."""
    свежая_база()
    (tmp_path / "2099_01_02_000000_second.sql").write_text(
        "alter table stage8_probe add column note text;"
    )
    (tmp_path / "2099_01_01_000000_first.sql").write_text(
        "create table stage8_probe (id bigserial primary key);\n"
        "do $$ begin\n"
        "    if exists (select from pg_roles where rolname = 'savdex_django') then\n"
        "        grant select, insert on stage8_probe to savdex_django;\n"
        "    end if;\n"
        "end $$;\n"
    )
    (tmp_path / "README.md").write_text("не миграция")
    env = {**ВЛАДЕЛЕЦ, "SAVDEX_MIGRATIONS_DIR": str(tmp_path)}

    def schema_с_миграциями() -> str:
        return subprocess.run(
            [sys.executable, "manage.py", "schema"],
            cwd=PYTHON, env=env, capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip

    вывод = schema_с_миграциями()
    assert вывод.index("first") < вывод.index("second")

    строки = sql(
        "select migration, batch from migrations where migration like %s order by id", ["2099_%"]
    )
    assert [r[0] for r in строки] == ["2099_01_01_000000_first", "2099_01_02_000000_second"]
    assert строки[0][1] < строки[1][1]
    колонки = sql(
        "select column_name from information_schema.columns "
        "where table_name = 'stage8_probe' order by ordinal_position"
    )
    assert колонки == [("id",), ("note",)]
    assert sql("select has_table_privilege('savdex_django', 'stage8_probe', 'insert')") == [(True,)]

    # Второй запуск — ничего нового
    assert "Миграция" not in schema_с_миграциями()

    # Сломанная миграция откатывается целиком и не записывается
    (tmp_path / "2099_01_03_000000_broken.sql").write_text(
        "create table stage8_half (id int); select * from нет_такой;"
    )
    with pytest.raises(subprocess.CalledProcessError):
        schema_с_миграциями()
    assert sql("select to_regclass('stage8_half') is null") == [(True,)]
    assert sql("select count(*) from migrations where migration like %s", ["%broken"]) == [(0,)]
