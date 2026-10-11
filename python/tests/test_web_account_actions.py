"""
Пароль и почта — проверки Django.

- Смена выданного пароля: проверка, «не тот же, что выдан», флаг снят,
  хеш в сессии — новый, администратору — в панель (409 для Inertia).
- «Забыли пароль»: ответ один при любом исходе, письмо со ссылкой
  (оформление — как у Laravel, язык — страницы, где просили сброс),
  токен брокера в password_reset_tokens, не чаще раза в минуту;
  гостевой маршрут.
- Сброс по токену: проверка, чужой, просроченный и верный токен.
- Подтверждение почты: код из кэша (попытки, одноразовость), письмо
  ещё раз (на языке страницы, без префикса — профиля), подписанная
  ссылка (подпись, отпечаток почты, срок).

Письма — в своём журнале (MAIL_MAILER=log), кэш — файловый.
Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import bcrypt
import pytest

from savdex import laravel_cache

from .pg_admin import APP_KEY, КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .test_web_register_actions import _письма, _разбор
from .web_site import ПАРОЛЬ, адрес

pytestmark = нужна_база

ПОЧТА = "account@savdex.uz"
НОВЫЙ = "Cement2027x"
ТОКЕН_СБРОСА = "a" * 64
#: Свой журнал писем: storage/logs — общий с другими проверками
ЖУРНАЛ = Path(КОРЕНЬ) / "storage/logs/python-mail-test-account.log"
КЭШ = Path(КОРЕНЬ) / "storage/framework/cache/data"
ОКРУЖЕНИЕ_DJANGO = {"MAIL_MAILER": "log", "CACHE_STORE": "file", "MAIL_LOG_PATH": str(ЖУРНАЛ)}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    было = os.environ.get("CACHE_STORE")
    os.environ["CACHE_STORE"] = "file"

    with адрес() as root:
        yield root

    if было is None:
        os.environ.pop("CACHE_STORE", None)
    else:
        os.environ["CACHE_STORE"] = было


def _хеш(значение: str) -> str:
    return "$2y$" + bcrypt.hashpw(значение.encode(), bcrypt.gensalt(4)).decode()[4:]


def _проверка(значение: str, хеш: str) -> bool:
    return bcrypt.checkpw(значение.encode(), ("$2b$" + хеш[4:]).encode())


def пользователь(**поля: Any) -> int:
    uid = учётка(
        ПОЧТА,
        **{"status": "active", "email_verified_at": "2026-01-01 00:00:00", **поля},
    )
    sql("update users set remember_token = 'старый' where id = %s", [uid])

    return uid


def подготовка(*шаги: Callable[[], None]) -> Callable[[], None]:
    """Чистые кэш (и счётчики throttle), журналы писем и токены сброса."""

    def run() -> None:
        shutil.rmtree(КЭШ, ignore_errors=True)
        ЖУРНАЛ.parent.mkdir(parents=True, exist_ok=True)
        ЖУРНАЛ.write_text("")
        sql("delete from password_reset_tokens")
        sql("delete from admin_actions")

        for шаг in шаги:
            шаг()

    return run


def _без_изменчивого(текст: str) -> str:
    текст = re.sub(r"\b\d{6}\b", "<код>", текст)
    текст = re.sub(r"expires=\d+", "expires=<срок>", текст)
    текст = re.sub(r"signature=[0-9a-f]{64}", "signature=<подпись>", текст)
    текст = re.sub(r"/reset-password/[0-9a-f]{64}", "/reset-password/<токен>", текст)

    return re.sub(r"https?://127\.0\.0\.1:\d+", "<сайт>", текст)


def _письма_сайта() -> list[dict[str, Any]]:
    return [_разбор(п) for п in _письма(ЖУРНАЛ.read_text())]


def снимок() -> dict[str, Any]:
    uid_rows = sql("select id from users where email = %s", [ПОЧТА])
    uid = uid_rows[0][0] if uid_rows else 0
    письма = _письма_сайта()
    токены = sql("select email, token, created_at is not null from password_reset_tokens")

    # Токен из письма сходится с хешем брокера
    for письмо in письма:
        найдено = re.search(r"/reset-password/([0-9a-f]{64})\?email=", письмо["text"])

        if найдено:
            assert len(токены) == 1 and _проверка(найдено.group(1), токены[0][1])

    код = laravel_cache.get(f"email_verification_code.{uid}")

    return {
        "users": sql(
            "select email, password like '$2y$12$%%', password like '$2y$04$%%', "
            "remember_token = 'старый', must_change_password, email_verified_at is not null "
            "from users where email = %s",
            [ПОЧТА],
        ),
        "tokens": [(e, t.startswith("$2y$"), c) for e, t, c in токены],
        "code": None if not isinstance(код, dict) else {"attempts": код.get("attempts")},
        "mail": [{k: _без_изменчивого(v) for k, v in п.items()} for п in письма],
        "journal": [
            (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
            for a, s, label, ch in sql(
                "select action, section, subject_label, changes::text from admin_actions "
                "order by id"
            )
        ],
    }


def _без_хеша(payload: str) -> str:
    """Хеш нового пароля в сессии (соль случайная): только «есть»."""
    return re.sub(r'("password_hash_web":)"[^"]*"', r'\1"<хеш>"', payload)


def форма(сайт: str, path: str, шаг: Callable[[], None], **kwargs: Any) -> dict[str, Any]:
    return отправить(сайт, path, подготовка(шаг), снимок, env=ОКРУЖЕНИЕ_DJANGO, **kwargs)


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Строка сессии после ответа — разобранным JSON, без токена и отметки входа."""
    payload = json.loads(_без_хеша(итог["сессия"]["payload"])) if итог["сессия"] else {}

    return {k: v for k, v in payload.items() if k != "_token" and not k.startswith("login_web")}


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]] | None:
    errors = сессия(итог).get("errors")

    return None if errors is None else dict(errors["default"]["messages"])


def куда(сайт: str, итог: dict[str, Any]) -> tuple[int, str | None]:
    """Статус и адрес перехода (без адреса сайта)."""
    ответ = итог["ответ"]
    location = ответ["headers"].get("location") or ответ["headers"].get("x-inertia-location")

    return ответ["status"], None if location is None else location.removeprefix(сайт)


#: Пользователь в снимке: почта, хеш нового пароля (12 раундов), прежний
#: хеш фабрики (4 раунда), токен «запомнить» прежний, «сменить пароль»,
#: почта подтверждена
БЫЛ = (ПОЧТА, False, True, True)
СМЕНИЛ = (ПОЧТА, True, False, True)
СБРОСИЛ = (ПОЧТА, True, False, False)

# ── Смена выданного пароля ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("body", "ошибка"),
    [
        ({}, ["Придумайте пароль"]),
        ({"password": НОВЫЙ, "password_confirmation": "другой"}, ["Пароли не совпадают"]),
        (
            {"password": "short1", "password_confirmation": "short1"},
            ["Пароль должен быть не короче 8 символов"],
        ),
        (
            {"password": "onlyletterslong", "password_confirmation": "onlyletterslong"},
            ["Добавьте в пароль хотя бы одну цифру"],
        ),
        (
            {"password": ["x"], "password_confirmation": ["x"]},
            ["Укажите текст.", "Пароль должен быть не короче 8 символов"],
        ),
        # Не тот же, что выдан
        (
            {"password": ПАРОЛЬ, "password_confirmation": ПАРОЛЬ},
            ["Новый пароль совпадает с прежним. Придумайте другой"],
        ),
        ({"password": НОВЫЙ, "password_confirmation": НОВЫЙ}, None),
    ],
)
def test_смена_пароля(сайт, body, ошибка):
    uid = пользователь(must_change_password=True)
    итог = форма(
        сайт,
        "/password/change",
        lambda: пользователь(must_change_password=True, password=_хеш(ПАРОЛЬ)),
        uid=uid,
        body=body,
    )

    if ошибка is None:
        # Флаг снят, хеш в сессии — новый
        assert куда(сайт, итог) == (302, "/cabinet")
        assert итог["база"]["users"] == [(*СМЕНИЛ, False, True)]
        assert сессия(итог)["success"] == "Пароль изменён"
        assert сессия(итог)["password_hash_web"] == "<хеш>"
    else:
        assert куда(сайт, итог) == (302, "/cabinet/settings")
        assert ошибки(итог) == {"password": ошибка}
        assert итог["база"]["users"] == [(*БЫЛ, True, True)]

    assert итог["база"]["journal"] == []


@pytest.mark.parametrize(("заголовки", "status"), [("inertia", 409), ("form", 302)])
def test_смена_пароля_администратора(сайт, заголовки, status):
    """Администратору — в панель: Inertia уходит туда по 409."""
    uid = пользователь(must_change_password=True, is_admin=True)
    headers = (
        inertia()
        if заголовки == "inertia"
        else {"Content-Type": "application/x-www-form-urlencoded"}
    )
    итог = форма(
        сайт,
        "/password/change",
        lambda: пользователь(must_change_password=True, is_admin=True, password=_хеш(ПАРОЛЬ)),
        uid=uid,
        body=f"_token={'t' * 40}&password={НОВЫЙ}&password_confirmation={НОВЫЙ}"
        if заголовки == "form"
        else {"password": НОВЫЙ, "password_confirmation": НОВЫЙ},
        content_type="application/x-www-form-urlencoded"
        if заголовки == "form"
        else "application/json",
        headers=headers,
    )

    assert куда(сайт, итог) == (status, "/admin")
    assert итог["база"]["users"] == [(*СМЕНИЛ, False, True)]
    # Правка администратора — в журнал, пароль скрыт
    [(action, section, label, changes)] = итог["база"]["journal"]
    assert (action, section, label) == ("updated", "users", f"Покупатель {ПОЧТА}")
    assert json.loads(changes) == {
        "before": {"password": "···", "must_change_password": True},
        "after": {"password": "···", "must_change_password": False},
    }


def test_смена_пароля_гостю_нельзя(сайт):
    пользователь(must_change_password=True, password=_хеш(ПАРОЛЬ))
    итог = форма(
        сайт,
        "/password/change",
        lambda: None,
        body={"password": НОВЫЙ, "password_confirmation": НОВЫЙ},
    )

    assert куда(сайт, итог) == (302, "/login")
    assert итог["база"]["users"] == [(*БЫЛ, True, True)]


# ── Забыли пароль ───────────────────────────────────────────────────

ОТВЕТ_СБРОСА = "Если такой адрес зарегистрирован, письмо со ссылкой уже отправлено."


def _свежий_токен() -> None:
    sql(
        "insert into password_reset_tokens (email, token, created_at) values (%s, %s, now())",
        [ПОЧТА, _хеш("прежний")],
    )


@pytest.mark.parametrize(
    ("body", "шаг", "ошибки_", "письмо"),
    [
        ({}, None, {"email": ["Введите почту"]}, False),
        ({"email": "нет"}, None, {"email": ["Проверьте адрес почты"]}, False),
        # Ответ один при любом исходе
        ({"email": "nobody@savdex.uz"}, None, None, False),
        ({"email": ПОЧТА}, None, None, True),
        ({"email": ПОЧТА.upper()}, None, None, True),
        ({"email": ПОЧТА, "channel": "telegram"}, None, None, True),
        ({"email": ПОЧТА, "channel": "pigeon"}, None, None, True),
        # Не чаще раза в минуту: свежий токен — письма нет
        ({"email": ПОЧТА}, _свежий_токен, None, False),
        ({"email": ПОЧТА, "channel": ["mail"]}, None, {"channel": ["Укажите текст."]}, False),
    ],
)
def test_забыли_пароль(сайт, body, шаг, ошибки_, письмо):
    пользователь()

    def готово() -> None:
        пользователь()

        if шаг is not None:
            шаг()

    итог = форма(сайт, "/forgot-password", готово, body=body)
    база = итог["база"]

    assert куда(сайт, итог) == (302, "/cabinet/settings")
    assert ошибки(итог) == ошибки_

    if ошибки_ is None:
        assert сессия(итог)["status"] == ОТВЕТ_СБРОСА

    # Токен брокера — хешем; со ссылкой из письма его сверяет снимок()
    assert база["tokens"] == ([(ПОЧТА, True, True)] if письмо or шаг else [])
    assert len(база["mail"]) == int(письмо)

    if письмо:
        # Страница без префикса — письмо на русском
        [m] = база["mail"]
        assert (m["subject"], m["to"]) == ("Восстановление пароля — SAVDEX", ПОЧТА)
        assert m["from"] == "SAVDEX <hello@example.com>"
        assert (
            "Сбросить пароль: <сайт>/reset-password/<токен>?email=account%40savdex.uz" in m["text"]
        )
        assert "Ссылка для сброса пароля действует 60 минут." in m["text"]
        assert ' lang="ru">' in m["html"]


@pytest.mark.parametrize(
    ("path", "данные", "lang", "тема", "кнопка"),
    [
        ("/en/forgot-password", None, "en", "Reset your password — SAVDEX", "Reset Password"),
        ("/uz/forgot-password", None, "uz", "Parolni tiklash — SAVDEX", "Parolni tiklash"),
        ("/tr/forgot-password", None, "tr", "Şifre sıfırlama — SAVDEX", "Şifreyi sıfırla"),
        # Адрес без префикса — язык страницы из сессии
        ("/forgot-password", {"locale": "zh"}, "zh", "重置密码 — SAVDEX", "重置密码"),
    ],
)
def test_забыли_пароль_на_языке_страницы(сайт, path, данные, lang, тема, кнопка):
    """Письмо — на языке страницы, где просили сброс, а не на языке профиля."""
    итог = форма(сайт, path, пользователь, данные=данные, body={"email": ПОЧТА})

    [m] = итог["база"]["mail"]
    assert (m["subject"], m["to"]) == (тема, ПОЧТА)
    # Ссылка — на языке письма (с префиксом), русская — без
    префикс = "" if lang == "ru" else f"/{lang}"
    assert f"{кнопка}: <сайт>{префикс}/reset-password/<токен>" in m["text"].replace("：", ": ")
    assert f' lang="{lang}">' in m["html"] and f">{кнопка}</a>" in m["html"]
    assert итог["база"]["tokens"] == [(ПОЧТА, True, True)]


def test_забыли_пароль_вошедшему_нельзя(сайт):
    uid = пользователь()
    итог = форма(сайт, "/forgot-password", lambda: None, uid=uid, body={"email": ПОЧТА})

    # Гостевой маршрут: вошедшего — на главную, письма нет
    assert куда(сайт, итог) == (302, "")
    assert итог["база"]["mail"] == [] and итог["база"]["tokens"] == []


# ── Сброс по токену ─────────────────────────────────────────────────


def _токен(минут_назад: int = 0, token: str = ТОКЕН_СБРОСА) -> Callable[[], None]:
    def run() -> None:
        пользователь(must_change_password=True)
        sql(
            "insert into password_reset_tokens (email, token, created_at) "
            "values (%s, %s, now() - make_interval(mins => %s))",
            [ПОЧТА, _хеш(token), минут_назад],
        )

    return run


ВЕРНЫЙ_СБРОС = {
    "token": ТОКЕН_СБРОСА,
    "email": ПОЧТА,
    "password": НОВЫЙ,
    "password_confirmation": НОВЫЙ,
}
НЕДЕЙСТВИТЕЛЬНА = {
    "email": ["Ссылка недействительна или устарела. Запросите новую — они живут 60 минут."]
}


@pytest.mark.parametrize(
    ("body", "шаг", "ошибки_"),
    [
        (
            {},
            _токен(),
            {
                "token": ["Заполните это поле."],
                "email": ["Введите почту"],
                "password": ["Придумайте пароль"],
            },
        ),
        (
            {**ВЕРНЫЙ_СБРОС, "password_confirmation": "другой"},
            _токен(),
            {"password": ["Пароли не совпадают"]},
        ),
        (
            {**ВЕРНЫЙ_СБРОС, "password": "short", "password_confirmation": "short"},
            _токен(),
            {
                "password": [
                    "Пароль должен быть не короче 8 символов",
                    "Добавьте в пароль хотя бы одну цифру",
                ]
            },
        ),
        ({**ВЕРНЫЙ_СБРОС, "email": "плохо"}, _токен(), {"email": ["Проверьте адрес почты"]}),
        # Чужой токен, чужая почта, просроченный, без токена
        ({**ВЕРНЫЙ_СБРОС, "token": "b" * 64}, _токен(), НЕДЕЙСТВИТЕЛЬНА),
        ({**ВЕРНЫЙ_СБРОС, "email": "nobody@savdex.uz"}, _токен(), НЕДЕЙСТВИТЕЛЬНА),
        (ВЕРНЫЙ_СБРОС, _токен(минут_назад=61), НЕДЕЙСТВИТЕЛЬНА),
        (ВЕРНЫЙ_СБРОС, lambda: пользователь(must_change_password=True), НЕДЕЙСТВИТЕЛЬНА),
        (ВЕРНЫЙ_СБРОС, _токен(), None),
    ],
)
def test_сброс_пароля(сайт, body, шаг, ошибки_):
    пользователь()
    итог = форма(сайт, "/reset-password", шаг, body=body)
    база = итог["база"]

    if ошибки_ is None:
        # Пароль сменён, токен «запомнить» новый, токен сброса израсходован — на вход
        assert куда(сайт, итог) == (302, "/login")
        assert сессия(итог)["status"] == "Пароль изменён. Войдите с новым паролем."
        assert база["users"] == [(*СБРОСИЛ, False, True)]
        assert база["tokens"] == []
    else:
        assert куда(сайт, итог) == (302, "/cabinet/settings")
        assert ошибки(итог) == ошибки_
        assert база["users"] == [(*БЫЛ, True, True)]
        assert база["tokens"] == ([] if шаг.__name__ == "<lambda>" else [(ПОЧТА, True, True)])


# ── Подтверждение почты ─────────────────────────────────────────────


def _код(код: str = "123456", попытки: int = 0) -> Callable[[], None]:
    def run() -> None:
        uid = пользователь(email_verified_at=None)
        laravel_cache.put(
            f"email_verification_code.{uid}", {"hash": _хеш(код), "attempts": попытки}, 900
        )

    return run


ПОДТВЕРЖДЕНА = "Почта подтверждена — теперь доступна публикация объявлений"
НЕ_ПОДОШЁЛ = {
    "code": ["Код не подошёл или устарел. Отправьте письмо повторно и введите код из него."]
}


@pytest.mark.parametrize(
    ("body", "шаг", "данные", "итог_"),
    [
        ({}, _код(), None, ({"code": ["Введите код из письма"]}, {"attempts": 0})),
        ({"code": "12345"}, _код(), None, ({"code": ["Код — шесть цифр"]}, {"attempts": 0})),
        ({"code": "12345a"}, _код(), None, ({"code": ["Код — шесть цифр"]}, {"attempts": 0})),
        ({"code": 123456.0}, _код(), None, "/cabinet"),
        # Неверный — попытка засчитана
        ({"code": "000000"}, _код(), None, (НЕ_ПОДОШЁЛ, {"attempts": 1})),
        ({"code": "123456"}, _код(), None, "/cabinet"),
        ({"code": 123456}, _код(), None, "/cabinet"),
        # Попытки кончились — код больше не действует
        ({"code": "123456"}, _код(попытки=5), None, (НЕ_ПОДОШЁЛ, None)),
        (
            {"code": "123456"},
            lambda: пользователь(email_verified_at=None),
            None,
            (НЕ_ПОДОШЁЛ, None),
        ),
        (
            {"code": "123456"},
            _код(),
            {"url": {"intended": "http://127.0.0.1/pricing"}},
            "http://127.0.0.1/pricing",
        ),
        # Уже подтверждена — в кабинет без сообщения
        ({"code": "000000"}, lambda: пользователь(), None, None),
    ],
)
def test_код_подтверждения(сайт, body, шаг, данные, итог_):
    uid = пользователь()
    итог = форма(сайт, "/verify-email/code", шаг, uid=uid, body=body, данные=данные)
    база = итог["база"]

    if isinstance(итог_, tuple):
        ошибки_, код = итог_
        assert куда(сайт, итог) == (302, "/cabinet/settings")
        assert ошибки(итог) == ошибки_ and база["code"] == код
        assert база["users"][0][5] is False
    else:
        # Подтверждена, код одноразовый — убран
        assert куда(сайт, итог) == (302, итог_ or "/cabinet")
        assert сессия(итог).get("success") == (None if итог_ is None else ПОДТВЕРЖДЕНА)
        assert база["users"][0][5] is True and база["code"] is None


@pytest.mark.parametrize("проверена", [False, True])
def test_письмо_ещё_раз(сайт, проверена):
    uid = пользователь()
    итог = форма(
        сайт,
        "/email/verification-notification",
        lambda: пользователь(email_verified_at="2026-01-01 00:00:00" if проверена else None),
        uid=uid,
        body={},
    )
    база = итог["база"]

    if проверена:
        assert куда(сайт, итог) == (302, "/cabinet") and база["mail"] == []
        return

    assert куда(сайт, итог) == (302, "/cabinet/settings")
    assert (
        сессия(итог)["status"] == "Письмо отправлено повторно. Не пришло — проверьте папку «Спам»."
    )
    # Новый код в кэше и письмо с кодом и подписанной ссылкой
    assert база["code"] == {"attempts": 0}
    [m] = база["mail"]
    assert (m["subject"], m["to"]) == ("Код подтверждения <код> — SAVDEX", ПОЧТА)
    assert "Ваш код подтверждения почты на площадке SAVDEX:\n\n# <код>" in m["text"]
    отпечаток = hashlib.sha1(ПОЧТА.encode()).hexdigest()
    assert f"<сайт>/verify-email/{uid}/{отпечаток}?expires=<срок>&signature=<подпись>" in m["text"]


@pytest.mark.parametrize(
    ("path", "профиль", "lang", "тема", "вводная"),
    [
        # Префикс адреса — язык страницы, даже если в профиле другой
        (
            "/en/email/verification-notification",
            "ru",
            "en",
            "Confirmation code <код> — SAVDEX",
            "Your email confirmation code for SAVDEX:",
        ),
        (
            "/tr/email/verification-notification",
            "uz",
            "tr",
            "Doğrulama kodu <код> — SAVDEX",
            "SAVDEX’te e-posta doğrulama kodunuz:",
        ),
        # Без префикса — язык профиля (users.locale)
        (
            "/email/verification-notification",
            "uz",
            "uz",
            "Tasdiqlash kodi <код> — SAVDEX",
            "SAVDEX platformasida elektron pochtani tasdiqlash kodingiz:",
        ),
    ],
)
def test_письмо_ещё_раз_на_языке(сайт, path, профиль, lang, тема, вводная):
    uid = пользователь(locale=профиль)
    итог = форма(
        сайт,
        path,
        lambda: пользователь(email_verified_at=None, locale=профиль),
        uid=uid,
        body={},
    )

    [m] = итог["база"]["mail"]
    assert (m["subject"], m["to"]) == (тема, ПОЧТА)
    assert f"{вводная}\n\n# <код>" in m["text"]
    assert f' lang="{lang}">' in m["html"]
    отпечаток = hashlib.sha1(ПОЧТА.encode()).hexdigest()
    assert f"<сайт>/verify-email/{uid}/{отпечаток}?expires=<срок>&signature=<подпись>" in m["text"]


def _ссылка(сайт: str, uid: int, *, почта: str = ПОЧТА, срок: int = 3600) -> str:
    отпечаток = hashlib.sha1(почта.encode()).hexdigest()
    путь = f"/verify-email/{uid}/{отпечаток}?expires={int(time.time()) + срок}"
    подпись = hmac.new(APP_KEY.encode(), (сайт + путь).encode(), hashlib.sha256).hexdigest()

    return путь + "&signature=" + подпись


def _испорчена(ссылка: str) -> str:
    return ссылка[:-1] + ("1" if ссылка.endswith("0") else "0")


@pytest.mark.parametrize(
    ("вариант", "итог_"),
    [
        ("верно", (302, "/cabinet", ПОДТВЕРЖДЕНА)),
        ("уже", (302, "/cabinet", "Почта уже подтверждена")),
        # Подпись, срок, чужой номер, отпечаток другой почты — 403
        ("подпись", (403, None, None)),
        ("срок", (403, None, None)),
        ("чужой", (403, None, None)),
        ("почта", (403, None, None)),
        ("без_подписи", (403, None, None)),
        ("intended", (302, "/pricing", ПОДТВЕРЖДЕНА)),
    ],
)
def test_ссылка_подтверждения(сайт, вариант, итог_):
    uid = пользователь()
    путь = {
        "верно": _ссылка(сайт, uid),
        "уже": _ссылка(сайт, uid),
        # Последний знак подписи — на другой: подпись сама может кончаться на «0»
        "подпись": _испорчена(_ссылка(сайт, uid)),
        "срок": _ссылка(сайт, uid, срок=-10),
        "чужой": _ссылка(сайт, uid + 1000),
        "почта": _ссылка(сайт, uid, почта="other@savdex.uz"),
        "без_подписи": _ссылка(сайт, uid).split("&signature=")[0],
        "intended": _ссылка(сайт, uid),
    }[вариант]
    итог = форма(
        сайт,
        путь,
        lambda: пользователь(email_verified_at="2026-01-01 00:00:00" if вариант == "уже" else None),
        uid=uid,
        method="GET",
        body="",
        headers={},
        данные={"url": {"intended": сайт + "/pricing"}} if вариант == "intended" else None,
    )
    status, location, success = итог_

    assert куда(сайт, итог) == (status, location)
    assert сессия(итог).get("success") == success
    assert итог["база"]["users"][0][5] is (status == 302)


def test_код_снимает_метку_не_подтверждено(сайт):
    """Код пропущен при регистрации — подтверждение почты снимает «Не подтверждено»."""
    from .factories import компания

    def шаг() -> None:
        _код()()
        cid = компания(email_unconfirmed=True)
        sql(
            "update users set email_code_skipped = true, company_id = %s where email = %s",
            [cid, ПОЧТА],
        )

    uid = пользователь()
    итог = форма(сайт, "/verify-email/code", шаг, uid=uid, body={"code": "123456"})

    assert куда(сайт, итог) == (302, "/cabinet")
    assert sql(
        "select u.email_code_skipped, c.email_unconfirmed from users u "
        "join companies c on c.id = u.company_id where u.email = %s",
        [ПОЧТА],
    ) == [(False, False)]
