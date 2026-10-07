"""
Заявка со страницы «Контакты» (POST /contact) → лид в CRM.

Писать может и гость: имя, телефон или почта (хотя бы одно — иначе
не ответить), компания по желанию и сам вопрос. Вошедший — заявка
привязана к его компании. Лид ложится на первый этап доски лидов
с источником «Форма на сайте» (savdex/crm/automation.lead_from_site).

От ботов: скрытое поле website (человек его не видит и не заполняет;
заполнено — «принято», но ничего не создаётся) и не больше 5 заявок
за 10 минут с одного адреса.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.web.actions import form
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.validation import validate

#: Телефон — как в настройках учётной записи
PHONE = r"/^\+?\d[\d\s\-()]{8,17}$/"

RULES = {
    "name": ["required", "string", "max:160"],
    "phone": ["nullable", "string", f"regex:{PHONE}"],
    "email": ["nullable", "string", "email", "max:160"],
    "company": ["nullable", "string", "max:190"],
    "message": ["required", "string", "min:5", "max:2000"],
}


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


@form()
def submit(request: HttpRequest) -> HttpResponse:
    """Принять заявку и создать лид."""
    from savdex.crm import automation

    ctx = action(
        request,
        auth=False,
        password_change=False,
        throttle=5,
        throttle_minutes=10,
        throttle_prefix="contact-request",
    )
    data = input_of(request)

    # Скрытое поле заполнил бот — ответ как обычно, лида нет
    if _text(data.get("website")):
        flash(ctx, "success", ctx.t("contacts.form_sent"))

        return back(ctx)

    for key in ("name", "phone", "email", "company"):
        data[key] = _text(data.get(key)) or None

    message = data.get("message")
    data["message"] = message.strip() if isinstance(message, str) else None

    errors = validate(
        data,
        RULES,
        ctx.locale,
        {
            "name.required": ctx.t("contacts.form_name_required"),
            "phone.regex": ctx.t("messages.phone_format"),
            "email.email": ctx.t("messages.auth.email_invalid"),
            "message.required": ctx.t("contacts.form_message_required"),
            "message.min": ctx.t("contacts.form_message_required"),
        },
    )

    if not data["phone"] and not data["email"] and "phone" not in errors:
        errors["phone"] = [ctx.t("contacts.form_reach_required")]

    if errors:
        return invalid(ctx, errors)

    user = ctx.user or {}
    automation.lead_from_site(
        name=str(data["name"]),
        phone=data["phone"],
        email=data["email"].lower() if data["email"] else None,
        company=data["company"],
        message=str(data["message"]),
        company_id=user.get("company_id"),
        locale=ctx.locale,
        ip=audit.client_ip(request),
    )
    flash(ctx, "success", ctx.t("contacts.form_sent"))

    return back(ctx)
