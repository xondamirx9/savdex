"""
Первые шаги регистрации — почта и код из письма (шаг 69), вместо
RegisteredUserController::sendCode, code, confirmCode, resendCode и details.

1. Почта (/register, POST /register/email) — адрес проверяется, на него
   уходит код; адрес — в сессии (register.email).
2. Код (/register/code) — шесть цифр из письма; верный — адрес
   подтверждён (register.verified_email).
3. Анкета (/register/details, POST /register — auth_actions.register):
   только с подтверждённым адресом.

Код для адреса, у которого ещё нет учётки, — EmailVerificationCode::
issueForEmail: в кэше Laravel хешем под register_email_code.<sha1 почты>
на 15 минут, пять неверных попыток — код гасится. Все шаги — за guest:
вошедший уходит на главную.

Сверка с настоящим Laravel — tests/test_web_register_code.py.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from typing import Any

from django.http import HttpRequest, HttpResponse

from savdex import laravel_cache
from savdex.web import analytics, guard, inertia, mail
from savdex.web.actions import form
from savdex.web.auth_actions import (
    SESSION_COUNTRY,
    SESSION_EMAIL,
    SESSION_SKIPPED,
    SESSION_VERIFIED,
    _guest,
    _php_string,
    _session,
    _to,
    _unique_email,
    code_optional,
    registration_email,
)
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.shared import Context
from savdex.web.validation import validate

log = logging.getLogger("savdex.register")

#: EmailVerificationCode::TTL_MINUTES и MAX_ATTEMPTS
TTL_MINUTES = 15
MAX_ATTEMPTS = 5


# ── Код для адреса ──────────────────────────────────────────────────


def _key(email: str) -> str:
    """EmailVerificationCode::emailKey: адрес — хешем, в имени файла кэша почта не нужна."""
    return "register_email_code." + hashlib.sha1(email.strip().lower().encode()).hexdigest()


def issue(email: str) -> str:
    """EmailVerificationCode::issueForEmail: новый код взамен прежнего."""
    code = str(100000 + secrets.randbelow(900000))
    laravel_cache.put(_key(email), {"hash": guard.make(code), "attempts": 0}, TTL_MINUTES * 60)

    return code


def check(email: str, code: str) -> bool:
    """EmailVerificationCode::checkForEmail: верный код одноразов."""
    key = _key(email)
    entry = laravel_cache.get(key, any_store=True)

    if not isinstance(entry, dict):
        return False

    if int(entry.get("attempts") or 0) >= MAX_ATTEMPTS:
        laravel_cache.forget_file(key)

        return False

    if not guard.check(code, str(entry.get("hash") or "")):
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        laravel_cache.put(key, entry, TTL_MINUTES * 60)

        return False

    laravel_cache.forget_file(key)

    return True


def _demo() -> bool:
    """config('app.demo_auto_verify'): демо-стенд без почты."""
    from savdex.payments.checkout import env_flag

    return env_flag("DEMO_AUTO_VERIFY")


def _mail_code(ctx: Context, email: str) -> bool:
    """
    RegisteredUserController::mailCode. На демо-стенде без почты код не
    уходит, а подставляется на втором шаге (demo_code). Сбой почты — не
    500, а False: человек видит, что письмо не ушло. Раньше сайт молча
    говорил «код отправлен», и человек ждал письмо, которого не будет.
    """
    code = issue(email)

    if _demo():
        flash(ctx, "demo_code", code)

        return True

    subject, body_html, body_text = mail.render(
        "register_code",
        url="",
        app_url=os.environ.get("APP_URL") or "http://localhost",
        lang=ctx.locale,
        code=code,
    )

    return mail.send(email, subject, body_html, body_text)


# ── Шаг 1 → 2: почта ────────────────────────────────────────────────


def _country_id(raw: Any) -> int | None:  # noqa: ANN401
    """Страна из списка регистрации (включённая) — номер, иначе None."""
    from savdex.web.cabinet import _rows

    try:
        key = int(str(raw).strip())
    except (TypeError, ValueError):
        return None

    return key if _rows("select 1 from countries where id = %s and is_active", [key]) else None


def _email_errors(ctx: Context, email: str) -> dict[str, list[str]]:
    """
    RegisterRequest::emailRules, emailMessages и refineEmailError: «нет
    собаки» и «адрес неполный» — свои подсказки; занятый адрес — как есть.
    """
    taken = ctx.t("messages.register.email_taken")
    errors = validate(
        {"email": email},
        {"email": ["required", "string", "email:rfc,strict", "max:190", _unique_email()]},
        ctx.locale,
        {
            "email.required": ctx.t("messages.register.email_required"),
            "email.email": ctx.t("messages.register.email_format"),
            "email.unique": taken,
        },
    )

    if email != "" and "email" in errors and taken not in errors["email"]:
        hint = None

        if "@" not in email:
            hint = ctx.t("messages.register.email_no_at")
        elif "." not in email[email.index("@") :]:
            hint = ctx.t("messages.register.email_incomplete")

        if hint is not None:
            errors["email"] = [hint]

    return errors


@form()
def send_code(request: HttpRequest) -> HttpResponse:
    """RegisteredUserController::sendCode (guest, throttle:10,10,register-email)."""
    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=10, throttle_prefix="register-email"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    data = input_of(request)
    # prepareForValidation: mb_strtolower(trim()) — и в старом вводе тоже
    email = _php_string(data.get("email")).strip(" \t\n\r\0\x0b").lower()
    data["email"] = email
    errors = _email_errors(ctx, email)

    # Страна — первой: от неё зависит, можно ли пропустить код (галочка
    # «Регистрация без кода» в справочнике стран)
    country = _country_id(data.get("country_id"))

    if country is None:
        errors["country_id"] = [ctx.t("messages.company.country_required")]

    if errors:
        return invalid(ctx, errors)

    # Письмо не ушло — остаёмся на первом шаге с понятной ошибкой
    if not _mail_code(ctx, email):
        return invalid(ctx, {"email": [ctx.t("messages.register.email_send_failed")]})

    store = _session(ctx)
    store.put(SESSION_EMAIL, email)
    store.put(SESSION_COUNTRY, country)
    store.forget(SESSION_VERIFIED)
    store.forget(SESSION_SKIPPED)
    analytics.queue(ctx, "sign_up_start", {"plan_param": analytics.intended_plan(ctx)})

    return _to(ctx, "/register/code")


# ── Шаг 2: код ──────────────────────────────────────────────────────


def _email(ctx: Context) -> str | None:
    email = _session(ctx).get(SESSION_EMAIL)

    return email if isinstance(email, str) and email != "" else None


def code_page(request: HttpRequest) -> HttpResponse:
    """RegisteredUserController::code: без адреса из первого шага — назад на него."""
    from savdex.web.auth import _flash, guest
    from savdex.web.cabinet import _seo

    ctx = guest(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    email = _email(ctx)

    if email is None:
        return _to(ctx, "/register")

    return inertia.render(
        ctx,
        "auth/RegisterCode",
        {
            "email": email,
            "status": _flash(ctx, "status"),
            # Только на демо-стенде без почты (_mail_code)
            "demoCode": _flash(ctx, "demo_code"),
            # Страна с галочкой «Регистрация без кода» — «Продолжить без кода»
            "canSkip": code_optional(_session(ctx).get(SESSION_COUNTRY)),
            # Китайский ящик (qq.com, 163.com…): письма идут дольше и чаще
            # в «Спам» — своя подсказка и адрес отправителя для белого списка
            "chinaMailbox": mail.is_chinese_mailbox(email),
            "sender": mail.sender_address(
                "CN_MAIL"
                if mail.is_chinese_mailbox(email) and mail.configured("CN_MAIL")
                else "MAIL"
            ),
        },
        _seo(ctx),
    )


@form()
def confirm_code(request: HttpRequest) -> HttpResponse:
    """RegisteredUserController::confirmCode (guest, throttle:10,1,register-code)."""
    from savdex.web.account_actions import _with_errors

    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=1, throttle_prefix="register-code"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    email = _email(ctx)

    if email is None:
        return _to(ctx, "/register")

    data = input_of(request)
    errors = validate(
        data,
        {"code": ["required", "digits:6"]},
        ctx.locale,
        {
            "code.required": ctx.t("messages.auth.code_required"),
            "code.digits": ctx.t("messages.auth.code_digits"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    if not check(email, _php_string(data.get("code"))):
        return _with_errors(ctx, {"code": [ctx.t("messages.auth.code_invalid")]})

    _session(ctx).put(SESSION_VERIFIED, email)

    return _to(ctx, "/register/details")


@form()
def resend_code(request: HttpRequest) -> HttpResponse:
    """RegisteredUserController::resendCode (guest, throttle:10,10,register-email)."""
    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=10, throttle_prefix="register-email"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    email = _email(ctx)

    if email is None:
        return _to(ctx, "/register")

    if _mail_code(ctx, email):
        flash(ctx, "status", ctx.t("messages.auth.mail_resent"))
    else:
        flash(ctx, "error", ctx.t("messages.register.email_send_failed"))

    return back(ctx)


@form()
def skip_code(request: HttpRequest) -> HttpResponse:
    """
    «Продолжить без кода» — только для стран с галочкой «Регистрация без
    кода»: к анкете без подтверждения. Учётка будет с пометкой «Не
    подтверждено», пока человек не подтвердит почту кодом из кабинета.
    """
    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=10, throttle_prefix="register-skip"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    store = _session(ctx)
    email = _email(ctx)

    if email is None:
        return _to(ctx, "/register")

    if not code_optional(store.get(SESSION_COUNTRY)):
        return _to(ctx, "/register/code")

    store.put(SESSION_SKIPPED, email)

    return _to(ctx, "/register/details")


# ── Шаг 3: анкета ───────────────────────────────────────────────────


def details(request: HttpRequest) -> HttpResponse:
    """RegisteredUserController::details: только после верного кода."""
    from savdex.web.auth import guest
    from savdex.web.cabinet import _rows, _seo
    from savdex.web.directory import _named, listed_countries
    from savdex.web.resumes import section_tree

    ctx = guest(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    store = _session(ctx)
    verified, skipped = registration_email(store)

    if verified is None:
        return _to(ctx, "/register/code" if store.get(SESSION_EMAIL) is not None else "/register")

    names = _named("categories", ctx.locale)
    # Код страны для телефона: выбрал страну — в поле сразу «+86 »
    phones = {r["id"]: r["phone_code"] for r in _rows("select id, phone_code from countries")}
    categories: list[dict[str, Any]] = [
        {"id": row["id"], "name": names[row["id"]]}
        for row in _rows(
            "select id from categories where parent_id is null and is_active order by sort, id"
        )
    ]

    return inertia.render(
        ctx,
        "auth/Register",
        {
            "email": verified,
            # Страна с первого шага; код пропущен — сменить её нельзя
            "countryId": store.get(SESSION_COUNTRY),
            "skipped": skipped,
            # Юрлицо выбирает, чем торгует, — разделы каталога верхнего уровня
            "categories": categories,
            # Страна юрлица — до номера: по ней номер проверяется (ТЗ-02)
            "countries": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "code": c["code"],
                    "phone_code": phones.get(c["id"]),
                }
                for c in listed_countries(ctx.locale)
            ],
            # Фрилансер — направление «Доп. услуг», на заказы которого откликается
            "serviceSections": section_tree(ctx),
        },
        _seo(ctx),
    )
