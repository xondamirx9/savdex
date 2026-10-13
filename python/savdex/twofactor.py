"""
Второй фактор входа в админку — код из приложения (TOTP, RFC 6238).

Пароль у сотрудника могут подсмотреть, подобрать или выудить письмом;
код из телефона — нет. Подключение — в админке («Вход по коду»,
savdex/adminsecurity.py): QR-код для приложения и первый верный код.
С этого момента вход в админку — и формой, и через сессию сайта
(adminpanel.AdminMiddleware) — пускает только после кода; кука входа
(savdex/bridge.py) помнит, что код введён.

SAVDEX_ADMIN_2FA_REQUIRED=true — сотрудник без подключённого кода не
пройдёт дальше страницы подключения. Потерял телефон —
`manage.py admin_2fa_reset почта` (код снимается, подключить заново).

Ключ приложения в базе зашифрован ключом от APP_KEY (Fernet): выгрузка
базы без APP_KEY кодов не даёт. Принятый код второй раз не проходит
(last_step), окно — шаг назад и вперёд: часы телефона расходятся.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from typing import Any
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from django.db import connection

from savdex.guards import allowed_writes

#: Длина шага и кода — как у всех приложений по умолчанию
PERIOD = 30
DIGITS = 6
#: Шагов в обе стороны: часы телефона и сервера расходятся
DRIFT = 1
ISSUER = "SAVDEX"


def required() -> bool:
    """SAVDEX_ADMIN_2FA_REQUIRED: без подключённого кода в админку нельзя."""
    return os.environ.get("SAVDEX_ADMIN_2FA_REQUIRED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _fernet() -> Fernet:
    from savdex.settings import _app_key

    key = _app_key()

    if not key:
        raise RuntimeError("APP_KEY не задан: второй фактор без ключа шифрования невозможен")

    derived = hashlib.sha256(b"savdex.admin-two-factor:" + key).digest()

    return Fernet(base64.urlsafe_b64encode(derived))


def new_secret() -> str:
    """Ключ приложения: 20 случайных байт в base32 (так его вводят руками)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, step: int) -> str:
    """HOTP (RFC 4226) для шага step — то, что покажет приложение."""
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF

    return str(number % 10**DIGITS).zfill(DIGITS)


def matching_step(secret: str, code: str, now: float | None = None) -> int | None:
    """Шаг, которому соответствует код (с учётом расхождения часов), или None."""
    code = "".join(ch for ch in str(code) if ch.isdigit())

    if len(code) != DIGITS:
        return None

    current = int((time.time() if now is None else now) // PERIOD)

    for step in range(current - DRIFT, current + DRIFT + 1):
        if hmac.compare_digest(code_at(secret, step), code):
            return step

    return None


def otpauth_uri(email: str, secret: str) -> str:
    """Адрес для QR-кода: его понимают все приложения-аутентификаторы."""
    label = quote(f"{ISSUER}:{email}")
    query = urlencode({"secret": secret, "issuer": ISSUER, "digits": DIGITS, "period": PERIOD})

    return f"otpauth://totp/{label}?{query}"


def _row(user_id: int) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "select secret, confirmed_at, last_step from admin_two_factor where user_id = %s",
            [user_id],
        )
        row = cursor.fetchone()

    if row is None:
        return None

    try:
        secret = _fernet().decrypt(row[0].encode()).decode()
    except InvalidToken:
        # Сменили APP_KEY — прежний ключ не прочесть: подключать заново
        return None

    return {"secret": secret, "confirmed_at": row[1], "last_step": row[2]}


def enrolled(user_id: int) -> bool:
    """Код подключён и подтверждён — вход только с ним."""
    row = _row(user_id)

    return row is not None and row["confirmed_at"] is not None


def pending_secret(user_id: int) -> str:
    """
    Ключ для подключения: начатый и не законченный — тот же (QR уже
    отсканирован), иначе новый. У подключённого — None не бывает: его
    сначала снимают (reset).
    """
    row = _row(user_id)

    if row is not None and row["confirmed_at"] is None:
        return str(row["secret"])

    secret = new_secret()
    sealed = _fernet().encrypt(secret.encode()).decode()

    with allowed_writes("admin_two_factor"), connection.cursor() as cursor:
        cursor.execute(
            "insert into admin_two_factor (user_id, secret, created_at, updated_at) "
            "values (%s, %s, now(), now()) on conflict (user_id) do update set "
            "secret = excluded.secret, confirmed_at = null, last_step = null, updated_at = now()",
            [user_id, sealed],
        )

    return secret


def _accept(user_id: int, step: int, *, confirm: bool) -> bool:
    """
    Принять код шага step: только если он новее последнего принятого —
    одним условным update, так что два одинаковых запроса разом не пройдут.
    """
    confirmed = ", confirmed_at = coalesce(confirmed_at, now())" if confirm else ""

    with allowed_writes("admin_two_factor"), connection.cursor() as cursor:
        cursor.execute(
            f"update admin_two_factor set last_step = %s, updated_at = now(){confirmed} "
            "where user_id = %s and (last_step is null or last_step < %s)",
            [step, user_id, step],
        )

        return bool(cursor.rowcount == 1)


def confirm(user_id: int, code: str) -> bool:
    """Первый верный код из приложения — подключение закончено."""
    row = _row(user_id)

    if row is None or row["confirmed_at"] is not None:
        return False

    step = matching_step(str(row["secret"]), code)

    return step is not None and _accept(user_id, step, confirm=True)


def verify(user_id: int, code: str) -> bool:
    """Код при входе: верный, свежий и не использованный раньше."""
    row = _row(user_id)

    if row is None or row["confirmed_at"] is None:
        return False

    step = matching_step(str(row["secret"]), code)

    return step is not None and _accept(user_id, step, confirm=False)


def reset(user_id: int) -> bool:
    """Снять код (потерян телефон): вход снова по паролю, подключать заново."""
    with allowed_writes("admin_two_factor"), connection.cursor() as cursor:
        cursor.execute("delete from admin_two_factor where user_id = %s", [user_id])

        return bool(cursor.rowcount > 0)
