"""
Скачивание файлов с приватного диска — как Storage::disk('local')
->download() и ->response() у Laravel (этап 5, шаг 44).

Файлы компании (/files/<номер>) и файлы IT-задачи
(/it-services/files/<номер>): доступ проверяется, как в
CompanyFileController::download и ItTaskController::file; тип — как у
Flysystem (finfo по содержимому, а для неопределённого — по
расширению), имя — человеческое, с ASCII-запасом через Str::ascii
(таблица снята с PHP, str_ascii.json) и filename* в UTF-8.

Сверка с настоящим Laravel — tests/test_web_downloads.py.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from urllib.parse import quote

from django.http import HttpRequest, HttpResponse

from savdex.laravel_storage import private_root
from savdex.web import filetype
from savdex.web.cabinet import _rows
from savdex.web.shared import Context
from savdex.web.throttle import throttled
from savdex.web.views import not_found

#: FinfoMimeTypeDetector: неопределённые ответы finfo — тип по расширению
_INCONCLUSIVE = (
    "application/x-empty",
    "text/plain",
    "text/x-asm",
    "application/octet-stream",
    "inode/x-empty",
)

#: GeneratedExtensionToMimeTypeMap — для расширений, что кладёт площадка
_BY_EXTENSION = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppz": "application/vnd.ms-powerpoint",
    "zip": "application/zip",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

_TOKEN = re.compile(r"^[a-z0-9!#$%&'*.^_`|~-]+$", re.IGNORECASE)


@cache
def _ascii_table() -> dict[str, str]:
    table: dict[str, str] = json.loads(
        (Path(__file__).with_name("str_ascii.json")).read_text(encoding="utf-8")
    )

    return table


def str_ascii(value: str) -> str:
    """Str::ascii: знак по таблице, неизвестный не-ASCII — прочь."""
    table = _ascii_table()

    return "".join(ch if ord(ch) < 128 else table.get(ch, "") for ch in value)


def _quote(value: str) -> str:
    """HeaderUtils::quote: токен как есть, иначе в кавычках."""
    if _TOKEN.match(value):
        return value

    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def disposition(kind: str, filename: str) -> str:
    """ResponseHeaderBag::makeDisposition с запасом fallbackName (Str::ascii без «%»)."""
    fallback = str_ascii(filename).replace("%", "")
    params = [f"filename={_quote(fallback)}"]

    if filename != fallback:
        params.append("filename*=" + _quote("utf-8''" + quote(filename, safe="-_.!~*'()")))

    return kind + "; " + "; ".join(params)


def mime_type(path: Path) -> str | None:
    """Flysystem LocalFilesystemAdapter::mimeType: finfo, затем расширение."""
    found = filetype.mime_type(path.read_bytes())

    if found is None or found in _INCONCLUSIVE:
        return _BY_EXTENSION.get(path.suffix.lstrip(".").lower())

    return found


def _file_response(path: Path, kind: str, name: str) -> HttpResponse:
    """FilesystemAdapter::response: тип, размер, Content-Disposition."""
    content = path.read_bytes()
    kind_of = mime_type(path)

    # Response::prepare у Symfony: текстовому типу — кодировка
    if kind_of is not None and kind_of.startswith("text/") and "charset" not in kind_of:
        kind_of += "; charset=utf-8"

    response = HttpResponse(content, content_type=kind_of)
    response["Content-Length"] = str(len(content))
    response["Content-Disposition"] = disposition(kind, name)
    response["Cache-Control"] = "no-cache, private"

    return response


def _human_name(title: str) -> str:
    """Название без слэшей и точек по краям: Content-Disposition их не принимает."""
    return re.sub(r"[/\\]+", "-", title).strip(" .-")


def _viewer_company(ctx: Context) -> int | None:
    user = ctx.user

    return None if user is None else user.get("company_id")


def company_file(request: HttpRequest, document_id: str) -> HttpResponse:
    """CompanyFileController::download (throttle:120,1)."""
    return throttled(request, 120, lambda ctx: _company_file(ctx, int(document_id)))


def _company_file(ctx: Context, document_id: int) -> HttpResponse:
    """
    Своим — всё, прочим — показанное на визитке действующей компании:
    у заблокированной и удалённой визитки нет, нет и файлов.
    """
    rows = _rows(
        "select d.*, c.status as company_status from company_documents d "
        "left join companies c on c.id = d.company_id and c.deleted_at is null "
        "where d.id = %s",
        [document_id],
    )

    if not rows:
        return not_found(ctx)

    document = rows[0]
    own = _viewer_company(ctx) == document["company_id"]
    material = document["type"] in ("presentation", "price_list", "catalog", "other")
    visible = (
        document["company_status"] == "active"
        and document["is_public"]
        and (material or document["moderation_status"] == "approved")
    )

    if not own and not visible:
        return not_found(ctx)

    path = private_root() / document["file_path"]

    if not path.is_file():
        return not_found(ctx)

    extension = path.suffix.lstrip(".")

    # Фотографии — inline: их смотрят на визитке, а не скачивают
    if extension.lower() in ("jpg", "jpeg", "png", "webp"):
        return _file_response(path, "inline", path.name)

    name = _human_name(str(document["title"]))

    return _file_response(path, "attachment", (name or "file") + "." + extension)


def it_task_file(request: HttpRequest, file_id: str) -> HttpResponse:
    """
    ItTaskController::file (auth): активной задачи действующей компании — всем,
    иначе только заказчику.
    """
    from savdex.web.cabinet import page

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    rows = _rows(
        "select f.*, t.company_id, t.status, c.status as company_status from it_task_files f "
        "join it_tasks t on t.id = f.it_task_id "
        "left join companies c on c.id = t.company_id and c.deleted_at is null "
        "where f.id = %s",
        [int(file_id)],
    )

    if not rows:
        return not_found(ctx)

    file = rows[0]
    own = _viewer_company(ctx) == file["company_id"]

    if (file["status"] != "active" or file["company_status"] != "active") and not own:
        return not_found(ctx)

    path = private_root() / file["file_path"]

    if not path.is_file():
        return not_found(ctx)

    return _file_response(path, "attachment", _human_name(str(file["title"])) or "file")
