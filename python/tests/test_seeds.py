"""
Шаг 73: справочники при деплое заводит Django (manage.py seed) — из
снимка savdex/bootstrap/seeds.json, как прежде сидеры Laravel.

- пустая база после manage.py seed --fresh — весь снимок, номер в номер
  (строки по порядку снимка, номера с 1 подряд), и снимок с неё —
  тот же seeds.json;
- на заполненной базе — как сидеры деплоя: недостающее досоздаётся,
  правки (название страны, выключенная категория, цена тарифа) не
  откатываются, поля категорий возвращаются к снимку.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from savdex import seeds

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база


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
def снимок_seeds() -> dict[str, Any]:
    return dict(json.loads(seeds.DATA.read_text(encoding="utf-8")))


def test_пустая_база_номер_в_номер(снимок_seeds, tmp_path):
    свежая_база()
    вывод = django("--fresh")
    база = снимок()

    # Весь снимок, по порядку и с номерами 1, 2, 3… — как db:seed на пустой базе
    for table in seeds.TABLES:
        assert [r["id"] for r in база[table]] == list(range(1, len(снимок_seeds[table]) + 1)), table

    assert "countries 59" in вывод and "settings" in вывод
    assert [r["code"] for r in база["countries"]][:2] == ["uz", "kz"]

    # Снимок с заведённой базы — тот же seeds.json: ничего не потеряно и не добавлено
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

    assert json.loads(путь.read_text()) == снимок_seeds


def _правки_остаются() -> None:
    """Правки из админки, которые деплой не откатывает."""
    sql("update country_translations set name = 'Моя страна' where locale = 'ru' and "
        "country_id = (select id from countries where code = 'kz')")  # fmt: skip
    sql("update categories set is_active = false where slug = 'metally'")
    sql("update plans set price_usd = 99 where code = 'flash'")
    sql("update settings set value = to_json('Своё'::text) where key = 'site_name'")


def _правки() -> None:
    _правки_остаются()
    # Удалённое деплой досоздаёт, поля категорий возвращает к снимку
    sql("delete from city_translations where city_id in (select id from cities where slug = "
        "'samarkand')")  # fmt: skip
    sql("delete from cities where slug = 'samarkand'")
    sql("delete from category_translations where category_id in "
        "(select id from categories where slug = 'stanki')")  # fmt: skip
    sql("delete from categories where slug = 'stanki'")
    sql("update category_fields set label = 'Другое имя' where key = 'mark'")
    sql("delete from plans where code = 'vip'")
    sql("delete from settings where key = 'support_email'")


def test_деплой_на_заполненной_базе():
    # Ожидание: свежие справочники, на которых остались только правки админки
    свежая_база()
    django("--fresh")
    _правки_остаются()
    ожидание = снимок()

    свежая_база()
    django("--fresh")
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

    assert без_номеров(д) == без_номеров(ожидание)
    assert "cities 1" in вывод and "plans 1" in вывод and "settings 1" in вывод
    assert "categories 1" in вывод
    # Правки из админки на месте, поле категории — как в снимке
    assert sql("select price_usd from plans where code = 'flash'")[0][0] == 99
    assert sql("select is_active from categories where slug = 'metally'") == [(False,)]
    assert sql("select label from category_fields where key = 'mark'") == [("Марка",)]
    assert sql(
        "select t.name from country_translations t join countries c on c.id = t.country_id "
        "where c.code = 'kz' and t.locale = 'ru'"
    ) == [("Моя страна",)]
    assert sql("select count(*) from city_translations t join cities c on c.id = t.city_id "
               "where c.slug = 'samarkand'") == [(5,)]  # fmt: skip
