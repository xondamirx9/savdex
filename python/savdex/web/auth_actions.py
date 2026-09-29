"""
Вход, выход, регистрация — формы на Django (этап 5, шаг 45). Копия
AuthenticatedSessionController, RegisteredUserController и
App\\Services\\Auth\\LoginThrottle.

Вход: единое сообщение для «нет такого» и «неверный пароль» с остатком
попыток; пять неудач за 15 минут по связке почта + IP — блокировка с
обратным отсчётом; заблокированного не пускает и с верным паролем.
Успех: счётчик сброшен, сессия под новым номером, метка последнего
входа, выданный пароль — на смену, иначе — туда, куда шёл (url.intended).

Сверка с настоящим Laravel — tests/test_web_auth_actions.py.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex.audit import client_ip
from savdex.guards import allowed_writes
from savdex.web import eloquent, guard, locales
from savdex.web.actions import form
from savdex.web.forms import _store, action, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.session import Store
from savdex.web.shared import Context
from savdex.web.validation import validate

# ── LoginThrottle ───────────────────────────────────────────────────

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
WINDOW_MINUTES = 15


class LoginThrottle:
    """Неудачные попытки входа по связке почта + IP — в таблице login_attempts."""

    def __init__(self, email: str, ip: str) -> None:
        self.email = email
        self.ip = ip

    def _since(self) -> datetime:
        return eloquent.now() - timedelta(minutes=WINDOW_MINUTES)

    def failed_attempts(self) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from login_attempts where email = %s and ip = %s "
                "and successful = false and created_at >= %s",
                [self.email, self.ip, _stamp(self._since())],
            )
            return int(cursor.fetchone()[0])

    def remaining(self) -> int:
        return max(0, MAX_ATTEMPTS - self.failed_attempts())

    def locked(self) -> bool:
        return self.remaining() == 0

    def seconds_until_unlock(self) -> int:
        """unlocksAt: самая ранняя из пяти последних неудач плюс 15 минут."""
        if not self.locked():
            return 0

        with connection.cursor() as cursor:
            cursor.execute(
                "select created_at from login_attempts where email = %s and ip = %s "
                "and successful = false and created_at >= %s "
                "order by created_at desc limit %s",
                [self.email, self.ip, _stamp(self._since()), MAX_ATTEMPTS],
            )
            # ->value(): первая строка выборки
            row = cursor.fetchone()

        unlocks = (row[0] if row else eloquent.now()) + timedelta(minutes=LOCKOUT_MINUTES)

        return max(0, int((unlocks - eloquent.now()).total_seconds()))

    def _record(self, successful: bool, user_agent: str | None) -> None:
        with allowed_writes("login_attempts"), connection.cursor() as cursor:
            cursor.execute(
                "insert into login_attempts (email, ip, successful, user_agent_hash, created_at) "
                "values (%s, %s, %s, %s, %s)",
                [
                    self.email,
                    self.ip,
                    successful,
                    hashlib.sha256(user_agent.encode()).hexdigest() if user_agent else None,
                    _stamp(eloquent.now()),
                ],
            )

    def record_failure(self, user_agent: str | None) -> None:
        self._record(False, user_agent)

    def record_success(self, user_agent: str | None) -> None:
        """Успешный вход обнуляет счётчик."""
        self._record(True, user_agent)

        with allowed_writes("login_attempts"), connection.cursor() as cursor:
            cursor.execute(
                "delete from login_attempts where email = %s and ip = %s and successful = false",
                [self.email, self.ip],
            )


def _lockout(ctx: Context, throttle: LoginThrottle) -> str:
    minutes = math.ceil(throttle.seconds_until_unlock() / 60)

    return ctx.t("messages.auth.locked_out", minutes=max(1, minutes))


# ── Общее ───────────────────────────────────────────────────────────


def _session(ctx: Context) -> Store:
    store = _store(ctx)
    assert store is not None

    return store


def _to(ctx: Context, path: str) -> HttpResponse:
    """redirect($url): адрес на хосте — на язык запроса (LocalizeUrl)."""
    target = path if path.startswith("http") else ctx.url(path)

    if ctx.url_locale is not None and target.startswith(ctx.root):
        target = locales.url(ctx.root, target[len(ctx.root) :] or "/", ctx.url_locale)

    return HttpResponseRedirect(target)


def _intended(ctx: Context, default: str) -> HttpResponse:
    """redirect()->intended(route(default))."""
    store = _session(ctx)
    saved = store.get("url.intended")
    store.forget("url.intended")

    return _to(ctx, saved if isinstance(saved, str) else default)


def _guest(ctx: Context) -> HttpResponse | None:
    """RedirectIfAuthenticated: вошедшему форма входа не нужна — на главную."""
    return _to(ctx, "/") if ctx.user is not None else None


def _agent(request: HttpRequest) -> str | None:
    return request.headers.get("User-Agent")


# ── Вход и выход ────────────────────────────────────────────────────


@form()
def login(request: HttpRequest) -> HttpResponse:
    """AuthenticatedSessionController::store (guest, throttle:20,1)."""
    ctx = action(request, auth=False, throttle=20, throttle_minutes=1)

    if (refused := _guest(ctx)) is not None:
        return refused

    data = input_of(request)
    errors = validate(
        data,
        {"email": ["required", "string", "email"], "password": ["required", "string"]},
        ctx.locale,
        {
            "email.required": ctx.t("messages.auth.email_required"),
            "email.email": ctx.t("messages.auth.email_invalid"),
            "password.required": ctx.t("messages.auth.password_required"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    email = str(data["email"]).strip(" \t\n\r\0\x0b").lower()
    throttle = LoginThrottle(email, client_ip(request) or "")

    if throttle.locked():
        return invalid(ctx, {"email": [_lockout(ctx, throttle)]})

    remember = _boolean(data.get("remember"))
    user = guard.attempt(ctx, email, str(data["password"]))

    if user is None:
        throttle.record_failure(_agent(request))
        fresh = LoginThrottle(email, client_ip(request) or "")
        message = (
            _lockout(ctx, fresh)
            if fresh.locked()
            else ctx.t(
                "messages.auth.wrong_credentials", left=fresh.remaining(), total=MAX_ATTEMPTS
            )
        )

        return invalid(ctx, {"email": [message]})

    store = _session(ctx)
    guard.login(ctx, store, user, remember)

    # Заблокированного не пускаем даже с верным паролем
    if user["status"] != "active":
        guard.logout(ctx, store)
        store.invalidate()

        return invalid(ctx, {"email": [ctx.t("messages.auth.blocked")]})

    throttle.record_success(_agent(request))
    store.migrate()
    row = _row(user["id"])
    eloquent.save(
        ctx,
        "users",
        row,
        {"last_login_at": eloquent.now(), "last_login_ip": client_ip(request)},
        section="users",
        model="User",
    )

    # Пароль, выданный вручную, обязателен к смене
    if row["must_change_password"]:
        return _to(ctx, "/password/change")

    return _intended(ctx, "/cabinet")


def _row(user_id: int) -> dict[str, Any]:
    from savdex.web.cabinet import _rows

    return _rows("select * from users where id = %s", [user_id])[0]


def _boolean(value: Any) -> bool:  # noqa: ANN401
    """$request->boolean(): FILTER_VALIDATE_BOOLEAN."""
    from savdex.web.company_contact_actions import _php_boolean

    return _php_boolean(value)


@form()
def logout(request: HttpRequest) -> HttpResponse:
    """AuthenticatedSessionController::destroy (auth)."""
    ctx = action(request)
    store = _session(ctx)
    guard.logout(ctx, store)
    store.invalidate()
    store.regenerate_token()

    # redirect('/') — адрес без языка; LocalizeUrl его не трогает только
    # для внешних, здесь — хост площадки
    return _to(ctx, "/")


def either(
    get: Any,  # noqa: ANN401
    post: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Один адрес: GET — страница, POST — форма (маршруты Laravel с тем же путём)."""

    def view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        handler = post if request.method == "POST" else get

        return handler(request, *args, **kwargs)  # type: ignore[no-any-return]

    return view
