"""
Шаг 73: справочники при деплое заводит Django (manage.py seed) вместо
сидеров Laravel — и заводит то же самое.

- снимок savdex/bootstrap/seeds.json не отстал от сидеров Laravel;
- пустая база после manage.py seed --fresh — та же, что после db:seed,
  номер в номер;
- на заполненной базе — как сидеры деплоя: недостающее досоздаётся,
  правки (название страны, выключенная категория, цена тарифа) не
  откатываются, поля категорий возвращаются к снимку.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from savdex import seeds

from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

LARAVEL = {**ОКРУЖЕНИЕ, "MACHINE_TRANSLATION_ENABLED": "false", "QUEUE_CONNECTION": "sync"}


def artisan(*args: str) -> None:
    subprocess.run(
        ["php", "artisan", *args, "--force"], cwd=КОРЕНЬ, env=LARAVEL, check=True,
        capture_output=True,
    )  # fmt: skip


def django(*args: str) -> str:
    # Справочники заводятся владельцем базы, как миграции (DB_URL)
    return subprocess.run(
        [sys.executable, "manage.py", "seed", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def снимок() -> dict[str, Any]:
    итог = {}

    for table in seeds.TABLES:
        rows = sql(f"select row_to_json(t)::text from {table} t order by id")
        итог[table] = [
            {k: v for k, v in json.loads(r[0]).items() if k not in ("created_at", "updated_at")}
            for r in rows
        ]

    return итог


@pytest.fixture(scope="module")
def после_laravel() -> dict[str, Any]:
    свежая_база()
    artisan("db:seed")

    return снимок()


def test_снимок_не_отстал(после_laravel, tmp_path):
    """data.json — то, что сидеры Laravel заводят на пустой базе."""
    путь = tmp_path / "data.json"
    subprocess.run(
        [
            sys.executable, "-c",
            f"import django; django.setup(); from savdex import seeds; "
            f"from pathlib import Path; seeds.export(Path({str(путь)!r}))",
        ],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON),
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
        },
        check=True,
        capture_output=True,
    )  # fmt: skip

    assert json.loads(путь.read_text()) == json.loads(seeds.DATA.read_text()), (
        "Сидеры Laravel заводят не то, что в снимке: manage.py seed --export"
    )


def test_пустая_база_как_db_seed(после_laravel):
    свежая_база()
    вывод = django("--fresh")

    assert снимок() == после_laravel
    assert "countries 33" in вывод and "settings" in вывод


def _правки() -> None:
    sql("update country_translations set name = 'Моя страна' where locale = 'ru' and "
        "country_id = (select id from countries where code = 'kz')")  # fmt: skip
    sql("delete from city_translations where city_id in (select id from cities where slug = "
        "'samarkand')")  # fmt: skip
    sql("delete from cities where slug = 'samarkand'")
    sql("update categories set is_active = false where slug = 'metally'")
    sql("delete from category_translations where category_id in "
        "(select id from categories where slug = 'stanki')")  # fmt: skip
    sql("delete from categories where slug = 'stanki'")
    sql("update category_fields set label = 'Другое имя' where key = 'mark'")
    sql("update plans set price_usd = 99 where code = 'flash'")
    sql("delete from plans where code = 'vip'")
    sql("update settings set value = to_json('Своё'::text) where key = 'site_name'")
    sql("delete from settings where key = 'support_email'")


def test_деплой_на_заполненной_базе(после_laravel):
    свежая_база()
    artisan("db:seed")
    _правки()
    for seeder in ("PlanSeeder", "CategorySeeder", "GeoSeeder", "SettingSeeder"):
        artisan("db:seed", f"--class={seeder}")
    л = снимок()

    свежая_база()
    artisan("db:seed")
    _правки()
    вывод = django()
    д = снимок()

    # Номера досозданных строк зависят от последовательностей — сверяем без них
    def без_номеров(данные: dict[str, Any]) -> dict[str, Any]:
        return {
            t: sorted(
                json.dumps({k: v for k, v in r.items() if k != "id" and not k.endswith("_id")},
                            sort_keys=True, ensure_ascii=False) for r in rows
            )
            for t, rows in данные.items()
        }  # fmt: skip

    assert без_номеров(д) == без_номеров(л)
    assert "cities 1" in вывод and "plans 1" in вывод and "settings 1" in вывод
    # Правки из админки на месте
    assert sql("select price_usd from plans where code = 'flash'")[0][0] == 99
