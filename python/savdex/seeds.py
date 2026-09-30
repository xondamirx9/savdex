"""
Справочники площадки при деплое (шаг 73) — вместо сидеров Laravel
(PlanSeeder, CategorySeeder, GeoSeeder, SettingSeeder, а на свежей базе —
ещё PromotionTypeSeeder и новости CmsSeeder).

Данные — savdex/bootstrap/seeds.json: снимок того, что сидеры Laravel заводят
на пустой базе (manage.py seed --export на базе после migrate:fresh и
db:seed). Что снимок не разошёлся с сидерами, пока они живы, проверяет
tests/test_seeds.py. Поведение — как у сидеров:

- тарифы, категории, страны и города — только недостающие (firstOrCreate
  по коду, slug, паре «страна + slug»); переводы — только у заведённых
  сейчас: правки из админки деплой не откатывает;
- поля категорий — updateOrCreate: источник правды — снимок;
- настройки — только недостающие ключи, порядок — место в списке;
- типы продвижения и стартовые новости — только на свежей базе
  (DatabaseSeeder), updateOrCreate.

Порядок и номера строк на свежей базе — те же, что у Laravel.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import connection

from savdex.guards import allowed_writes

DATA = Path(__file__).resolve().parent / "bootstrap" / "seeds.json"

#: Таблица → (столбцы-ключ, столбцы, которые подменяются ключом родителя)
#: Родитель — (столбец, таблица, её ключевые столбцы)
TABLES: dict[str, dict[str, Any]] = {
    "countries": {"key": ["code"]},
    "country_translations": {
        "key": ["country_id", "locale"],
        "parents": {"country_id": ("countries", ["code"])},
    },
    "cities": {"key": ["country_id", "slug"], "parents": {"country_id": ("countries", ["code"])}},
    "city_translations": {
        "key": ["city_id", "locale"],
        "parents": {"city_id": ("cities", ["country_id", "slug"])},
    },
    "plans": {"key": ["code"]},
    "categories": {"key": ["slug"], "parents": {"parent_id": ("categories", ["slug"])}},
    "category_translations": {
        "key": ["category_id", "locale"],
        "parents": {"category_id": ("categories", ["slug"])},
    },
    "category_fields": {
        "key": ["category_id", "key"],
        "parents": {"category_id": ("categories", ["slug"])},
    },
    "promotion_types": {"key": ["code"]},
    "news_posts": {"key": ["slug"]},
    "settings": {"key": ["key"]},
}

_SKIP = ("id", "created_at", "updated_at")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _rows(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, list(params))
        names = [c[0] for c in cursor.description or []]

        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _types(table: str) -> dict[str, str]:
    return {
        row["column_name"]: row["data_type"]
        for row in _rows(
            "select column_name, data_type from information_schema.columns "
            "where table_schema = current_schema() and table_name = %s",
            [table],
        )
    }


# ── Снимок ───────────────────────────────────────────────────────────


def _plain(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    return value


def _natural(table: str, row_id: int, cache: dict[tuple[str, int], list[Any]]) -> list[Any]:
    """Ключ строки по номеру — с ключами родителей вместо их номеров."""
    if (table, row_id) not in cache:
        spec = TABLES[table]
        row = _rows(f"select * from {table} where id = %s", [row_id])[0]
        key: list[Any] = []

        for column in spec["key"]:
            parent = spec.get("parents", {}).get(column)
            value = row[column]
            key.append(_natural(parent[0], value, cache) if parent and value is not None else value)

        cache[(table, row_id)] = key

    return cache[(table, row_id)]


def export(path: Path = DATA) -> dict[str, Any]:
    """Снимок справочников текущей базы — после сидеров Laravel на пустой базе."""
    cache: dict[tuple[str, int], list[Any]] = {}
    out: dict[str, Any] = {}

    for table, spec in TABLES.items():
        rows = []

        for row in _rows(f"select * from {table} order by id"):
            item = {k: _plain(v) for k, v in row.items() if k not in _SKIP}

            for column, (parent, _) in spec.get("parents", {}).items():
                if item[column] is not None:
                    item[column] = _natural(parent, row[column], cache)

            rows.append(item)

        out[table] = rows

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    return out


# ── Заведение ────────────────────────────────────────────────────────


class _Seeder:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.types: dict[str, dict[str, str]] = {}
        self.created = dict.fromkeys(TABLES, 0)

    def _types(self, table: str) -> dict[str, str]:
        if table not in self.types:
            self.types[table] = _types(table)

        return self.types[table]

    def _resolve(self, table: str, key: list[Any]) -> int | None:
        """Номер строки по ключу (с ключами родителей)."""
        spec = TABLES[table]
        where, params = [], []

        for column, value in zip(spec["key"], key, strict=True):
            parent = spec.get("parents", {}).get(column)

            if parent and value is not None:
                value = self._resolve(parent[0], value)

                if value is None:
                    return None

            where.append(f"{column} is null" if value is None else f"{column} = %s")

            if value is not None:
                params.append(value)

        found = _rows(f"select id from {table} where {' and '.join(where)} limit 1", params)

        return int(found[0]["id"]) if found else None

    def _row(self, table: str, item: dict[str, Any]) -> dict[str, Any]:
        """Строка снимка с номерами родителей вместо ключей."""
        row = dict(item)

        for column, (parent, _) in TABLES[table].get("parents", {}).items():
            if row.get(column) is not None:
                row[column] = self._resolve(parent, row[column])

        return row

    def _key_of(self, table: str, item: dict[str, Any]) -> list[Any]:
        return [item[c] for c in TABLES[table]["key"]]

    def _write(self, table: str, row: dict[str, Any], row_id: int | None) -> int:
        types = self._types(table)
        columns = [c for c in row if c in types]
        stamp = _now()

        def cast(column: str) -> str:
            return (
                "%s::jsonb"
                if types[column] == "jsonb"
                else ("%s::json" if types[column] == "json" else "%s")
            )

        values = [
            json.dumps(row[c], ensure_ascii=False)
            if types[c] in ("json", "jsonb") and row[c] is not None
            else row[c]
            for c in columns
        ]

        with allowed_writes(table), connection.cursor() as cursor:
            if row_id is None:
                cursor.execute(
                    f"insert into {table} ({', '.join(_quote(c) for c in columns)}, created_at, "
                    f"updated_at) values ({', '.join(cast(c) for c in columns)}, %s, %s) "
                    "returning id",
                    [*values, stamp, stamp],
                )
                self.created[table] += 1

                return int(cursor.fetchone()[0])

            # updateOrCreate: updated_at — только если что-то изменилось
            sets = ", ".join(f"{_quote(c)} = {cast(c)}" for c in columns)
            differs = " or ".join(
                f"{_quote(c)}::jsonb is distinct from %s::jsonb"
                if types[c] in ("json", "jsonb")
                else f"{_quote(c)} is distinct from %s"
                for c in columns
            )
            cursor.execute(
                f"update {table} set {sets}, updated_at = %s where id = %s and ({differs})",
                [*values, stamp, row_id, *values],
            )

            return row_id

    def first_or_create(self, table: str, children: tuple[str, ...] = ()) -> None:
        """firstOrCreate по ключу; дочерние (переводы) — только у заведённых сейчас."""
        fresh: set[str] = set()

        for item in self.data.get(table, []):
            if self._resolve(table, self._key_of(table, item)) is None:
                self._write(table, self._row(table, item), None)
                fresh.add(json.dumps(self._key_of(table, item)))

        for child in children:
            column = next(iter(TABLES[child]["parents"]))

            for item in self.data.get(child, []):
                if json.dumps(item[column]) in fresh and (
                    self._resolve(child, self._key_of(child, item)) is None
                ):
                    self._write(child, self._row(child, item), None)

    def update_or_create(self, table: str) -> None:
        for item in self.data.get(table, []):
            row_id = self._resolve(table, self._key_of(table, item))
            self._write(table, self._row(table, item), row_id)

    def settings(self) -> None:
        """SettingSeeder: только недостающие ключи."""
        known = {row["key"] for row in _rows("select key from settings")}

        for item in self.data.get("settings", []):
            if item["key"] not in known:
                self._write("settings", dict(item), None)


def _quote(column: str) -> str:
    # «group», «key» — слова SQL
    return f'"{column}"'


def seed(fresh: bool = False, data: dict[str, Any] | None = None) -> dict[str, int]:
    """
    Справочники: на свежей базе — как db:seed (DatabaseSeeder), затем, как
    на каждом деплое, — PlanSeeder, CategorySeeder, GeoSeeder, SettingSeeder.
    Итог — сколько строк заведено в каждой таблице.
    """
    seeder = _Seeder(data if data is not None else json.loads(DATA.read_text(encoding="utf-8")))

    def geo() -> None:
        # Страна за страной, как GeoSeeder: номера строк — как у Laravel
        for country in seeder.data.get("countries", []):
            one = {
                **seeder.data,
                "countries": [country],
                "country_translations": [
                    t for t in seeder.data["country_translations"]
                    if t["country_id"] == [country["code"]]
                ],
                "cities": [
                    c for c in seeder.data["cities"] if c["country_id"] == [country["code"]]
                ],
            }  # fmt: skip
            part = _Seeder(one)
            part.types = seeder.types
            part.first_or_create("countries", ("country_translations",))

            for city in one["cities"]:
                part.data = {
                    **one,
                    "cities": [city],
                    "city_translations": [
                        t for t in seeder.data["city_translations"]
                        if t["city_id"] == [[country["code"]], city["slug"]]
                    ],
                }  # fmt: skip
                part.first_or_create("cities", ("city_translations",))

            for table, count in part.created.items():
                seeder.created[table] += count

    def categories() -> None:
        # Раздел, затем его подкатегории и их поля — как CategorySeeder
        parents = [c for c in seeder.data["categories"] if c["parent_id"] is None]

        for parent in parents:
            family = [parent] + [
                c for c in seeder.data["categories"] if c["parent_id"] == [parent["slug"]]
            ]

            for category in family:
                part = _Seeder(
                    {
                        "categories": [category],
                        "category_translations": [
                            t for t in seeder.data["category_translations"]
                            if t["category_id"] == [category["slug"]]
                        ],
                        "category_fields": [
                            f for f in seeder.data["category_fields"]
                            if f["category_id"] == [category["slug"]]
                        ],
                    }
                )  # fmt: skip
                part.types = seeder.types
                part.first_or_create("categories", ("category_translations",))

                if category["parent_id"] is not None:
                    part.update_or_create("category_fields")

                for table, count in part.created.items():
                    seeder.created[table] += count

    if fresh:
        # DatabaseSeeder: Geo, Plan, Category, PromotionType, Cms (новости и настройки)
        geo()
        seeder.first_or_create("plans")
        categories()
        seeder.update_or_create("promotion_types")
        seeder.update_or_create("news_posts")
        seeder.settings()

    # Каждый деплой: PlanSeeder, CategorySeeder, GeoSeeder, SettingSeeder
    seeder.first_or_create("plans")
    categories()
    geo()
    seeder.settings()

    return seeder.created
