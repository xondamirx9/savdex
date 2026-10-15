"""
Код подтверждения по SMS — Telnyx Verify.

Код придумывает и отправляет сам Telnyx по шаблону профиля проверки
(Verify Profile): текст, подпись и регистрация шаблона для Китая — в
панели Telnyx, не здесь. Сайт только просит «отправь код на номер» и
«проверь этот код».

Настройки (окружение сервера, в репозитории их нет):
  TELNYX_API_KEY            ключ API (Bearer)
  TELNYX_VERIFY_PROFILE_ID  профиль проверки
  TELNYX_API_URL            адрес API (по умолчанию api.telnyx.com/v2; в тестах — заглушка)

Любая ошибка сети или ответа — False, а не исключение: человек видит
«не удалось отправить SMS» и может получить код на почту.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from savdex import laravel_cache

log = logging.getLogger("savdex.sms")

API_URL = "https://api.telnyx.com/v2"

TIMEOUT = 15

#: Сколько SMS на один номер в сутки: каждое SMS платное, а номер
#: в форму может вписать кто угодно
MAX_PER_DAY = 5


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def configured() -> bool:
    """Ключ и профиль проверки заданы — кнопка «Код по SMS» видна."""
    return _env("TELNYX_API_KEY") != "" and _env("TELNYX_VERIFY_PROFILE_ID") != ""


def normalize(raw: str, dial_code: str | None = None) -> str | None:
    """
    Номер в международном виде (+8613812345678) или None. Без «+» в начале
    дописывается код страны с первого шага регистрации (если номер с него
    ещё не начинается); «00» в начале — то же, что «+».
    """
    text = (raw or "").strip()
    digits = re.sub(r"\D+", "", text)

    if text.startswith("00"):
        digits = digits[2:]
    elif not text.startswith("+") and dial_code:
        code = re.sub(r"\D+", "", dial_code)

        if code and not digits.startswith(code):
            digits = code + digits

    return "+" + digits if 8 <= len(digits) <= 15 else None


def verified_elsewhere(phone: str, user_id: int | None = None) -> bool:
    """
    Номер уже подтверждён другой учёткой (сравнение по цифрам: в учётках
    номер мог быть вписан с пробелами и скобками). Один подтверждённый
    номер — одна учётка: по нему восстанавливают пароль. Удалённая учётка
    номер не держит: человек может зарегистрироваться с ним заново.
    """
    from savdex.web.cabinet import _rows

    digits = re.sub(r"\D+", "", phone)

    return bool(
        _rows(
            "select 1 from users where phone_verified_at is not null and deleted_at is null"
            " and regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = %s"
            " and id <> %s limit 1",
            [digits, user_id or 0],
        )
    )


def verified_user(raw: str) -> dict[str, Any] | None:
    """
    Учётка с этим подтверждённым номером — для входа и «Забыли пароль».
    Сначала номер целиком (с кодом страны); не нашёлся — без кода страны
    («90 123 45 67»): по концу номера, если такая учётка одна.
    """
    from savdex.web.cabinet import _rows

    digits = re.sub(r"\D+", "", raw or "")

    if len(digits) < 7:
        return None

    query = (
        "select * from users where phone_verified_at is not null and deleted_at is null"
        " and regexp_replace(coalesce(phone, ''), '\\D', '', 'g') "
    )
    rows = _rows(query + "= %s order by id limit 1", [digits])

    if not rows and len(digits) >= 9:
        rows = _rows(query + "like %s order by id limit 2", ["%" + digits])
        rows = rows if len(rows) == 1 else []

    return rows[0] if rows else None


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_env('TELNYX_API_KEY')}"}


def _url(path: str) -> str:
    return (_env("TELNYX_API_URL") or API_URL).rstrip("/") + path


def _daily_key(phone: str) -> str:
    return "sms_sent." + hashlib.sha1(phone.encode()).hexdigest()


def _sent_today(phone: str) -> int:
    value = laravel_cache.get(_daily_key(phone), any_store=True)

    return value if isinstance(value, int) else 0


def daily_limit_reached(phone: str) -> bool:
    """На этот номер сегодня уже ушло MAX_PER_DAY SMS."""
    return _sent_today(phone) >= MAX_PER_DAY


def send_code(phone: str) -> bool:
    """POST /verifications/sms: Telnyx шлёт код на номер. Успех — True."""
    if not configured():
        return False

    try:
        response = httpx.post(
            _url("/verifications/sms"),
            headers=_headers(),
            json={"phone_number": phone, "verify_profile_id": _env("TELNYX_VERIFY_PROFILE_ID")},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        log.warning("sms.send_error: %s", e)

        return False

    if not response.is_success:
        log.warning("sms.send_failed: %s %s", response.status_code, response.text[:500])

        return False

    laravel_cache.put(_daily_key(phone), _sent_today(phone) + 1, 24 * 3600)

    return True


def check_code(phone: str, code: str) -> bool:
    """POST /verifications/by_phone_number/{номер}/actions/verify: код верный — True."""
    if not configured() or not re.fullmatch(r"\d{4,10}", code or ""):
        return False

    try:
        response = httpx.post(
            _url(f"/verifications/by_phone_number/{quote(phone, safe='')}/actions/verify"),
            headers=_headers(),
            json={"code": code, "verify_profile_id": _env("TELNYX_VERIFY_PROFILE_ID")},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        log.warning("sms.check_error: %s", e)

        return False

    if not response.is_success:
        return False

    try:
        result = response.json()["data"]["response_code"]
    except (ValueError, KeyError, TypeError):
        return False

    return bool(result == "accepted")
