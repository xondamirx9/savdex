"""
Подтверждение почты — App\\Support\\EmailVerificationCode и письмо
VerifyEmailCode со стороны Django (этап 5, шаг 45).

Код — шесть цифр (100000–999999), в кэше Laravel хешем bcrypt под
ключом email_verification_code.<номер> на 15 минут; пять неверных
попыток — код гасится. Письмо: код и подписанная ссылка
/verify-email/<номер>/<sha1 почты> на 60 минут.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from typing import Any

from savdex import laravel_cache
from savdex.web import guard, mail, signed
from savdex.web.shared import Context

TTL_MINUTES = 15
MAX_ATTEMPTS = 5
#: config('auth.verification.expire')
LINK_MINUTES = 60


def _key(user_id: int) -> str:
    return f"email_verification_code.{user_id}"


def issue(user_id: int) -> str:
    """EmailVerificationCode::issue: новый код взамен прежнего."""
    code = str(100000 + secrets.randbelow(900000))
    laravel_cache.put(_key(user_id), {"hash": guard.make(code), "attempts": 0}, TTL_MINUTES * 60)

    return code


def check(user_id: int, code: str) -> bool:
    """EmailVerificationCode::check: верный код одноразов."""
    entry = laravel_cache.get(_key(user_id))

    if not isinstance(entry, dict):
        return False

    if int(entry.get("attempts") or 0) >= MAX_ATTEMPTS:
        laravel_cache.forget(_key(user_id))

        return False

    if not guard.check(code, str(entry.get("hash") or "")):
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        laravel_cache.put(_key(user_id), entry, TTL_MINUTES * 60)

        return False

    laravel_cache.forget(_key(user_id))

    return True


def link(ctx: Context, user: dict[str, Any]) -> str:
    """VerifyEmail::verificationUrl: подписанная ссылка на час."""
    digest = hashlib.sha1(str(user["email"]).encode()).hexdigest()

    return signed.temporary(ctx.root, f"/verify-email/{user['id']}/{digest}", LINK_MINUTES)


def send(ctx: Context, user: dict[str, Any]) -> None:
    """User::sendEmailVerificationNotification: сбой — в журнал, не в ответ."""
    code = issue(user["id"])
    subject, body_html, body_text = mail.render(
        "verify",
        url=link(ctx, user),
        app_url=os.environ.get("APP_URL") or "http://localhost",
        lang=ctx.locale,
        code=code,
    )
    mail.send(str(user["email"]), subject, body_html, body_text)
