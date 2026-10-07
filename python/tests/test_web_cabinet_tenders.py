"""
Свои тендеры в кабинете: «Мои тендеры», «Создать тендер», правка,
продлить, завершить, открыть снова и удалить. Тендер из кабинета живёт
120 дней: срок не дальше, продлить — на любое число дней до 365; завершить —
с компанией, с которой договорились, или «Сделка не состоялась».

Тендер заводит компания: заказчик по умолчанию — её название, автор —
вошедший; новый тендер сразу на витрине. Чужой тендер — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
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


def день(n: int) -> str:
    """Дата через n дней (UTC), как в поле формы."""
    return (datetime.now(UTC) + timedelta(days=n)).strftime("%Y-%m-%d")


def тендеры(
    *статусы: str,
    автор: Callable[[], int] = _свой,
    source: str = "admin",
    deadline: str | None = None,
) -> Callable[[], None]:
    """Подготовка: тендеры 1, 2… автора с этими статусами."""

    def run() -> None:
        sql("delete from tenders")
        sql("delete from admin_actions where section = 'tenders'")
        sql("select setval('tenders_id_seq', 1, false)")
        uid = автор()

        for status in статусы:
            sql(
                "insert into tenders (slug, title, title_i18n, description, customer, currency, "
                "status, published_at, author_id, created_at, updated_at, source, deadline_at, "
                "expiry_warned_at) values "
                "(null, 'Поставка цемента М400', '{\"en\": \"Cement supply\"}', "
                "'Двести тонн цемента с доставкой на объект', 'ООО «Стройзаказ»', 'UZS', %s, "
                "now() - interval '1 day', %s, now() - interval '1 day', now() - interval '1 day', "
                "%s, %s, now())",
                [status, uid, source, deadline],
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
    "deadline_at": день(10),
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
    assert (строка[7], строка[8], строка[9]) == ("150000000.00", "UZS", f"{день(10)} 23:59:59")
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
    ("было", "стало"),
    [
        ("archived", "published"),
        # Черновик снят модерацией — автору его не вернуть
        ("draft", "draft"),
    ],
)
def test_открыть_снова(сайт, было, стало):
    итог = отправить(сайт, "/cabinet/tenders/1/reopen", тендеры(было), снимок, uid=заказчик())

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
        (2, "archived", "Завершён"),
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
    assert page["props"]["lifetime"] == 120


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


# ── Срок: 30 дней, продлить, завершить ─────────────────────────────


def итог_тендера() -> Any:
    return sql(
        "select status, source, deadline_at::text, outcome, outcome_party, outcome_amount::text, "
        "finished_at is not null, expiry_warned_at is not null from tenders order by id"
    )


def test_новый_срок_по_умолчанию(сайт):
    итог = отправить(
        сайт,
        "/cabinet/tenders",
        тендеры(),
        итог_тендера,
        uid=заказчик(),
        body={**ФОРМА, "deadline_at": ""},
    )

    assert итог["база"] == [
        ("published", "cabinet", f"{день(120)} 23:59:59", None, None, None, False, False)
    ]


def test_новый_срок_дальше_120_дней(сайт):
    итог = отправить(
        сайт,
        "/cabinet/tenders",
        тендеры(),
        итог_тендера,
        uid=заказчик(),
        body={**ФОРМА, "deadline_at": день(121)},
    )

    assert list(сессия(итог)["errors"]) == ["deadline_at"]
    assert "Продлить" in сессия(итог)["errors"]["deadline_at"][0]
    assert итог["база"] == []


@pytest.mark.parametrize(
    ("срок", "ошибка", "стало", "предупреждён"),
    [
        # Дальше 120 дней — только «Продлить»
        (день(125), True, None, True),
        # Стёрли срок — у кабинетного тендера остаётся прежний
        ("", False, f"{день(25)} 23:59:59", True),
        # Срок сдвинули — предупреждение «истекает» снова придёт к новому сроку
        (день(20), False, f"{день(20)} 23:59:59", False),
    ],
)
def test_правка_срока_кабинетного(сайт, срок, ошибка, стало, предупреждён):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1",
        тендеры("published", source="cabinet", deadline=f"{день(25)} 23:59:59"),
        итог_тендера,
        uid=заказчик(),
        body={**ФОРМА, "deadline_at": срок},
        method="PATCH",
    )

    assert ("deadline_at" in сессия(итог)["errors"]) is ошибка
    assert итог["база"][0][2] == (стало or f"{день(25)} 23:59:59")
    assert итог["база"][0][7] is предупреждён


@pytest.mark.parametrize(
    ("было", "body", "стало"),
    [
        # Договорились — с компанией
        (
            "published",
            {"outcome": "contract", "party": " ООО «Цемент» ", "amount": "120000000"},
            ("archived", "contract", "ООО «Цемент»", "120000000.00", True),
        ),
        # «Сделка не состоялась» — компания не нужна и не пишется
        (
            "published",
            {"outcome": "no_deal", "party": "ООО «Цемент»", "amount": "5"},
            ("archived", "no_deal", None, None, True),
        ),
        ("expired", {"outcome": "no_deal"}, ("archived", "no_deal", None, None, True)),
        # Ни компании, ни галочки — не завершается
        (
            "published",
            {"outcome": "contract", "party": "  "},
            ("published", None, None, None, False),
        ),
        ("published", {"outcome": "contract"}, ("published", None, None, None, False)),
        ("published", {}, ("published", None, None, None, False)),
        ("published", {"outcome": "cancelled"}, ("published", None, None, None, False)),
        # Уже завершён — второй раз не переписывается
        (
            "archived",
            {"outcome": "contract", "party": "ООО «Цемент»"},
            ("archived", None, None, None, False),
        ),
    ],
)
def test_завершить(сайт, было, body, стало):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1/finish",
        тендеры(было, source="cabinet", deadline=f"{день(5)} 23:59:59"),
        итог_тендера,
        uid=заказчик(),
        body=body,
    )
    status, _, _, outcome, party, amount, finished, _ = итог["база"][0]

    assert (status, outcome, party, amount, finished) == стало

    if стало[1] is None and было != "archived":
        assert {"outcome", "party"} & set(сессия(итог)["errors"])


@pytest.mark.parametrize(
    ("было", "срок", "дней", "стало"),
    [
        # От прежнего срока, предупреждение сброшено
        ("published", 2, "14", ("published", f"{день(16)} 23:59:59", False)),
        # Срок прошёл — от сегодня, тендер снова на витрине
        ("expired", -3, "7", ("published", f"{день(7)} 23:59:59", False)),
        # Любое число дней от 1 до 365
        ("published", 2, "5", ("published", f"{день(7)} 23:59:59", False)),
        ("published", 2, "365", ("published", f"{день(367)} 23:59:59", False)),
        # Ноль, больше года и не число — отказ
        ("published", 2, "0", ("published", f"{день(2)} 23:59:59", True)),
        ("published", 2, "366", ("published", f"{день(2)} 23:59:59", True)),
        ("published", 2, "две недели", ("published", f"{день(2)} 23:59:59", True)),
        # Завершённый не продлевается — его открывают снова
        ("archived", 2, "30", ("archived", f"{день(2)} 23:59:59", True)),
    ],
)
def test_продлить(сайт, было, срок, дней, стало):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1/extend",
        тендеры(было, source="cabinet", deadline=f"{день(срок)} 23:59:59"),
        итог_тендера,
        uid=заказчик(),
        body={"days": дней},
    )
    status, _, deadline, _, _, _, _, warned = итог["база"][0]

    assert (status, deadline, warned) == стало


def test_продлить_чужой_404(сайт):
    итог = отправить(
        сайт,
        "/cabinet/tenders/1/extend",
        тендеры("published", автор=чужой, source="cabinet", deadline=f"{день(2)} 23:59:59"),
        итог_тендера,
        uid=заказчик(),
        body={"days": "30"},
    )

    assert итог["ответ"]["status"] == 404
    assert итог["база"][0][2] == f"{день(2)} 23:59:59"


def test_открыть_снова_кабинетный(сайт):
    def подготовка() -> None:
        тендеры("archived", source="cabinet", deadline=f"{день(-5)} 23:59:59")()
        sql("update tenders set outcome = 'no_deal', finished_at = now()")

    итог = отправить(сайт, "/cabinet/tenders/1/reopen", подготовка, итог_тендера, uid=заказчик())

    # Итог снят, срок прошёл — снова 30 дней
    assert итог["база"] == [
        ("published", "cabinet", f"{день(120)} 23:59:59", None, None, None, False, False)
    ]


def test_список_сроки_и_итоги(сайт):
    тендеры("published", "archived", "expired", source="cabinet", deadline=f"{день(2)} 23:59:59")()
    sql(
        "update tenders set outcome = 'contract', outcome_party = 'ООО «Цемент»', "
        "outcome_amount = 120000000 where id = 2"
    )
    ответ = открыть(сайт, "/cabinet/tenders", cookies=вход(заказчик()))
    props = страница(ответ["body"])["props"]
    по_номеру = {t["id"]: t for t in props["tenders"]}

    assert (props["extendDays"], props["extendMax"]) == ([30, 60, 120], 365)
    assert по_номеру[1]["days_left"] == 2
    assert (по_номеру[2]["outcome_label"], по_номеру[2]["outcome_party"]) == (
        "Сделка состоялась",
        "ООО «Цемент»",
    )
    assert по_номеру[2]["outcome_amount"].startswith("120 000 000")
    assert (по_номеру[3]["status_label"], по_номеру[3]["days_left"]) == ("Истёк", None)
