"""
Чистка витрины по ТЗ-01 («чистые данные и доверие»): три правки данных,
которые команда сначала видит списком и только потом разрешает.

  1. demand.csv — объявления, которые на деле заявки «куплю»: все заявки
     площадки (служебная компания, загрузка из Excel — savdex/web/platform.py)
     и любые объявления с заголовком «Куплю…», «Требуется…», «Buy…», «求购…»
     и т. п. Сейчас они записаны предложениями (type = supply), и раздел
     «Запросы» пуст.
  2. descriptions.csv — заявки площадки, в описании которых видно, откуда
     заявка взята: «Оригинальное объявление», «по платному доступу»,
     «Агрору», «Дата публикации»… Такие предложения вырезаются целиком,
     на всех языках описания.
  3. companies.csv — тестовые компании на витрине: названные в ТЗ и
     похожие на случайный набор латинских букв. Они скрываются с витрины
     (статус «скрыта»), а не удаляются.

Порядок (ТЗ-01, «Порядок выката»): manage.py showcase_cleanup report —
файлы уходят команде; лишние строки из них просто удаляют; затем
manage.py showcase_cleanup apply применяет ровно те номера, что остались
в файлах. Описания при этом вычищаются заново по текущему тексту — в
файле они только для просмотра.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import connection
from django.utils import timezone

from savdex.data.models import COMPANY_HIDDEN
from savdex.guards import allowed_writes
from savdex.web import platform

DEMAND_FILE = "demand.csv"
DESCRIPTIONS_FILE = "descriptions.csv"
COMPANIES_FILE = "companies.csv"

# ── 1. Заявки «куплю» ───────────────────────────────────────────────

#: Начало заголовка заявки на закупку (ТЗ-01, п.2.1). Слова — целиком:
#: «Buyer guide» — не заявка, «Buy cement» — заявка
_DEMAND_WORDS = (
    "куплю",
    "требуется",
    "требуются",
    "закупаем",
    "ищем",
    "нужен",
    "нужна",
    "нужно",
    "нужны",
    "sotib olaman",
    "kerak",
    "buy",
    "buying",
    "looking for",
    "wtb",
)
#: Китайский пишется без пробелов — граница слова там не работает
_DEMAND_ZH = ("求购", "采购")

_DEMAND_TITLE = re.compile(
    r"^[\W_]*(?:(?:"
    + "|".join(re.escape(w) for w in _DEMAND_WORDS)
    + r")\b|"
    + "|".join(_DEMAND_ZH)
    + ")",
    re.IGNORECASE,
)


def demand_title(title: str | None) -> str | None:
    """Слово, с которого начинается заголовок заявки, или None."""
    found = _DEMAND_TITLE.match(title or "")

    return found.group(0).strip(" \t\"'«»“”„-—:.,!").lower() if found else None


def _titles(row: dict[str, Any]) -> list[str]:
    titles = [row["title"] or ""]
    i18n = _json(row.get("title_i18n"))

    return titles + [str(v) for v in i18n.values() if v]


def demand_candidates() -> list[dict[str, Any]]:
    """Объявления, которые надо перевести в запросы (type = demand)."""
    service = platform.service_company_id()
    found = []

    for row in _rows(
        "select l.id, l.company_id, l.source, l.status, l.type, l.title, l.title_i18n, "
        "c.name as company from listings l join companies c on c.id = l.company_id "
        "where l.deleted_at is null and l.type <> 'demand' order by l.id"
    ):
        own = platform.owns(row, service)
        word = next((w for w in map(demand_title, _titles(row)) if w), None)

        if own or word:
            found.append(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "company": platform.NAME if own else row["company"],
                    "title": row["title"],
                    "reason": "заявка площадки" if own else f"заголовок: «{word}»",
                }
            )

    return found


# ── 2. Описания заявок площадки ─────────────────────────────────────

#: Предложение с любым из этих кусков выдаёт источник заявки (ТЗ-01, п.3).
#: Сравнение — без учёта регистра, ё = е, кавычки любые
_SOURCE_MARKERS = (
    # ru
    "оригинальное объявление",
    "оригинал объявления",
    "платному доступу",
    "платный доступ",
    "контакты покупателя закрыты",
    "агрору",
    "agroru",
    "разделе спрос площадки",
    "дата публикации",
    # en
    "original listing",
    "original ad",
    "paid access",
    "buyer's contacts are hidden",
    "buyer contacts are hidden",
    "publication date",
    "date of publication",
    "published on",
    # uz
    "asl e’lon",
    "asl e'lon",
    "asl eʼlon",
    "pullik kirish",
    "pullik ruxsat",
    "pullik asosda",
    "nashr sanasi",
    "e’lon qilingan sana",
    "e'lon qilingan sana",
    "chop etilgan sana",
    # tr
    "orijinal ilan",
    "asıl ilan",
    "ücretli erişim",
    "yayın tarihi",
    "yayınlanma tarihi",
    # zh
    "原始公告",
    "原始信息",
    "原始需求",
    "原文",
    "付费",
    "发布日期",
    "发布时间",
)

#: Конец предложения — точка, «!», «?» (и китайские) перед пробелом или
#: концом текста; переносы строк — тоже граница
_ENDS = ".!?。！？"
_OPEN = "«“„"
_CLOSE = "»”“"


def _plain(text: str) -> str:
    """Для сравнения с маркерами: регистр, ё, кавычки и лишние пробелы."""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[«»“”„\"]", "", text)

    return re.sub(r"\s+", " ", text)


def sentences(text: str) -> list[str]:
    """
    Текст по предложениям, каждое — со своими пробелами после него, так что
    "".join(sentences(t)) == t. Точка внутри кавычек «…» предложение не
    заканчивает: «Оригинальное объявление: «Куплю печь. Срочно.»» — одно.
    """
    parts: list[str] = []
    start = depth = 0
    i = 0

    while i < len(text):
        char = text[i]

        if char in _OPEN and not (char == "“" and depth > 0):
            depth += 1
        elif char in _CLOSE and depth > 0:
            depth -= 1

        boundary = char == "\n" or (
            char in _ENDS and depth == 0 and (i + 1 == len(text) or text[i + 1].isspace())
        )
        # Китайская точка — граница и без пробела после неё
        boundary = boundary or (char in "。！？" and depth == 0)

        if boundary:
            end = i + 1

            while end < len(text) and text[end].isspace():
                end += 1

            parts.append(text[start:end])
            start = i = end

            continue

        i += 1

    if start < len(text):
        parts.append(text[start:])

    return parts


def clean(text: str | None) -> str | None:
    """Описание без предложений, выдающих источник заявки."""
    if not text:
        return text

    kept = [s for s in sentences(text) if not any(m in _plain(s) for m in _MARKERS)]

    return "".join(kept).rstrip()


_MARKERS = tuple(_plain(m) for m in _SOURCE_MARKERS)


@dataclass
class Cleaned:
    description: str | None
    description_i18n: dict[str, Any] | None
    #: (поле, было, стало) — для отчёта
    changes: list[tuple[str, str, str]]


def cleaned(row: dict[str, Any]) -> Cleaned:
    """Описание и его переводы после чистки; changes пуст — чистить нечего."""
    changes = []
    description = clean(row["description"])

    if description != row["description"]:
        changes.append(("description", row["description"] or "", description or ""))

    i18n = _json(row.get("description_i18n"))
    new_i18n = dict(i18n)

    for locale, text in i18n.items():
        if isinstance(text, str):
            new_i18n[locale] = clean(text)

            if new_i18n[locale] != text:
                changes.append((f"description.{locale}", text, new_i18n[locale] or ""))

    return Cleaned(description, new_i18n if i18n else row.get("description_i18n"), changes)


def _platform_listings(ids: Iterable[int] | None = None) -> list[dict[str, Any]]:
    service = platform.service_company_id()

    if service is None:
        return []

    query = (
        "select id, company_id, source, title, title_i18n, description, description_i18n "
        "from listings where company_id = %s and source = 'import' and deleted_at is null"
    )
    params: list[Any] = [service]

    if ids is not None:
        ids = list(ids)

        if not ids:
            return []

        query += f" and id in ({', '.join(['%s'] * len(ids))})"
        params += ids

    return _rows(query + " order by id", params)


def description_candidates() -> list[dict[str, Any]]:
    """Заявки площадки, в описании которых видно источник."""
    found = []

    for row in _platform_listings():
        result = cleaned(row)

        for field, before, after in result.changes:
            found.append({"id": row["id"], "field": field, "before": before, "after": after})

    return found


# ── 3. Тестовые компании ────────────────────────────────────────────

#: Названы в ТЗ-01, п.4.1
_TEST_NAMES = ("ооо ромашка", "ooo turk", "ooo oscar travel", "rirjgijg", "ооо узбекистан")

#: Кириллица, похожая на латиницу: «ООО» набирают и так, и так
_LOOKALIKE = str.maketrans("аеорсухк", "aeopcyxk")

#: Правовая форма перед названием — для проверки «случайных букв» не нужна
_LEGAL_FORM = re.compile(r"^(?:ooo|oao|zao|llc|ltd|mchj|xk|ип)\s+", re.IGNORECASE)

#: Три согласных подряд — так в названиях из случайных букв («rirjgijg»)
_CONSONANTS = re.compile(r"[bcdfghjklmnpqrstvwxz]{3,}")


def _name_key(name: str) -> str:
    name = re.sub(r"[«»\"'“”„]", "", name).strip().lower()

    return re.sub(r"\s+", " ", name).translate(_LOOKALIKE)


_TEST_KEYS = {_name_key(n) for n in _TEST_NAMES}


def random_letters(name: str) -> bool:
    """Название из случайных латинских букв: одно слово, без гласных подряд."""
    word = _LEGAL_FORM.sub("", _name_key(name))

    return bool(re.fullmatch(r"[a-z]{5,}", word)) and bool(_CONSONANTS.search(word))


def company_candidates() -> list[dict[str, Any]]:
    """
    Компании, которые стоит скрыть: названные в ТЗ — всегда, «случайные
    буквы» — только без живых объявлений и без проверки, чтобы не задеть
    настоящую компанию с необычным названием.
    """
    found = []

    for row in _rows(
        "select c.id, c.name, c.verification_level, c.created_at, "
        "(select count(*) from listings l where l.company_id = c.id and l.status = 'active' "
        "and l.deleted_at is null) as listings from companies c "
        "where c.status = 'active' and c.deleted_at is null order by c.id"
    ):
        if _name_key(row["name"]) in _TEST_KEYS:
            reason = "названа в ТЗ"
        elif random_letters(row["name"]) and not row["listings"] and not row["verification_level"]:
            reason = "похоже на случайные буквы — проверить"
        else:
            continue

        found.append(
            {
                "id": row["id"],
                "name": row["name"],
                "listings": int(row["listings"]),
                "verified": int(row["verification_level"] or 0),
                "created_at": row["created_at"],
                "reason": reason,
            }
        )

    return found


# ── Отчёт и применение ──────────────────────────────────────────────


def report(directory: Path) -> dict[str, int]:
    """Три файла CSV для команды; сколько строк в каждом."""
    directory.mkdir(parents=True, exist_ok=True)
    tables = {
        DEMAND_FILE: demand_candidates(),
        DESCRIPTIONS_FILE: description_candidates(),
        COMPANIES_FILE: company_candidates(),
    }

    for name, rows in tables.items():
        _write(directory / name, rows)

    return {name: len(rows) for name, rows in tables.items()}


def approved_ids(path: Path) -> list[int]:
    """Номера из первого столбца файла, который вернула команда."""
    if not path.exists():
        return []

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)

        return sorted({int(r["id"]) for r in rows if (r.get("id") or "").strip().isdigit()})


def apply(directory: Path, dry_run: bool = False) -> dict[str, int]:
    """
    Применить согласованные файлы. Повторный запуск ничего не портит:
    уже переведённые, вычищенные и скрытые строки не меняются.
    """
    now = timezone.now().replace(microsecond=0, tzinfo=None)
    demand = approved_ids(directory / DEMAND_FILE)
    texts = approved_ids(directory / DESCRIPTIONS_FILE)
    companies = approved_ids(directory / COMPANIES_FILE)
    done = {"demand": 0, "descriptions": 0, "companies": 0}

    rows = _platform_listings(texts)
    updates = [(row, cleaned(row)) for row in rows]
    updates = [(row, result) for row, result in updates if result.changes]

    if dry_run:
        done["demand"] = _count(
            "select count(*) as n from listings where type <> 'demand' and deleted_at is null",
            demand,
        )
        done["descriptions"] = len(updates)
        done["companies"] = _count(
            "select count(*) as n from companies where status = 'active' and deleted_at is null",
            companies,
        )

        return done

    from savdex.web.listing_actions import _search_text

    with allowed_writes("listings", "companies"), connection.cursor() as cursor:
        for chunk in _chunks(demand):
            cursor.execute(
                "update listings set type = 'demand', updated_at = %s where type <> 'demand' "
                f"and deleted_at is null and id in ({', '.join(['%s'] * len(chunk))})",
                [now, *chunk],
            )
            done["demand"] += cursor.rowcount

        for row, result in updates:
            after = {**row, "description": result.description}
            cursor.execute(
                "update listings set description = %s, description_i18n = %s, "
                "search_text = %s, updated_at = %s where id = %s",
                [
                    result.description,
                    json.dumps(result.description_i18n, ensure_ascii=False)
                    if isinstance(result.description_i18n, dict)
                    else result.description_i18n,
                    _search_text({**after, "title_i18n": _json(row.get("title_i18n"))}),
                    now,
                    row["id"],
                ],
            )
            done["descriptions"] += cursor.rowcount

        for chunk in _chunks(companies):
            cursor.execute(
                "update companies set status = %s, updated_at = %s where status = 'active' "
                f"and deleted_at is null and id in ({', '.join(['%s'] * len(chunk))})",
                [COMPANY_HIDDEN, now, *chunk],
            )
            done["companies"] += cursor.rowcount

    return done


# ── Мелочи ──────────────────────────────────────────────────────────


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        names = [c[0] for c in cursor.description or []]

        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _json(value: Any) -> dict[str, Any]:  # noqa: ANN401
    if isinstance(value, dict):
        return value

    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}

        return parsed if isinstance(parsed, dict) else {}

    return {}


def _count(query: str, ids: list[int]) -> int:
    total = 0

    for chunk in _chunks(ids):
        rows = _rows(f"{query} and id in ({', '.join(['%s'] * len(chunk))})", chunk)
        total += int(rows[0]["n"]) if rows else 0

    return total


def _chunks(ids: list[int], size: int = 500) -> Iterable[list[int]]:
    for start in range(0, len(ids), size):
        yield ids[start : start + size]


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    # utf-8-sig: Excel открывает кириллицу и иероглифы без «кракозябр»
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not rows:
            handle.write("id\n")

            return

        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
