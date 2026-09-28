"""
Контакты своей компании — формы на Django (этап 5, шаг 31): добавить,
изменить, удалить. Копия App\\Http\\Controllers\\Cabinet\\CompanyContactController.

Проверка значения зависит от типа: почта — как email:rfc
(savdex.web.email_rfc), телефон — шаблон PHP, остальное — строка; одно
значение в компании — один раз (Rule::unique). Первый контакт своего
типа становится основным. Последний телефон или почту удалить нельзя.
У CompanyContact событий нет, в журнал он не пишется.

Сверка с настоящим Laravel — tests/test_web_company_contact_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context
from savdex.web.validation import Check, validate
from savdex.web.views import not_found

#: CompanyContact::TYPES
TYPES = ("phone", "email", "telegram", "whatsapp", "website")

#: Телефон — тот же шаблон, что у регистрации и профиля
PHONE = r"/^\+?\d[\d\s\-()]{8,17}$/"


def _php_boolean(value: Any) -> bool:  # noqa: ANN401
    """filter_var(…, FILTER_VALIDATE_BOOLEAN): «1», «true», «on», «yes» — да."""
    if isinstance(value, bool):
        return value

    if isinstance(value, int | float):
        return value == 1

    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")

    return False


def _validated(
    ctx: Context, data: dict[str, Any], company_id: int | None, ignore: int | None = None
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """CompanyContactController::validated: данные полей с правилами и ошибки."""
    type_ = data.get("type")
    kind = {"email": "email:rfc", "phone": f"regex:{PHONE}"}.get(
        type_ if isinstance(type_, str) else "", "string"
    )

    def unique(value: Any) -> bool:  # noqa: ANN401
        """Rule::unique('company_contacts')->where('company_id', …)->ignore(…)."""
        if not isinstance(value, str | int | float) or isinstance(value, bool):
            return True

        sql = "select count(*) as n from company_contacts where value = %s"
        params: list[Any] = [str(value)]

        if ignore is not None:
            sql += " and id <> %s"
            params.append(ignore)

        if company_id is None:
            sql += " and company_id is null"
        else:
            sql += " and company_id = %s"
            params.append(company_id)

        return int(_rows(sql, params)[0]["n"]) == 0

    rules: dict[str, list[str | Check]] = {
        "type": ["required", "in:" + ",".join(TYPES)],
        "value": ["required", "string", "max:190", kind, Check("unique", unique)],
        "label": ["nullable", "string", "max:60"],
        "contact_person": ["nullable", "string", "max:120"],
        "is_public": ["boolean"],
        "sort_order": ["nullable", "integer", "min:0", "max:99"],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "value.required": ctx.t("messages.contact.value_required"),
            "value.email": ctx.t("messages.register.email_format"),
            "value.regex": ctx.t("messages.phone_format"),
            "value.unique": ctx.t("messages.contact.duplicate"),
        },
    )

    return {k: data[k] for k in rules if k in data}, errors


def _owned(ctx: Context, contact_id: int) -> dict[str, Any] | None:
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from company_contacts where company_id = %s and id = %s",
        [company["id"], contact_id],
    )

    return rows[0] if rows else None


@form()
def store(request: HttpRequest) -> HttpResponse:
    """CompanyContactController::store."""
    ctx = action(request)
    company = company_of(ctx)

    if company is None:
        flash(ctx, "error", ctx.t("messages.company.fill_first"))

        return back(ctx)

    data = input_of(request)
    valid, errors = _validated(ctx, data, company["id"])

    if errors:
        return invalid(ctx, errors)

    # firstOrNew по типу и значению: после Rule::unique такой строки нет
    found = _rows(
        "select * from company_contacts where company_id = %s and type = %s and value = %s limit 1",
        [company["id"], valid["type"], valid["value"]],
    )
    count = _rows(
        "select count(*) as n from company_contacts where company_id = %s", [company["id"]]
    )[0]["n"]
    sort_order = valid.get("sort_order")
    fields = {
        "label": valid.get("label"),
        "contact_person": valid.get("contact_person"),
        "is_public": _php_boolean(data["is_public"]) if "is_public" in data else True,
        "sort_order": int(count) if sort_order is None else sort_order,
    }

    if found:
        eloquent.save(ctx, "company_contacts", found[0], fields, section=None, model="")
        flash(ctx, "success", ctx.t("messages.contact.updated"))

        return back(ctx)

    # Первый контакт своего типа становится основным
    primary = not _rows(
        "select 1 from company_contacts where company_id = %s and type = %s and is_primary limit 1",
        [company["id"], valid["type"]],
    )
    now = _stamp(eloquent.now())

    with allowed_writes("company_contacts"), connection.cursor() as cursor:
        cursor.execute(
            "insert into company_contacts (company_id, type, value, label, contact_person, "
            "is_public, sort_order, is_primary, created_at, updated_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                company["id"],
                valid["type"],
                valid["value"],
                fields["label"],
                fields["contact_person"],
                fields["is_public"],
                fields["sort_order"],
                primary,
                now,
                now,
            ],
        )

    flash(ctx, "success", ctx.t("messages.contact.added"))

    return back(ctx)


@form("PATCH")
def update(request: HttpRequest, contact_id: str) -> HttpResponse:
    """CompanyContactController::update."""
    ctx = action(request)
    contact = _owned(ctx, int(contact_id))

    if contact is None:
        return not_found(ctx)

    valid, errors = _validated(ctx, input_of(request), contact["company_id"], contact["id"])

    if errors:
        return invalid(ctx, errors)

    if "is_public" in valid:
        valid["is_public"] = bool(_php_boolean(valid["is_public"]))

    eloquent.save(ctx, "company_contacts", contact, valid, section=None, model="")
    flash(ctx, "success", ctx.t("messages.contact.updated"))

    return back(ctx)


@form("DELETE")
def destroy(request: HttpRequest, contact_id: str) -> HttpResponse:
    """CompanyContactController::destroy: последний телефон или почту — нельзя."""
    ctx = action(request)
    contact = _owned(ctx, int(contact_id))

    if contact is None:
        return not_found(ctx)

    remaining = _rows(
        "select count(*) as n from company_contacts where company_id = %s "
        "and type in ('phone', 'email') and id <> %s",
        [contact["company_id"], contact["id"]],
    )[0]["n"]

    if remaining == 0 and contact["type"] in ("phone", "email"):
        flash(ctx, "error", ctx.t("messages.contact.last_one"))

        return back(ctx)

    with allowed_writes("company_contacts"), connection.cursor() as cursor:
        cursor.execute("delete from company_contacts where id = %s", [contact["id"]])

    flash(ctx, "success", ctx.t("messages.contact.deleted"))

    return back(ctx)


def contact(request: HttpRequest, contact_id: str) -> HttpResponse:
    """/cabinet/company/contacts/<id>: PATCH — изменить, DELETE — удалить."""
    if request.method == "DELETE":
        return destroy(request, contact_id)

    return update(request, contact_id)
