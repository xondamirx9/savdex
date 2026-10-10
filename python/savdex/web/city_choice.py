"""
Город компании (ТЗ-02 §2).

- «Другой город»: в справочнике выбранной страны нужного города может не
  быть. Тогда в форме выбирается пункт «other» и название пишется текстом
  (city_name). Название становится скрытой записью справочника этой страны
  (is_active = false): компания и её объявления показывают его как любой
  город, а в общие списки и фильтры оно не попадает, пока модератор не
  включит город в админке. Такое же название в той же стране — та же запись.
- Город — только из выбранной страны: «Китай + Ташкент» не сохраняется
  (проверка на сервере, city_in_country).
"""

from __future__ import annotations

from typing import Any

from django.db import connection

from savdex.guards import allowed_writes
from savdex.tenders.slug import slugify
from savdex.web.validation import Check

#: Значение пункта «Другой город» в списке городов
OTHER = "other"

#: Языки названий: введённое название — на всех, иначе другой язык видел бы slug
LOCALES = ("ru", "uz", "en", "zh", "tr")


#: Строка перевода: название и метки времени (UTC без пояса, как у Eloquent)
_TRANSLATION = "(%s, %s, %s, now() at time zone 'utc', now() at time zone 'utc')"


def _rows(query: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _int(value: Any) -> int | None:  # noqa: ANN401
    try:
        return int(str(value).strip()) if value not in (None, "") else None
    except ValueError:
        return None


def _city(country_id: int, name: str) -> int:
    """Город страны с таким названием на любом языке; нет — новый, скрытый."""
    found = _rows(
        "select c.id from cities c join city_translations t on t.city_id = c.id "
        "where c.country_id = %s and lower(t.name) = lower(%s) order by c.id limit 1",
        [country_id, name],
    )

    if found:
        return int(found[0]["id"])

    base = slugify(name)[:60].strip("-") or "city"
    slug, n = base, 2

    while _rows("select 1 from cities where country_id = %s and slug = %s", [country_id, slug]):
        slug, n = f"{base}-{n}", n + 1

    with allowed_writes("cities", "city_translations"), connection.cursor() as cursor:
        cursor.execute(
            "insert into cities (country_id, slug, sort, is_active, created_at, updated_at) "
            "values (%s, %s, 1000, false, now() at time zone 'utc', now() at time zone 'utc') "
            "returning id",
            [country_id, slug],
        )
        city_id = int(cursor.fetchone()[0])
        cursor.execute(
            "insert into city_translations (city_id, locale, name, created_at, updated_at) values "
            + ", ".join([_TRANSLATION] * len(LOCALES)),
            [v for locale in LOCALES for v in (city_id, locale, name)],
        )

    return city_id


def resolve_other(data: dict[str, Any]) -> None:
    """
    «Другой город» → номер записи справочника. Без названия или страны —
    город не выбран: ошибку «Выберите город» даст правило city_id.
    """
    if str(data.get("city_id")) != OTHER:
        return

    name = " ".join(str(data.get("city_name") or "").split())[:120]
    country_id = _int(data.get("country_id"))
    data["city_id"] = _city(country_id, name) if name and country_id is not None else None


def city_in_country(data: dict[str, Any], company: dict[str, Any] | None = None) -> Check:
    """Город — из выбранной страны (страна из запроса, иначе страна компании)."""

    def passes(value: Any) -> bool:  # noqa: ANN401
        city_id = _int(value)
        country_id = _int(data.get("country_id")) or (company or {}).get("country_id")

        if city_id is None or country_id is None:
            return True

        # Города нет вовсе — это ошибка правила exists, не этой проверки
        found = _rows("select country_id from cities where id = %s", [city_id])

        return not found or found[0]["country_id"] == country_id

    return Check("city_country", passes)
