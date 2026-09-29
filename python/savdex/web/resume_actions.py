"""
Своё резюме — формы на Django (этап 5, шаги 28 и 32): правка,
опубликовать, скрыть и удалить. Копия
App\\Http\\Controllers\\Cabinet\\ResumeController; фото — отдельным шагом.

Правка — как Eloquent: validated() без лишних ключей вложенных
массивов, пустые карточки мест работы, учёбы и языков отбрасываются,
массивы пишутся текстом json_encode, опыт в месяцах считается по
периодам (Resume::experienceMonths), смена заголовка, «о себе» или мест
работы сбрасывает их переводы (событие saving). Новому резюме — адрес
из заголовка и номера.

Резюме в журнал администратора не пишется. Перевод опубликованного
подбирает обработчик Python (manage.py translate), задачу ставить не
нужно. Удаление мягкое; фото уходит с публичного диска.

Сверка с настоящим Laravel — tests/test_web_resume_actions.py.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.audit import _php_json
from savdex.guards import allowed_writes
from savdex.laravel_storage import public_root
from savdex.tenders.slug import slugify
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import _rows
from savdex.web.forms import _store, action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.resumes import (
    EDUCATION_LEVELS,
    EMPLOYMENT,
    FIELDS,
    LANGUAGE_LEVELS,
    SCHEDULE,
)
from savdex.web.shared import Context
from savdex.web.validation import Check, _passes, validate, validated
from savdex.web.views import not_found

PUBLISHED, HIDDEN, BLOCKED = "published", "hidden", "blocked"


def _own(ctx: Context) -> dict[str, Any] | None:
    """ResumeController::own: своё резюме не в корзине, иначе None (404)."""
    assert ctx.user is not None
    rows = _rows(
        "select * from resumes where user_id = %s and deleted_at is null order by id limit 1",
        [ctx.user["id"]],
    )

    return rows[0] if rows else None


def _save(ctx: Context, resume: dict[str, Any], changes: dict[str, Any]) -> None:
    eloquent.save(ctx, "resumes", resume, changes, section=None, model="Resume")


@form()
def publish(request: HttpRequest) -> HttpResponse:
    """ResumeController::publish: сразу на витрину, заблокированное — нет."""
    ctx = action(request)
    resume = _own(ctx)

    if resume is None:
        return not_found(ctx)

    if resume["status"] == BLOCKED:
        # back()->withErrors: ошибка без старого ввода
        _store(ctx).flash(
            "errors",
            {
                "default": {
                    "format": ":message",
                    "messages": {"status": [ctx.t("messages.resume.blocked")]},
                }
            },
        )

        return back(ctx)

    _save(
        ctx,
        resume,
        {"status": PUBLISHED, "published_at": resume["published_at"] or eloquent.now()},
    )
    flash(ctx, "status", ctx.t("messages.resume.published"))

    return back(ctx)


@form()
def hide(request: HttpRequest) -> HttpResponse:
    """ResumeController::hide: только опубликованное."""
    ctx = action(request)
    resume = _own(ctx)

    if resume is None:
        return not_found(ctx)

    if resume["status"] == PUBLISHED:
        _save(ctx, resume, {"status": HIDDEN})

    flash(ctx, "status", ctx.t("messages.resume.hidden"))

    return back(ctx)


@form("DELETE")
def destroy(request: HttpRequest) -> HttpResponse:
    """ResumeController::destroy: фото с диска, резюме — в корзину."""
    ctx = action(request)
    resume = _own(ctx)

    if resume is None:
        return not_found(ctx)

    if resume["photo_path"]:
        (public_root() / resume["photo_path"]).unlink(missing_ok=True)

    now = _stamp(eloquent.now())

    with allowed_writes("resumes"), connection.cursor() as cursor:
        cursor.execute(
            "update resumes set deleted_at = %s, updated_at = %s where id = %s",
            [now, now, resume["id"]],
        )

    flash(ctx, "status", ctx.t("messages.resume.deleted"))

    return back(ctx)


def page(request: HttpRequest) -> HttpResponse:
    """/cabinet/resume: GET — страница (cabinet.resume), PATCH — правка, DELETE — удалить."""
    from savdex.web.cabinet import resume

    if request.method == "DELETE":
        return destroy(request)

    if request.method == "PATCH":
        return update(request)

    return resume(request)


# ── Правка ───────────────────────────────────────────────────────────

#: Currencies::codes()
CURRENCIES = ("UZS", "USD", "EUR", "CNY", "TRY", "RUB", "KZT")

#: Поля-массивы с кастом array у Resume
JSON_FIELDS = ("employment", "schedule", "skills", "jobs", "education", "languages")


def _exists(table: str) -> Check:
    """exists:<таблица>,id."""

    def passes(value: Any) -> bool:  # noqa: ANN401
        if isinstance(value, dict | list) or value is None:
            return False

        try:
            key = int(str(value).strip())
        except ValueError:
            return False

        return bool(_rows(f"select 1 from {table} where id = %s limit 1", [key]))

    return Check("exists", passes)


def _rules() -> dict[str, list[str | Check]]:
    """ResumeController::validated."""
    year = datetime.now(UTC).year

    return {
        "title": ["required", "string", "min:3", "max:120"],
        "field": ["nullable", "in:" + ",".join(FIELDS)],
        "country_id": ["nullable", "integer", _exists("countries")],
        "city_id": ["nullable", "integer", _exists("cities")],
        "salary": ["nullable", "integer", "min:0", "max:1000000000"],
        "currency": ["nullable", "in:" + ",".join(CURRENCIES)],
        "employment": ["nullable", "array"],
        "employment.*": ["in:" + ",".join(EMPLOYMENT)],
        "schedule": ["nullable", "array"],
        "schedule.*": ["in:" + ",".join(SCHEDULE)],
        "about": ["nullable", "string", "max:5000"],
        "skills": ["nullable", "array", "max:30"],
        "skills.*": ["nullable", "string", "max:40"],
        "jobs": ["nullable", "array", "max:20"],
        "jobs.*.company": ["nullable", "string", "max:190"],
        "jobs.*.position": [
            "required_with:jobs.*.company",
            "nullable",
            "string",
            "max:190",
        ],
        "jobs.*.start": ["nullable", "string", "max:7"],
        "jobs.*.end": ["nullable", "string", "max:7"],
        "jobs.*.duties": ["nullable", "string", "max:2000"],
        "education": ["nullable", "array", "max:10"],
        "education.*.institution": ["nullable", "string", "max:190"],
        "education.*.faculty": ["nullable", "string", "max:190"],
        "education.*.level": ["nullable", "in:" + ",".join(EDUCATION_LEVELS)],
        "education.*.year": ["nullable", "integer", f"between:1950,{year + 10}"],
        "languages": ["nullable", "array", "max:10"],
        "languages.*.name": ["nullable", "string", "max:40"],
        "languages.*.level": ["nullable", "in:" + ",".join(LANGUAGE_LEVELS)],
        "contact_name": ["nullable", "string", "max:190"],
        "contact_phone": ["nullable", "string", "max:32"],
        "contact_email": ["nullable", "email", "max:190"],
        "show_phone": ["boolean"],
        "show_email": ["boolean"],
    }


def _php_str(value: Any) -> str:  # noqa: ANN401
    """(string) $value."""
    if value is None or value is False:
        return ""

    if value is True:
        return "1"

    return str(value)


def _clean(rows: Any, required: tuple[str, ...]) -> list[Any]:  # noqa: ANN401
    """ResumeController::clean: карточка, где заполнено хоть одно из полей."""
    items = rows.values() if isinstance(rows, dict) else rows or []

    return [
        row
        for row in items
        if isinstance(row, dict)
        and any(_php_str(row.get(k)).strip(" \t\n\r\0\x0b") != "" for k in required)
    ]


def _month(value: Any) -> date | None:  # noqa: ANN401
    """Resume::month: «2019-04» или «2019» — первое число месяца; мусор — None."""
    found = re.match(r"(\d{4})(?:-(\d{1,2}))?", _php_str(value).strip(" \t\n\r\0\x0b"), re.ASCII)

    if found is None:
        return None

    year = int(found.group(1))
    month = max(1, min(12, int(found.group(2)))) if found.group(2) else 1

    if year < 1950 or year > datetime.now(UTC).year + 1:
        return None

    return date(year, month, 1)


def experience_months(jobs: list[Any]) -> int:
    """Resume::experienceMonths: пересекающиеся периоды не складываются дважды."""
    today = datetime.now(UTC).date().replace(day=1)
    periods = []

    for job in jobs:
        start = _month(job.get("start") if isinstance(job, dict) else None)

        if start is None:
            continue

        end = _month(job.get("end")) or today

        if end < start:
            continue

        periods.append((start, end))

    periods.sort(key=lambda p: p[0])
    months = 0
    cursor: date | None = None

    for start, end in periods:
        if cursor is not None and start <= cursor:
            start = cursor

        if end <= start:
            continue

        months += (end.year - start.year) * 12 + end.month - start.month
        cursor = end

    return min(months, 65_000)


def _json_same(before: Any, after: Any) -> bool:  # noqa: ANN401
    """Каст array: сравниваются разобранные значения строго (порядок ключей, типы)."""
    return json.dumps(before) == json.dumps(after)


def _bool(value: Any) -> bool:  # noqa: ANN401
    return value in (True, 1, "1", "true")


@form("PATCH")
def update(request: HttpRequest) -> HttpResponse:
    """ResumeController::update."""
    ctx = action(request)
    assert ctx.user is not None
    data = input_of(request)
    rules = _rules()
    errors = validate(data, rules, ctx.locale)

    if errors:
        return invalid(ctx, errors)

    fields = validated(data, rules)
    fields["jobs"] = _clean(fields.get("jobs"), ("company", "position"))
    fields["education"] = _clean(fields.get("education"), ("institution",))
    fields["languages"] = _clean(fields.get("languages"), ("name",))
    skills = fields.get("skills") or []
    fields["skills"] = [
        t
        for t in (
            _php_str(v).strip(" \t\n\r\0\x0b")
            for v in (skills.values() if isinstance(skills, dict) else skills)
        )
        if t != ""
    ]

    for key in ("show_phone", "show_email"):
        if key in fields:
            fields[key] = _bool(fields[key])

    fields["experience_months"] = experience_months(fields["jobs"])
    resume = _own(ctx)
    now = _stamp(eloquent.now())

    if resume is None:
        _insert(ctx, fields, now)
    else:
        _update(resume, fields, now)

    flash(ctx, "status", ctx.t("messages.resume.saved"))

    return back(ctx)


def _value(key: str, value: Any) -> Any:  # noqa: ANN401
    """Значение для записи: массивы — текстом json_encode, как каст array."""
    return (
        None
        if value is None and key in JSON_FIELDS
        else (_php_json(value) if key in JSON_FIELDS else value)
    )


def _insert(ctx: Context, fields: dict[str, Any], now: str) -> None:
    """Новое резюме, затем адрес из заголовка и номера (saveQuietly)."""
    assert ctx.user is not None
    row = {**fields, "user_id": ctx.user["id"]}
    columns = list(row)

    with allowed_writes("resumes"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into resumes ({', '.join(columns)}, updated_at, created_at) "
            f"values ({', '.join(['%s'] * len(columns))}, %s, %s) returning id",
            [*(_value(c, row[c]) for c in columns), now, now],
        )
        resume_id = cursor.fetchone()[0]
        slug = slugify(str(fields["title"]))[:60].rstrip() + f"-{resume_id}"
        cursor.execute(
            "update resumes set slug = %s, updated_at = %s where id = %s",
            [slug, now, resume_id],
        )


def _update(resume: dict[str, Any], fields: dict[str, Any], now: str) -> None:
    """fill()->save(): только изменившееся; saving сбрасывает переводы правленого."""
    dirty = {}

    for key, value in fields.items():
        before = resume.get(key)

        if key in JSON_FIELDS:
            same = _json_same(before, value)
        elif key in ("show_phone", "show_email"):
            same = bool(before) is bool(value)
        else:
            same = eloquent._same(before, value)

        if not same:
            dirty[key] = value

    for field in ("title", "about", "jobs"):
        if field in dirty and resume.get(f"{field}_i18n") is not None:
            dirty[f"{field}_i18n"] = None

    if dirty:
        sets = ", ".join(f"{c} = %s" for c in dirty)

        with allowed_writes("resumes"), connection.cursor() as cursor:
            cursor.execute(
                f"update resumes set {sets}, updated_at = %s where id = %s",
                [*(_value(c, v) for c, v in dirty.items()), now, resume["id"]],
            )

    # Адрес — и когда правок нет: save() без изменений, затем saveQuietly
    if not resume["slug"]:
        slug = slugify(str(fields["title"]))[:60].rstrip() + f"-{resume['id']}"

        with allowed_writes("resumes"), connection.cursor() as cursor:
            cursor.execute(
                "update resumes set slug = %s, updated_at = %s where id = %s",
                [slug, now, resume["id"]],
            )


# ── Фото резюме (этап 5, шаг 44) ────────────────────────────────────

#: Правило image у Laravel: картинка по содержимому, без svg
IMAGE_MIMES = "jpg,jpeg,png,gif,bmp,webp"


@form()
def photo(request: HttpRequest) -> HttpResponse:
    """
    ResumeController::photo — сразу рабочая. У Laravel каждая загрузка
    кончается ошибкой 500 (размер [400, 400] вместо ['w' => 400, 'h' => 400]);
    по решению владельца форма переезжает исправленной: фото 400×400
    в WebP (ImageStore::THUMB), прежнее удаляется после замены.
    """
    from savdex.web import image_store

    ctx = action(request)
    data: dict[str, Any] = {**input_of(request), **request.FILES.dict()}
    # Правило image: файл-картинка по содержимому, текст ошибки — validation.image
    image = Check("image", lambda value: _passes("mimes", IMAGE_MIMES, value))
    errors = validate(data, {"photo": ["required", image, "max:5120"]}, ctx.locale)

    if errors:
        return invalid(ctx, errors)

    resume = _own(ctx)

    if resume is None:
        return not_found(ctx)

    try:
        upload = data["photo"]
        assert isinstance(upload, UploadedFile)
        path = image_store.store(upload.read(), "resumes", image_store.THUMB)
    except image_store.UnreadableImageError:
        return invalid(ctx, {"photo": [ctx.t("messages.image.none_readable")]})

    previous = resume["photo_path"]
    _save(ctx, resume, {"photo_path": path})
    image_store.delete(previous)
    flash(ctx, "status", ctx.t("messages.resume.photo_saved"))

    return back(ctx)
