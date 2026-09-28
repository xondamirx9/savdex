"""
Своё резюме — формы на Django (этап 5, шаг 28): опубликовать, скрыть и
удалить. Копия App\\Http\\Controllers\\Cabinet\\ResumeController
(publish, hide, destroy); правка и фото — отдельным шагом.

Резюме в журнал администратора не пишется. Перевод опубликованного
подбирает обработчик Python (manage.py translate), задачу ставить не
нужно. Удаление мягкое; фото уходит с публичного диска.

Сверка с настоящим Laravel — tests/test_web_resume_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.laravel_storage import public_root
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import _rows
from savdex.web.forms import _store, action, back, flash
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context
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
    """/cabinet/resume: GET — страница (cabinet.resume), DELETE — удалить резюме."""
    from savdex.web.cabinet import resume

    if request.method == "DELETE":
        return destroy(request)

    return resume(request)
