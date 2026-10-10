"""
Пароль и почта — формы на Django (этап 5, шаг 46). Копия
ForcePasswordController, PasswordResetController (с PasswordResetDelivery
и брокером паролей Laravel) и EmailVerificationController.

Сброс пароля — токены брокера Laravel: строка password_reset_tokens
(почта, bcrypt токена, время), ссылка живёт 60 минут, новую можно
запросить не чаще раза в 60 секунд; ответ формы один при любом исходе.
Подтверждение почты — код из письма (verification.check) или
подписанная ссылка.

Сверка с настоящим Laravel — tests/test_web_account_actions.py.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex import laravel_session
from savdex.guards import allowed_writes
from savdex.web import eloquent, guard, locales, mail, messaging, password_rule, verification
from savdex.web.actions import form
from savdex.web.auth_actions import _guest, _intended, _row, _session, _to
from savdex.web.cabinet import _rows
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.session import random_string
from savdex.web.shared import Context
from savdex.web.validation import _php_string, validate

#: config('auth.passwords.users'): срок ссылки и пауза между запросами
RESET_EXPIRE_MINUTES = 60
RESET_THROTTLE_SECONDS = 60


def _with_errors(ctx: Context, errors: dict[str, list[str]]) -> HttpResponse:
    """back()->withErrors([...]): ошибки без ввода."""
    _session(ctx).flash("errors", {"default": {"format": ":message", "messages": errors}})

    return back(ctx)


# ── Выданный пароль — сменить ───────────────────────────────────────


@form()
def force_password(request: HttpRequest) -> HttpResponse:
    """ForcePasswordController::update (auth, throttle:10,60,password-forced)."""
    ctx = action(request, throttle=10, throttle_minutes=60, throttle_prefix="password-forced")
    assert ctx.user is not None
    data = input_of(request)
    custom = {
        "password.required": ctx.t("messages.auth.password_new"),
        "password.confirmed": ctx.t("messages.auth.password_mismatch"),
        **password_rule.custom_messages(ctx.t),
    }
    errors = validate(data, {"password": ["required", "string", "confirmed"]}, ctx.locale, custom)

    if data.get("password") not in (None, ""):
        merged = errors.get("password", [])
        merged += [
            m
            for m in password_rule.messages("password", data["password"], ctx.locale, custom)
            if m not in merged
        ]

        if merged:
            errors["password"] = merged

    if errors:
        return invalid(ctx, errors)

    user = _row(ctx.user["id"])
    password = str(data["password"])

    # Новый пароль не должен совпадать с выданным
    if guard.check(password, user["password"]):
        return _with_errors(ctx, {"password": [ctx.t("messages.auth.password_same")]})

    fresh_hash = guard.make(password)
    eloquent.save(
        ctx,
        "users",
        user,
        {"password": fresh_hash, "must_change_password": False},
        section="users",
        model="User",
        casts={"must_change_password": "bool"},
    )
    # AuthenticateSession панели сверяет хеш пароля из сессии — уже новый
    _session(ctx).put("password_hash_web", fresh_hash)

    if user["is_admin"]:
        # Inertia::location('/admin'): панель — не страница Inertia; адрес — как есть
        if request.headers.get("X-Inertia"):
            response = HttpResponse("", status=409)
            response["X-Inertia-Location"] = "/admin"

            return response

        return HttpResponseRedirect("/admin")

    flash(ctx, "success", ctx.t("messages.auth.password_changed"))

    return _to(ctx, "/cabinet")


# ── Забыли пароль ───────────────────────────────────────────────────


def _normalized_email(data: dict[str, Any]) -> str:
    """PasswordResetController::normalizedEmail: без пробелов и строчными."""
    return _string(data.get("email")).strip(" \t\n\r\0\x0b").lower()


def _email_messages(ctx: Context) -> dict[str, str]:
    return {
        "email.required": ctx.t("messages.auth.email_required"),
        "email.email": ctx.t("messages.auth.email_invalid"),
    }


def _reset_record(email: str) -> dict[str, Any] | None:
    rows = _rows("select * from password_reset_tokens where email = %s", [email])

    return rows[0] if rows else None


def create_reset_token(email: str) -> str:
    """DatabaseTokenRepository::create: прежний токен прочь, новый — хешем в базу."""
    key = laravel_session.keys()[0] if laravel_session.keys() else b""
    token = hmac.new(key, random_string(40).encode(), hashlib.sha256).hexdigest()

    with allowed_writes("password_reset_tokens"), connection.cursor() as cursor:
        cursor.execute("delete from password_reset_tokens where email = %s", [email])
        cursor.execute(
            "insert into password_reset_tokens (email, token, created_at) values (%s, %s, %s)",
            [email, guard.make(token), _stamp(eloquent.now())],
        )

    return token


def _reset_link(ctx: Context, token: str, email: str) -> str:
    """url(route('password.reset', ['token' => …, 'email' => …], false))."""
    # На языке письма: англоязычное письмо открывает английскую страницу,
    # а не русскую в новом браузере без сохранённого языка
    path = f"/reset-password/{quote(token, safe='')}?email={quote(email, safe='')}"

    return locales.url(ctx.root, path, ctx.locale)


def _send_reset_mail(ctx: Context, email: str) -> None:
    """Password::sendResetLink: нет такого или ссылка свежая — ничего."""
    user = guard.user_by_email(email)

    if user is None:
        return

    email = str(user["email"])
    record = _reset_record(email)

    # recentlyCreatedToken: не чаще раза в 60 секунд
    if (
        record is not None
        and record["created_at"] is not None
        and record["created_at"] + timedelta(seconds=RESET_THROTTLE_SECONDS) > eloquent.now()
    ):
        return

    token = create_reset_token(email)
    subject, body_html, body_text = mail.render(
        "reset",
        url=_reset_link(ctx, token, email),
        app_url=os.environ.get("APP_URL") or "http://localhost",
        lang=ctx.locale,
    )
    mail.send(email, subject, body_html, body_text)


def _send_reset_message(ctx: Context, email: str, channel: str) -> None:
    """PasswordResetDelivery::send для мессенджеров: ссылка — в Telegram или WhatsApp."""
    user = guard.user_by_email(email)

    if user is None:
        return

    token = create_reset_token(str(user["email"]))
    link = _reset_link(ctx, token, str(user["email"]))

    if channel == "telegram" and user["telegram_chat_id"] is not None:
        messaging.telegram(
            str(user["telegram_chat_id"]), ctx.t("messages.auth.reset_message", link=link)
        )
    elif channel == "whatsapp" and (user["phone"] or "") != "":
        messaging.whatsapp(str(user["phone"]), link, user["locale"] or "ru")


@form()
def forgot_password(request: HttpRequest) -> HttpResponse:
    """PasswordResetController::email (guest, throttle:6,1,password-email): ответ один всегда."""
    from savdex.web.auth import reset_channels

    ctx = action(
        request, auth=False, throttle=6, throttle_minutes=1, throttle_prefix="password-email"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    data = input_of(request)
    errors = validate(
        data,
        {"email": ["required", "email"], "channel": ["nullable", "string"]},
        ctx.locale,
        _email_messages(ctx),
    )

    if errors:
        return invalid(ctx, errors)

    channel = data.get("channel")

    if channel not in reset_channels():
        channel = "mail"

    email = _normalized_email(data)

    if channel == "mail":
        _send_reset_mail(ctx, email)
    else:
        _send_reset_message(ctx, email, str(channel))

    flash(ctx, "status", ctx.t(f"messages.auth.reset_sent_{channel}"))

    return back(ctx)


@form()
def reset_password(request: HttpRequest) -> HttpResponse:
    """PasswordResetController::update (guest, throttle:10,60,password-reset) и Password::reset."""
    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=60, throttle_prefix="password-reset"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    data = input_of(request)
    custom = {
        **_email_messages(ctx),
        "password.required": ctx.t("messages.auth.password_new"),
        "password.confirmed": ctx.t("messages.auth.password_mismatch"),
        **password_rule.custom_messages(ctx.t),
    }
    rules: dict[str, list[Any]] = {
        "token": ["required"],
        "email": ["required", "email"],
        "password": ["required", "confirmed"],
    }
    errors = validate(data, rules, ctx.locale, custom)

    if data.get("password") not in (None, ""):
        merged = errors.get("password", [])
        merged += [
            m
            for m in password_rule.messages("password", data["password"], ctx.locale, custom)
            if m not in merged
        ]

        if merged:
            errors["password"] = merged

    errors = {k: errors[k] for k in rules if k in errors}

    if errors:
        return invalid(ctx, errors)

    user = guard.user_by_email(_normalized_email(data))
    record = _reset_record(str(user["email"])) if user is not None else None
    fresh = (
        record is not None
        and record["created_at"] is not None
        and record["created_at"] + timedelta(minutes=RESET_EXPIRE_MINUTES) > eloquent.now()
    )

    if user is None or not fresh or not guard.check(str(data["token"]), record["token"]):  # type: ignore[index]
        return _with_errors(ctx, {"email": [ctx.t("messages.auth.reset_expired")]})

    eloquent.save(
        ctx,
        "users",
        user,
        {
            "password": guard.make(str(data["password"])),
            "remember_token": random_string(60),
            "must_change_password": False,
        },
        section="users",
        model="User",
        casts={"must_change_password": "bool"},
    )

    with allowed_writes("password_reset_tokens"), connection.cursor() as cursor:
        cursor.execute("delete from password_reset_tokens where email = %s", [user["email"]])

    flash(ctx, "status", ctx.t("messages.auth.password_reset"))

    return _to(ctx, "/login")


# ── Подтверждение почты ─────────────────────────────────────────────


def _mark_verified(ctx: Context, user: dict[str, Any]) -> bool:
    """markEmailAsVerified: метка времени, если её не было."""
    if user["email_verified_at"] is not None:
        return False

    eloquent.save(
        ctx,
        "users",
        user,
        {"email_verified_at": eloquent.now()},
        section="users",
        model="User",
    )
    confirm_skipped(user["id"])

    return True


#: Код пропущен при регистрации — почта подтверждена: метка «Не
#: подтверждено» снимается с человека и его компании
CONFIRM_SKIPPED = (
    "update companies set email_unconfirmed = false where email_unconfirmed and id = "
    "(select company_id from users where id = %s and email_code_skipped)",
    "update users set email_code_skipped = false where id = %s and email_code_skipped",
)


def confirm_skipped(user_id: int) -> None:
    """Снимает «Не подтверждено» — только подтверждение почты кодом (или админом)."""
    with allowed_writes("companies", "users"), connection.cursor() as cursor:
        for query in CONFIRM_SKIPPED:
            cursor.execute(query, [user_id])


@form()
def verify_code(request: HttpRequest) -> HttpResponse:
    """EmailVerificationController::confirm (auth, throttle:6,1,verify-email)."""
    ctx = action(request, throttle=6, throttle_minutes=1, throttle_prefix="verify-email")
    assert ctx.user is not None
    user = _row(ctx.user["id"])

    if user["email_verified_at"] is not None:
        return _to(ctx, "/cabinet")

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

    if not verification.check(user["id"], _string(data.get("code"))):
        return _with_errors(ctx, {"code": [ctx.t("messages.auth.code_invalid")]})

    _mark_verified(ctx, user)
    flash(ctx, "success", ctx.t("messages.auth.verified"))

    return _intended(ctx, "/cabinet")


@form()
def verify_send(request: HttpRequest) -> HttpResponse:
    """EmailVerificationController::send (auth, throttle:6,1,verify-email): письмо ещё раз."""
    ctx = action(request, throttle=6, throttle_minutes=1, throttle_prefix="verify-email")
    assert ctx.user is not None
    user = _row(ctx.user["id"])

    if user["email_verified_at"] is not None:
        return _to(ctx, "/cabinet")

    verification.send(ctx, user)
    flash(ctx, "status", ctx.t("messages.auth.mail_resent"))

    return back(ctx)


@form("GET")
def verify_link(request: HttpRequest, user_id: str, digest: str) -> HttpResponse:
    """EmailVerificationController::verify (auth, signed, throttle:6,1,verify-email)."""
    from savdex.web import signed
    from savdex.web.views import error

    ctx = action(request, throttle=6, throttle_minutes=1, throttle_prefix="verify-email")
    assert ctx.user is not None

    # ValidateSignature: адрес запроса без подписи, ключом app.key
    if not signed.valid(ctx.root + request.path, request.META.get("QUERY_STRING", "")):
        return error(ctx, 403)

    user = _row(ctx.user["id"])
    expected = hashlib.sha1(str(user["email"]).encode()).hexdigest()

    # EmailVerificationRequest::authorize: номер и отпечаток почты — свои
    if not hmac.compare_digest(str(user["id"]), user_id) or not hmac.compare_digest(
        expected, digest
    ):
        return error(ctx, 403)

    if user["email_verified_at"] is not None:
        flash(ctx, "success", ctx.t("messages.auth.already_verified"))

        return _to(ctx, "/cabinet")

    _mark_verified(ctx, user)
    flash(ctx, "success", ctx.t("messages.auth.verified"))

    return _intended(ctx, "/cabinet")


def _string(value: Any) -> str:  # noqa: ANN401
    """$request->string(): (string) значения."""
    return _php_string(value)


# ── Удалить учётную запись ──────────────────────────────────────────


@form()
def delete_account(request: HttpRequest) -> HttpResponse:
    """
    SettingsController::destroy (auth): пароль ещё раз; у владельца
    объявления компании — в архив; выход, мягкое удаление, сессия заново.
    """
    ctx = action(request)
    assert ctx.user is not None
    data = input_of(request)
    errors = validate(
        data,
        {"password": ["required", "string"]},
        ctx.locale,
        {"password.required": ctx.t("messages.settings.password_confirm")},
    )

    if errors:
        return invalid(ctx, errors)

    user = _row(ctx.user["id"])

    if not guard.check(_string(data["password"]), user["password"]):
        return _with_errors(ctx, {"password": [ctx.t("messages.settings.password_wrong")]})

    now = _stamp(eloquent.now())

    if user["company_role"] == "owner" and user["company_id"] is not None:
        # $user->company->activeListings()->update(...): без событий моделей
        with allowed_writes("listings"), connection.cursor() as cursor:
            cursor.execute(
                "update listings set status = 'archived', updated_at = %s "
                "where company_id = %s and status = 'active' and deleted_at is null "
                "and exists (select 1 from companies c where c.id = %s and c.deleted_at is null)",
                [now, user["company_id"], user["company_id"]],
            )

    store = _session(ctx)
    guard.logout(ctx, store)

    # $user->delete(): SoftDeletes — deleted_at и updated_at; вошедшего уже нет,
    # журнал администратора не пишется
    with allowed_writes("users"), connection.cursor() as cursor:
        cursor.execute(
            "update users set deleted_at = %s, updated_at = %s where id = %s",
            [now, now, user["id"]],
        )

    store.invalidate()
    store.regenerate_token()
    flash(ctx, "success", ctx.t("messages.settings.account_deleted"))

    return _to(ctx, "/")
