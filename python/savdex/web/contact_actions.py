"""
«Мои контакты» — формы на Django (этап 5): статус и заметка открытого
контакта, жалоба на нерабочий контакт, выгрузка в CSV. Копия
App\\Http\\Controllers\\Cabinet\\ContactController.

У ContactUnlock событий нет и в журнал администратора он не пишется:
запись — простым update изменившихся полей с updated_at.

Сверка с настоящим Laravel — tests/test_web_contact_actions.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.shared import Context
from savdex.web.validation import validate
from savdex.web.views import not_found

#: ContactUnlock::STATUSES — подписи в коде, по-русски на всех языках
STATUSES = {
    "new": "Новый",
    "contacted": "Связался",
    "negotiating": "В переговорах",
    "deal": "Сделка",
    "rejected": "Не подошёл",
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _owned(ctx: Context, unlock_id: int) -> dict[str, Any] | None:
    """ContactController::owned: раскрытие своей компании, иначе None (404)."""
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from contact_unlocks where company_id = %s and id = %s",
        [company["id"], unlock_id],
    )

    return rows[0] if rows else None


def _save(row: dict[str, Any], changes: dict[str, Any]) -> None:
    """$unlock->fill(…)->save(): только изменившиеся поля и updated_at."""
    dirty = {k: v for k, v in changes.items() if row.get(k) != v}

    if not dirty:
        return

    sets = ", ".join(f"{c} = %s" for c in dirty)

    with allowed_writes("contact_unlocks"), connection.cursor() as cursor:
        cursor.execute(
            f"update contact_unlocks set {sets}, updated_at = %s where id = %s",
            [*dirty.values(), _now(), row["id"]],
        )


@form("PATCH")
def update(request: HttpRequest, unlock_id: str) -> HttpResponse:
    """ContactController::update: статус из списка и заметка до 500 знаков."""
    ctx = action(request)
    row = _owned(ctx, int(unlock_id))

    if row is None:
        return not_found(ctx)

    data = input_of(request)
    rules = {
        "status": ["nullable", "in:" + ",".join(STATUSES)],
        "note": ["nullable", "string", "max:500"],
    }
    errors = validate(data, rules, ctx.locale)

    if errors:
        return invalid(ctx, errors)

    # validated(): только поля с правилами, которые пришли в запросе
    _save(row, {k: data[k] for k in rules if k in data})
    flash(ctx, "success", ctx.t("messages.saved"))

    return back(ctx)


@form()
def complain(request: HttpRequest, unlock_id: str) -> HttpResponse:
    """ContactController::complain: жалоба одна, причина 10–500 знаков."""
    ctx = action(request)
    row = _owned(ctx, int(unlock_id))

    if row is None:
        return not_found(ctx)

    if row["complaint_status"] is not None:
        flash(ctx, "error", ctx.t("messages.complaint.pending"))

        return back(ctx)

    data = input_of(request)
    errors = validate(
        data,
        {"reason": ["required", "string", "min:10", "max:500"]},
        ctx.locale,
        {
            "reason.required": ctx.t("messages.complaint.reason_required"),
            "reason.min": ctx.t("messages.complaint.reason_min"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    _save(
        row,
        {
            "complaint_status": "pending",
            "complaint_reason": data["reason"],
            "complained_at": _now(),
        },
    )
    flash(ctx, "success", ctx.t("messages.complaint.sent"))

    return back(ctx)


def _field(value: str) -> str:
    """
    Поле fputcsv($out, …, ';'): в кавычках, если есть «;», кавычка,
    обратная косая, пробел, таб или перевод строки; кавычка удваивается,
    кроме стоящей сразу за обратной косой (escape у PHP).
    """
    if not value or not any(ch in value for ch in ';"\\ \t\n\r'):
        return value

    out = ['"']
    escaped = False

    for ch in value:
        if ch == "\\":
            escaped = True
        elif not escaped and ch == '"':
            out.append('"')
        else:
            escaped = False

        out.append(ch)

    out.append('"')

    return "".join(out)


def _fputcsv(fields: list[str]) -> str:
    return ";".join(_field(f) for f in fields) + "\n"


@form("GET")
def export(request: HttpRequest) -> HttpResponse:
    """
    ContactController::export (throttle:10,60): CSV с BOM (иначе Excel
    путает кириллицу), разделитель «;», свежие раскрытия первыми.
    """
    ctx = action(request, throttle=10, throttle_minutes=60)
    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    rows = _rows(
        "select u.*, c.name as c_name, l.title as l_title from contact_unlocks u "
        "left join companies c on c.id = u.target_company_id and c.deleted_at is null "
        "left join listings l on l.id = u.listing_id and l.deleted_at is null "
        "where u.company_id = %s order by u.created_at desc, u.id desc",
        [company["id"]],
    )
    contacts: dict[int, list[dict[str, Any]]] = {}

    for c in _rows(
        "select company_id, type, value from company_contacts where company_id = any(%s) "
        "order by is_primary desc, sort_order, id",
        [[r["target_company_id"] for r in rows]],
    ):
        contacts.setdefault(c["company_id"], []).append(c)

    lines = [
        "\ufeff",
        _fputcsv(
            [
                ctx.t("cabinet.contacts.company"),
                ctx.t("messages.export.phones"),
                ctx.t("messages.export.emails"),
                ctx.t("cabinet.contacts.listing"),
                ctx.t("cabinet.contacts.opened"),
                ctx.t("cabinet.contacts.status"),
                ctx.t("cabinet.contacts.note"),
            ]
        ),
    ]

    for r in rows:
        own = contacts.get(r["target_company_id"], []) if r["c_name"] is not None else []
        lines.append(
            _fputcsv(
                [
                    r["c_name"] or "",
                    ", ".join(c["value"] for c in own if c["type"] == "phone"),
                    ", ".join(c["value"] for c in own if c["type"] == "email"),
                    r["l_title"] or "",
                    r["created_at"].strftime("%d.%m.%Y"),
                    STATUSES.get(r["status"], r["status"] or ""),
                    r["note"] or "",
                ]
            )
        )

    response = HttpResponse("".join(lines), content_type="text/csv; charset=UTF-8")
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    response["Content-Disposition"] = f"attachment; filename=savdex-contacts-{stamp}.csv"

    return response
