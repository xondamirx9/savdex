"""
Этап 5: страницы входа, регистрации и пароля на Django неотличимы
от Laravel — страница, ответ посредника и сессия после ответа.

Гостевые (/login, /register, /forgot-password, /reset-password/<токен>):
вошедший уходит на главную (guest), язык из адреса при этом запоминается;
?plan= платного тарифа на регистрации — url.intended на оплату; сообщение
status из сессии показывается один раз.

После входа (/verify-email, /password/change, /onboarding/company,
/reviews/new): гость — на вход; пароль, выданный вручную, — на смену,
кроме самой смены и подтверждения почты; подтверждённая почта —
по url.intended или в кабинет; компания уже есть — в кабинет.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_session import СЕССИЯ, завести, кука, одинаково, по_сторонам
from .web_site import laravel, из_django, из_laravel, пользователь, страница

pytestmark = нужна_база

SID = "Q" * 40


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    for seeder in ("PlanSeeder", "GeoSeeder", "CategorySeeder"):
        subprocess.run(
            ["php", "artisan", "db:seed", f"--class={seeder}", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            check=True,
            capture_output=True,
        )

    with laravel() as root:
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
    """Подготовка стороны: строка sessions с нуля — вошедший uid и данные."""
    payload = {"_token": "t" * 40, **данные}

    if uid is not None:
        payload[laravel_session.LOGIN_KEY] = uid

    def подготовить() -> None:
        # Язык прошлой сверки (/uz/…) уводил бы на /uz/…
        if uid is not None:
            sql("update users set locale = 'ru' where id = %s", [uid])

        завести(SID, payload)

    return подготовить


def сверить_сессию(
    сайт: str, path: str, подготовить: Callable[[], None] = lambda: None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ответ Django и строка сессии после него — одинаковые с Laravel."""
    стороны = по_сторонам(сайт, path, подготовить, cookies={СЕССИЯ: кука(СЕССИЯ, SID)})

    return стороны["django"][0], одинаково(стороны)


def куда(ответ: dict[str, Any]) -> str:
    assert ответ["status"] == 302, ответ["status"]

    return str(ответ["headers"]["location"])


def пропсы(ответ: dict[str, Any]) -> dict[str, Any]:
    assert ответ["status"] == 200, ответ["body"][:500]
    props: dict[str, Any] = страница(ответ["body"])["props"]

    return props


# ── Гостевые ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/uz/login",
        "/register",
        "/en/register",
        "/forgot-password",
        "/zh/forgot-password",
        "/reset-password/abc123?email=Ivan%40Savdex.uz",
        "/tr/reset-password/abc123",
    ],
)
def test_гостевые_страницы(сайт, path):
    ответ, _ = сверить_сессию(сайт, path, сессия())
    пропсы(ответ)


def ошибка_500(сайт: str, path: str) -> None:
    """
    «Array to string conversion» у Laravel: страница 500 с кодом обращения.
    Код — md5 сообщения и секунды, поэтому сверяется всё, кроме него.
    """
    ответы = []

    for сторона in (из_django, из_laravel):
        сессия()()
        ответы.append(сторона(сайт, path, {СЕССИЯ: кука(СЕССИЯ, SID)}))

    стр = [страница(о["body"]) for о in ответы]

    assert [о["status"] for о in ответы] == [500, 500]
    assert all(re.fullmatch(r"[0-9a-f]{8}", с["props"].pop("reference")) for с in стр)
    assert стр[0] == стр[1]


def test_сброс_пароля_почта_массивом(сайт):
    ошибка_500(сайт, "/reset-password/abc123?email[]=x")


def test_сброс_пароля_токен_и_почта(сайт):
    ответ, _ = сверить_сессию(сайт, "/reset-password/tok-1?email=%20a%40b.uz%20", сессия())
    props = пропсы(ответ)

    assert props["token"] == "tok-1" and props["email"] == "a@b.uz"


def test_способы_восстановления(сайт):
    ответ, _ = сверить_сессию(сайт, "/forgot-password", сессия())

    assert пропсы(ответ)["channels"] == ["mail"]


@pytest.mark.parametrize("path", ["/login", "/forgot-password"])
def test_сообщение_status_один_раз(сайт, path):
    ответ, итог = сверить_сессию(
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
        _, итог = сверить_сессию(сайт, path, сессия())

        # json_encode экранирует «/»
        assert ("billing?plan=" in итог["payload"]) is ждём, path

    # Массив вместо строки — у Laravel ошибка 500
    ошибка_500(сайт, "/register?plan[]=x")


@pytest.mark.parametrize("path", ["/login", "/register", "/forgot-password", "/reset-password/x"])
def test_вошедший_уходит_на_главную(сайт, path):
    uid = учётка("guest-in@savdex.uz")
    ответ, _ = сверить_сессию(сайт, path, сессия(uid))

    assert куда(ответ).rstrip("/").endswith(сайт.split("//")[1].split("/")[0])


def test_вошедший_на_языке_запоминает_язык(сайт):
    uid = учётка("guest-uz@savdex.uz")

    def подготовить() -> None:
        sql("update users set locale = 'ru' where id = %s", [uid])
        сессия(uid)()

    ответ, итог = сверить_сессию(сайт, "/uz/login", подготовить)

    assert куда(ответ).endswith("/uz")
    assert '"locale":"uz"' in итог["payload"]
    assert sql("select locale from users where id = %s", [uid]) == [("uz",)]


# ── После входа ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["/verify-email", "/password/change", "/onboarding/company", "/uz/reviews/new"]
)
def test_гость_уходит_на_вход(сайт, path):
    ответ, итог = сверить_сессию(сайт, path, сессия())

    assert "/login" in куда(ответ)
    assert '"intended":' in итог["payload"]


def test_подтверждение_почты_ждёт(сайт):
    uid = учётка("unverified-auth@savdex.uz", email_verified_at=None)
    ответ, _ = сверить_сессию(сайт, "/verify-email", сессия(uid))

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

    ответ, итог = сверить_сессию(сайт, path, сессия(uid, **данные))

    assert куда(ответ).endswith(ждём)
    assert "intended" not in итог["payload"]


def test_смена_пароля(сайт):
    uid = учётка("forced@savdex.uz", must_change_password=True)

    # Сама смена пароля и подтверждение почты открыты
    пропсы(сверить_сессию(сайт, "/password/change", сессия(uid))[0])
    пропсы(
        сверить_сессию(
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
        ответ, итог = сверить_сессию(сайт, path, сессия(uid))

        assert "/password/change" in куда(ответ)
        assert '"warning":' in итог["payload"]

    # Без флага смены пароля — в кабинет
    учётка("forced@savdex.uz", must_change_password=False)

    for path, ждём in (("/password/change", "/cabinet"), ("/uz/password/change", "/uz/cabinet")):
        assert куда(сверить_сессию(сайт, path, сессия(uid))[0]).endswith(ждём)


@pytest.mark.parametrize("account_type", ["legal", "individual", "freelancer", "strange"])
@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_шаг_компании(сайт, account_type, prefix):
    uid = учётка("onboarding@savdex.uz", account_type=account_type, company_id=None)
    ответ, _ = сверить_сессию(сайт, f"{prefix}/onboarding/company", сессия(uid))
    props = пропсы(ответ)

    assert props["accountType"] == (account_type if account_type != "strange" else "legal")
    assert props["cities"] and props["categories"] and props["serviceCategories"]


def test_шаг_компании_пройден(сайт):
    company = php("echo App\\Models\\Company::factory()->create()->id;").splitlines()[-1]
    uid = учётка("onboarded@savdex.uz", company_id=int(company))

    assert куда(сверить_сессию(сайт, "/onboarding/company", сессия(uid))[0]).endswith("/cabinet")


@pytest.mark.parametrize(
    ("legal_form", "город", "открыт"),
    [("legal", False, True), ("legal", True, False), ("individual", False, False)],
)
def test_шаг_компании_после_регистрации(сайт, legal_form, город, открыт):
    """
    Юрлицо заводит компанию на первом шаге регистрации: пока город не
    указан, второй шаг открыт и дозаполняет недостающее (completing).
    """
    city = "App\\Models\\City::query()->value('id')" if город else "null"
    company = php(
        "echo App\\Models\\Company::factory()->create("
        f"['legal_form' => '{legal_form}', 'city_id' => {city}])->id;"
    ).splitlines()[-1]
    uid = учётка("registered@savdex.uz", company_id=int(company))
    ответ, _ = сверить_сессию(сайт, "/onboarding/company", сессия(uid))

    if открыт:
        assert пропсы(ответ)["completing"] is True
    else:
        assert куда(ответ).endswith("/cabinet")


def test_отзыв_о_площадке(сайт):
    uid = учётка("platform-review@savdex.uz", company_id=None)

    props = пропсы(сверить_сессию(сайт, "/reviews/new", сессия(uid))[0])
    assert props["review"] is None and props["blocked"] is None

    sql(
        "insert into platform_reviews (user_id, rating, rating_usability, rating_search, "
        "rating_support, body, status, moderator_note, created_at, updated_at) values "
        "(%s, 4, 5, 3, null, %s, 'moderation', 'Уточните', now(), now())",
        [uid, "Удобно искать поставщиков, но поддержка отвечает медленно."],
    )

    for path in ("/reviews/new", "/en/reviews/new"):
        props = пропсы(сверить_сессию(сайт, path, сессия(uid))[0])
        assert props["review"]["rating_support"] == 0

    # Почта не подтверждена, аккаунт или компания заблокированы
    sql("update users set email_verified_at = null where id = %s", [uid])
    assert пропсы(сверить_сессию(сайт, "/reviews/new", сессия(uid))[0])["blocked"]

    sql("update users set email_verified_at = now(), status = 'blocked' where id = %s", [uid])
    assert пропсы(сверить_сессию(сайт, "/reviews/new", сессия(uid))[0])["blocked"]

    company = php(
        "echo App\\Models\\Company::factory()->create(['status' => 'blocked'])->id;"
    ).splitlines()[-1]
    sql("update users set status = 'active', company_id = %s where id = %s", [int(company), uid])
    assert пропсы(сверить_сессию(сайт, "/reviews/new", сессия(uid))[0])["blocked"]
