"""
Раздел «Тарифы» админки на Django — сквозь настоящую базу и сайт.

Тарифы заводит настоящий manage.py seed (как при деплое). Проверяется: права (правит суперадмин,
финансы только смотрят, прочие не видят), лимиты «пусто — без ограничений»,
цены и сроки, код, что витрина /pricing видит правку сразу, запрет
удаления (free/vip, подписки, счета, промокоды) и журнал.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from .pg_admin import (
    PYTHON,
    ОКРУЖЕНИЕ,
    django,
    sql,
    журнал,
    нужна_база,
    свежая_база,
    сотрудник,
)
from .web_site import адрес, открыть, страница

pytestmark = нужна_база

LIST = "/py/admin/billing/plan/"
ADD = "/py/admin/billing/plan/add/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    # Справочники, как при деплое (вместо PlanSeeder) — под владельцем базы
    subprocess.run(
        [sys.executable, "manage.py", "seed"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        check=True,
    )

    return {role: сотрудник(role) for role in ("superadmin", "finance", "admin")}


def _id(code: str) -> int:
    [(pk,)] = sql("select id from plans where code = %s", [code])

    return int(pk)


def _форма(code: str, **поля: Any) -> dict[str, Any]:
    [row] = sql(
        "select name, sort, price_usd::text, coalesce(price_uzs::text, ''), period_days, "
        "listing_days, coalesce(listings_limit::text, ''), coalesce(contacts_limit::text, ''), "
        "coalesce(responses_limit::text, ''), promo_units, verification_days, "
        "advanced_analytics, sees_interested_names, has_microsite, is_active "
        "from plans where code = %s",
        [code],
    ) or [("Новый", 9, "10", "", 30, 30, "", "", "", 0, 5, False, False, False, True)]
    keys = (
        "name", "sort", "price_usd", "price_uzs", "period_days", "listing_days",
        "listings_limit", "contacts_limit", "responses_limit", "promo_units", "verification_days",
    )  # fmt: skip
    data: dict[str, Any] = {
        "code": code,
        **{k: str(v) for k, v in zip(keys, row[:11], strict=True)},
    }
    for flag, value in zip(
        ("advanced_analytics", "sees_interested_names", "has_microsite", "is_active"),
        row[11:],
        strict=True,
    ):
        if value:
            data[flag] = "on"
    data.update(поля)

    return {k: v for k, v in data.items() if v is not None}


def test_список_и_права(люди):
    вход, список = django(люди["finance"], ("get", LIST, None))

    assert вход == 302
    assert "Business · business" in список["body"] or "business" in список["body"]
    assert "без ограничений" in список["body"]

    _, чужой = django(люди["admin"], ("get", LIST, None))
    assert чужой["status"] == 403

    # Финансам тарифы — только на чтение: цены правит суперадмин
    _, правка = django(
        люди["finance"],
        ("post", f"{LIST}{_id('flash')}/change/", _форма("flash", price_usd="1")),
    )
    assert правка["status"] == 403
    assert sql("select price_usd::text from plans where code = 'flash'") != [("1.00",)]


def test_правка_видна_на_витрине_и_в_журнале(люди):
    pk = _id("business")
    _, ответ = django(
        люди["superadmin"],
        ("post", f"{LIST}{pk}/change/", _форма("business", price_usd="55", listings_limit="")),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert sql("select price_usd::text, listings_limit from plans where id = %s", [pk]) == [
        ("55.00", None)
    ]
    # Витрина /pricing читает тариф сразу — кэша у тарифов нет
    with адрес() as сайт:
        витрина = открыть(сайт, "/pricing")
    page = страница(витрина["body"])
    [business] = [plan for plan in page["props"]["plans"] if plan["code"] == "business"]
    assert page["component"] == "Pricing"
    assert business["price_usd"] == 55.0
    assert business["listings_limit"] is None

    запись = журнал("updated")
    assert запись["section"] == "plans"
    assert запись["user_role"] == "superadmin"
    assert запись["subject_type"] == "App\\Models\\Plan"
    assert запись["changes"]["after"]["price_usd"] == "55.00"


@pytest.mark.parametrize(
    ("поля", "ошибка"),
    [
        ({"price_usd": "-1"}, "Цена не может быть меньше нуля."),
        ({"price_uzs": "0"}, "Больше нуля — или оставьте пустым."),
        ({"period_days": "0"}, "Хотя бы один день."),
        ({"listing_days": "0"}, "Хотя бы один день."),
    ],
)
def test_цены_и_сроки(люди, поля, ошибка):
    _, ответ = django(
        люди["superadmin"], ("post", f"{LIST}{_id('flash')}/change/", _форма("flash", **поля))
    )

    assert ответ["status"] == 200
    assert ошибка in ответ["body"]


def test_новый_тариф_код_и_удаление(люди):
    _, плохой, хороший = django(
        люди["superadmin"],
        ("post", ADD, _форма("Бизнес", name="Бизнес")),
        ("post", ADD, _форма("enterprise", name="Enterprise", price_usd="199")),
    )

    assert "Только латиница" in плохой["body"]
    assert хороший["status"] == 302, хороший["body"][:3000]

    pk = _id("enterprise")
    _, удалён = django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert удалён["status"] == 302
    assert sql("select count(*) from plans where code = 'enterprise'") == [(0,)]


@pytest.mark.parametrize("code", ["free", "vip"])
def test_free_и_vip_не_удаляются(люди, code):
    pk = _id(code)

    _, форма, удаление = django(
        люди["superadmin"],
        ("get", f"{LIST}{pk}/change/", None),
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
    )

    assert f"Нельзя: на тариф «{code}» опирается код площадки" in форма["body"]
    assert удаление["status"] == 403


def test_промокоды_держат_тариф(люди):
    """Промокоды на тариф раньше уходили каскадом вместе с ним."""
    pk = _id("premium")
    sql(
        "insert into promo_codes (code, plan_id, days, is_active, created_at, updated_at) "
        "values ('SVDX-TEST0001', %s, 30, true, now(), now())",
        [pk],
    )

    _, форма, удаление = django(
        люди["superadmin"],
        ("get", f"{LIST}{pk}/change/", None),
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
    )

    assert "Нельзя, на тариф ссылаются: промокоды — 1" in форма["body"]
    assert удаление["status"] == 403
    assert sql("select count(*) from promo_codes where plan_id = %s", [pk]) == [(1,)]
