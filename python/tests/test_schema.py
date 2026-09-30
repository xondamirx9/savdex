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

from savdex import schema

from .pg_admin import PYTHON, АДРЕС, КОРЕНЬ, ОКРУЖЕНИЕ, нужна_база, свежая_база

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
