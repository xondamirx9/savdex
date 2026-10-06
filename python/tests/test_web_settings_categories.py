"""
Категории компании и пауза рассылки в настройках кабинета: по
категориям бот присылает новые объявления и тендеры. Категории меняет
только владелец, не больше пяти; паузу — каждый для себя.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from .factories import категория, компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


@pytest.fixture(scope="module")
def разделы() -> list[int]:
    return [категория(f"Раздел {i}") for i in range(7)]


def выбрано(cid: int) -> list[int]:
    return [
        r[0]
        for r in sql(
            "select category_id from company_category where company_id = %s order by id", [cid]
        )
    ]


def человек(role: str) -> tuple[int, int]:
    cid = компания()
    uid = учётка(f"{role}-{cid}@savdex.uz", company_id=cid, company_role=role)

    return cid, uid


def сохранить(сайт: str, uid: int, body: Any) -> dict[str, Any]:
    итог = отправить(
        сайт,
        "/cabinet/settings/categories",
        lambda: None,
        uid=uid,
        body=body,
        method="PATCH",
        headers=inertia(),
    )
    assert итог["ответ"]["status"] == 303

    return dict(json.loads(итог["сессия"]["payload"]))


def test_владелец_меняет(сайт, разделы):
    cid, uid = человек("owner")
    sql("insert into company_category (company_id, category_id) values (%s, %s)", [cid, разделы[0]])

    сессия = сохранить(сайт, uid, {"categories": [разделы[1], разделы[2], разделы[1]]})

    assert "success" in сессия and "errors" not in сессия
    assert выбрано(cid) == [разделы[1], разделы[2]]

    # Пустой список — всё снято
    сохранить(сайт, uid, {"categories": []})
    assert выбрано(cid) == []


@pytest.mark.parametrize(
    "body",
    [
        "шесть",
        "чужой",
        "строка",
    ],
)
def test_ошибки(сайт, разделы, body):
    cid, uid = человек("owner")
    sql("insert into company_category (company_id, category_id) values (%s, %s)", [cid, разделы[0]])
    данные = {
        "шесть": {"categories": разделы[:6]},
        "чужой": {"categories": [999_999]},
        "строка": {"categories": "мебель"},
    }[body]

    сессия = сохранить(сайт, uid, данные)

    assert "categories" in json.dumps(сессия.get("errors", {}))
    assert выбрано(cid) == [разделы[0]]


def test_сотрудник_не_меняет(сайт, разделы):
    cid, uid = человек("manager")
    sql("insert into company_category (company_id, category_id) values (%s, %s)", [cid, разделы[0]])

    сессия = сохранить(сайт, uid, {"categories": [разделы[3]]})

    assert "владелец" in json.dumps(сессия["errors"], ensure_ascii=False)
    assert выбрано(cid) == [разделы[0]]


@pytest.mark.parametrize(("on", "стало"), [(False, [(False,)]), (True, [(True,)])])
def test_пауза_рассылки(сайт, on, стало):
    _, uid = человек("manager")
    итог = отправить(
        сайт,
        "/cabinet/settings/telegram-feed",
        lambda: None,
        uid=uid,
        body={"on": on},
        method="PATCH",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303
    assert (
        sql(
            "select telegram from notification_preferences "
            "where user_id = %s and event = 'category_feed'",
            [uid],
        )
        == стало
    )
