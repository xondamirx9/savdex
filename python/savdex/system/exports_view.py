"""
Страница «Выгрузка в Excel» (шаг 68) — вместо страницы Filament
ExcelExports и DownloadExportController.

- видят те, у кого backups.view; кнопка «Выгрузить сейчас» и скачивание —
  у кого backups.export (суперадмин или выдано лично);
- запуск и каждое скачивание — строка журнала действий: в книгах почта,
  телефоны и IP всех пользователей, и вопрос «кто унёс базу» должен
  иметь ответ;
- чужой или выдуманный путь к файлу — 404, а не 403: не подтверждаем,
  что такой файл есть;
- пока выгрузка идёт, страница обновляется сама раз в пять секунд.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.template.response import TemplateResponse
from django.urls import reverse

from savdex import audit
from savdex.adminsite import _admin_of, site
from savdex.system import exports

#: Итог сверки у прежних выгрузок (PHP и Python в паре) и у нынешних
CHECKS = {
    "self": ("success", "сошлась с базой"),
    "match": ("success", "совпала с PHP"),
    "differs": ("danger", "расходится"),
    "failed": ("warning", "не удалась"),
    "timeout": ("warning", "не уложилась во время"),
    "skipped": ("gray", "не сверялась"),
}

STATES = {
    exports.QUEUED: ("gray", "в очереди"),
    exports.RUNNING: ("warning", "идёт…"),
    exports.DONE: ("success", "готово"),
    exports.FAILED: ("danger", "ошибка"),
}


def _row(run: dict[str, Any]) -> dict[str, Any]:
    python: dict[str, Any] = run["python"] if isinstance(run.get("python"), dict) else {}
    php: dict[str, Any] = run["php"] if isinstance(run.get("php"), dict) else {}
    # Старые выгрузки: книги отдавала PHP-версия, список — в php.files
    files = run.get("files") or php.get("files") or []
    tone, state = STATES.get(str(run.get("status")), STATES[exports.FAILED])
    check = CHECKS.get(str(python.get("status")))
    differences = python.get("differences")
    label = check[1] if check else ""

    if label == "расходится" and differences:
        label += f": {differences}"

    return {
        "id": run.get("id"),
        "when": exports.when(run.get("queued_at")),
        "who": run.get("requested_by") or "—",
        "status": run.get("status"),
        "state": state,
        "tone": tone,
        "note": run.get("note") or "",
        "output": php.get("output") if run.get("status") == exports.FAILED else "",
        "files": [
            {"name": file, "label": "Компании" if "companies" in file else "Объявления"}
            for file in files
            if isinstance(file, str)
        ],
        "engine": "книги Python-версии"
        if run.get("engine", "php") == "python"
        else "книги PHP-версии",
        "check": ({"tone": check[0], "label": label} if check else None),
        "check_note": python.get("note") or "",
        "problems": [str(p) for p in python.get("problems") or []],
    }


def view(request: HttpRequest) -> HttpResponse:
    admin_ = _admin_of(request)

    if not admin_.can("backups.view"):
        raise PermissionDenied

    can_export = admin_.can("backups.export")

    if request.method == "POST":
        if not can_export:
            raise PermissionDenied

        run_id = exports.create(admin_.name, admin_.id)

        if run_id is None:
            messages.warning(request, "Выгрузка уже идёт — дождитесь её.")
        else:
            audit.record(
                connection,
                action="exported",
                section="backups",
                actor=admin_,
                note=f"Выгрузка базы в Excel: {run_id}",
                ip=audit.client_ip(request),
            )
            exports.start(run_id)
            messages.success(
                request, "Выгрузка запущена. Страница обновится сама, когда файлы будут готовы."
            )

        return HttpResponseRedirect(reverse("savdex_admin:system_exports"))

    active = exports.active() is not None
    context: dict[str, Any] = {
        **site.each_context(request),
        "title": "Выгрузка в Excel",
        "lead": (
            "Вся база в двух книгах: компании и объявления. Файлы хранятся на постоянном "
            "диске, деплой их не стирает."
        ),
        "runs": [_row(run) for run in exports.all_runs()],
        "active": active,
        "can_export": can_export,
        "keep": exports.keep(),
    }

    return TemplateResponse(request, "admin/system/exports.html", context)


def download(request: HttpRequest, run_id: str, file: str) -> HttpResponseBase:
    if not _admin_of(request).can("backups.export"):
        raise PermissionDenied

    path = exports.book_path(run_id, file)

    # 404, а не 403: чужой или выдуманный путь не должен подтверждать,
    # что такой файл существует
    if path is None:
        raise Http404

    audit.record(
        connection,
        action="downloaded",
        section="backups",
        actor=_admin_of(request),
        note=f"Скачан файл выгрузки {run_id}/{file}",
        ip=audit.client_ip(request),
    )

    return FileResponse(path.open("rb"), as_attachment=True, filename=file)
