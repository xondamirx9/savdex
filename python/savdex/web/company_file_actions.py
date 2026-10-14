"""
Файлы компании — формы на Django (этап 5, шаг 42): загрузить, показать
или скрыть на визитке, удалить. Копия
App\\Http\\Controllers\\Cabinet\\CompanyFileController.

Файлы лежат на приватном диске Laravel (storage/app/private), имя —
40 случайных знаков и расширение по содержимому (UploadedFile::store):
тип определяет libmagic, как finfo у PHP (savdex/web/filetype.py).
Документы для верификации ждут модератора, материалам он не нужен.
У администратора — строки журнала (AuditObserver, раздел documents).

Сверка с настоящим Laravel — tests/test_web_company_file_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.laravel_storage import private_root
from savdex.web import eloquent, filetype
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.company_contact_actions import _php_boolean
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.image_store import _random
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context
from savdex.web.validation import _strtotime, validate, validated
from savdex.web.views import not_found

#: CompanyDocument::VERIFICATION_TYPES и ::MATERIAL_TYPES
VERIFICATION_TYPES = ("registration", "license", "certificate", "quality")
MATERIAL_TYPES = ("presentation", "price_list", "catalog", "other")

#: CompanyDocument::ALLOWED_MIMES и ::MAX_SIZE_KB
ALLOWED_MIMES = ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "jpg", "jpeg", "png", "zip")
MAX_SIZE_KB = 20480

CASTS = {"is_public": "bool", "file_size": "int"}


def _owned(ctx: Context, document_id: int) -> dict[str, Any] | None:
    """CompanyFileController::owned: файл своей компании, иначе None (404)."""
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from company_documents where company_id = %s and id = %s",
        [company["id"], document_id],
    )

    return rows[0] if rows else None


def _date_attribute(value: Any) -> str | None:  # noqa: ANN401
    """Приведение date при записи (fromDateTime): «Y-m-d H:i:s»."""
    if value is None:
        return None

    parsed = _strtotime(value)
    assert parsed is not None

    return parsed[0].strftime("%Y-%m-%d %H:%M:%S")


@form()
def store(request: HttpRequest) -> HttpResponse:
    """CompanyFileController::store (throttle:20,60)."""
    ctx = action(request, throttle=20, throttle_minutes=60, throttle_prefix="company-file")
    company = company_of(ctx)

    if company is None:
        flash(ctx, "error", ctx.t("messages.company.fill_first"))

        return back(ctx)

    data: dict[str, Any] = {**input_of(request), **request.FILES.dict()}
    rules: dict[str, list[str | Any]] = {
        "type": ["required", "in:" + ",".join((*VERIFICATION_TYPES, *MATERIAL_TYPES))],
        "title": ["required", "string", "max:190"],
        "file": ["required", "file", "mimes:" + ",".join(ALLOWED_MIMES), f"max:{MAX_SIZE_KB}"],
        "valid_until": ["nullable", "date", "after:today"],
        "is_public": ["boolean"],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "title.required": ctx.t("messages.file.title_required"),
            "file.required": ctx.t("messages.file.required"),
            "file.mimes": ctx.t("messages.file.mimes"),
            "file.max": ctx.t("messages.file.max"),
            "valid_until.after": ctx.t("messages.file.expired"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    valid = validated(data, rules)
    upload = data["file"]
    assert isinstance(upload, UploadedFile)
    content = upload.read()
    extension = filetype.guess_extension(content)
    path = f"companies/{company['id']}/documents/{_random(40)}" + (
        f".{extension}" if extension else ""
    )

    # Сбой записи — ответ человеку, а не страница 500
    try:
        target = private_root() / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    except OSError:
        flash(ctx, "error", ctx.t("messages.file.save_failed"))

        return back(ctx)

    material = valid["type"] in MATERIAL_TYPES
    now = _stamp(eloquent.now())
    row: dict[str, Any] = {
        "company_id": company["id"],
        "type": valid["type"],
        "title": valid["title"],
        "file_path": path,
        "file_size": upload.size,
        # Тип присылает браузер: внешние данные, обрезка до ширины колонки
        "mime": (upload.content_type or "application/octet-stream")[:255],
        "valid_until": _date_attribute(valid.get("valid_until")),
        "is_public": _php_boolean(data.get("is_public", True)),
        "moderation_status": "approved" if material else "pending",
        "updated_at": now,
        "created_at": now,
    }
    columns = list(row)

    with allowed_writes("company_documents"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into company_documents ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            list(row.values()),
        )
        row["id"] = cursor.fetchone()[0]

    eloquent.journal(ctx, "created", "documents", "CompanyDocument", row, {"after": dict(row)})

    if not material:
        from savdex import product_events

        product_events.record(
            "verification_submitted",
            company_id=company["id"],
            user_id=ctx.user["id"] if ctx.user else None,
            plan=product_events.plan_code(company["id"]),
            locale=ctx.locale,
            props={"document_id": row["id"], "document_type": row["type"]},
        )

    # Скрытый материал партнёры не видят — так и говорим
    if not material:
        message = "messages.file.document_uploaded"
    elif row["is_public"]:
        message = "messages.file.material_uploaded"
    else:
        message = "messages.file.material_uploaded_hidden"

    flash(ctx, "success", ctx.t(message))

    return back(ctx)


@form("PATCH")
def update(request: HttpRequest, document_id: str) -> HttpResponse:
    """CompanyFileController::update: показ на визитке."""
    ctx = action(request)
    document = _owned(ctx, int(document_id))

    if document is None:
        return not_found(ctx)

    shown = _php_boolean(input_of(request).get("is_public", False))
    eloquent.save(
        ctx,
        "company_documents",
        document,
        {"is_public": shown},
        section="documents",
        model="CompanyDocument",
        casts=CASTS,
    )
    flash(ctx, "success", ctx.t("messages.file.shown" if shown else "messages.file.hidden"))

    return back(ctx)


@form("DELETE")
def destroy(request: HttpRequest, document_id: str) -> HttpResponse:
    """CompanyFileController::destroy: файл с диска, строку — прочь."""
    ctx = action(request)
    document = _owned(ctx, int(document_id))

    if document is None:
        return not_found(ctx)

    (private_root() / document["file_path"]).unlink(missing_ok=True)

    with allowed_writes("company_documents"), connection.cursor() as cursor:
        cursor.execute("delete from company_documents where id = %s", [document["id"]])

    eloquent.journal(ctx, "deleted", "documents", "CompanyDocument", document, None)
    flash(ctx, "success", ctx.t("messages.file.deleted"))

    return back(ctx)


def document(request: HttpRequest, document_id: str) -> HttpResponse:
    """/cabinet/company/files/<id>: PATCH — показ, DELETE — удалить."""
    if request.method == "DELETE":
        return destroy(request, document_id)

    return update(request, document_id)
