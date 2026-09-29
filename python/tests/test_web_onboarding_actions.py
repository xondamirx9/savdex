"""
Второй шаг регистрации, пропуск, «Оцените SavdEx» и удаление учётки на
Django неотличимы от Laravel.

- Компания со второго шага: проверка (ИНН по правилу Tin — у физлица
  и ПИНФЛ, одна компания на ИНН, до пяти направлений), форма
  собственности из регистрации, адрес из названия, направления,
  владелец, переход к подтверждению почты; у кого компания есть —
  в кабинет. Пропуск — туда же с предупреждением.
- Отзыв о площадке: проверка, кто может, премодерация и проверка
  текста, правка своего — снова на проверку.
- Удаление учётки: пароль ещё раз, объявления владельца — в архив,
  выход, мягкое удаление, новая сессия.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база, страна
from .test_web_forms import отправить, учётка
from .web_site import ПАРОЛЬ, laravel

pytestmark = нужна_база

ПОЧТА = "onboard@savdex.uz"
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    страна("kz", {"ru": "Казахстан"})
    sql(
        "insert into cities (country_id, slug, sort, is_active, created_at, updated_at) "
        "values (%s, 'tashkent', 0, true, now(), now())",
        [uz],
    )
    php(
        f"App\\Models\\Company::factory()->create(['slug' => 'mine', 'country_id' => {uz},"
        " 'tin' => '301234567']);"
        "App\\Models\\Company::factory()->create(['slug' => 'blocked', 'status' => 'blocked']);"
        "foreach (['cement', 'metal', 'wood', 'glass', 'paint', 'tiles'] as $slug) {"
        " App\\Models\\Category::factory()->create(['slug' => $slug]); }"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def _номер(table: str, slug: str) -> int:
    return int(sql(f"select id from {table} where slug = %s", [slug])[0][0])


def _страна(code: str) -> int:
    return int(sql("select id from countries where code = %s", [code])[0][0])


def _город() -> int:
    return int(sql("select id from cities where slug = 'tashkent'")[0][0])


def пользователь(**поля: Any) -> int:
    return учётка(
        ПОЧТА,
        **{
            "status": "active",
            "company_id": None,
            "company_role": "owner",
            "account_type": "legal",
            "email_verified_at": "2026-01-01 00:00:00",
            "deleted_at": None,
            **поля,
        },
    )


def _журнал() -> list[Any]:
    return [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions order by id"
        )
    ]


# ── Второй шаг регистрации ──────────────────────────────────────────


def сброс_компаний(**поля: Any) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions")
        sql("update users set company_id = null where email = %s", [ПОЧТА])
        sql("delete from companies where slug not in ('mine', 'blocked')")
        sql("select setval('companies_id_seq', (select max(id) from companies) + 1, false)")
        sql("select setval('company_category_id_seq', 1, false)")
        пользователь(**поля)

    return run


def снимок_компаний() -> Any:
    return {
        "companies": sql(
            "select id, slug, name, type, legal_form, country_id, city_id, tin, primary_role, "
            "custom_category, status, search_text, created_at is not null "
            "from companies where slug not in ('mine', 'blocked') order by id"
        ),
        "categories": sql(
            "select id, company_id, category_id, created_at, updated_at from company_category "
            "order by id"
        ),
        "user": sql(
            "select company_id is not null, company_role from users where email = %s", [ПОЧТА]
        ),
        "journal": _журнал(),
    }


def верно() -> dict[str, Any]:
    return {
        "name": "  Цемент Плюс ",
        "type": "manufacturer",
        "country_id": _страна("uz"),
        "city_id": _город(),
        "tin": "302345678",
        "primary_role": "supplier",
        "categories": [_номер("categories", "cement"), str(_номер("categories", "metal"))],
        "custom_category": "Бетон",
    }


@pytest.mark.parametrize(
    ("правка", "поля"),
    [
        ({}, {}),
        ({}, {"account_type": "individual"}),
        ({"type": None}, {"account_type": "freelancer"}),
        ({"type": None}, {}),
        ({"type": None, "name": ""}, {"account_type": "individual"}),
        ({"tin": "12345678901234"}, {"account_type": "individual"}),
        ({"tin": "12345678901234"}, {}),
        ({"tin": "3023456"}, {"account_type": "individual"}),
        ({"tin": "30234567a"}, {}),
        ({"tin": "111111111"}, {}),
        ({"tin": "301234567"}, {}),
        ({"tin": "12345", "country_id": "kz"}, {}),
        ({"tin": "1234567", "country_id": "kz"}, {}),
        ({"tin": None}, {"account_type": "robot"}),
        # Нечисловой город у Laravel — ошибка 500 (exists сравнивает строку
        # с числовым столбцом), у Django — ошибка проверки: здесь число
        ({"country_id": 99999, "city_id": 99998}, {}),
        ({"primary_role": "seller"}, {}),
        ({"categories": "cement"}, {}),
        ({"categories": ["all6"]}, {}),
        ({"categories": [99999, "abc"]}, {}),
        ({"categories": ["dup"]}, {}),
        ({"custom_category": "x" * 81, "name": "Ц"}, {}),
        ({"categories": None}, {}),
    ],
)
def test_второй_шаг(сайт, правка, поля):
    body = {**верно(), **правка}

    if body.get("country_id") == "kz":
        body["country_id"] = _страна("kz")

    if body.get("categories") == ["all6"]:
        body["categories"] = [_номер("categories", s) for s in ("cement", "metal", "wood")] + [
            _номер("categories", s) for s in ("glass", "paint", "tiles")
        ]

    if body.get("categories") == ["dup"]:
        body["categories"] = [_номер("categories", "wood")] * 2

    uid = пользователь(**поля)
    итог = отправить(
        сайт, "/onboarding/company", сброс_компаний(**поля), снимок_компаний, uid=uid, body=body
    )

    if not правка and not поля:
        assert итог["ответ"]["headers"]["location"].endswith("/verify-email")
        assert len(итог["база"]["companies"]) == 1


@pytest.mark.parametrize("admin", [False, True])
def test_второй_шаг_журнал_администратора(сайт, admin):
    uid = пользователь(is_admin=admin)
    отправить(
        сайт,
        "/onboarding/company",
        сброс_компаний(is_admin=admin),
        снимок_компаний,
        uid=uid,
        body=верно(),
    )


def test_второй_шаг_компания_уже_есть(сайт):
    uid = пользователь()
    mine = _номер("companies", "mine")
    отправить(
        сайт,
        "/onboarding/company",
        сброс_компаний(company_id=mine, company_role="owner"),
        снимок_компаний,
        uid=uid,
        body=верно(),
    )


@pytest.mark.parametrize("uid", [True, None])
def test_пропустить(сайт, uid):
    номер = пользователь()
    отправить(
        сайт,
        "/onboarding/skip",
        сброс_компаний(),
        снимок_компаний,
        uid=номер if uid else None,
        body={},
    )


# ── «Оцените SavdEx» ────────────────────────────────────────────────


def сброс_отзыва(
    *, был: bool = False, премодерация: bool | None = None, **поля: Any
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from platform_reviews")
        sql("select setval('platform_reviews_id_seq', 1, false)")
        sql("delete from settings where key = 'reviews_premoderation'")
        sql("delete from cache")

        if премодерация is not None:
            sql(
                "insert into settings (key, label, type, value, created_at, updated_at) "
                "values ('reviews_premoderation', 'Премодерация', 'boolean', %s, now(), now())",
                [json.dumps(премодерация)],
            )

        uid = пользователь(**поля)

        if был:
            sql(
                "insert into platform_reviews (user_id, company_id, rating, rating_usability, "
                "body, status, moderator_note, moderated_by, moderated_at, created_at, "
                "updated_at) values (%s, null, 5, 4, 'Прежний текст отзыва о площадке, "
                "достаточно длинный', 'hidden', 'Уберите ссылку', 1, now(), "
                "now() - interval '1 day', now() - interval '1 day')",
                [uid],
            )

    return run


def снимок_отзыва() -> Any:
    return sql(
        "select id, user_id is not null, company_id, rating, rating_usability, rating_search, "
        "rating_support, body, status, screening_flags, moderator_note, moderated_by, "
        "moderated_at, updated_at > now() - interval '1 hour' from platform_reviews order by id"
    )


ОТЗЫВ = {
    "rating": 5,
    "rating_usability": "4",
    "rating_search": 0,
    "body": "  Удобно искать поставщиков цемента, быстро отвечают.  ",
}


@pytest.mark.parametrize(
    ("body", "настройка"),
    [
        ({}, {}),
        ({"rating": 6, "body": "коротко", "rating_support": 9}, {}),
        ({"rating": "4.5", "body": ["x"]}, {}),
        ({"rating": 4.0, "body": ОТЗЫВ["body"]}, {}),
        (ОТЗЫВ, {}),
        (ОТЗЫВ, {"премодерация": False}),
        (ОТЗЫВ, {"премодерация": False, "был": True}),
        (ОТЗЫВ, {"был": True}),
        (
            {**ОТЗЫВ, "body": "Пишите мне на почту test@mail.ru, всё расскажу подробно"},
            {"премодерация": False},
        ),
        (ОТЗЫВ, {"email_verified_at": None}),
        (ОТЗЫВ, {"status": "blocked"}),
        (ОТЗЫВ, {"company": "blocked"}),
        (ОТЗЫВ, {"company": "mine"}),
    ],
)
def test_отзыв_о_площадке(сайт, body, настройка):
    настройка = dict(настройка)

    if "company" in настройка:
        настройка["company_id"] = _номер("companies", настройка.pop("company"))

    uid = пользователь()
    отправить(
        сайт,
        "/reviews/new",
        сброс_отзыва(**настройка),
        снимок_отзыва,
        uid=uid,
        body=body,
    )


# ── Удалить учётную запись ──────────────────────────────────────────


def сброс_удаления(**поля: Any) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions")
        sql("delete from listings")
        mine = _номер("companies", "mine")
        php(
            "foreach (['active', 'active', 'draft', 'archived'] as $status) {"
            f" App\\Models\\Listing::factory()->create(['company_id' => {mine},"
            " 'status' => $status]); }"
            "App\\Models\\Listing::factory()->create(['status' => 'active']);"
            "echo 'ok';",
            БЕЗ_ПЕРЕВОДА,
        )
        sql("update listings set updated_at = now() - interval '1 day'")
        пользователь(**поля)
        sql(
            "update users set remember_token = 'старый', updated_at = now() - interval '1 day' "
            "where email = %s",
            [ПОЧТА],
        )

    return run


def снимок_удаления() -> Any:
    return {
        "user": sql(
            "select deleted_at is not null, updated_at > now() - interval '1 hour', "
            "remember_token = 'старый' from users where email = %s",
            [ПОЧТА],
        ),
        "listings": sql(
            "select company_id is not null, status, updated_at > now() - interval '1 hour' "
            "from listings order by id"
        ),
        "journal": _журнал(),
    }


@pytest.mark.parametrize(
    ("body", "поля"),
    [
        ({}, {}),
        ({"password": ["x"]}, {}),
        ({"password": "неверный"}, {}),
        ({"password": ПАРОЛЬ}, {"company": "mine", "company_role": "owner"}),
        ({"password": ПАРОЛЬ}, {"company": "mine", "company_role": "manager"}),
        ({"password": ПАРОЛЬ}, {"company": "mine", "company_role": "owner", "is_admin": True}),
        ({"password": ПАРОЛЬ}, {}),
    ],
)
def test_удалить_учётку(сайт, body, поля):
    поля = dict(поля)

    if "company" in поля:
        поля["company_id"] = _номер("companies", поля.pop("company"))

    uid = пользователь(**поля)
    итог = удаление(сайт, сброс_удаления(**поля), uid, body)

    if body.get("password") == ПАРОЛЬ:
        assert итог["db"]["user"][0][0] is True and итог["location"] == сайт


def удаление(
    сайт: str, подготовка: Callable[[], None], uid: int, body: dict[str, Any]
) -> dict[str, Any]:
    """Сессия после удаления — новая: номер берётся из куки ответа."""
    from savdex import laravel_session

    from .test_web_auth_actions import _сессия_из_ответа
    from .test_web_forms import SID, ТОКЕН, inertia
    from .test_web_session import СЕССИЯ, завести, кука, строка
    from .web_site import из_django, из_laravel

    стороны = {}

    for имя, сторона in (("django", из_django), ("laravel", из_laravel)):
        подготовка()
        завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})
        ответ = сторона(
            сайт,
            "/cabinet/settings/delete",
            {СЕССИЯ: кука(СЕССИЯ, SID)},
            {**inertia(), "Referer": сайт + "/cabinet/settings", "User-Agent": "savdex-parity"},
            method="POST",
            body=json.dumps(body),
            content_type="application/json",
        )
        сессия = _сессия_из_ответа(ответ)
        стороны[имя] = {
            "status": ответ["status"],
            "location": ответ["headers"].get("location"),
            "cookies": sorted(ответ["cookies"]),
            "session": None
            if сессия is None
            else {"payload": сессия["payload"], "user_id": сессия["user_id"]},
            "old_session": строка(SID) is not None,
            "db": снимок_удаления(),
        }

    assert стороны["django"] == стороны["laravel"], json.dumps(
        стороны, ensure_ascii=False, default=str
    )

    return стороны["django"]


# ── Второй шаг у юрлица с компанией из регистрации ─────────────────


def сброс_дополнения(*, город: bool = False, форма: str = "legal") -> Callable[[], None]:
    """Компания заведена при регистрации: название, ИНН, два раздела, без города."""

    def run() -> None:
        сброс_компаний()()
        [(cid,)] = sql(
            "insert into companies (name, slug, legal_form, tin, primary_role, status, "
            "custom_category, city_id, created_at, updated_at) values ('Цемент Плюс', "
            "'cement-plus', %s, '302345678', 'both', 'active', 'Бетон', %s, "
            "now() - interval '1 day', now() - interval '1 day') returning id",
            [форма, _город() if город else None],
        )
        sql(
            "insert into company_category (company_id, category_id) select %s, id "
            "from categories where slug in ('cement', 'metal')",
            [cid],
        )
        пользователь(company_id=cid)

    return run


def снимок_дополнения() -> Any:
    return {
        "companies": sql(
            "select slug, name, type, country_id, city_id, primary_role, custom_category, "
            "updated_at > now() - interval '1 hour' from companies where slug = 'cement-plus'"
        ),
        "categories": sql(
            "select c.slug from company_category cc join categories c on c.id = cc.category_id "
            "join companies k on k.id = cc.company_id where k.slug = 'cement-plus' order by c.slug"
        ),
        "journal": _журнал(),
    }


@pytest.mark.parametrize(
    ("правка", "настройка"),
    [
        ({}, {}),
        ({"categories": ["wood", "glass", "paint", "tiles"]}, {}),
        ({"categories": ["cement"], "custom_category": None}, {}),
        ({"type": None, "city_id": None}, {}),
        ({}, {"город": True}),
        ({}, {"форма": "individual"}),
    ],
)
def test_дополнение_компании(сайт, правка, настройка):
    body = {**верно(), "custom_category": "Сухие смеси", **правка}

    if body.get("categories"):
        body["categories"] = [
            _номер("categories", s) if isinstance(s, str) and not s.isdigit() else s
            for s in body["categories"]
        ]

    uid = пользователь()
    отправить(
        сайт,
        "/onboarding/company",
        сброс_дополнения(**настройка),
        снимок_дополнения,
        uid=uid,
        body=body,
    )
