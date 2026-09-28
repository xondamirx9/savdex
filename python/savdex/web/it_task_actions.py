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
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.forms import action, back, flash, input_of, invalid, redirect
from savdex.web.search_text import index
from savdex.web.shared import Context
from savdex.web.validation import validate
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
