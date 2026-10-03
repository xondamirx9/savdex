"""
Действия кабинета с оглядкой на состояние: черновик не продлевается в
обход проверки публикации (и галочками тоже); правка объявления на
витрине не пропускает заголовок «x»; снятый с продажи тариф и выключенный
вид продвижения не купить по прямому запросу; заблокированная компания
не пишет в чат; повторное «выполнено» не переписывает итог IT-задачи;
номер длиннее bigint в адресе — 404, а не 500.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from .factories import it_задача, компания, объявление
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .test_web_forms import xsrf, отправить
from .web_site import адрес, вход, открыть, пользователь

pytestmark = нужна_база

ЧЕРНОВИК = "Черновик не продлевается — опубликуйте его через мастер объявления."


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        [sys.executable, "manage.py", "seed", "--fresh"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        check=True,
        capture_output=True,
    )

    своя = компания(slug="own")
    компания(slug="closed", status="blocked")
    компания(slug="other")

    for slug, status in (("draft", "draft"), ("expired", "expired"), ("live", "active")):
        объявление(
            slug=slug,
            status=status,
            company_id=своя,
            title="Цемент М500 оптом с доставкой",
            description="Мешки по 50 кг, доставка по Ташкенту за сутки, отсрочка платежа.",
        )

    it_задача(slug="done", company_id=своя)

    with адрес() as root:
        yield root


def _id(table: str, slug: str) -> int:
    return int(sql(f"select id from {table} where slug = %s", [slug])[0][0])


def _владелец(email: str, slug: str = "own") -> int:
    return пользователь(email, company_id=_id("companies", slug))


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


def _статус(slug: str) -> str:
    return str(sql("select status from listings where slug = %s", [slug])[0][0])


def test_черновик_не_продлевается(сайт):
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_id('listings', 'draft')}/renew",
        lambda: None,
        uid=_владелец("renew1@x.uz"),
    )

    assert _сессия(итог)["error"] == ЧЕРНОВИК
    assert _статус("draft") == "draft"


def test_галочками_продлевается_только_бывшее_на_витрине(сайт):
    итог = отправить(
        сайт,
        "/cabinet/listings/bulk",
        lambda: None,
        uid=_владелец("renew2@x.uz"),
        body={"action": "renew", "ids": [_id("listings", "draft"), _id("listings", "expired")]},
    )

    assert итог["ответ"]["status"] == 302
    assert (_статус("draft"), _статус("expired")) == ("draft", "active")

    одни_черновики = отправить(
        сайт,
        "/cabinet/listings/bulk",
        lambda: None,
        uid=_владелец("renew3@x.uz"),
        body={"action": "renew", "ids": [_id("listings", "draft")]},
    )

    assert _сессия(одни_черновики)["error"] == ЧЕРНОВИК


@pytest.mark.parametrize(
    ("slug", "сохранится"),
    [("live", "Цемент М500 оптом с доставкой"), ("draft", "x")],
)
def test_автосохранение_на_витрине_не_портит_объявление(сайт, slug, сохранится):
    """У черновика заголовок «x» — допустимый набросок; на витрине — нет."""
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_id('listings', slug)}/autosave",
        lambda: None,
        uid=_владелец(f"autosave-{slug}@x.uz"),
        body={"title": "x", "description": "коротко", "unit": "мешок"},
    )

    assert итог["ответ"]["status"] == 200
    assert sql("select title, unit from listings where slug = %s", [slug]) == [
        (сохранится, "мешок")
    ]
    sql(
        "update listings set title = 'Цемент М500 оптом с доставкой', "
        "description = 'Мешки по 50 кг, доставка по Ташкенту за сутки, отсрочка платежа.' "
        "where slug = %s",
        [slug],
    )


def test_снятый_тариф_не_продаётся(сайт):
    [(plan,)] = sql(
        "select id from plans where coalesce(price_uzs, 0) > 0 or price_usd > 0 order by id limit 1"
    )
    sql("update plans set is_active = false where id = %s", [plan])

    try:
        итог = отправить(
            сайт,
            "/cabinet/billing/order",
            lambda: None,
            uid=_владелец("order@x.uz"),
            body={"kind": "plan", "id": plan},
        )
    finally:
        sql("update plans set is_active = true where id = %s", [plan])

    assert итог["ответ"]["status"] == 404
    assert sql("select count(*) from payments where plan_id = %s", [plan]) == [(0,)]


def test_выключенное_продвижение_не_купить(сайт):
    [(kind,)] = sql("select id from promotion_types order by id limit 1")
    sql("update promotion_types set is_active = false where id = %s", [kind])

    try:
        итог = отправить(
            сайт,
            "/cabinet/promo",
            lambda: None,
            uid=_владелец("promo@x.uz"),
            body={"listing_id": _id("listings", "live"), "promotion_type_id": kind},
        )
    finally:
        sql("update promotion_types set is_active = true where id = %s", [kind])

    assert итог["ответ"]["status"] == 302
    assert "promotion_type_id" in json.dumps(_сессия(итог)["errors"])
    assert sql("select count(*) from promotions") == [(0,)]


def test_заблокированная_компания_не_пишет_в_чат(сайт):
    [(thread,)] = sql(
        "insert into message_threads (listing_id, buyer_company_id, seller_company_id, "
        "created_at, updated_at) values (%s, %s, %s, now(), now()) returning id",
        [_id("listings", "live"), _id("companies", "closed"), _id("companies", "own")],
    )
    итог = отправить(
        сайт,
        f"/cabinet/chats/{thread}",
        lambda: None,
        uid=_владелец("chat@x.uz", "closed"),
        body={"body": "Здравствуйте"},
    )

    assert итог["ответ"]["status"] == 302
    assert "Компания заблокирована модератором" in json.dumps(
        _сессия(итог)["errors"], ensure_ascii=False
    )
    assert sql("select count(*) from messages where thread_id = %s", [thread]) == [(0,)]


def test_повторное_выполнено_не_переписывает_итог(сайт):
    task = _id("it_tasks", "done")
    uid = _владелец("complete@x.uz")

    for summary in ("Сдали в срок", "Переписано"):
        отправить(
            сайт,
            f"/cabinet/it-tasks/{task}/complete",
            lambda: None,
            uid=uid,
            body={"result_summary": summary},
        )

    assert sql("select status, result_summary from it_tasks where id = %s", [task]) == [
        ("completed", "Сдали в срок")
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/cabinet/listings/99999999999999999999/edit",
        "/cabinet/chats/99999999999999999999",
        "/cabinet/it-tasks/99999999999999999999/edit",
    ],
)
def test_огромный_номер_в_адресе_404(сайт, path):
    куки = вход(_владелец(f"huge-{path.split('/')[2]}@x.uz"))

    assert открыть(сайт, path, куки)["status"] == 404


def test_автосохранение_с_ошибкой_отвечает_422(сайт):
    """fetch ждёт JSON: ошибка ввода — 422 с полями, а не редирект на HTML."""
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_id('listings', 'draft')}/autosave",
        lambda: None,
        uid=_владелец("autosave-422@x.uz"),
        body={"price": -5},
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": xsrf(),
        },
    )

    assert итог["ответ"]["status"] == 422
    assert list(json.loads(итог["ответ"]["body"])["errors"]) == ["price"]
