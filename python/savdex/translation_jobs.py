"""
Задачи машинного перевода — копии App\\Jobs\\Translate* и команды
translations:fill, с добором несложившегося, как routes/console.php.

Каждая задача: по недостающим языкам (ключа нет или он null) —
запрос к переводчику; перед записью строка перечитывается, и то, что
за это время появилось в базе, главнее (левый операнд «+» у PHP);
array_filter убирает несложившееся — его доберёт следующий проход.

Запись — как Eloquent: только если значение сменилось (массивы PHP
сравниваются вместе с порядком ключей), json — текстом json_encode
(столбцы json хранят текст как есть), с updated_at. Объявление и
закупка сохраняются с событием saving — пересчитывается search_text;
резюме и новость — saveQuietly, без событий.

Запускает фоновый обработчик: manage.py translate (см. команду).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from django.db import connection

from savdex.guards import SHARED_WRITES, allowed_writes
from savdex.translator import TARGETS, Translator, enabled
from savdex.web.search_text import index
from savdex.web.session import php_json_encode

log = logging.getLogger("savdex.translate")

#: FillContentTranslations::MAX_ATTEMPTS
MAX_ATTEMPTS = 5

#: TranslateResume::JOBS_LIMIT — переводятся первые места работы
JOBS_LIMIT = 8

_TRIM = " \t\n\r\0\x0b"


# ── Семантика PHP ────────────────────────────────────────────────────


def _array(value: Any) -> dict[str, Any]:  # noqa: ANN401
    """«?? []» над json-столбцом: null — пусто, список — ключи 0…n."""
    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, list):
        return {str(i): v for i, v in enumerate(value)}

    return {}


def _falsy(value: Any) -> bool:  # noqa: ANN401
    """Ложь у PHP: null, false, 0, 0.0, «», «0», пустой массив."""
    if value is None or value is False:
        return True

    if isinstance(value, int | float) and not isinstance(value, bool):
        return value == 0

    if isinstance(value, str):
        return value in ("", "0")

    if isinstance(value, dict | list):
        return len(value) == 0

    return False


def _filter(values: dict[str, Any]) -> dict[str, Any]:
    """array_filter без функции: ложные значения прочь, ключи на месте."""
    return {k: v for k, v in values.items() if not _falsy(v)}


def _union(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """$left + $right: ключи левого впереди, из правого — только новые."""
    return {**left, **{k: v for k, v in right.items() if k not in left}}


def _filled(value: Any) -> bool:  # noqa: ANN401
    """filled(): не null и не пустая после trim строка."""
    if value is None:
        return False

    if isinstance(value, str):
        return value.strip(_TRIM) != ""

    return not (isinstance(value, dict | list) and len(value) == 0)


def _same(a: Any, b: Any) -> bool:  # noqa: ANN401
    """=== у PHP для массивов: те же пары, в том же порядке, тех же типов."""
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(_same(a[k], b[k]) for k in a)

    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))

    return type(a) is type(b) and a == b


def _cast(raw: Any) -> Any:  # noqa: ANN401
    """Каст array: json в массив (null — null), список — ключи 0…n."""
    if raw is None:
        return None

    return _array(raw) if isinstance(raw, dict | list) else raw


def _json(value: Any) -> str | None:  # noqa: ANN401
    return None if value is None else php_json_encode(value)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _row(table: str, columns: str, key: int, soft: bool) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select {columns} from {table} where id = %s"
            + (" and deleted_at is null" if soft else ""),
            [key],
        )
        found = cursor.fetchone()
        names = [c[0] for c in cursor.description or []]

    return dict(zip(names, found, strict=True)) if found else None


def _save(table: str, key: int, original: dict[str, Any], changes: dict[str, Any]) -> bool:
    """
    Model::save(): только изменившиеся поля (json — сравнением
    раскодированных массивов, как originalIsEquivalent), с updated_at.
    """
    dirty = {}

    for column, value in changes.items():
        before = original[column]

        if isinstance(value, dict | list) or value is None:
            if not _same(_cast(before), value):
                dirty[column] = _json(value)
        elif before != value:
            dirty[column] = value

    if not dirty:
        return False

    sets = ", ".join(f"{c} = %s" for c in dirty)
    # news_posts — таблица Django (раздел новостей), разрешение не нужно
    allowed = (table,) if table in SHARED_WRITES else ()

    with allowed_writes(*allowed), connection.cursor() as cursor:
        cursor.execute(
            f"update {table} set {sets}, updated_at = %s where id = %s",
            [*dirty.values(), _now(), key],
        )

    return True


def _fill(
    translator: Translator,
    current: dict[str, Any],
    text: Any,  # noqa: ANN401
    when: bool = True,
) -> dict[str, Any]:
    """$map[$locale] ??= translate(text): по недостающим языкам, по порядку TARGETS."""
    result = dict(current)

    if not when:
        return result

    for locale in TARGETS:
        if result.get(locale) is None:
            result[locale] = translator.translate(str(text or ""), locale)

    return result


def _search_text(parts: list[Any]) -> str:
    """search_text из частей через array_filter и implode(' ')."""
    return index(" ".join(str(p) for p in parts if not _falsy(p)))


# ── Задачи ───────────────────────────────────────────────────────────


def translate_listing(listing_id: int, translator: Translator) -> None:
    """TranslateListing: заголовок и описание; save() — search_text заново."""
    columns = "title, description, title_i18n, description_i18n, search_text"
    listing = _row("listings", columns, listing_id, soft=True)

    if listing is None:
        return

    titles = _fill(translator, _array(listing["title_i18n"]), listing["title"])
    descriptions = _fill(
        translator,
        _array(listing["description_i18n"]),
        listing["description"],
        _filled(listing["description"]),
    )
    fresh = _row("listings", columns, listing_id, soft=True)

    if fresh is None:
        return

    new_titles = _filter(_union(_array(fresh["title_i18n"]), titles))
    new_descriptions = _filter(_union(_array(fresh["description_i18n"]), descriptions))
    search = _search_text([fresh["title"], str(fresh["description"] or ""), *new_titles.values()])
    _save(
        "listings",
        listing_id,
        fresh,
        {"title_i18n": new_titles, "description_i18n": new_descriptions, "search_text": search},
    )


def translate_resume(resume_id: int, translator: Translator) -> None:
    """TranslateResume: должность, «о себе», первые места работы; saveQuietly."""
    columns = "title, about, jobs, title_i18n, about_i18n, jobs_i18n"
    resume = _row("resumes", columns, resume_id, soft=True)

    if resume is None:
        return

    titles = _array(resume["title_i18n"])
    abouts = _array(resume["about_i18n"])
    jobs = _array(resume["jobs_i18n"])
    original = _array(resume["jobs"])

    for locale in TARGETS:
        if titles.get(locale) is None:
            titles[locale] = translator.translate(str(resume["title"] or ""), locale)

        if _filled(resume["about"]) and abouts.get(locale) is None:
            abouts[locale] = translator.translate(str(resume["about"]), locale)

        if original and jobs.get(locale) is None:
            jobs[locale] = _jobs(translator, original, locale)

    fresh = _row("resumes", columns, resume_id, soft=True)

    if fresh is None:
        return

    keep_jobs = len(_array(fresh["jobs"])) == len(original)
    _save(
        "resumes",
        resume_id,
        fresh,
        {
            "title_i18n": _filter(_union(_array(fresh["title_i18n"]), titles)),
            "about_i18n": _filter(_union(_array(fresh["about_i18n"]), abouts)),
            "jobs_i18n": _filter(_union(_array(fresh["jobs_i18n"]), jobs))
            if keep_jobs
            else _cast(fresh["jobs_i18n"]),
        },
    )


def _jobs(translator: Translator, jobs: dict[str, Any], locale: str) -> list[dict[str, Any]]:
    rows = []

    for i, (_, job) in enumerate(jobs.items()):
        job = job if isinstance(job, dict) else {}
        rows.append(
            {
                field: translator.translate(str(job[field]), locale)
                if i < JOBS_LIMIT and _filled(job.get(field))
                else None
                for field in ("position", "duties")
            }
        )

    return rows


def translate_tender(tender_id: int, translator: Translator) -> None:
    """TranslateTender: без перечитывания; save() — search_text с заказчиком."""
    columns = "title, description, customer, title_i18n, description_i18n, search_text"
    tender = _row("tenders", columns, tender_id, soft=False)

    if tender is None:
        return

    titles = _filter(_fill(translator, _array(tender["title_i18n"]), tender["title"]))
    descriptions = _filter(
        _fill(
            translator,
            _array(tender["description_i18n"]),
            tender["description"],
            _filled(tender["description"]),
        )
    )
    search = _search_text(
        [
            tender["title"],
            str(tender["description"] or ""),
            str(tender["customer"] or ""),
            *titles.values(),
        ]
    )
    _save(
        "tenders",
        tender_id,
        tender,
        {"title_i18n": titles, "description_i18n": descriptions, "search_text": search},
    )


def translate_news(post_id: int, translator: Translator) -> None:
    """TranslateNewsPost: заголовок, анонс, текст; saveQuietly."""
    columns = "title, excerpt, body, title_i18n, excerpt_i18n, body_i18n"
    post = _row("news_posts", columns, post_id, soft=False)

    if post is None:
        return

    changes = {
        "title_i18n": _filter(_fill(translator, _array(post["title_i18n"]), post["title"])),
        "excerpt_i18n": _filter(
            _fill(
                translator, _array(post["excerpt_i18n"]), post["excerpt"], _filled(post["excerpt"])
            )
        ),
        "body_i18n": _filter(
            _fill(translator, _array(post["body_i18n"]), post["body"], _filled(post["body"]))
        ),
    }
    _save("news_posts", post_id, post, changes)


def fill_content(translator: Translator, limit: int = 20) -> tuple[int, int]:
    """translations:fill --limit: тексты страниц из очереди content_translations."""
    done = failed = 0

    with connection.cursor() as cursor:
        cursor.execute(
            "select id, locale, source, attempts from content_translations "
            "where translation is null and attempts < %s order by attempts, id limit %s",
            [MAX_ATTEMPTS, max(1, limit)],
        )
        rows = cursor.fetchall()

    for row_id, locale, source, attempts in rows:
        translated = translator.translate(str(source), str(locale))

        # Переводчик просит подождать: попытку не списываем, проход — всё
        if translated is None and translator.rate_limited:
            log.warning("Переводчик ограничил частоту запросов — продолжим позже")
            break

        with allowed_writes("content_translations"), connection.cursor() as cursor:
            if translated is not None:
                cursor.execute(
                    "update content_translations set translation = %s, updated_at = %s "
                    "where id = %s",
                    [translated, _now(), row_id],
                )
                done += 1
            else:
                cursor.execute(
                    "update content_translations set attempts = %s, updated_at = %s where id = %s",
                    [attempts + 1, _now(), row_id],
                )
                failed += 1

    return done, failed


# ── Добор несложившегося ─────────────────────────────────────────────

_LACKING = " or ".join(f"not coalesce(({{col}})::jsonb ? '{locale}', false)" for locale in TARGETS)

#: Что переводить: (задача, запрос номеров, порция) — как добор в routes/console.php
CATCHUP: dict[str, tuple[Callable[[int, Translator], None], str, int]] = {
    "listings": (
        translate_listing,
        "select id from listings where status = 'active' and deleted_at is null and ("
        + _LACKING.format(col="title_i18n")
        + ") order by id limit %s",
        20,
    ),
    "resumes": (
        translate_resume,
        "select id from resumes where status = 'published' and deleted_at is null and ("
        + _LACKING.format(col="title_i18n")
        + ") order by id limit %s",
        10,
    ),
    "tenders": (
        translate_tender,
        "select id from tenders where status = 'published' and ("
        + _LACKING.format(col="title_i18n")
        + ") order by id limit %s",
        20,
    ),
    "news": (
        translate_news,
        "select id from news_posts where is_published and ("
        + " or ".join(
            f"not coalesce((title_i18n)::jsonb ? '{loc}', false) "
            f"or (excerpt is not null and excerpt <> '' "
            f"and not coalesce((excerpt_i18n)::jsonb ? '{loc}', false)) "
            f"or (body is not null and body <> '' "
            f"and not coalesce((body_i18n)::jsonb ? '{loc}', false))"
            for loc in TARGETS
        )
        + ") order by id limit %s",
        20,
    ),
}


def lacking(kind: str) -> list[int]:
    """Номера записей вида kind, которым не хватает переводов (порция добора)."""
    _, query, limit = CATCHUP[kind]

    with connection.cursor() as cursor:
        cursor.execute(query, [limit])

        return [int(r[0]) for r in cursor.fetchall()]


def run(kind: str, key: int, translator: Translator) -> None:
    """Одна задача; сбой — в журнал, не дальше: перевод — украшение."""
    if not enabled():
        return

    try:
        CATCHUP[kind][0](key, translator)
    except Exception:
        log.exception("Перевод %s #%s не удался", kind, key)


__all__ = ["CATCHUP", "fill_content", "lacking", "run"]
