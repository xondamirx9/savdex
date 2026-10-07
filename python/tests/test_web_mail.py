"""
Письма площадки на пяти языках (savdex.web.mail.render).

Каждое письмо (verify, register_code, reset) есть на ru, en, uz, tr, zh:
без оставшихся меток __…__, с атрибутом lang своего языка, с непустой
темой, текст у языков разный, а разметка — одна. Неизвестный язык —
русское письмо. Без базы.
"""

from __future__ import annotations

import re

import pytest

from savdex.web import locales, mail

ПИСЬМА = ("verify", "register_code", "reset")
URL = "https://savdex.uz/verify-email/7/abc?expires=1&signature=f&x=<y>"
APP = "https://savdex.uz"
КОД = "481516"

#: Строка, по которой узнаётся язык: тема и кнопка/вводная
ПРИМЕТЫ = {
    ("verify", "ru"): "Код подтверждения 481516 — SAVDEX",
    ("verify", "en"): "Confirmation code 481516 — SAVDEX",
    ("verify", "uz"): "Tasdiqlash kodi 481516 — SAVDEX",
    ("verify", "tr"): "Doğrulama kodu 481516 — SAVDEX",
    ("verify", "zh"): "验证码 481516 — SAVDEX",
    ("register_code", "ru"): "Код подтверждения 481516 — SAVDEX",
    ("register_code", "en"): "Confirmation code 481516 — SAVDEX",
    ("register_code", "uz"): "Tasdiqlash kodi 481516 — SAVDEX",
    ("register_code", "tr"): "Doğrulama kodu 481516 — SAVDEX",
    ("register_code", "zh"): "验证码 481516 — SAVDEX",
    ("reset", "ru"): "Восстановление пароля — SAVDEX",
    ("reset", "en"): "Reset your password — SAVDEX",
    ("reset", "uz"): "Parolni tiklash — SAVDEX",
    ("reset", "tr"): "Şifre sıfırlama — SAVDEX",
    ("reset", "zh"): "重置密码 — SAVDEX",
}


def _письмо(имя: str, lang: str | None) -> tuple[str, str, str]:
    return mail.render(имя, url=URL, app_url=APP, lang=lang, code=КОД)


def _разметка(body_html: str) -> str:
    """HTML без текста — только теги и атрибуты."""
    return re.sub(r">[^<]*<", "><", re.sub(r' lang="[^"]*"', "", body_html))


@pytest.mark.parametrize("lang", locales.CODES)
@pytest.mark.parametrize("имя", ПИСЬМА)
def test_письмо_на_каждом_языке(имя, lang):
    subject, body_html, body_text = _письмо(имя, lang)

    assert subject.strip() == subject and subject == ПРИМЕТЫ[(имя, lang)]

    for часть in (subject, body_html, body_text):
        assert not re.search(r"__[A-Z_]+__", часть)

    assert f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}">' in body_html
    # Ссылка в HTML экранирована, в тексте — как есть; в письме с кодом
    # регистрации ссылки нет
    экранированная = (
        "https://savdex.uz/verify-email/7/abc?expires=1&amp;signature=f&amp;x=&lt;y&gt;"
    )
    assert (f'href="{экранированная}"' in body_html) is (имя != "register_code")
    assert (URL in body_text) is (имя != "register_code")
    assert f'<a href="{APP}"' in body_html and body_text.startswith(f"SAVDEX: {APP}\n")

    if имя != "reset":
        assert КОД in subject and f"# {КОД}\n" in body_text and f">{КОД}</h1>" in body_html


@pytest.mark.parametrize("имя", ПИСЬМА)
def test_языки_различаются_разметка_одна(имя):
    письма = {lang: _письмо(имя, lang) for lang in locales.CODES}

    for i in range(3):
        # Тема, HTML и текст у каждого языка свои
        assert len({п[i] for п in письма.values()}) == len(locales.CODES)

    # Разметка одна — разнятся только текст и lang
    assert len({_разметка(п[1]) for п in письма.values()}) == 1


def test_русское_письмо():
    _, body_html, body_text = _письмо("verify", "ru")

    assert "Ваш код подтверждения почты на площадке SAVDEX:\n\n# 481516" in body_text
    assert f"Или подтвердите одним нажатием: {URL}" in body_text
    assert ">Здравствуйте!</h1>" in body_html

    _, body_html, body_text = _письмо("reset", "ru")
    assert f"Сбросить пароль: {URL}" in body_text
    assert "Ссылка для сброса пароля действует 60 минут." in body_text
    assert ">Сбросить пароль</a>" in body_html


def test_английский_сброс_как_у_laravel():
    _, body_html, body_text = _письмо("reset", "en")

    assert f"Reset Password: {URL}" in body_text
    assert "This password reset link will expire in 60 minutes." in body_text
    assert "If you did not request a password reset, no further action is required." in body_text
    assert ">Reset Password</a>" in body_html


@pytest.mark.parametrize("lang", ["xx", "", None, "RU", "en-US", "../ru", "zh-Hans"])
@pytest.mark.parametrize("имя", ПИСЬМА)
def test_неизвестный_язык_русский(имя, lang):
    assert _письмо(имя, lang) == _письмо(имя, "ru")


def test_нет_перевода_русский(tmp_path, monkeypatch):
    """Письмо без файлов какого-то языка — целиком русское, и lang тоже ru."""
    for файл in mail._TEMPLATES.glob("verify.*"):
        if файл.name.split(".")[1] in ("ru", "en"):
            (tmp_path / файл.name).write_bytes(файл.read_bytes())

    (tmp_path / "verify.en.subject").unlink()
    monkeypatch.setattr(mail, "_TEMPLATES", tmp_path)

    subject, body_html, _ = _письмо("verify", "en")

    assert subject == ПРИМЕТЫ[("verify", "ru")]
    assert ' lang="ru">' in body_html


def test_выбор_языка():
    assert mail.language("uz", "en") == "uz"
    assert mail.language(None, "tr", "en") == "tr"
    assert mail.language(None, "xx", "") == "ru"
    assert mail.language() == "ru"


def test_файлы_шаблонов():
    """
    Ровно письма × языки × части — без прежних одноязычных файлов.
    notification — письмо уведомлений (savdex/deliveries.py),
    telegram_code — код привязки Telegram-бота (savdex/telegram_bot.py).
    """
    имена = {п.name for п in mail._TEMPLATES.iterdir()}
    ждём = {
        f"{имя}.{lang}.{ext}"
        for имя in (*ПИСЬМА, "notification", "telegram_code")
        for lang in locales.CODES
        for ext in ("subject", "html", "txt")
    }

    assert имена == ждём
