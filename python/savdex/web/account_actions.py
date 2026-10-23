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
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex import laravel_session
from savdex.guards import allowed_writes
from savdex.web import (
    code_lock,
    eloquent,
    guard,
    later,
    locales,
    mail,
    messaging,
    password_rule,
    session,
    verification,
)
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
        {
            "password": fresh_hash,
            # Кука «запомнить» на других устройствах — недействительна
            "remember_token": random_string(60),
            "must_change_password": False,
        },
        section="users",
        model="User",
        casts={"must_change_password": "bool"},
    )
    # AuthenticateSession панели сверяет хеш пароля из сессии — уже новый
    store = _session(ctx)
    store.put("password_hash_web", fresh_hash)
    # Другие устройства со старым паролем — прочь, эта сессия остаётся
    session.end_user_sessions(int(user["id"]), keep=store.id)

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

    # Зарегистрировался по телефону и почту не подтвердил — восстановление
    # только по SMS (reset_options): почту мог вписать и чужую
    if "mail" not in reset_options(user):
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

    # Почта не подтверждена — ссылка только письмом. Иначе занявший чужой
    # адрес (регистрация без кода или по SMS) снова забирал бы аккаунт через
    # свой Telegram или WhatsApp после того, как хозяин почты его вернул
    if user["email_verified_at"] is None:
        return

    token = create_reset_token(str(user["email"]))
    link = _reset_link(ctx, token, str(user["email"]))

    if channel == "telegram" and user["telegram_chat_id"] is not None:
        messaging.telegram(
            str(user["telegram_chat_id"]), ctx.t("messages.auth.reset_message", link=link)
        )
    elif channel == "whatsapp" and (user["phone"] or "") != "" and user["phone_verified_at"]:
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

    channel = str(data.get("channel"))

    if channel not in reset_channels():
        channel = "mail"

    email = _normalized_email(data)
    flash(ctx, "status", ctx.t(f"messages.auth.reset_sent_{channel}"))

    # Есть ли такая учётка, решается уже после ответа: и текст, и время одни
    if channel == "mail":
        return later.after(back(ctx), lambda: _send_reset_mail(ctx, email))

    return later.after(back(ctx), lambda: _send_reset_message(ctx, email, channel))


# ── Забыли пароль: почта или телефон — дальше один экран для всех ───
#
# Что бы ни ввели и есть ли такая учётка, ответ один: «Если аккаунт с
# такими данными есть, мы отправили ссылку на почту или код в SMS», поле
# для кода и «Отправить ещё раз» — способами, включёнными на сайте, а не
# у этой учётки. Учётка — в сессии (её человек не видит); письмо, SMS и
# мессенджеры уходят после ответа (later.after) — и по времени ответа
# не понять, нашлась ли она.

#: Учётка, чей пароль восстанавливают; не нашлась — ключа нет
SESSION_RESET_FOUND = "reset.found"
#: Экран «Отправили» — после любого ввода
SESSION_RESET_SENT = "reset.sent"
#: Что ввели (почта строчными или номер): на это считаются неверные коды,
#: если SMS не уходило, — иначе по блокировке было бы видно, что номера нет
SESSION_RESET_LOGIN = "reset.login"
#: Номер, на который ушёл код, и учётка, чей пароль сбрасывается по SMS
SESSION_RESET_PHONE = "reset.sms_phone"
SESSION_RESET_USER = "reset.sms_user"


def reset_options(user: dict[str, Any]) -> list[str]:
    """
    Куда можно прислать восстановление этой учётке:
    - почта — если подтверждена или телефон не подтверждён (зарегистрировался
      по почте и телефон в профиле не подтверждал);
    - SMS — если телефон подтверждён (регистрация по телефону или «Подтвердить
      по SMS» в профиле);
    - Telegram и WhatsApp — как раньше, только при подтверждённой почте.
    """
    from savdex.web import sms
    from savdex.web.auth import reset_channels

    email_ok = user["email_verified_at"] is not None
    phone_ok = user["phone_verified_at"] is not None and (user["phone"] or "") != ""
    messengers = reset_channels()
    options: list[str] = []

    if email_ok or not phone_ok:
        options.append("mail")

    if phone_ok and sms.configured():
        options.append("sms")

    if email_ok and "telegram" in messengers and user["telegram_chat_id"] is not None:
        options.append("telegram")

    if email_ok and phone_ok and "whatsapp" in messengers:
        options.append("whatsapp")

    return options


def site_channels() -> list[str]:
    """Способы «Отправить ещё раз» — включённые на сайте, одни для всех."""
    from savdex.web import sms
    from savdex.web.auth import reset_channels

    channels = reset_channels()

    return [channels[0], "sms", *channels[1:]] if sms.configured() else channels


def _found(ctx: Context) -> dict[str, Any] | None:
    """Учётка шага «Почта или телефон» — живая, из базы заново."""
    found = _session(ctx).get(SESSION_RESET_FOUND)

    if not isinstance(found, int):
        return None

    rows = _rows("select * from users where id = %s and deleted_at is null", [found])

    return rows[0] if rows else None


def _send_reset_sms(phone: str, known: bool = True) -> None:
    """
    Код в SMS — только на подтверждённый номер (known=False — проверить
    здесь), не заблокированный пятью неверными кодами и в пределах суток:
    каждое SMS платное.
    """
    from savdex.web import sms

    if (known or sms.verified_user(phone) is not None) and (
        sms.locked_minutes(phone) == 0 and not sms.daily_limit_reached(phone)
    ):
        sms.send_code(phone)


def _delivery(ctx: Context, user: dict[str, Any], channel: str) -> Callable[[], None] | None:
    """
    Отправка этой учётке выбранным способом — что сделать после ответа.
    SMS: номер — в сессию сразу, по нему потом сверяется код.
    """
    from savdex.web import sms

    if channel == "sms":
        phone = sms.normalize(str(user["phone"] or ""))

        if phone is None:
            return None

        _session(ctx).put(SESSION_RESET_PHONE, phone)

        return lambda: _send_reset_sms(phone)

    email = str(user["email"])

    if channel == "mail":
        return lambda: _send_reset_mail(ctx, email)

    return lambda: _send_reset_message(ctx, email, channel)


def _sent(ctx: Context, message: str, job: Callable[[], None] | None) -> HttpResponse:
    """Ответ один: экран «Отправили» с текстом; отправка — после него."""
    flash(ctx, "status", message)
    response = _to(ctx, "/forgot-password")

    return later.after(response, job) if job is not None else response


def _forget(store: session.Store, *keys: str) -> None:
    for key in keys:
        store.forget(key)


@form()
def forgot_find(request: HttpRequest) -> HttpResponse:
    """
    «Забыли пароль», шаг 1: почта или телефон (телефон — только
    подтверждённый). Ссылка или код — способом, которым искали, если он
    есть у учётки, иначе первым доступным. Ответ один при любом исходе.
    """
    from savdex.web import sms

    ctx = action(
        request, auth=False, throttle=6, throttle_minutes=1, throttle_prefix="password-email"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    raw = _string(input_of(request).get("login")).strip(" \t\n\r\0\x0b")

    if raw == "":
        return invalid(ctx, {"login": [ctx.t("messages.auth.login_required")]})

    if "@" in raw:
        if validate({"email": raw}, {"email": ["email"]}, ctx.locale):
            return invalid(ctx, {"login": [ctx.t("messages.auth.login_invalid")]})

        login = raw.lower()
        user = guard.user_by_email(login)
    elif (phone := sms.normalize(raw)) is not None:
        login = phone
        user = sms.verified_user(raw)
    else:
        return invalid(ctx, {"login": [ctx.t("messages.auth.login_invalid")]})

    store = _session(ctx)
    _forget(store, SESSION_RESET_FOUND, SESSION_RESET_PHONE, SESSION_RESET_USER)
    store.put(SESSION_RESET_SENT, True)
    store.put(SESSION_RESET_LOGIN, login)
    options = reset_options(user) if user is not None else []
    job = None

    if user is not None and options:
        store.put(SESSION_RESET_FOUND, int(user["id"]))
        wanted = "mail" if "@" in raw else "sms"
        job = _delivery(ctx, user, wanted if wanted in options else options[0])

    return _sent(ctx, ctx.t("messages.auth.reset_sent_any"), job)


def _resend(ctx: Context, channel: str) -> HttpResponse:
    """«Отправить ещё раз»: у учётки такого способа нет — ничего, ответ тот же."""
    if not _session(ctx).get(SESSION_RESET_SENT) or channel not in site_channels():
        return _to(ctx, "/forgot-password")

    user = _found(ctx)
    job = None

    if user is not None and channel in reset_options(user):
        job = _delivery(ctx, user, channel)

    return _sent(ctx, ctx.t(f"messages.auth.reset_sent_{channel}"), job)


@form()
def forgot_send(request: HttpRequest) -> HttpResponse:
    """«Отправить ещё раз» почтой или в мессенджер."""
    ctx = action(
        request, auth=False, throttle=6, throttle_minutes=1, throttle_prefix="password-email"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    return _resend(ctx, _string(input_of(request).get("channel")))


@form()
def forgot_sms_resend(request: HttpRequest) -> HttpResponse:
    """«Отправить ещё раз» по SMS — своя частота: каждое SMS платное."""
    ctx = action(
        request, auth=False, throttle=3, throttle_minutes=10, throttle_prefix="password-sms"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    return _resend(ctx, "sms")


@form()
def forgot_restart(request: HttpRequest) -> HttpResponse:
    """«Другой аккаунт»: к шагу «Почта или телефон»."""
    ctx = action(request, auth=False)

    if (refused := _guest(ctx)) is not None:
        return refused

    _forget(
        _session(ctx),
        SESSION_RESET_FOUND,
        SESSION_RESET_SENT,
        SESSION_RESET_LOGIN,
        SESSION_RESET_PHONE,
    )

    return _to(ctx, "/forgot-password")


# ── Забыли пароль: код по SMS на подтверждённый номер ───────────────


@form()
def forgot_sms(request: HttpRequest) -> HttpResponse:
    """
    «Забыли пароль» по SMS: код — на номер, подтверждённый в учётке. Ответ
    один при любом номере (как и у почты), а SMS уходит только на номер,
    который есть в базе подтверждённым, — после ответа.
    """
    from savdex.web import sms

    ctx = action(
        request, auth=False, throttle=3, throttle_minutes=10, throttle_prefix="password-sms"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    if not sms.configured():
        return _to(ctx, "/forgot-password")

    phone = sms.normalize(_string(input_of(request).get("phone")))

    if phone is None:
        return invalid(ctx, {"phone": [ctx.t("messages.phone_format")]})

    store = _session(ctx)
    _forget(store, SESSION_RESET_FOUND, SESSION_RESET_USER)
    store.put(SESSION_RESET_SENT, True)
    store.put(SESSION_RESET_LOGIN, phone)
    store.put(SESSION_RESET_PHONE, phone)

    return _sent(
        ctx, ctx.t("messages.auth.reset_sent_sms"), lambda: _send_reset_sms(phone, known=False)
    )


@form()
def forgot_sms_confirm(request: HttpRequest) -> HttpResponse:
    """
    Код из SMS верный — на страницу нового пароля (тот же токен брокера,
    что и в письме). Почту при этом не «возвращают»: см. reset_password.
    SMS не уходило (учётки нет) — код просто не подходит, и неверные
    считаются на введённое, как у настоящего номера.
    """
    from savdex.web import sms

    ctx = action(
        request, auth=False, throttle=10, throttle_minutes=1, throttle_prefix="password-sms-code"
    )

    if (refused := _guest(ctx)) is not None:
        return refused

    store = _session(ctx)
    sent = store.get(SESSION_RESET_PHONE)
    login = store.get(SESSION_RESET_LOGIN)
    phone = sent if isinstance(sent, str) and sent != "" else None

    if phone is None and not (isinstance(login, str) and login != ""):
        return _to(ctx, "/forgot-password")

    code = _string(input_of(request).get("sms_code")).strip()

    if code == "":
        return invalid(ctx, {"sms_code": [ctx.t("messages.auth.code_required")]})

    target = code_lock.phone(phone) if phone is not None else f"reset:{login}"

    if (locked := code_lock.locked_message(ctx, target)) is not None:
        return _with_errors(ctx, {"sms_code": [locked]})

    user = sms.verified_user(phone) if phone is not None else None

    if phone is None or user is None or not sms.check_code(phone, code):
        if phone is None:
            # Неверный код засчитывает check_code, а его здесь не звали
            code_lock.fail(target)

        message = code_lock.failure_message(ctx, target, "messages.auth.sms_code_invalid")

        return _with_errors(ctx, {"sms_code": [message]})

    email = str(user["email"])
    token = create_reset_token(email)
    _forget(
        store, SESSION_RESET_PHONE, SESSION_RESET_FOUND, SESSION_RESET_SENT, SESSION_RESET_LOGIN
    )
    store.put(SESSION_RESET_USER, user["id"])

    return _to(ctx, f"/reset-password/{quote(token, safe='')}?email={quote(email, safe='')}")


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

    changes: dict[str, Any] = {
        "password": guard.make(str(data["password"])),
        "remember_token": random_string(60),
        "must_change_password": False,
    }

    # Почта не подтверждена — ссылка могла прийти только письмом
    # (_send_reset_message), значит сбросивший владеет адресом. Аккаунт —
    # ему: почта подтверждена, а телефон и Telegram того, кто занял адрес
    # без кода, отвязываются. Кроме сброса кодом из SMS (forgot_sms_confirm):
    # он доказал номер, а не почту
    store = _session(ctx)
    by_sms = store.get(SESSION_RESET_USER) == user["id"]
    store.forget(SESSION_RESET_USER)
    reclaimed = user["email_verified_at"] is None and not by_sms

    if reclaimed:
        changes.update(
            email_verified_at=eloquent.now(),
            phone=None,
            phone_verified_at=None,
            telegram_chat_id=None,
        )

    eloquent.save(
        ctx,
        "users",
        user,
        changes,
        section="users",
        model="User",
        casts={"must_change_password": "bool"},
    )

    if reclaimed:
        confirm_skipped(user["id"])

    with allowed_writes("password_reset_tokens", "sessions"), connection.cursor() as cursor:
        cursor.execute("delete from password_reset_tokens where email = %s", [user["email"]])
        # Новый пароль — все входы с других устройств закрываются: украденная
        # или чужая сессия иначе жила бы и после сброса
        cursor.execute("delete from sessions where user_id = %s", [user["id"]])

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
    """Снимает «Не подтверждено» — подтверждение почты или телефона кодом (или админом)."""
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

    target = code_lock.email(str(user["email"]))

    if (locked := code_lock.locked_message(ctx, target)) is not None:
        return _with_errors(ctx, {"code": [locked]})

    if not verification.check(user["id"], _string(data.get("code"))):
        code_lock.fail(target)

        return _with_errors(
            ctx, {"code": [code_lock.failure_message(ctx, target, "messages.auth.code_invalid")]}
        )

    code_lock.clear(target)
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

    # Пять неверных кодов — 15 минут и нового письма нет (code_lock)
    if (locked := code_lock.locked_message(ctx, code_lock.email(str(user["email"])))) is not None:
        flash(ctx, "error", locked)

        return back(ctx)

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
    Почта, подтверждённый телефон, ИНН и ПИНФЛ освобождаются: с ними можно
    зарегистрироваться заново (компания — если в ней больше никого).
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
    with allowed_writes("users", "companies"), connection.cursor() as cursor:
        cursor.execute(
            "update users set deleted_at = %s, updated_at = %s where id = %s",
            [now, now, user["id"]],
        )

        # Владелец, и в компании больше никого — компания (профиль физлица
        # и фрилансера тоже) удаляется вместе с ним: иначе её ИНН или ПИНФЛ
        # оставались «заняты», и заново зарегистрироваться было нельзя
        if user["company_role"] == "owner" and user["company_id"] is not None:
            cursor.execute(
                "update companies set deleted_at = %s, updated_at = %s "
                "where id = %s and deleted_at is null and not exists ("
                "select 1 from users where company_id = %s and deleted_at is null)",
                [now, now, user["company_id"], user["company_id"]],
            )

    store.invalidate()
    store.regenerate_token()
    flash(ctx, "success", ctx.t("messages.settings.account_deleted"))

    return _to(ctx, "/")
