"""
Выдача доступа в админку — содержательная часть команды `admin`.

Перенос `savdex:admin` (app/Console/Commands/MakeAdmin.php). Первая
команда, которая пишет в базу, поэтому здесь особенно много того, что
PHP делает молча и что надо повторить буква в букву:

- почта проверяется тем же правилом, что `filter_var(…, FILTER_VALIDATE_EMAIL)`:
  его регулярное выражение взято из исходников PHP как есть;
- пароль генерируется как `Str::password(14, symbols: false)`;
- пароль хешируется bcrypt с префиксом `$2y$`, как `password_hash`.
  Библиотека Python пишет `$2b$` — алгоритм тот же, но PHP такой хеш
  не узнаёт (`password_get_info` → unknown), и Laravel при входе
  бросает исключение. Администратор с паролем от Python не вошёл бы
  в админку вовсе;
- пароль длиннее 72 байт PHP молча обрезает; bcrypt для Python 5-й
  версии отказывает — здесь обрезается, как в PHP;
- время — UTC без пояса, как пишет Laravel (config/app.php, timezone).

Пишется только таблица users, и только внутри `allowed_writes("users")`
(savdex/guards.py): у модели User нет событий, которые пришлось бы
переносить.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import bcrypt
from django.db import transaction

from savdex import access
from savdex.guards import allowed_writes

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

# Роли — из общей копии AdminAccess
SUPERADMIN = access.SUPERADMIN
MODERATOR = access.MODERATOR
ROLES = access.ROLES

# ── Почта ───────────────────────────────────────────────────────────

#: FILTER_VALIDATE_EMAIL без FILTER_FLAG_EMAIL_UNICODE: регулярное
#: выражение Майкла Раштона из ext/filter/logical_filters.c (PHP 8.4),
#: флаги /iD. Без флага u PCRE работает с байтами — поэтому и здесь
#: байты, а `re.IGNORECASE` для байтов, как и PCRE, знает только ASCII.
#:
#: Copyright © Michael Rushton 2009-10, http://squiloople.com/
#: Feel free to use and redistribute this code. But please keep this copyright notice.
_EMAIL = re.compile(
    rb"(?!(?:(?:\x22?\x5C[\x00-\x7E]\x22?)|(?:\x22?[^\x5C\x22]\x22?)){255"
    rb",})(?!(?:(?:\x22?\x5C[\x00-\x7E]\x22?)|(?:\x22?[^\x5C\x22]\x22?)){"
    rb"65,}@)(?:(?:[\x21\x23-\x27\x2A\x2B\x2D\x2F-\x39\x3D\x3F\x5E-\x7E]+"
    rb")|(?:\x22(?:[\x01-\x08\x0B\x0C\x0E-\x1F\x21\x23-\x5B\x5D-\x7F]|(?:"
    rb"\x5C[\x00-\x7F]))*\x22))(?:\.(?:(?:[\x21\x23-\x27\x2A\x2B\x2D\x2F-"
    rb"\x39\x3D\x3F\x5E-\x7E]+)|(?:\x22(?:[\x01-\x08\x0B\x0C\x0E-\x1F\x21"
    rb"\x23-\x5B\x5D-\x7F]|(?:\x5C[\x00-\x7F]))*\x22)))*@(?:(?:(?!.*[^.]{"
    rb"64,})(?:(?:(?:xn--)?[a-z0-9]+(?:-+[a-z0-9]+)*\.){1,126}){1,}(?:(?:"
    rb"[a-z][a-z0-9]*)|(?:(?:xn--)[a-z0-9]+))(?:-+[a-z0-9]+)*)|(?:\[(?:(?"
    rb":IPv6:(?:(?:[a-f0-9]{1,4}(?::[a-f0-9]{1,4}){7})|(?:(?!(?:.*[a-f0-9"
    rb"][:\]]){7,})(?:[a-f0-9]{1,4}(?::[a-f0-9]{1,4}){0,5})?::(?:[a-f0-9]"
    rb"{1,4}(?::[a-f0-9]{1,4}){0,5})?)))|(?:(?:IPv6:(?:(?:[a-f0-9]{1,4}(?"
    rb"::[a-f0-9]{1,4}){5}:)|(?:(?!(?:.*[a-f0-9]:){5,})(?:[a-f0-9]{1,4}(?"
    rb"::[a-f0-9]{1,4}){0,3})?::(?:[a-f0-9]{1,4}(?::[a-f0-9]{1,4}){0,3}:)"
    rb"?)))?(?:(?:25[0-5])|(?:2[0-4][0-9])|(?:1[0-9]{2})|(?:[1-9]?[0-9]))"
    rb"(?:\.(?:(?:25[0-5])|(?:2[0-4][0-9])|(?:1[0-9]{2})|(?:[1-9]?[0-9]))"
    rb"){3}))\]))",
    re.IGNORECASE,
)

#: Что снимает trim() в PHP — меньше, чем str.strip() в Python
_PHP_TRIM = " \t\n\r\0\x0b"


def normalize_email(raw: str) -> str:
    """Как `mb_strtolower(trim($email))`."""
    return raw.strip(_PHP_TRIM).lower()


def valid_email(email: str) -> bool:
    """Как `filter_var($email, FILTER_VALIDATE_EMAIL) !== false`."""
    data = email.encode("utf-8", errors="surrogateescape")

    # «Длина адреса — не больше 320 октетов», RFC 2821; проверка PHP
    return len(data) <= 320 and _EMAIL.fullmatch(data) is not None


# ── Пароль ──────────────────────────────────────────────────────────

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_NUMBERS = "0123456789"


def generate_password(length: int = 14) -> str:
    """
    Как `Str::password(14, symbols: false)`: хотя бы одна буква и одна
    цифра, остальное — из обоих наборов, всё перемешано.
    """
    chars = [secrets.choice(_LETTERS), secrets.choice(_NUMBERS)]
    chars += [secrets.choice(_LETTERS + _NUMBERS) for _ in range(length - len(chars))]

    # Перемешивание криптостойким генератором, как shuffle() в Laravel
    # (Randomizer поверх random_bytes)
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


def hash_password(password: str, rounds: int = 12) -> str:
    """Как `password_hash($password, PASSWORD_BCRYPT, ['cost' => $rounds])`."""
    data = password.encode("utf-8")[:72]
    hashed = bcrypt.hashpw(data, bcrypt.gensalt(rounds=rounds, prefix=b"2b")).decode("ascii")

    # $2b$ и $2y$ — один и тот же алгоритм; PHP узнаёт только $2y$
    return "$2y$" + hashed.removeprefix("$2b$")


# ── Запись ──────────────────────────────────────────────────────────


class AccountDeletedError(RuntimeError):
    """Учётка с этой почтой удалена — выдавать ей права нельзя."""

    def __init__(self, email: str, deleted_at: datetime) -> None:
        super().__init__(
            f"Учётка {email} удалена {deleted_at:%d.%m.%Y}. "
            "Восстановите её в админке или выберите другую почту."
        )


@dataclass(frozen=True)
class Granted:
    created: bool
    email: str
    password: str
    role: str

    @property
    def role_label(self) -> str:
        return ROLES.get(self.role, "Роль не назначена")


def _now() -> str:
    # Laravel пишет время в поясе приложения (UTC) без пояса и без долей секунды
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def grant(
    connection: BaseDatabaseWrapper,
    *,
    email: str,
    role: str,
    name: str,
    password: str,
    rounds: int = 12,
) -> Granted:
    """
    Создать администратора или выдать роль существующему пользователю.

    Что пишется — ровно то, что пишет `$user->forceFill([...])->save()`
    в PHP-команде. У существующего пользователя подтверждение почты
    сохраняется, если оно было; пароль заменяется всегда.
    """
    hashed = hash_password(password, rounds)
    now = _now()

    with (
        transaction.atomic(using=connection.alias),
        connection.cursor() as cursor,
        allowed_writes("users"),
    ):
        # Действующий аккаунт — раньше удалённого, как в PHP: почта
        # удалённого свободна, и на один адрес их может быть два
        cursor.execute(
            "select id, deleted_at from users where email = %s "
            "order by deleted_at is not null, id desc limit 1",
            [email],
        )
        row = cursor.fetchone()

        if row is not None and row[1] is not None:
            raise AccountDeletedError(email, row[1])

        if row is None:
            cursor.execute(
                "insert into users (name, email, is_admin, admin_role, status, password, "
                "must_change_password, email_verified_at, updated_at, created_at) "
                "values (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s)",
                [name, email, True, role, hashed, True, now, now, now],
            )
        else:
            cursor.execute(
                "update users set is_admin = %s, admin_role = %s, status = 'active', "
                "password = %s, must_change_password = %s, "
                "email_verified_at = coalesce(email_verified_at, %s), updated_at = %s "
                "where id = %s",
                [True, role, hashed, True, now, now, row[0]],
            )

    return Granted(created=row is None, email=email, password=password, role=role)
