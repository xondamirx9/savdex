"""
Мастер объявления на Django неотличим от Laravel: новый черновик (без
компании — в профиль, сверх лимита — к списку, пустой черновик
переиспользуется) и публикация (строгая проверка, цена или «договорная»,
лимит тарифа, адрес, уведомление компании, журнал администратора;
отклонённое — нельзя; неподтверждённая почта — на подтверждение).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Category::factory()->create(['slug' => 'cement']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def _компания() -> int:
    return int(sql("select id from companies where slug = 'mine'")[0][0])


def владелец(*, admin: bool = False, verified: bool = True, company: bool = True) -> int:
    return учётка(
        "owner@savdex.uz",
        company_id=_компания() if company else None,
        is_admin=admin,
        email_verified_at="2026-09-01 10:00:00" if verified else None,
    )


def объявления(*строки: tuple[str, str]) -> Callable[[], None]:
    """Подготовка: объявления компании (статус, заголовок) с номерами от 1."""

    def run() -> None:
        sql("delete from listings")
        sql("delete from activity_events")
        sql("delete from user_notifications")
        sql("delete from admin_actions where section = 'listings'")
        sql("select setval('listings_id_seq', 1, false)")

        for status, title in строки:
            sql(
                "insert into listings (company_id, user_id, type, title, description, status, "
                "currency, wizard_step, created_at, updated_at) values (%s, (select id from "
                "users where email = 'owner@savdex.uz'), 'supply', %s, %s, %s, 'UZS', 1, "
                "now() - interval '1 day', now() - interval '1 day')",
                [_компания(), title, None if title == "" else "Мешки", status],
            )

    return run


def снимок() -> Any:
    журнал = [
        (a, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, label, ch in sql(
            "select action, subject_label, changes::text from admin_actions "
            "where section = 'listings' order by id"
        )
    ]

    return {
        "listings": sql(
            "select id, category_id, title, description, price::text, bundle_price::text, "
            "price_negotiable, currency, unit, status, wizard_step, slug, "
            "published_at is not null, expires_at::date - current_date, search_text "
            "from listings order by id"
        ),
        "events": sql("select type, tone, message, url from activity_events order by id"),
        "notifications": sql("select type, title, tone, url from user_notifications order by id"),
        "journal": журнал,
    }


# ── Новый черновик ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("было", "лимит"),
    [
        ((), None),
        ((("draft", ""),), None),
        ((("draft", "Готовый черновик"),), None),
        ((("active", "Цемент"),), 1),
        ((("active", "Цемент"),), 2),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_новый_черновик(сайт, было, лимит, admin):
    uid = владелец(admin=admin)

    def подготовка() -> None:
        sql("update plans set listings_limit = %s where code = 'free'", [лимит])
        объявления(*было)()

    итог = отправить(
        сайт,
        "/cabinet/listings/create",
        подготовка,
        снимок,
        uid=uid,
        method="GET",
        headers={},
    )

    assert итог["ответ"]["status"] == 302


@pytest.mark.parametrize("случай", ["без компании", "почта"])
def test_новый_черновик_отказ(сайт, случай):
    uid = владелец(company=случай != "без компании", verified=случай != "почта")
    отправить(
        сайт,
        "/en/cabinet/listings/create",
        объявления(),
        снимок,
        uid=uid,
        method="GET",
        headers={},
    )


# ── Публикация ──────────────────────────────────────────────────────


def _категория() -> int:
    return int(sql("select id from categories where slug = 'cement'")[0][0])


ВЕРНО = {
    "title": "Цемент М400 в мешках по 50 кг",
    "description": "Портландцемент, доставка по Ташкенту, самовывоз со склада в Сергели.",
    "price": "52000",
    "currency": "UZS",
    "unit": "мешок",
    "price_negotiable": False,
}


@pytest.mark.parametrize(
    "body",
    [
        "верно",
        {"price": None, "price_negotiable": True},
        {"price": None, "price_negotiable": False},
        {"title": "Коротко"},
        {"description": "мало"},
        {"category_id": None},
        {"category_id": 999999},
        {"price": "-5", "bundle_price": "abc"},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_публикация(сайт, body, admin):
    uid = владелец(admin=admin)
    тело = {**ВЕРНО, "category_id": _категория()}

    if isinstance(body, dict):
        тело.update(body)

    итог = отправить(
        сайт,
        "/cabinet/listings/1/publish",
        объявления(("draft", "")),
        снимок,
        uid=uid,
        body=тело,
        headers=inertia(),
    )

    if body == "верно":
        assert итог["база"]["listings"][0][9] == "active"
        assert итог["база"]["notifications"]


@pytest.mark.parametrize(
    ("было", "лимит"),
    [
        ((("rejected", "Отклонённое"),), None),
        ((("draft", ""), ("active", "Цемент")), 1),
        ((("active", "Уже на витрине"),), 1),
    ],
)
def test_публикация_отказ(сайт, было, лимит):
    uid = владелец()

    def подготовка() -> None:
        sql("update plans set listings_limit = %s where code = 'free'", [лимит])
        объявления(*было)()

    отправить(
        сайт,
        "/cabinet/listings/1/publish",
        подготовка,
        снимок,
        uid=uid,
        body={**ВЕРНО, "category_id": _категория()},
        headers=inertia(),
    )


# ── Автосохранение ──────────────────────────────────────────────────


def снимок_черновика() -> Any:
    return {
        **снимок(),
        "attributes": sql(
            "select listing_id, key, value from listing_attributes order by listing_id, key"
        ),
        "tags": sql("select tags::text, type, wizard_step from listings order by id"),
    }


def с_деталями() -> None:
    объявления(("draft", ""))()
    sql("delete from listing_attributes")
    sql(
        "insert into listing_attributes (listing_id, key, value, created_at, updated_at) values "
        "(1, 'spec_weight', '50 kg', now(), now()), (1, 'spec_voltage', '220', now(), now()), "
        "(1, 'grade', 'M400', now(), now())"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"title": "Цемент М400 Ташкент", "step": 2, "type": "demand"},
        {"title": "", "description": None, "price": "", "bundle_price": None},
        {"price_negotiable": False, "bundle_price": "12000.5", "min_order": "10"},
        {"category_id": "cat"},
        {
            "category_id": "cat",
            "attributes": {"spec_color": " серый  ", "spec_dimensions": "x x cm"},
        },
        {"attributes": {"spec_weight": "50,5 kg", "spec_color": "<b>серый</b>", "grade": "M500"}},
        {"attributes": {"spec_weight": "много", "spec_length": None, "spec_unknown": "x"}},
        {"title": "Цемент М400 Ташкент", "tags": ["цемент", "м400", "ташкент", "чужой"]},
        {"tags": ["x"] * 9},
        {"type": "barter", "step": 7, "price": "-1"},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_автосохранение(сайт, body, admin):
    uid = владелец(admin=admin)
    тело = dict(body)

    if тело.get("category_id") == "cat":
        тело["category_id"] = _категория()

    итог = отправить(
        сайт,
        "/cabinet/listings/1/autosave",
        с_деталями,
        снимок_черновика,
        uid=uid,
        body=тело,
        headers={"Accept": "application/json", "X-XSRF-TOKEN": inertia()["X-XSRF-TOKEN"]},
        drop=("saved_at",),
    )

    if "tags" in body and len(body["tags"]) < 9:
        import json

        ответ = json.loads(итог["ответ"]["body"])
        assert "цемент" in ответ["tag_options"]
        assert json.loads(итог["база"]["tags"][0][0]) == ["цемент", "м400", "ташкент"]
