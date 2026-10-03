"""
IT-задачи своей компании — формы на Django (этап 5, шаг 27): закрыть,
отметить выполненной, открыть заново, удалить задачу и файл задачи.
Копия App\\Http\\Controllers\\Cabinet\\ItTaskController.

Запись — как Eloquent (savdex.web.eloquent): изменившиеся поля,
search_text (событие saving у ItTask), у администратора — строка
журнала (раздел ittasks). Удаление задачи — настоящее: файлы с диска
local, строки файлов и разговоров уходят каскадом внешних ключей.

Сверка с настоящим Laravel — tests/test_web_it_task_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.laravel_storage import private_root
from savdex.web import eloquent, filetype
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.chat_actions import _unverified
from savdex.web.forms import action, back, flash, input_of, invalid, redirect
from savdex.web.image_store import _random
from savdex.web.listing_actions import _stamp, refuse_blocked
from savdex.web.search_text import index
from savdex.web.shared import Context
from savdex.web.validation import _strtotime, validate, validated
from savdex.web.views import not_found

ACTIVE, CLOSED, COMPLETED = "active", "closed", "completed"


def _search_text(task: dict[str, Any]) -> dict[str, Any]:
    """ItTask saving: search_text из заголовка, описания и стека."""
    stack = task["stack"] if isinstance(task["stack"], list) else []
    parts = [task["title"], task["description"] or "", " ".join(str(t) for t in stack)]

    return {"search_text": index(" ".join(p for p in parts if p not in (None, "", "0")))}


def _owned(ctx: Context, task_id: int) -> dict[str, Any] | None:
    """ItTaskController::owned: задача своей компании, иначе None (404)."""
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from it_tasks where company_id = %s and id = %s", [company["id"], task_id]
    )

    return rows[0] if rows else None


def _save(ctx: Context, task: dict[str, Any], changes: dict[str, Any]) -> None:
    eloquent.save(
        ctx, "it_tasks", task, changes, section="ittasks", model="ItTask", saving=_search_text
    )


def _delete_file(path: str | None) -> None:
    """Storage::disk('local')->delete(): нет файла — не ошибка."""
    if path:
        (private_root() / path).unlink(missing_ok=True)


@form()
def close(request: HttpRequest, task_id: str) -> HttpResponse:
    """ItTaskController::close: только открытую."""
    ctx = action(request)
    task = _owned(ctx, int(task_id))

    if task is None:
        return not_found(ctx)

    if task["status"] == ACTIVE:
        _save(ctx, task, {"status": CLOSED, "closed_at": eloquent.now()})

    flash(ctx, "success", ctx.t("messages.it_task.closed"))

    return back(ctx)


@form()
def complete(request: HttpRequest, task_id: str) -> HttpResponse:
    """ItTaskController::complete: исполнитель — только из откликнувшихся."""
    ctx = action(request)
    task = _owned(ctx, int(task_id))

    if task is None:
        return not_found(ctx)

    # Завершённая уже подведена: повторный запрос не переписывает итог и исполнителя
    if task["status"] == COMPLETED:
        flash(ctx, "success", ctx.t("messages.it_task.completed"))

        return back(ctx)

    responders = [
        str(r["buyer_company_id"])
        for r in _rows(
            "select buyer_company_id from message_threads where it_task_id = %s", [task["id"]]
        )
    ]
    data = input_of(request)
    errors = validate(
        data,
        {
            "result_url": ["nullable", "url", "max:255"],
            "result_summary": ["nullable", "string", "max:600"],
            "contractor_company_id": ["nullable", "integer", "in:" + ",".join(responders)],
        },
        ctx.locale,
        {
            "result_url.url": ctx.t("messages.it_task.url"),
            "contractor_company_id.in": ctx.t("messages.it_task.contractor_in"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    now = eloquent.now()
    _save(
        ctx,
        task,
        {
            "status": COMPLETED,
            "completed_at": now,
            "closed_at": task["closed_at"] or now,
            "result_url": data.get("result_url"),
            "result_summary": data.get("result_summary"),
            "contractor_company_id": data.get("contractor_company_id"),
        },
    )
    flash(ctx, "success", ctx.t("messages.it_task.completed"))

    return back(ctx)


@form()
def reopen(request: HttpRequest, task_id: str) -> HttpResponse:
    """ItTaskController::reopen: снова на витрину, срок не трогаем."""
    ctx = action(request)
    task = _owned(ctx, int(task_id))

    if task is None:
        return not_found(ctx)

    if (refused := refuse_blocked(ctx, task["company_id"])) is not None:
        return refused

    if task["status"] != ACTIVE:
        _save(
            ctx,
            task,
            {"status": ACTIVE, "closed_at": None, "published_at": eloquent.now()},
        )

    flash(ctx, "success", ctx.t("messages.it_task.reopened"))

    return back(ctx)


@form("DELETE")
def destroy(request: HttpRequest, task_id: str) -> HttpResponse:
    """ItTaskController::destroy: файлы с диска, задача — насовсем."""
    ctx = action(request)
    task = _owned(ctx, int(task_id))

    if task is None:
        return not_found(ctx)

    for file in _rows(
        "select file_path from it_task_files where it_task_id = %s order by id", [task["id"]]
    ):
        _delete_file(file["file_path"])

    with allowed_writes("it_tasks"), connection.cursor() as cursor:
        cursor.execute("delete from it_tasks where id = %s", [task["id"]])

    eloquent.journal(ctx, "deleted", "ittasks", "ItTask", task, None)
    flash(ctx, "success", ctx.t("messages.it_task.deleted"))

    return redirect(ctx, ctx.url("/cabinet/it-tasks"))


@form("DELETE")
def destroy_file(request: HttpRequest, task_id: str, file_id: str) -> HttpResponse:
    """ItTaskController::destroyFile."""
    ctx = action(request)
    task = _owned(ctx, int(task_id))

    if task is None:
        return not_found(ctx)

    files = _rows(
        "select * from it_task_files where it_task_id = %s and id = %s",
        [task["id"], int(file_id)],
    )

    if not files:
        return not_found(ctx)

    _delete_file(files[0]["file_path"])

    with allowed_writes("it_task_files"), connection.cursor() as cursor:
        cursor.execute("delete from it_task_files where id = %s", [files[0]["id"]])

    flash(ctx, "success", ctx.t("messages.file.deleted"))

    return back(ctx)


# ── Создать и изменить (этап 5, шаг 43) ────────────────────────────

#: ItTask::SERVICE_TYPES, ::BUDGET_TYPES, ::CURRENCIES, ::MAX_STACK
SERVICE_TYPES = (
    "web", "mobile", "erp", "integration", "design", "automation", "support",
    "logistics", "hr", "customs", "accounting", "other",
)  # fmt: skip
BUDGET_TYPES = ("fixed", "range", "negotiable")
CURRENCIES = ("UZS", "USD")
MAX_STACK = 10

#: ItTaskFile::ALLOWED_MIMES, ::MAX_SIZE_KB, ::MAX_FILES
FILE_MIMES = (
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "zip",
)
FILE_MAX_KB = 20480
MAX_FILES = 5

CASTS = {
    "stack": "json",
    "budget_from": "decimal:2",
    "budget_to": "decimal:2",
    "deadline_at": "date",
}


def _uploads(request: HttpRequest) -> list[Any]:
    """$request->file('files', []): files[] или files[0], files[1]…"""
    files = list(request.FILES.getlist("files[]"))

    indexed = [k for k in request.FILES if k.startswith("files[") and k != "files[]"]

    for key in sorted(
        indexed,
        key=lambda k: (not k[6:-1].isdigit(), int(k[6:-1] or 0) if k[6:-1].isdigit() else 0, k),
    ):
        files += request.FILES.getlist(key)

    return files


def _validated(ctx: Context, request: HttpRequest) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """ItTaskController::validated: данные формы и ошибки."""
    data: dict[str, Any] = {**input_of(request)}
    files = _uploads(request)

    if files:
        data["files"] = files

    rules: dict[str, list[str | Any]] = {
        "title": ["required", "string", "min:10", "max:120"],
        "description": ["required", "string", "min:30", "max:8000"],
        "service_type": ["required", "in:" + ",".join(SERVICE_TYPES)],
        "stack": ["nullable", "array", f"max:{MAX_STACK}"],
        "stack.*": ["string", "max:30"],
        "budget_type": ["required", "in:" + ",".join(BUDGET_TYPES)],
        "budget_from": [
            "nullable", "numeric", "min:0", "max:99999999999",
            "required_if:budget_type,fixed,range",
        ],
        "budget_to": [
            "nullable", "numeric", "min:0", "max:99999999999",
            "required_if:budget_type,range", "gte:budget_from",
        ],
        "currency": ["required", "in:" + ",".join(CURRENCIES)],
        "deadline_at": ["nullable", "date", "after:today"],
        "files": ["nullable", "array", f"max:{MAX_FILES}"],
        "files.*": ["file", "mimes:" + ",".join(FILE_MIMES), f"max:{FILE_MAX_KB}"],
    }  # fmt: skip
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "title.required": ctx.t("messages.it_task.title_required"),
            "title.min": ctx.t("messages.it_task.title_min"),
            "description.required": ctx.t("messages.it_task.description_required"),
            "description.min": ctx.t("messages.it_task.description_min"),
            "budget_from.required_if": ctx.t("messages.it_task.budget_required"),
            "budget_to.required_if": ctx.t("messages.it_task.budget_to_required"),
            "budget_to.gte": ctx.t("messages.it_task.budget_to_gte"),
            "deadline_at.after": ctx.t("messages.it_task.deadline_future"),
            "files.max": ctx.t("messages.it_task.files_max", max=MAX_FILES),
            "files.*.mimes": ctx.t("messages.it_task.files_mimes"),
            "files.*.max": ctx.t("messages.it_task.files_size"),
        },
    )

    if errors:
        return {}, errors

    valid = validated(data, rules)
    tags = valid.get("stack") or []
    tags = list(tags.values()) if isinstance(tags, dict) else list(tags)
    stack: list[str] = []

    # Стек — чистые непустые строки без дублей
    for tag in tags:
        text = "" if tag is None else str(tag).strip(" \t\n\r\0\x0b")

        if text not in ("", "0") and text not in stack:
            stack.append(text)

    valid["stack"] = stack

    if valid["budget_type"] == "negotiable":
        valid["budget_from"] = None
        valid["budget_to"] = None
    elif valid["budget_type"] == "fixed":
        valid["budget_to"] = None

    valid.pop("files", None)

    if valid.get("deadline_at") is not None:
        parsed = _strtotime(valid["deadline_at"])
        assert parsed is not None
        # Приведение date при записи: «Y-m-d H:i:s»
        valid["deadline_at"] = parsed[0].strftime("%Y-%m-%d %H:%M:%S")

    return valid, {}


def _store_files(task_id: int, files: list[Any]) -> None:
    """ItTaskController::storeFiles: сколько влезет до пяти, имя на диске — случайное."""
    room = MAX_FILES - int(
        _rows("select count(*) as n from it_task_files where it_task_id = %s", [task_id])[0]["n"]
    )

    for upload in files[: max(0, room)]:
        content = upload.read()
        extension = filetype.guess_extension(content)
        path = f"it-tasks/{task_id}/{_random(40)}" + (f".{extension}" if extension else "")

        try:
            target = private_root() / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        except OSError:
            continue

        now = _stamp(eloquent.now())

        with allowed_writes("it_task_files"), connection.cursor() as cursor:
            cursor.execute(
                "insert into it_task_files (it_task_id, title, file_path, file_size, mime, "
                "updated_at, created_at) values (%s, %s, %s, %s, %s, %s, %s)",
                [
                    task_id,
                    str(upload.name or "")[:190],
                    path,
                    upload.size or 0,
                    (upload.content_type or "application/octet-stream")[:255],
                    now,
                    now,
                ],
            )


@form()
def store(request: HttpRequest) -> HttpResponse:
    """ItTaskController::store (verified, throttle:20,60): сразу на витрину."""
    ctx = action(request, throttle=20, throttle_minutes=60, throttle_prefix="task-create")

    if (refused := _unverified(ctx)) is not None:
        return refused

    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    if (refused := refuse_blocked(ctx, company["id"])) is not None:
        return refused

    valid, errors = _validated(ctx, request)

    if errors:
        return invalid(ctx, errors)

    now = _stamp(eloquent.now())
    row: dict[str, Any] = {
        **valid,
        "company_id": company["id"],
        "user_id": ctx.user["id"],
        "status": ACTIVE,
        "published_at": now,
    }
    row.update(_search_text(row))
    row.update(updated_at=now, created_at=now)
    columns = list(row)

    with allowed_writes("it_tasks"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into it_tasks ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [eloquent._written(CASTS.get(c), row[c]) for c in columns],
        )
        row["id"] = cursor.fetchone()[0]
        # Событие created: адрес из заголовка и номера, запись без событий
        row["slug"] = _task_slug(str(row["title"]), row["id"])
        row["updated_at"] = _stamp(eloquent.now())
        cursor.execute(
            "update it_tasks set slug = %s, updated_at = %s where id = %s",
            [row["slug"], row["updated_at"], row["id"]],
        )

    after = {c: eloquent._written(CASTS.get(c), v) for c, v in row.items()}
    eloquent.journal(ctx, "created", "ittasks", "ItTask", row, {"after": after})
    _store_files(row["id"], _uploads(request))
    flash(ctx, "success", ctx.t("messages.it_task.published"))

    return redirect(ctx, ctx.url("/cabinet/it-tasks"))


def _task_slug(title: str, task_id: int) -> str:
    """ItTask::makeSlug: Str::slug(Str::transliterate(…)), до 60 знаков, и номер."""
    from savdex.tenders.slug import slugify

    return (slugify(title) or "task")[:60].rstrip() + f"-{task_id}"


@form("PATCH")
def update(request: HttpRequest, task_id: str) -> HttpResponse:
    """ItTaskController::update: fill и save, затем новые файлы."""
    ctx = action(request)
    task = _owned(ctx, int(task_id))

    if task is None:
        return not_found(ctx)

    valid, errors = _validated(ctx, request)

    if errors:
        return invalid(ctx, errors)

    eloquent.save(
        ctx,
        "it_tasks",
        task,
        valid,
        section="ittasks",
        model="ItTask",
        saving=_search_text,
        casts=CASTS,
    )
    _store_files(task["id"], _uploads(request))
    flash(ctx, "success", ctx.t("messages.it_task.updated"))

    return redirect(ctx, ctx.url("/cabinet/it-tasks"))


def _spoofed(request: HttpRequest) -> str:
    """Request::getMethod с подменой: POST и _method (или заголовок) — PATCH, DELETE…"""
    if request.method != "POST":
        return str(request.method)

    header = request.headers.get("X-HTTP-Method-Override")
    method = header or input_of(request).get("_method") or "POST"

    return str(method).upper() if isinstance(method, str) else "POST"


def task(request: HttpRequest, task_id: str) -> HttpResponse:
    """/cabinet/it-tasks/<id>: PATCH (форма с файлами — POST и _method) и DELETE."""
    method = _spoofed(request)

    if method in ("PATCH", "DELETE"):
        request.method = method

    if request.method == "DELETE":
        return destroy(request, task_id)

    return update(request, task_id)


def tasks(request: HttpRequest) -> HttpResponse:
    """/cabinet/it-tasks: GET — список, POST — новая задача."""
    from savdex.web.cabinet import it_tasks

    if request.method == "POST":
        return store(request)

    return it_tasks(request)
