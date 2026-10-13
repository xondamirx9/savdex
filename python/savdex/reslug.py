"""
Адреса страниц латиницей (ТЗ-02 §4) — для уже заведённых записей.

Раньше иероглифы в адрес не попадали: китайская компания получила
/company/company, её объявления — /listing/-861 … /listing/-864. Новые
записи получают адрес уже правильно (savdex/tenders/slug.py, slug_fields),
а старые переписывает manage.py reslug — при каждом деплое, только те,
что ещё плохие:

- компания с адресом «company» или «company-N», у которой из названия
  выходит латиница (пиньинь и т. п.), — на неё; не вышло — «company-<id>»;
- объявление с адресом на «-» — «<заголовок латиницей>-<id>» или «<id>».

Прежний адрес остаётся в slug_redirects: страница по нему отвечает 301 на
текущий адрес (redirect_for).
"""

from __future__ import annotations

import re
from typing import Any

from django.db import connection
from django.http import HttpResponse, HttpResponsePermanentRedirect

from savdex.guards import allowed_writes
from savdex.tenders.slug import numbered_slug, slugify

#: Сущность → (таблица, адрес на сайте)
ENTITIES = {"company": ("companies", "/company/"), "listing": ("listings", "/listing/")}


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _taken(table: str, slug: str, key: int) -> bool:
    return bool(_rows(f"select 1 from {table} where slug = %s and id <> %s limit 1", [slug, key]))


def company_slug(name: str, key: int) -> str | None:
    """Новый адрес компании с плохим адресом; None — адрес уже годный."""
    base = slugify(name)[:60].strip("-")

    # «Company Group» и так даёт «company…» — адрес не плохой
    if base.startswith("company"):
        return None

    if len(base) < 3:
        return f"company-{key}"

    return base


def _move(entity: str, row: dict[str, Any], new: str) -> None:
    table, _ = ENTITIES[entity]

    if _taken(table, new, row["id"]):
        new = f"{new}-{row['id']}"

    if new == row["slug"]:
        return

    with allowed_writes(table, "slug_redirects"), connection.cursor() as cursor:
        cursor.execute(
            "insert into slug_redirects (entity, old_slug, target_id, created_at) "
            "values (%s, %s, %s, now() at time zone 'utc') "
            "on conflict (entity, old_slug) do update set target_id = excluded.target_id",
            [entity, row["slug"], row["id"]],
        )
        cursor.execute(f"update {table} set slug = %s where id = %s", [new, row["id"]])


def run() -> dict[str, int]:
    """Переписать плохие адреса; итог — сколько у компаний и объявлений."""
    moved = {"company": 0, "listing": 0}

    for row in _rows(
        "select id, name, slug from companies where slug ~ '^company(-[0-9]+)?$' order by id"
    ):
        new = company_slug(str(row["name"] or ""), row["id"])

        if new is not None and not re.fullmatch(rf"{re.escape(new)}(-[0-9]+)?", row["slug"]):
            _move("company", row, new)
            moved["company"] += 1

    for row in _rows("select id, title, slug from listings where left(slug, 1) = '-' order by id"):
        _move("listing", row, numbered_slug(str(row["title"] or ""), row["id"]))
        moved["listing"] += 1

    return moved


def redirect_for(ctx: Any, entity: str, slug: str) -> HttpResponse | None:  # noqa: ANN401
    """301 со старого адреса на текущий; адреса не было — None (дальше 404)."""
    from savdex.web import locales

    table, prefix = ENTITIES[entity]
    found = _rows(
        f"select t.slug from slug_redirects r join {table} t on t.id = r.target_id "
        "where r.entity = %s and r.old_slug = %s and t.deleted_at is null limit 1",
        [entity, slug],
    )

    if not found or found[0]["slug"] == slug:
        return None

    return HttpResponsePermanentRedirect(
        locales.url(ctx.root, prefix + str(found[0]["slug"]), ctx.locale)
    )
