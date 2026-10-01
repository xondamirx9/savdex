"""
Мастер объявления — проверки Django: новый черновик (без
компании — в профиль, сверх лимита — к списку, пустой черновик
переиспользуется) и публикация (строгая проверка, цена или «договорная»,
лимит тарифа, адрес, уведомление компании, журнал администратора;
отклонённое — нельзя; неподтверждённая почта — на подтверждение).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import категория, компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

#: Без машинного перевода: он ходит в сеть
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


def тарифы() -> None:
    """PlanSeeder: тарифы из снимка справочников (savdex/bootstrap/seeds.json)."""
    from savdex.seeds import DATA

    for plan in json.loads(DATA.read_text(encoding="utf-8"))["plans"]:
        sql(
            f"insert into plans ({', '.join(plan)}, created_at, updated_at) "
            f"values ({', '.join(['%s'] * len(plan))}, now(), now())",
            list(plan.values()),
        )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    тарифы()
    компания(slug="mine")
    категория(slug="cement")

    with адрес() as root:
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


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Строка сессии после ответа — разобранным JSON."""
    return dict(json.loads(итог["сессия"]["payload"]))


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    """Ошибки проверки, которые форма увидит после перехода назад."""
    return dict(сессия(итог).get("errors", {}).get("default", {}).get("messages", {}))


# ── Новый черновик ──────────────────────────────────────────────────

ЛИМИТ = "Достигнут лимит тарифа Free: 1 активных объявлений."


@pytest.mark.parametrize(
    ("было", "лимит", "куда", "стало"),
    [
        ((), None, "/cabinet/listings/1/edit", [(1, "draft", "")]),
        # Пустой черновик переиспользуется
        ((("draft", ""),), None, "/cabinet/listings/1/edit", [(1, "draft", "")]),
        (
            (("draft", "Готовый черновик"),),
            None,
            "/cabinet/listings/2/edit",
            [(1, "draft", "Готовый черновик"), (2, "draft", "")],
        ),
        # Сверх лимита — к списку
        ((("active", "Цемент"),), 1, "/cabinet/listings", [(1, "active", "Цемент")]),
        (
            (("active", "Цемент"),),
            2,
            "/cabinet/listings/2/edit",
            [(1, "active", "Цемент"), (2, "draft", "")],
        ),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_новый_черновик(сайт, было, лимит, куда, стало, admin):
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
        env=БЕЗ_ПЕРЕВОДА,
        method="GET",
        headers={},
    )
    база = итог["база"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + куда
    assert [(r[0], r[9], r[2]) for r in база["listings"]] == стало

    if куда == "/cabinet/listings":
        assert сессия(итог)["error"] == (
            f"{ЛИМИТ} Снимите ненужное с публикации или смените тариф."
        )

    # Новый черновик — строка журнала администратора
    новый = len(стало) > len(было)
    assert [(a, label) for a, label, _ in база["journal"]] == (
        [("created", f"Listing #{len(стало)}")] if новый and admin else []
    )


@pytest.mark.parametrize(
    ("случай", "куда"),
    [("без компании", "/en/cabinet/company"), ("почта", "/en/verify-email")],
)
def test_новый_черновик_отказ(сайт, случай, куда):
    uid = владелец(company=случай != "без компании", verified=случай != "почта")
    итог = отправить(
        сайт,
        "/en/cabinet/listings/create",
        объявления(),
        снимок,
        uid=uid,
        env=БЕЗ_ПЕРЕВОДА,
        method="GET",
        headers={},
    )

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + куда
    assert итог["база"]["listings"] == []

    if случай == "без компании":
        assert сессия(итог)["warning"] == (
            "Fill in your company details first — a listing is published on its behalf"
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
ОПУБЛИКОВАНО = "Объявление опубликовано — покупатели уже видят его в каталоге."


def опубликовано(сайт: str, итог: dict[str, Any], *, price: str | None, договорная: bool) -> None:
    """Объявление 1 на витрине: строгие поля, адрес, срок, уведомление компании."""
    база = итог["база"]
    [row] = [r for r in база["listings"] if r[0] == 1]
    сообщение = f"Объявление «{ВЕРНО['title']}» опубликовано и видно покупателям"

    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/listings"
    assert сессия(итог)["success"] == ОПУБЛИКОВАНО
    assert row[:14] == (
        1,
        _категория(),
        ВЕРНО["title"],
        ВЕРНО["description"],
        price,
        None,
        договорная,
        "UZS",
        "мешок",
        "active",
        4,
        "tsement-m400-v-meshkakh-po-50-kg-1",
        True,
        90,
    )
    assert row[14].startswith("цемент м400 в мешках по 50 кг портландцемент")
    assert база["events"] == [("moderation", "success", сообщение, сайт + "/cabinet/listings")]
    assert база["notifications"] == [
        ("moderation", сообщение, "success", сайт + "/cabinet/listings")
    ]


@pytest.mark.parametrize(
    ("body", "ошибки_"),
    [
        ("верно", None),
        # Цена или «договорная»
        ({"price": None, "price_negotiable": True}, None),
        (
            {"price": None, "price_negotiable": False},
            {"price": ["Укажите цену или отметьте «цена договорная»"]},
        ),
        (
            {"title": "Коротко"},
            {"title": ["Заголовок слишком короткий: укажите товар, марку и объём"]},
        ),
        (
            {"description": "мало"},
            {"description": ["Описание слишком короткое — расскажите об условиях и объёмах"]},
        ),
        (
            {"category_id": None},
            {"category_id": ["Выберите категорию — без неё объявление не найдут"]},
        ),
        # Своих текстов у этих правил нет ни у сайта, ни у Laravel (lang без
        # validation.php) — ключ сообщения как есть
        ({"category_id": 999999}, {"category_id": ["validation.exists"]}),
        (
            {"price": "-5", "bundle_price": "abc"},
            {"price": ["validation.min.numeric"], "bundle_price": ["validation.numeric"]},
        ),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_публикация(сайт, body, ошибки_, admin):
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
        env=БЕЗ_ПЕРЕВОДА,
        body=тело,
        headers=inertia(),
    )
    база = итог["база"]

    assert итог["ответ"]["status"] == 302

    if ошибки_ is None:
        опубликовано(
            сайт,
            итог,
            price=None if тело["price"] is None else "52000.00",
            договорная=bool(тело["price_negotiable"]),
        )
        # Администратору — строка журнала о правке
        assert {(a, label) for a, label, _ in база["journal"]} == (
            {("updated", ВЕРНО["title"])} if admin else set()
        )
    else:
        # Назад к форме с ошибками и вводом, черновик не тронут
        assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
        assert ошибки(итог) == ошибки_
        assert сессия(итог)["_old_input"]["title"] == тело["title"]
        assert [(r[0], r[9], r[2]) for r in база["listings"]] == [(1, "draft", "")]
        assert база["events"] == база["notifications"] == база["journal"] == []


@pytest.mark.parametrize(
    ("было", "лимит", "ошибка"),
    [
        # Отклонённое — нельзя
        (
            (("rejected", "Отклонённое"),),
            None,
            "Это объявление отклонено — на витрину оно не вернётся. Разместите новое.",
        ),
        # Лимит тарифа
        ((("draft", ""), ("active", "Цемент")), 1, ЛИМИТ),
        # Уже на витрине — в лимите оно само и есть: правка проходит
        ((("active", "Уже на витрине"),), 1, None),
    ],
)
def test_публикация_отказ(сайт, было, лимит, ошибка):
    uid = владелец()

    def подготовка() -> None:
        sql("update plans set listings_limit = %s where code = 'free'", [лимит])
        объявления(*было)()

    итог = отправить(
        сайт,
        "/cabinet/listings/1/publish",
        подготовка,
        снимок,
        uid=uid,
        env=БЕЗ_ПЕРЕВОДА,
        body={**ВЕРНО, "category_id": _категория()},
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 302

    if ошибка is None:
        опубликовано(сайт, итог, price="52000.00", договорная=False)
    else:
        assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
        assert сессия(итог)["error"] == ошибка
        assert [(r[0], r[9], r[2]) for r in итог["база"]["listings"]] == [
            (i, status, title) for i, (status, title) in enumerate(было, 1)
        ]
        assert итог["база"]["notifications"] == []


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


ГРАДЕ = (1, "grade", "M400")
ВЕС = (1, "spec_weight", "50 kg")


@pytest.mark.parametrize(
    ("body", "ожидание"),
    [
        (
            {"title": "Цемент М400 Ташкент", "step": 2, "type": "demand"},
            {
                "title": "Цемент М400 Ташкент",
                "tags": (None, "demand", 2),
                # Без категории детали товара (spec_*) убираются
                "attributes": [ГРАДЕ],
                "tag_options": ["цемент", "м400", "ташкент", "m400", "tashkent"],
            },
        ),
        (
            {"title": "", "description": None, "price": "", "bundle_price": None},
            {"attributes": [ГРАДЕ], "tag_options": ["m400", "tashkent"]},
        ),
        (
            {"price_negotiable": False, "bundle_price": "12000.5", "min_order": "10"},
            {"bundle_price": "12000.50", "attributes": [ГРАДЕ]},
        ),
        # Категория с деталями: вес остаётся, напряжения у цемента нет
        (
            {"category_id": "cat"},
            {
                "category": True,
                "attributes": [ГРАДЕ, ВЕС],
                "tag_options": ["cement", "m400", "tashkent"],
            },
        ),
        # Значение детали чистится, неразборчивое — не сохраняется
        (
            {
                "category_id": "cat",
                "attributes": {"spec_color": " серый  ", "spec_dimensions": "x x cm"},
            },
            {
                "category": True,
                "attributes": [ГРАДЕ, (1, "spec_color", "серый"), ВЕС],
                "tag_options": ["cement", "m400", "tashkent"],
            },
        ),
        (
            {
                "attributes": {
                    "spec_weight": "50,5 kg",
                    "spec_color": "<b>серый</b>",
                    "grade": "M500",
                }
            },
            {"attributes": [(1, "grade", "M500")], "tag_options": ["m500", "tashkent"]},
        ),
        (
            {"attributes": {"spec_weight": "много", "spec_length": None, "spec_unknown": "x"}},
            {"attributes": [ГРАДЕ]},
        ),
        # Метки — только из предложенных
        (
            {"title": "Цемент М400 Ташкент", "tags": ["цемент", "м400", "ташкент", "чужой"]},
            {
                "title": "Цемент М400 Ташкент",
                "attributes": [ГРАДЕ],
                "tags": ('["цемент","м400","ташкент"]', "supply", 1),
                "tag_options": ["цемент", "м400", "ташкент", "m400", "tashkent"],
            },
        ),
        ({"tags": ["x"] * 9}, {"errors": {"tags": ["validation.max.array"]}}),
        (
            {"type": "barter", "step": 7, "price": "-1"},
            {
                "errors": {
                    "type": ["validation.in"],
                    "price": ["validation.min.numeric"],
                    "step": ["validation.between.numeric"],
                }
            },
        ),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_автосохранение(сайт, body, ожидание, admin):
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
        env=БЕЗ_ПЕРЕВОДА,
        body=тело,
        headers={"Accept": "application/json", "X-XSRF-TOKEN": inertia()["X-XSRF-TOKEN"]},
    )
    база = итог["база"]
    [row] = база["listings"]

    if "errors" in ожидание:
        # Проверка не прошла — назад с ошибками, черновик не тронут
        assert итог["ответ"]["status"] == 302
        assert ошибки(итог) == ожидание["errors"]
        assert база["attributes"] == [ГРАДЕ, (1, "spec_voltage", "220"), ВЕС]
        assert row[2] == "" and база["tags"] == [(None, "supply", 1)]
        assert база["journal"] == []
        return

    ответ = json.loads(итог["ответ"]["body"])
    assert итог["ответ"]["status"] == 200 and "saved_at" in ответ
    assert ответ["tag_options"] == ожидание.get("tag_options", ["m400", "tashkent"])
    assert row[1] == (_категория() if ожидание.get("category") else None)
    assert row[2] == ожидание.get("title", "")
    assert row[5] == ожидание.get("bundle_price")
    assert row[9] == "draft"
    assert база["attributes"] == ожидание["attributes"]
    tags, type_, step = база["tags"][0]
    assert (json.loads(tags) if tags else None, type_, step) == (
        json.loads(ожидание["tags"][0]) if "tags" in ожидание and ожидание["tags"][0] else None,
        *ожидание.get("tags", (None, "supply", 1))[1:],
    )
    # Администратору — строка журнала о правке черновика
    assert bool(база["journal"]) == admin
