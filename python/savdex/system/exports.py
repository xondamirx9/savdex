"""
Выгрузки базы в Excel из админки — копия App\\Support\\DatabaseExports на
Django (шаг 68, вместо страницы Filament ExcelExports).

Каждая выгрузка — папка на постоянном диске, та же, что у Laravel
(storage/app/private/exports), поэтому история прежних выгрузок видна:

  exports/2026-09-26-125530-ab12/
    run.json                   — кто, когда, чем кончилось
    savdex-companies-….xlsx    — книги, которые скачивают
    savdex-listings-….xlsx

Книги пишет manage.py export_xlsx (savdex/management/commands) и сам
сверяет каждую ячейку с базой; отдаётся только сошедшаяся книга. Сверки
с PHP-версией больше нет: пять боевых выгрузок подряд совпали с ней, и
Python давно основная версия — PHP-выгрузка уходит вместе с Laravel.

Выгрузка идёт фоновым процессом (manage.py run_export <номер>), а не
в запросе: она читает всю базу минуту-другую. Две сразу не запускаются.
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"

#: Номер выгрузки: время и хвост от совпадения в одну секунду
ID = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}-[a-z0-9]{4}$")

#: Имя книги, которую можно скачать
BOOK = re.compile(r"^savdex-(companies|listings)-[0-9-]+\.xlsx$")

#: Метка строки итога в выводе export_xlsx
RESULT = "SAVDEX-RESULT "

#: config('exports.stale_minutes'): зависшая дольше — прервана
STALE_MINUTES = 30


def root() -> Path:
    """Storage::disk('local') + config('exports.directory')."""
    configured = os.environ.get("SAVDEX_EXPORTS_DIR")

    if configured:
        return Path(configured)

    return Path(settings.LARAVEL_ROOT) / "storage/app/private/exports"


def keep() -> int:
    """config('exports.keep'): сколько последних выгрузок хранить."""
    try:
        return max(1, int(os.environ.get("EXPORTS_KEEP", "10")))
    except ValueError:
        return 10


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(moment: datetime) -> str:
    """now()->toIso8601String(): 2026-09-30T15:00:00+00:00."""
    return moment.isoformat()


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


# ── История ─────────────────────────────────────────────────────────


def find(run_id: str) -> dict[str, Any] | None:
    if not ID.fullmatch(run_id):
        return None

    try:
        data = json.loads((root() / run_id / "run.json").read_text())
    except (OSError, ValueError):
        return None

    return data if isinstance(data, dict) else None


def _with_staleness(run: dict[str, Any]) -> dict[str, Any]:
    if run.get("status") not in (QUEUED, RUNNING):
        return run

    since = _parse(run.get("started_at") or run.get("queued_at"))

    if since is not None and (_now() - since).total_seconds() >= STALE_MINUTES * 60:
        return {
            **run,
            "status": FAILED,
            "note": f"прервана: не закончилась за {STALE_MINUTES} минут",
        }

    return run


def all_runs() -> list[dict[str, Any]]:
    """Все выгрузки, новые сверху."""
    try:
        names = [p.name for p in root().iterdir() if p.is_dir()]
    except OSError:
        return []

    runs = [_with_staleness(run) for name in names if (run := find(name)) is not None]

    return sorted(runs, key=lambda run: str(run.get("id")), reverse=True)


def active() -> dict[str, Any] | None:
    """Идущая или ждущая выгрузка, если есть."""
    return next((run for run in all_runs() if run.get("status") in (QUEUED, RUNNING)), None)


def books(run_id: str) -> list[str]:
    try:
        return sorted(
            p.name for p in (root() / run_id).iterdir() if p.is_file() and BOOK.fullmatch(p.name)
        )
    except OSError:
        return []


def book_path(run_id: str, file: str) -> Path | None:
    """Путь к книге, только если она настоящая: номер и имя — по шаблону."""
    if not ID.fullmatch(run_id) or not BOOK.fullmatch(file):
        return None

    path = root() / run_id / file

    return path if path.is_file() else None


def _save(run_id: str, run: dict[str, Any]) -> None:
    folder = root() / run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=4))


def _update(run_id: str, changes: dict[str, Any]) -> None:
    _save(run_id, {**(find(run_id) or {"id": run_id}), **changes})


def prune() -> None:
    """Хранятся последние keep() выгрузок; идущие не трогаются."""
    for run in all_runs()[keep() :]:
        if run.get("status") in (QUEUED, RUNNING):
            continue

        shutil.rmtree(root() / str(run["id"]), ignore_errors=True)


# ── Запуск ──────────────────────────────────────────────────────────


def create(requested_by: str, requested_by_id: int | None) -> str | None:
    """Завести выгрузку. None — одна уже идёт."""
    if active() is not None:
        return None

    alphabet = string.ascii_lowercase + string.digits
    run_id = (
        _now().strftime("%Y-%m-%d-%H%M%S")
        + "-"
        + "".join(secrets.choice(alphabet) for _ in range(4))
    )
    _save(
        run_id,
        {
            "id": run_id,
            "status": QUEUED,
            "requested_by": requested_by,
            "requested_by_id": requested_by_id,
            "queued_at": _iso(_now()),
        },
    )

    return run_id


def start(run_id: str) -> None:
    """
    Фоновый процесс manage.py run_export — отдельно от запроса.

    Через короткий sh, который сразу выходит: выгрузка достаётся init,
    и у процесса gunicorn не копятся зомби от каждого нажатия.
    """
    subprocess.run(
        [
            "/bin/sh",
            "-c",
            '"$@" </dev/null >/dev/null 2>&1 &',
            "sh",
            sys.executable,
            str(Path(settings.BASE_DIR) / "manage.py"),
            "run_export",
            run_id,
        ],
        cwd=str(settings.BASE_DIR),
        check=True,
        start_new_session=True,
    )


def run(run_id: str) -> None:
    """DatabaseExports::run: книги Python-версии, со сверкой с базой."""
    from django.core.management import call_command

    if find(run_id) is None:
        return

    _update(run_id, {"status": RUNNING, "started_at": _iso(_now())})
    out, err = io.StringIO(), io.StringIO()

    try:
        call_command("export_xlsx", dir=str(root() / run_id), json=True, stdout=out, stderr=err)
    except SystemExit:
        pass  # расхождения — итог прочтём ниже
    except Exception as error:
        err.write(str(error))

    line = next((ln for ln in out.getvalue().splitlines() if ln.startswith(RESULT)), None)
    data: dict[str, Any] = json.loads(line[len(RESULT) :]) if line else {}
    self_check = bool(data.get("self_check"))
    files = books(run_id)

    if self_check and len(files) == 2:
        _update(
            run_id,
            {
                "status": DONE,
                "engine": "python",
                "files": files,
                "python": {"status": "self", "self_check": True},
                "finished_at": _iso(_now()),
            },
        )
    else:
        # Несошедшиеся или недописанные книги не отдаются
        for file in files:
            (root() / run_id / file).unlink(missing_ok=True)

        problems = list(data.get("self_problems") or [])[:20]
        _update(
            run_id,
            {
                "status": FAILED,
                "engine": "python",
                "python": {
                    "status": "failed" if not line else "differs",
                    "self_check": self_check,
                    "problems": problems,
                    "note": (err.getvalue() or out.getvalue()).strip()[-2000:] or None,
                },
                "note": "выгрузка не сошлась с базой" if line else "выгрузка не удалась",
                "finished_at": _iso(_now()),
            },
        )

    prune()


def when(value: str | None) -> str:
    """ExcelExports::when: время по Ташкенту, «d.m.Y H:i»."""
    from zoneinfo import ZoneInfo

    moment = _parse(value)

    if moment is None:
        return "—"

    return moment.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%d.%m.%Y %H:%M")
