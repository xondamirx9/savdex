"""
Вход и выход — SessionGuard, EloquentUserProvider и BcryptHasher Laravel
со стороны Django (этап 5, шаг 45).

Пароли — bcrypt с префиксом $2y$ и стоимостью BCRYPT_ROUNDS (12 по
умолчанию); при входе хеш с другой стоимостью пересчитывается
(rehash_on_login). Вход: номер в сессию и сессия под новым номером;
«запомнить меня» — токен remember_token (если пуст — новый, запись без
updated_at) и кука remember_web_… на 400 дней. Выход: номер из сессии
прочь, кука «запомнить» — забыть (если была), remember_token — новый.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import os
import re
from typing import Any

import bcrypt
from django.db import connection

from savdex import laravel_session
from savdex.admins import hash_password
from savdex.guards import allowed_writes
from savdex.web import eloquent
from savdex.web.cabinet import _rows
from savdex.web.session import Store, random_string
from savdex.web.shared import Context

#: SessionGuard::$rememberDuration — 400 дней в минутах
REMEMBER_MINUTES = 576000


def rounds() -> int:
    """config('hashing.bcrypt.rounds'): BCRYPT_ROUNDS или 12."""
    try:
        return int(os.environ.get("BCRYPT_ROUNDS") or 12)
    except ValueError:
        return 12


def make(password: str) -> str:
    """Hash::make."""
    return hash_password(password, rounds())


def check(password: str, hashed: str | None) -> bool:
    """Hash::check: пустой хеш — нет; bcrypt сверяет первые 72 байта."""
    if not hashed:
        return False

    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], ("$2b$" + hashed.removeprefix("$2y$")).encode()
        )
    except ValueError:
        return False


def needs_rehash(hashed: str) -> bool:
    """password_needs_rehash: другой алгоритм или другая стоимость."""
    match = re.match(r"^\$2[aby]\$(\d{2})\$", hashed)

    return match is None or int(match.group(1)) != rounds()


def password_for_cookie(hashed: str) -> str:
    """SessionGuard::hashPasswordForCookie: HMAC хеша ключом app.key (строкой)."""
    key = os.environ.get("APP_KEY") or "base-key-for-password-hash-mac"

    return hmac.new(key.encode(), hashed.encode(), hashlib.sha256).hexdigest()


def user_by_email(email: str) -> dict[str, Any] | None:
    """EloquentUserProvider::retrieveByCredentials: почта как есть, не в корзине."""
    rows = _rows("select * from users where email = %s and deleted_at is null limit 1", [email])

    return rows[0] if rows else None


def attempt(ctx: Context, email: str, password: str) -> dict[str, Any] | None:
    """Auth::attempt без входа: пользователь при верном пароле (хеш — пересчитан)."""
    user = user_by_email(email)

    if user is None or not check(password, user["password"]):
        return None

    # rehashPasswordIfRequired: forceFill(['password' => …])->save()
    if needs_rehash(user["password"]):
        eloquent.save(
            ctx, "users", user, {"password": make(password)}, section="users", model="User"
        )

    return user


def _as(ctx: Context, user_id: int | None) -> None:
    """setUser: кто вошёл — для Auth::user() дальше в запросе (журнал, уведомления)."""
    ctx.visitor = dataclasses.replace(ctx.visitor, user_id=user_id)
    ctx.__dict__.pop("user", None)


def _set_remember_token(ctx: Context, user: dict[str, Any], token: str) -> None:
    """updateRememberToken: запись без меток времени, у администратора — журнал."""
    before = user["remember_token"]

    with allowed_writes("users"), connection.cursor() as cursor:
        cursor.execute("update users set remember_token = %s where id = %s", [token, user["id"]])

    user["remember_token"] = token
    eloquent.journal(
        ctx,
        "updated",
        "users",
        "User",
        user,
        {"before": {"remember_token": before}, "after": {"remember_token": token}},
    )


def login(ctx: Context, store: Store, user: dict[str, Any], remember: bool = False) -> None:
    """SessionGuard::login."""
    # updateSession: номер — в сессию, сессия — под новым номером
    store.data[laravel_session.LOGIN_KEY] = user["id"]
    store.migrate()
    store.user_id = user["id"]
    _as(ctx, user["id"])

    if remember:
        if not user["remember_token"]:
            _set_remember_token(ctx, user, random_string(60))

        store.queued.append(
            (
                laravel_session.REMEMBER_COOKIE,
                f"{user['id']}|{user['remember_token']}|{password_for_cookie(user['password'])}",
                REMEMBER_MINUTES,
            )
        )


def logout(ctx: Context, store: Store) -> None:
    """SessionGuard::logout: из сессии прочь, «запомнить» — забыть и новый токен."""
    user = None

    if ctx.user is not None:
        rows = _rows("select * from users where id = %s", [ctx.user["id"]])
        user = rows[0] if rows else None

    store.data.pop(laravel_session.LOGIN_KEY, None)
    store.queued = [q for q in store.queued if q[0] != laravel_session.REMEMBER_COOKIE]

    if ctx.request.COOKIES.get(laravel_session.REMEMBER_COOKIE):
        store.queued.append((laravel_session.REMEMBER_COOKIE, None, -2628000))

    if user is not None and user["remember_token"]:
        _set_remember_token(ctx, user, random_string(60))

    store.user_id = None
    _as(ctx, None)
