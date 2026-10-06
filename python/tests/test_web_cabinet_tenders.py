"""
Свои тендеры в кабинете: «Мои тендеры», «Создать тендер», правка,
закрыть, открыть снова и удалить. Тендер заводит компания: заказчик по
умолчанию — её название, автор — вошедший; новый тендер сразу на
витрине. Чужой тендер — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import отправить, учётка
from .web_site import адрес, вход, открыть, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="buyer", name="ООО «Стройзаказ»")

    with адрес() as root:
        yield root


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def заказчик(*, admin: bool = False, verified: bool = True, company: bool = True) -> int:
    return учётка(
        "buyer@savdex.uz",
        name="Алишер",
        phone="+998901234567",
        company_id=_компания("buyer") if company else None,
        is_admin=admin,
        email_verified_at="2026-09-01 10:00:00" if verified else None,
    )


def чужой() -> int:
    return учётка("other@savdex.uz", email_verified_at="2026-09-01 10:00:00")


def _свой() -> int:
    """Номер заказчика, не трогая его полей (is_admin ставит сам тест)."""
    found = sql("select id from users where email = 'buyer@savdex.uz'")

    return int(found[0][0]) if found else заказчик()


def тендеры(*статусы: str, автор: Callable[[], int] = _свой) -> Callable[[], None]:
    """Подготовка: тендеры 1, 2… автора с этими статусами."""

    def run() -> None:
        sql("delete from tenders")
        sql("delete from admin_actions where section = 'tenders'")
        sql("select setval('tenders_id_seq', 1, false)")
        uid = автор()

        for status in статусы:
            sql(
                "insert into tenders (slug, title, title_i18n, description, customer, currency, "
                "status, published_at, author_id, created_at, updated_at) values "
                "(null, 'Поставка цемента М400', '{\"en\": \"Cement supply\"}', "
                "'Двести тонн цемента с доставкой на объект', 'ООО «Стройзаказ»', 'UZS', %s, "
                "now() - interval '1 day', %s, now() - interval '1 day', now() - interval '1 day')",
                [status, uid],
            )

    return run


def снимок() -> Any:
    return {
        "tenders": sql(
            "select id, slug, title, title_i18n::text, customer, category_id, location, "
            "budget::text, currency, deadline_at::text, contact_name, contact_phone, "
            "contact_email, status, author_id, published_at > now() - interval '1 hour', "
            "search_text from tenders order by id"
        ),
        "journal": [
            a
            for (a,) in sql(
                "select action from admin_actions where section = 'tenders' order by id"
            )
        ],
    }


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(итог["сессия"]["payload"])

    return {
        "success": payload.get("success"),
        "warning": payload.get("warning"),
        "errors": payload.get("errors", {}).get("default", {}).get("messages", {}),
    }


ФОРМА = {
    "title": "Поставка цемента М400, 200 тонн",
    "description": "Двести тонн цемента М400 в мешках с доставкой на объект в Ташкенте",
    "customer": "ООО «Стройзаказ»",
    "category_id": "",
    "location": "Ташкент",
    "budget": "150000000",
    "currency": "UZS",
    "deadline_at": "2099-06-30",
    "contact_name": "Алишер",
    "contact_phone": "+998901234567",
    "contact_email": "buyer@savdex.uz",
}


@pytest.mark.parametrize("admin", [False, True])
def test_новый(сайт, admin):
    итог = отправить(
        сайт, "/cabinet/tenders", тендеры(), снимок, uid=заказчик(admin=admin), body=ФОРМА
    )
    [строка] = итог["база"]["tenders"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/tenders"
    assert сессия(итог)["success"] == "Тендер опубликован — он уже в каталоге на вкладке «Тендеры»"
    # Адрес — из заголовка и номера, сразу на витрине, автор — вошедший
    assert строка[1].endswith("-1") and строка[1].startswith("postavka-tsementa")
    assert строка[13] == "published" and строка[14] == заказчик() and строка[15]
    assert (строка[7], строка[8], строка[9]) == ("150000000.00", "UZS", "2099-06-30 23:59:59")
    assert строка[5] is None and "цемент" in строка[16]
    assert итог["база"]["journal"] == (["created"] if admin else [])


@pytest.mark.parametrize(
    ("изменения", "ошибки"),
    [
        ({"title": "Цемент"}, ["title"]),
        ({"description": ""}, ["description"]),
        ({"customer": "  "}, ["customer"]),
        ({"currency": "GBP", "budget": "-5"}, ["budget", "currency"]),
        ({"deadline_at": "2020-01-01"}, ["deadline_at"]),
        ({"contact_email": "не почта"}, ["contact_email"]),
        ({"category_id": "999999"}, ["category_id"]),
    ],
)
def test_новый_ошибки(сайт, изменения, ошибки):
    итог = отправить(
        сайт,
        "/cabinet/tenders",
        тендеры(),
        снимок,
        uid=заказчик(),
        body={**ФОРМА, **изменения},
    )

    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
    assert sorted(сессия(итог)["errors"]) == ошибки
    assert итог["база"]["tenders"] == []


def test_новый_без_компании(сайт):
    итог = отправить(
        сайт, "/cabinet/tenders", тендеры(), снимок, uid=заказчик(company=False), body=ФОРМА
    )

    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/company"
    assert итог["база"]["tenders"] == []


def test_новый_без_почты(сайт):
    итог = отправить(
        сайт, "/cabinet/tenders", тендеры(), снимок, uid=заказчик(verified=False), body=ФОРМА
    )

    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
    assert итог["база"]["tenders"] == []


def test_правка(сайт):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1",
        тендеры("published"),
        снимок,
        uid=заказчик(),
        body={**ФОРМА, "budget": "", "deadline_at": ""},
        method="PATCH",
    )
    [строка] = итог["база"]["tenders"]

    assert итог["ответ"]["status"] == 303
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/tenders"
    # Заголовок сменился — старые переводы сброшены, их доберёт фоновый перевод
    assert (строка[2], строка[3]) == ("Поставка цемента М400, 200 тонн", None)
    assert (строка[7], строка[9], строка[6]) == (None, None, "Ташкент")


def test_правка_без_смены_текста_оставляет_перевод(сайт):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1",
        тендеры("published"),
        снимок,
        uid=заказчик(),
        body={
            **ФОРМА,
            "title": "Поставка цемента М400",
            "description": "Двести тонн цемента с доставкой на объект",
        },
        method="PATCH",
    )

    assert json.loads(итог["база"]["tenders"][0][3]) == {"en": "Cement supply"}


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/cabinet/tenders/1", "PATCH"),
        ("/cabinet/tenders/1", "DELETE"),
        ("/cabinet/tenders/1/close", "POST"),
        ("/cabinet/tenders/1/reopen", "POST"),
    ],
)
def test_чужой_404(сайт, path, method):
    итог = отправить(
        сайт,
        path,
        тендеры("published", автор=чужой),
        снимок,
        uid=заказчик(),
        body=ФОРМА,
        method=method,
    )

    assert итог["ответ"]["status"] == 404
    assert итог["база"]["tenders"][0][13] == "published"


@pytest.mark.parametrize(
    ("было", "путь", "стало"),
    [
        ("published", "close", "archived"),
        ("archived", "close", "archived"),
        ("archived", "reopen", "published"),
        # Черновик снят модерацией — автору его не вернуть
        ("draft", "reopen", "draft"),
    ],
)
def test_закрыть_открыть(сайт, было, путь, стало):
    итог = отправить(сайт, f"/cabinet/tenders/1/{путь}", тендеры(было), снимок, uid=заказчик())

    assert итог["ответ"]["status"] == 302
    assert итог["база"]["tenders"][0][13] == стало


def test_удалить(сайт):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1",
        тендеры("published", "archived"),
        снимок,
        uid=заказчик(admin=True),
        method="DELETE",
    )

    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/tenders"
    assert [r[0] for r in итог["база"]["tenders"]] == [2]
    assert итог["база"]["journal"] == ["deleted"]


def test_список_только_свои(сайт):
    тендеры("published", "archived")()
    sql(
        "insert into tenders (title, currency, status, author_id, created_at, updated_at) "
        "values ('Чужая закупка бумаги', 'UZS', 'published', %s, now(), now())",
        [чужой()],
    )
    ответ = открыть(сайт, "/cabinet/tenders", cookies=вход(заказчик()))
    props = страница(ответ["body"])["props"]

    assert страница(ответ["body"])["component"] == "cabinet/tenders/Index"
    assert props["hasCompany"] is True
    assert [(t["id"], t["status"], t["status_label"]) for t in props["tenders"]] == [
        (2, "archived", "Закрыт"),
        (1, "published", "Опубликован"),
    ]
    assert all(t["title"] != "Чужая закупка бумаги" for t in props["tenders"])


def test_форма_нового(сайт):
    ответ = открыть(сайт, "/cabinet/tenders/create", cookies=вход(заказчик()))
    page = страница(ответ["body"])

    assert page["component"] == "cabinet/tenders/Form"
    assert page["props"]["tender"] is None
    assert page["props"]["defaults"] == {
        "customer": "ООО «Стройзаказ»",
        "contact_name": "Алишер",
        "contact_phone": "+998901234567",
        "contact_email": "buyer@savdex.uz",
    }
    assert "UZS" in page["props"]["currencies"]


def test_форма_нового_без_компании(сайт):
    ответ = открыть(сайт, "/cabinet/tenders/create", cookies=вход(заказчик(company=False)))

    assert ответ["status"] == 302
    assert ответ["headers"]["location"].endswith("/cabinet/company")


def test_форма_правки(сайт):
    тендеры("published")()
    ответ = открыть(сайт, "/cabinet/tenders/1/edit", cookies=вход(заказчик()))
    tender = страница(ответ["body"])["props"]["tender"]

    assert (tender["id"], tender["title"], tender["currency"]) == (
        1,
        "Поставка цемента М400",
        "UZS",
    )

    тендеры("published", автор=чужой)()
    чужая = открыть(сайт, "/cabinet/tenders/1/edit", cookies=вход(заказчик()))

    assert чужая["status"] == 404
