"""
Первые шаги регистрации — почта и код из письма (шаг 69), вместо
RegisteredUserController::sendCode, code, confirmCode, resendCode и details.

1. Почта (/register, POST /register/email) — адрес проверяется, на него
   уходит код; адрес — в сессии (register.email). Или телефон (POST
   /register/phone) — код уходит в SMS (Telnyx), номер — register.sms_phone.
2. Код (/register/code) — шесть цифр из письма; верный — адрес
   подтверждён (register.verified_email). По телефону — код из SMS
   (POST /register/sms/confirm): номер подтверждён (register.sms_verified).
3. Анкета (/register/details, POST /register — auth_actions.register):
   только с подтверждённым адресом или номером. По телефону почта — поле
   анкеты, без подтверждения: подтвердить её можно потом в профиле.

Код для адреса, у которого ещё нет учётки, — EmailVerificationCode::
issueForEmail: в кэше Laravel хешем под register_email_code.<sha1 почты>
на 15 минут. Пять неверных кодов подряд — 15 минут блокировки адреса
(code_lock): ни ввести код, ни получить новый. Все шаги — за guest:
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
from savdex.web import analytics, captcha, code_lock, guard, inertia, mail, sms
from savdex.web.actions import form
from savdex.web.auth_actions import (
    SESSION_COUNTRY,
    SESSION_EMAIL,
    SESSION_METHOD,
    SESSION_SKIPPED,
    SESSION_SMS_PHONE,
    SESSION_SMS_VERIFIED,
    SESSION_VERIFIED,
    _guest,
    _php_string,
    _session,
    _to,
    _unique_email,
    code_optional,
    registration_email,
    sms_phone,
)
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.shared import Context
from savdex.web.validation import validate

log = logging.getLogger("savdex.register")

#: EmailVerificationCode::TTL_MINUTES
TTL_MINUTES = 15


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
    """
    EmailVerificationCode::checkForEmail: верный код одноразов. Неверные
    считает code_lock — на адрес, а не на код: пять подряд — 15 минут
    блокировки, и новый код её не снимает.
    """
    key = _key(email)
    entry = laravel_cache.get(key, any_store=True)

    if not isinstance(entry, dict) or not guard.check(code, str(entry.get("hash") or "")):
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

    # Капча — до письма: без неё бот рассылал бы коды на чужие адреса
    if (problem := captcha.confirm(_session(ctx), "register", data.get("captcha"))) is not None:
        return invalid(ctx, {"captcha": [ctx.t(f"captcha.errors.{problem}")]})

    # Пять неверных кодов на этот адрес — 15 минут и нового кода нет
    if (locked := code_lock.locked_message(ctx, code_lock.email(email))) is not None:
        return invalid(ctx, {"email": [locked]})

    # Письмо не ушло — остаёмся на первом шаге с понятной ошибкой
    if not _mail_code(ctx, email):
        return invalid(ctx, {"email": [ctx.t("messages.register.email_send_failed")]})

    store = _session(ctx)
    store.put(SESSION_METHOD, "email")
    store.put(SESSION_EMAIL, email)
    store.put(SESSION_COUNTRY, country)
    store.forget(SESSION_VERIFIED)
    store.forget(SESSION_SKIPPED)
    store.forget(SESSION_SMS_PHONE)
    store.forget(SESSION_SMS_VERIFIED)
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

    phone = _phone(ctx)

    # По телефону: код из SMS на номер первого шага
    if phone is not None:
        return inertia.render(
            ctx,
            "auth/RegisterCode",
            {
                "method": "phone",
                "phone": phone,
                "email": None,
                "status": _flash(ctx, "status"),
                "demoCode": None,
                "canSkip": False,
                "phoneAvailable": True,
                "chinaMailbox": False,
                "sender": None,
            },
            _seo(ctx),
        )

    email = _email(ctx)

    if email is None:
        return _to(ctx, "/register")

    return inertia.render(
        ctx,
        "auth/RegisterCode",
        {
            "method": "email",
            "phone": None,
            "email": email,
            "status": _flash(ctx, "status"),
            # Только на демо-стенде без почты (_mail_code)
            "demoCode": _flash(ctx, "demo_code"),
            # Страна с галочкой «Регистрация без кода» — «Продолжить без кода»
            "canSkip": code_optional(_session(ctx).get(SESSION_COUNTRY)),
            # Письмо не приходит — ссылка «Зарегистрируйтесь по телефону»
            "phoneAvailable": sms.configured(),
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

    target = code_lock.email(email)

    if (locked := code_lock.locked_message(ctx, target)) is not None:
        return _with_errors(ctx, {"code": [locked]})

    if not check(email, _php_string(data.get("code"))):
        code_lock.fail(target)

        return _with_errors(
            ctx, {"code": [code_lock.failure_message(ctx, target, "messages.auth.code_invalid")]}
        )

    code_lock.clear(target)
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

    if (locked := code_lock.locked_message(ctx, code_lock.email(email))) is not None:
        flash(ctx, "error", locked)
    elif _mail_code(ctx, email):
        flash(ctx, "status", ctx.t("messages.auth.mail_resent"))
    else:
        flash(ctx, "error", ctx.t("messages.register.email_send_failed"))

    return back(ctx)


# ── Регистрация по телефону (Telnyx Verify, savdex/web/sms.py) ─────


def _dial_code(country_id: Any) -> str | None:  # noqa: ANN401
    """Телефонный код страны с первого шага: «+86»."""
    from savdex.web.cabinet import _rows

    try:
        key = int(str(country_id))
    except (TypeError, ValueError):
        return None

    rows = _rows("select phone_code from countries where id = %s", [key])
    code = str(rows[0]["phone_code"] or "") if rows else ""

    return ("+" + code.lstrip("+")) if code else None


def _phone(ctx: Context) -> str | None:
    """Номер первого шага, если человек регистрируется по телефону."""
    store = _session(ctx)
    phone = store.get(SESSION_SMS_PHONE)

    if store.get(SESSION_METHOD) != "phone":
        return None

    return phone if isinstance(phone, str) and phone != "" else None


def _send_sms(ctx: Context, phone: str) -> str | None:
    """Код на номер; не ушёл — текст ошибки. Каждое SMS платное."""
    if (locked := code_lock.locked_message(ctx, code_lock.phone(phone))) is not None:
        return locked

    if sms.daily_limit_reached(phone):
        return ctx.t("messages.register.sms_limit")

    if not sms.send_code(phone):
        return ctx.t("messages.register.sms_failed")

    return None


@form()
def send_phone(request: HttpRequest) -> HttpResponse:
    """
    Шаг 1, «Телефон»: страна и номер — Telnyx шлёт код. Частота с адреса
    сети и не больше sms.MAX_PER_DAY SMS в сутки на номер. Номер, уже
    подтверждённый другой учёткой, второй раз не регистрируется.
    """
    ctx = action(
        request, auth=False, throttle=5, throttle_minutes=10, throttle_prefix="register-sms"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    if not sms.configured():
        return _to(ctx, "/register")

    data = input_of(request)
    country = _country_id(data.get("country_id"))
    errors: dict[str, list[str]] = {}

    if country is None:
        errors["country_id"] = [ctx.t("messages.company.country_required")]

    phone = sms.normalize(_php_string(data.get("phone")), _dial_code(country))

    if phone is None:
        errors["phone"] = [ctx.t("messages.phone_format")]
    elif sms.verified_elsewhere(phone):
        errors["phone"] = [ctx.t("messages.register.phone_taken")]

    if errors:
        return invalid(ctx, errors)

    assert phone is not None

    # Капча — до SMS: каждое SMS платное, без неё бот гонял бы их на чужие номера
    if (problem := captcha.confirm(_session(ctx), "register", data.get("captcha"))) is not None:
        return invalid(ctx, {"captcha": [ctx.t(f"captcha.errors.{problem}")]})

    if (failed := _send_sms(ctx, phone)) is not None:
        return invalid(ctx, {"phone": [failed]})

    store = _session(ctx)
    store.put(SESSION_METHOD, "phone")
    store.put(SESSION_SMS_PHONE, phone)
    store.put(SESSION_COUNTRY, country)
    store.forget(SESSION_EMAIL)
    store.forget(SESSION_VERIFIED)
    store.forget(SESSION_SKIPPED)
    store.forget(SESSION_SMS_VERIFIED)
    analytics.queue(ctx, "sign_up_start", {"plan_param": analytics.intended_plan(ctx)})
    flash(ctx, "status", ctx.t("messages.register.sms_sent", phone=phone))

    return _to(ctx, "/register/code")


@form()
def send_sms(request: HttpRequest) -> HttpResponse:
    """Шаг 2 по телефону: «Отправить код ещё раз» на номер первого шага."""
    ctx = action(
        request, auth=False, throttle=5, throttle_minutes=10, throttle_prefix="register-sms"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    phone = _phone(ctx)

    if phone is None:
        return _to(ctx, "/register")

    if (failed := _send_sms(ctx, phone)) is not None:
        flash(ctx, "error", failed)
    else:
        flash(ctx, "status", ctx.t("messages.register.sms_sent", phone=phone))

    return back(ctx)


@form()
def confirm_sms(request: HttpRequest) -> HttpResponse:
    """Код из SMS верный — номер подтверждён, анкета открыта."""
    from savdex.web.account_actions import _with_errors

    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=1, throttle_prefix="register-code"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    phone = _phone(ctx)

    if phone is None:
        return _to(ctx, "/register")

    code = _php_string(input_of(request).get("sms_code")).strip()

    if code == "":
        return invalid(ctx, {"sms_code": [ctx.t("messages.auth.code_required")]})

    target = code_lock.phone(phone)

    if (locked := code_lock.locked_message(ctx, target)) is not None:
        return _with_errors(ctx, {"sms_code": [locked]})

    if not sms.check_code(phone, code):
        message = code_lock.failure_message(ctx, target, "messages.auth.sms_code_invalid")

        return _with_errors(ctx, {"sms_code": [message]})

    _session(ctx).put(SESSION_SMS_VERIFIED, {"phone": phone})

    return _to(ctx, "/register/details")


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
    phone = sms_phone(store)

    # По телефону: номер подтверждён, почту человек впишет в анкете
    if phone is not None:
        verified, skipped = "", False
    else:
        email, skipped = registration_email(store)

        if email is None:
            started = store.get(SESSION_EMAIL) is not None or _phone(ctx) is not None

            return _to(ctx, "/register/code" if started else "/register")

        verified = email

    names = _named("categories", ctx.locale)
    city_names = _named("cities", ctx.locale)
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
            # Регистрация по телефону: номер закреплён, почта — поле анкеты
            "smsPhone": phone,
            # Юрлицо выбирает, чем торгует, — разделы каталога верхнего уровня
            "categories": categories,
            # Город физлица и фрилансера — из справочника страны или «Другой»
            "cities": [
                {"id": c["id"], "name": city_names[c["id"]], "country_id": c["country_id"]}
                for c in _rows(
                    "select id, country_id from cities where is_active order by sort, id"
                )
            ],
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
