"""Коды второго фактора (savdex/twofactor.py) — без базы."""

from __future__ import annotations

import base64

from savdex import twofactor

#: Ключ из приложения B RFC 6238 (SHA-1): «12345678901234567890»
RFC = base64.b32encode(b"12345678901234567890").decode()


def test_код_как_в_rfc_6238():
    # Т = 59 с → шаг 1 → 94287082; шестизначный код — последние шесть цифр
    assert twofactor.code_at(RFC, 59 // 30) == "287082"
    # Т = 1111111109 с → 07081804
    assert twofactor.code_at(RFC, 1111111109 // 30) == "081804"


def test_расхождение_часов_на_шаг():
    код = twofactor.code_at(RFC, 1)

    assert twofactor.matching_step(RFC, код, now=59) == 1
    # Шаг вперёд и назад — ещё годен, два шага — уже нет
    assert twofactor.matching_step(RFC, код, now=89) == 1
    assert twofactor.matching_step(RFC, код, now=119) is None


def test_код_с_пробелом_и_мусор():
    код = twofactor.code_at(RFC, 1)

    assert twofactor.matching_step(RFC, f"{код[:3]} {код[3:]}", now=59) == 1
    assert twofactor.matching_step(RFC, "12345", now=59) is None
    assert twofactor.matching_step(RFC, "абвгде", now=59) is None


def test_адрес_для_qr():
    uri = twofactor.otpauth_uri("anna@savdex.uz", "ABCD")

    assert uri.startswith("otpauth://totp/SAVDEX%3Aanna%40savdex.uz?")
    assert "secret=ABCD" in uri and "issuer=SAVDEX" in uri


def test_ключ_новый_каждый_раз():
    assert twofactor.new_secret() != twofactor.new_secret()
    assert len(twofactor.new_secret()) == 32
