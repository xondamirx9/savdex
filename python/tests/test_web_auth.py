"""
Этап 5: страницы входа, регистрации и пароля на Django — страница,
ответ посредника и сессия после ответа.

Гостевые (/login, /register, /forgot-password, /reset-password/<токен>):
вошедший уходит на главную (guest), язык из адреса при этом запоминается;
?plan= платного тарифа на регистрации — url.intended на оплату; сообщение
status из сессии показывается один раз.

После входа (/verify-email, /password/change, /onboarding/company,
/reviews/new): гость — на вход; пароль, выданный вручную, — на смену,
кроме самой смены и подтверждения почты; подтверждённая почта —
по url.intended или в кабинет; компания уже есть — в кабинет.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .factories import компания
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import (
    СЕССИЯ,
    адрес,
    завести,
    из_django,
    кука,
    куки_ответа,
    открыть,
    пользователь,
    страница,
    строка,
)

pytestmark = нужна_база

SID = "Q" * 40


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    # Тарифы, города и категории, как при деплое — под владельцем базы
    subprocess.run(
        [sys.executable, "manage.py", "seed"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        check=True,
        capture_output=True,
    )

    with адрес() as root:
        yield root


def учётка(email: str, **поля: Any) -> int:
    """Пользователь с почтой (создаётся один раз), поля — каждый раз заново."""
    found = sql("select id from users where email = %s", [email])
    uid = int(found[0][0]) if found else пользователь(email)
    поля = {"locale": "ru", "must_change_password": False, **поля}
    sets = ", ".join(f"{k} = %s" for k in поля)
    sql(f"update users set {sets} where id = %s", [*поля.values(), uid])

    return uid


def сессия(uid: int | None = None, **данные: Any) -> Callable[[], None]:
    """Подготовка запроса: строка sessions с нуля — вошедший uid и данные."""
    payload = {"_token": "t" * 40, **данные}

    if uid is not None:
        payload[laravel_session.LOGIN_KEY] = uid

    def подготовить() -> None:
        # Язык прошлой проверки (/uz/…) уводил бы на /uz/…
        if uid is not None:
            sql("update users set locale = 'ru' where id = %s", [uid])

        завести(SID, payload)

    return подготовить


def зайти(
    сайт: str, path: str, подготовить: Callable[[], None] = lambda: None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ответ Django и строка сессии после него (по куке ответа, иначе — прежняя)."""
    подготовить()
    ответ = открыть(сайт, path, {СЕССИЯ: кука(СЕССИЯ, SID)})
    sid = (куки_ответа(ответ).get(СЕССИЯ) or {}).get("value") or SID
    итог = строка(sid)
    assert итог is not None, sid

    return ответ, итог


def куда(ответ: dict[str, Any]) -> str:
    assert ответ["status"] == 302, ответ["status"]

    return str(ответ["headers"]["location"])


def пропсы(ответ: dict[str, Any]) -> dict[str, Any]:
    assert ответ["status"] == 200, ответ["body"][:500]
    props: dict[str, Any] = страница(ответ["body"])["props"]

    return props


# ── Гостевые ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "component", "locale"),
    [
        ("/login", "auth/Login", "ru"),
        ("/uz/login", "auth/Login", "uz"),
        ("/register", "auth/RegisterEmail", "ru"),
        ("/en/register", "auth/RegisterEmail", "en"),
        ("/forgot-password", "auth/ForgotPassword", "ru"),
        ("/zh/forgot-password", "auth/ForgotPassword", "zh"),
        ("/reset-password/abc123?email=Ivan%40Savdex.uz", "auth/ResetPassword", "ru"),
        ("/tr/reset-password/abc123", "auth/ResetPassword", "tr"),
    ],
)
def test_гостевые_страницы(сайт, path, component, locale):
    ответ, итог = зайти(сайт, path, сессия())
    page = страница(ответ["body"])

    assert ответ["status"] == 200
    assert (page["component"], page["props"]["locale"]) == (component, locale)
    assert page["props"]["auth"]["user"] is None
    assert итог["user_id"] is None
    # Язык из префикса запоминается в сессии
    assert ('"locale":"' + locale + '"' in итог["payload"]) is (locale != "ru")


def ошибка_500(сайт: str, path: str) -> None:
    """
    «Array to string conversion», как у Laravel: страница 500 с кодом
    обращения (md5 сообщения и секунды — первые 8 знаков).
    """
    сессия()()
    ответ = из_django(сайт, path, {СЕССИЯ: кука(СЕССИЯ, SID)})
    стр = страница(ответ["body"])

    assert ответ["status"] == 500
    assert стр["component"] == "Error"
    assert стр["props"]["status"] == 500
    assert re.fullmatch(r"[0-9a-f]{8}", стр["props"]["reference"])


def test_сброс_пароля_почта_массивом(сайт):
    ошибка_500(сайт, "/reset-password/abc123?email[]=x")


def test_сброс_пароля_токен_и_почта(сайт):
    ответ, _ = зайти(сайт, "/reset-password/tok-1?email=%20a%40b.uz%20", сессия())
    props = пропсы(ответ)

    assert props["token"] == "tok-1" and props["email"] == "a@b.uz"


def test_способы_восстановления(сайт):
    ответ, _ = зайти(сайт, "/forgot-password", сессия())

    assert пропсы(ответ)["channels"] == ["mail"]


@pytest.mark.parametrize("path", ["/login", "/forgot-password"])
def test_сообщение_status_один_раз(сайт, path):
    ответ, итог = зайти(
        сайт,
        path,
        сессия(status="Ссылка отправлена", _flash={"old": [], "new": ["status"]}),
    )

    assert пропсы(ответ)["status"] == "Ссылка отправлена"
    assert '"old":["status"]' in итог["payload"]


def test_тариф_из_регистрации_в_url_intended(сайт):
    plan = sql("select code from plans where code <> 'free' and is_active order by id limit 1")
    code = str(plan[0][0])

    for path, ждём in (
        (f"/register?plan={code}", True),
        (f"/uz/register?plan={code}", True),
        ("/register?plan=free", False),
        ("/register?plan=nope", False),
    ):
        _, итог = зайти(сайт, path, сессия())

        # json_encode экранирует «/»
        assert ("billing?plan=" in итог["payload"]) is ждём, path

    # Массив вместо строки — у Laravel ошибка 500
    ошибка_500(сайт, "/register?plan[]=x")


@pytest.mark.parametrize("path", ["/login", "/register", "/forgot-password", "/reset-password/x"])
def test_вошедший_уходит_на_главную(сайт, path):
    uid = учётка("guest-in@savdex.uz")
    ответ, _ = зайти(сайт, path, сессия(uid))

    assert куда(ответ).rstrip("/").endswith(сайт.split("//")[1].split("/")[0])


def test_вошедший_на_языке_запоминает_язык(сайт):
    uid = учётка("guest-uz@savdex.uz")

    def подготовить() -> None:
        sql("update users set locale = 'ru' where id = %s", [uid])
        сессия(uid)()

    ответ, итог = зайти(сайт, "/uz/login", подготовить)

    assert куда(ответ).endswith("/uz")
    assert '"locale":"uz"' in итог["payload"]
    assert sql("select locale from users where id = %s", [uid]) == [("uz",)]


# ── После входа ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["/verify-email", "/password/change", "/onboarding/company", "/uz/reviews/new"]
)
def test_гость_уходит_на_вход(сайт, path):
    ответ, итог = зайти(сайт, path, сессия())

    assert "/login" in куда(ответ)
    assert '"intended":' in итог["payload"]


def test_подтверждение_почты_ждёт(сайт):
    uid = учётка("unverified-auth@savdex.uz", email_verified_at=None)
    ответ, _ = зайти(сайт, "/verify-email", сессия(uid))

    assert пропсы(ответ)["email"] == "unverified-auth@savdex.uz"


@pytest.mark.parametrize(
    ("path", "intended", "ждём"),
    [
        ("/verify-email", None, "/cabinet"),
        ("/uz/verify-email", None, "/uz/cabinet"),
        ("/verify-email", "/cabinet/billing?plan=pro", "/cabinet/billing?plan=pro"),
        ("/en/verify-email", "/cabinet/billing?plan=pro", "/en/cabinet/billing?plan=pro"),
        ("/verify-email", "https://example.com/x", "https://example.com/x"),
    ],
)
def test_почта_подтверждена_дальше(сайт, path, intended, ждём):
    uid = учётка("verified-auth@savdex.uz")
    данные = {}

    if intended is not None:
        адрес = сайт + intended if intended.startswith("/") else intended
        данные = {"url": {"intended": адрес}}

    ответ, итог = зайти(сайт, path, сессия(uid, **данные))

    assert куда(ответ).endswith(ждём)
    assert "intended" not in итог["payload"]


def test_смена_пароля(сайт):
    uid = учётка("forced@savdex.uz", must_change_password=True)

    # Сама смена пароля и подтверждение почты открыты
    пропсы(зайти(сайт, "/password/change", сессия(uid))[0])
    пропсы(
        зайти(
            сайт,
            "/verify-email",
            lambda: (
                sql("update users set email_verified_at = null where id = %s", [uid]),
                сессия(uid)(),
            ),
        )[0]
    )
    sql("update users set email_verified_at = now() where id = %s", [uid])

    # Остальное — на смену пароля с предупреждением
    for path in ("/onboarding/company", "/reviews/new", "/uz/reviews/new"):
        ответ, итог = зайти(сайт, path, сессия(uid))

        assert "/password/change" in куда(ответ)
        assert '"warning":' in итог["payload"]

    # Без флага смены пароля — в кабинет
    учётка("forced@savdex.uz", must_change_password=False)

    for path, ждём in (("/password/change", "/cabinet"), ("/uz/password/change", "/uz/cabinet")):
        assert куда(зайти(сайт, path, сессия(uid))[0]).endswith(ждём)


@pytest.mark.parametrize("account_type", ["legal", "individual", "freelancer", "strange"])
@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_шаг_компании(сайт, account_type, prefix):
    uid = учётка("onboarding@savdex.uz", account_type=account_type, company_id=None)
    ответ, _ = зайти(сайт, f"{prefix}/onboarding/company", сессия(uid))
    props = пропсы(ответ)

    assert props["accountType"] == (account_type if account_type != "strange" else "legal")
    assert props["cities"] and props["categories"] and props["serviceCategories"]


def test_шаг_компании_пройден(сайт):
    uid = учётка("onboarded@savdex.uz", company_id=компания())

    assert куда(зайти(сайт, "/onboarding/company", сессия(uid))[0]).endswith("/cabinet")


@pytest.mark.parametrize(
    ("legal_form", "город", "открыт"),
    [("legal", False, True), ("legal", True, False), ("individual", False, False)],
)
def test_шаг_компании_после_регистрации(сайт, legal_form, город, открыт):
    """
    Юрлицо заводит компанию на первом шаге регистрации: пока город не
    указан, второй шаг открыт и дозаполняет недостающее (completing).
    """
    city = sql("select id from cities order by id limit 1")[0][0] if город else None
    uid = учётка("registered@savdex.uz", company_id=компания(legal_form=legal_form, city_id=city))
    ответ, _ = зайти(сайт, "/onboarding/company", сессия(uid))

    if открыт:
        assert пропсы(ответ)["completing"] is True
    else:
        assert куда(ответ).endswith("/cabinet")


def test_отзыв_о_площадке(сайт):
    uid = учётка("platform-review@savdex.uz", company_id=None)

    props = пропсы(зайти(сайт, "/reviews/new", сессия(uid))[0])
    assert props["review"] is None and props["blocked"] is None

    sql(
        "insert into platform_reviews (user_id, rating, rating_usability, rating_search, "
        "rating_support, body, status, moderator_note, created_at, updated_at) values "
        "(%s, 4, 5, 3, null, %s, 'moderation', 'Уточните', now(), now())",
        [uid, "Удобно искать поставщиков, но поддержка отвечает медленно."],
    )

    for path in ("/reviews/new", "/en/reviews/new"):
        props = пропсы(зайти(сайт, path, сессия(uid))[0])
        assert props["review"]["rating_support"] == 0

    # Почта не подтверждена, аккаунт или компания заблокированы
    sql("update users set email_verified_at = null where id = %s", [uid])
    assert пропсы(зайти(сайт, "/reviews/new", сессия(uid))[0])["blocked"]

    sql("update users set email_verified_at = now(), status = 'blocked' where id = %s", [uid])
    assert пропсы(зайти(сайт, "/reviews/new", сессия(uid))[0])["blocked"]

    company = компания(status="blocked")
    sql("update users set status = 'active', company_id = %s where id = %s", [company, uid])
    assert пропсы(зайти(сайт, "/reviews/new", сессия(uid))[0])["blocked"]
