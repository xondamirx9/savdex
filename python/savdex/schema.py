"""
Схема базы без PHP (шаг 73): снимок того, что оставляют миграции Laravel
на пустой базе, — savdex/bootstrap/baseline.sql (таблицы, индексы и строки,
которые заводят сами миграции, вместе с таблицей migrations), и права
роли savdex_django из миграций grant_django_* — savdex/bootstrap/grants.sql.

  manage.py schema            пустая база — создать схему из снимка
                              (и выдать права роли, если она есть);
                              затем — новые миграции из
                              savdex/bootstrap/migrations
  manage.py schema --status   «empty» или «ready»
  manage.py schema --export   снять снимок с базы после migrate:fresh

Таблица migrations в снимке полная, поэтому php artisan migrate после
неё ничего не делает. Что снимок не отстал от миграций Laravel, проверяет
tests/test_schema.py.

С этапа 8 Laravel в образе нет, и изменения схемы — файлы SQL в
savdex/bootstrap/migrations/<дата>_<что>.sql (имя — как у миграций
Laravel, по нему же порядок). Каждый применяется один раз, целиком
в одной транзакции, и записывается в ту же таблицу migrations — так
php artisan migrate на копии с Laravel их не повторит. Права роли
savdex_django на новые таблицы файл выдаёт сам, если роль есть:

  do $$ begin
      if exists (select from pg_roles where rolname = 'savdex_django') then
          grant select, insert, update, delete on новая_таблица to savdex_django;
      end if;
  end $$;

Правило 4.2 (DDL — не из кода сайта) предохранитель держит по-прежнему:
снимок и миграции применяются в обход обёртки соединения, только отсюда.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from django.db import connection, transaction

DIRECTORY = Path(__file__).resolve().parent / "bootstrap"
BASELINE = DIRECTORY / "baseline.sql"
MIGRATIONS = DIRECTORY / "migrations"
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


def _migrations_directory() -> Path:
    configured = os.environ.get("SAVDEX_MIGRATIONS_DIR")

    return Path(configured) if configured else MIGRATIONS


def pending() -> list[Path]:
    """Файлы миграций, которых ещё нет в таблице migrations, по порядку имён."""
    files = sorted(_migrations_directory().glob("*.sql"))

    if not files:
        return []

    with connection.cursor() as cursor:
        cursor.execute("select migration from migrations")
        done = {row[0] for row in cursor.fetchall()}

    return [path for path in files if path.stem not in done]


def migrate() -> list[str]:
    """Применить новые миграции: каждую — в своей транзакции, с записью в migrations."""
    applied: list[str] = []

    for path in pending():
        sql = path.read_text(encoding="utf-8")

        with transaction.atomic(), connection.cursor() as cursor:
            raw = cursor.cursor  # в обход предохранителя, как create()
            raw.execute("select coalesce(max(batch), 0) + 1 from migrations")
            row = raw.fetchone()
            batch = row[0] if row else 1
            raw.execute(sql)
            raw.execute(
                "insert into migrations (migration, batch) values (%s, %s)", [path.stem, batch]
            )

        applied.append(path.stem)

    return applied


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
