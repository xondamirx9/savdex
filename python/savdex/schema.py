"""
Схема базы без PHP (шаг 73): снимок того, что оставляют миграции Laravel
на пустой базе, — savdex/bootstrap/baseline.sql (таблицы, индексы и строки,
которые заводят сами миграции, вместе с таблицей migrations), и права
роли savdex_django из миграций grant_django_* — savdex/bootstrap/grants.sql.

  manage.py schema            пустая база — создать схему из снимка
                              (и выдать права роли, если она есть);
                              непустую не трогает
  manage.py schema --status   «empty» или «ready»
  manage.py schema --export   снять снимок с базы после migrate:fresh

Таблица migrations в снимке полная, поэтому php artisan migrate после
неё ничего не делает, а новые миграции Laravel (пока он жив) дописываются
как раньше. Что снимок не отстал от миграций, проверяет
tests/test_schema.py. Правило 4.2 (DDL — только Laravel) предохранитель
держит по-прежнему: снимок применяется в обход обёртки соединения, только
на пустой базе.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from django.db import connection, transaction

DIRECTORY = Path(__file__).resolve().parent / "bootstrap"
BASELINE = DIRECTORY / "baseline.sql"
GRANTS = DIRECTORY / "grants.sql"
ROLE = "savdex_django"

#: Строки pg_dump, которые меняются от версии к версии и не нужны
_NOISE = re.compile(r"^(\\restrict .*|\\unrestrict .*|-- Dumped (from|by) .*)$", re.M)


def empty() -> bool:
    """Пустая база — нет таблицы migrations."""
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('migrations') is null")
        row = cursor.fetchone()

    return bool(row[0]) if row else True


def _role_exists() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select count(*) from pg_roles where rolname = %s", [ROLE])
        row = cursor.fetchone()

    return bool(row and row[0])


def create() -> bool:
    """Создать схему на пустой базе. False — база не пустая, ничего не сделано."""
    if not empty():
        return False

    baseline = BASELINE.read_text(encoding="utf-8")
    grants = GRANTS.read_text(encoding="utf-8") if _role_exists() else ""

    with transaction.atomic(), connection.cursor() as cursor:
        raw = cursor.cursor  # в обход предохранителя: DDL — только здесь
        raw.execute(baseline)
        # Снимок сбрасывает search_path на пустой — вернуть обычный
        raw.execute("select pg_catalog.set_config('search_path', '\"$user\", public', false)")

        if grants:
            raw.execute(grants)

    return True


def _pg_dump(url: str, *args: str) -> str:
    out = subprocess.run(
        ["pg_dump", "--no-owner", *args, url], check=True, capture_output=True, text=True
    ).stdout

    return _NOISE.sub("", out)


def export(url: str | None = None, directory: Path = DIRECTORY) -> None:
    """Снимок с базы после migrate:fresh (адрес — DB_URL владельца)."""
    url = url or os.environ["DB_URL"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "baseline.sql").write_text(
        _pg_dump(url, "--no-privileges", "--inserts"), encoding="utf-8"
    )
    grants = [
        line
        for line in _pg_dump(url, "--schema-only").splitlines()
        if line.startswith("GRANT ") and line.endswith(f" TO {ROLE};")
    ]
    (directory / "grants.sql").write_text("\n".join(grants) + "\n", encoding="utf-8")
