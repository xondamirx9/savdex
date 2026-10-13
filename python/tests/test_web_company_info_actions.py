"""
Данные компании в настройках на Django (ответы JSON):
сведения и справочники; сохранение — заполнить пустое можно всегда, смена
заполненного ставит метку и закрывает смену на полгода, пока срок идёт —
422 с полями; проверка как у профиля компании; обращение в поддержку.
Только владелец компании.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex.web.search_text import index

from .factories import компания
from .pg_admin import sql, нужна_база, свежая_база, страна
from .test_web_forms import xsrf, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ПОЧТА = "info@savdex.uz"
JSON = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "X-XSRF-TOKEN": xsrf(),
}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    компания(
        slug="mine",
        country_id=uz,
        name="Цемент Трейд",
        tin="301234567",
        legal_name=None,
        is_it_provider=False,
        it_specializations=None,
    )
    компания(slug="other", tin="305123456")

    with адрес() as root:
        yield root


def _компания() -> int:
    return int(sql("select id from companies where slug = 'mine'")[0][0])


def сброс(
    *, роль: str = "owner", сменено: str | None = None, admin: bool = False
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from support_messages")
        sql("delete from support_tickets")
        sql("delete from admin_actions")
        sql(
            "update companies set name = 'Цемент Трейд', legal_name = null, tin = '301234567', "
            "founded_year = null, is_it_provider = false, it_specializations = null, "
            "address = null, profile_changed_at = %s, search_text = %s, "
            "updated_at = now() - interval '1 day' where slug = 'mine'",
            [сменено, index("Цемент Трейд")],
        )
        учётка(ПОЧТА, company_id=_компания(), company_role=роль, is_admin=admin)

    return run


def снимок() -> Any:
    return {
        "company": sql(
            "select name, legal_name, tin, founded_year, is_it_provider, "
            "it_specializations::text, address, search_text, profile_changed_at is not null, "
            "updated_at > now() - interval '1 hour' from companies where slug = 'mine'"
        ),
        "tickets": sql(
            "select subject, author_name, author_email, status, channel, priority, "
            "closed_at, last_reply_at is not null from support_tickets order by id"
        ),
        "messages": [
            (a, f, i, re.sub(r"#\d+", "#N", b))
            for a, f, i, b in sql(
                "select author_id is not null, from_staff, is_internal, body "
                "from support_messages order by id"
            )
        ],
        "journal": [
            (a, s, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
            for a, s, ch in sql(
                "select action, section, changes::text from admin_actions order by id"
            )
        ],
    }


def запрос(сайт: str, path: str, method: str, body: Any, **настройка: Any) -> dict[str, Any]:
    uid = учётка(ПОЧТА, company_id=_компания())

    return отправить(
        сайт,
        path,
        сброс(**настройка),
        снимок,
        uid=uid,
        method=method,
        body=body,
        headers=JSON,
    )


def ответ(итог: dict[str, Any]) -> dict[str, Any]:
    assert итог["ответ"]["headers"]["content-type"].startswith("application/json")

    return dict(json.loads(итог["ответ"]["body"]))


ЗАКРЫТО = "2026-08-01 10:00:00"


@pytest.mark.parametrize(
    ("настройка", "статус", "смена"),
    [
        ({}, 200, (None, None)),
        # Сменили 01.08.2026 — следующая смена через полгода
        ({"сменено": ЗАКРЫТО}, 200, ("01.08.2026", "01.02.2027")),
        # Только владелец компании
        ({"роль": "manager"}, 403, None),
    ],
)
def test_сведения(сайт, настройка, статус, смена):
    итог = запрос(сайт, "/cabinet/settings/company-info", "GET", "", **настройка)

    assert итог["ответ"]["status"] == статус

    if смена is None:
        return

    данные = ответ(итог)
    assert данные["company"]["name"] == "Цемент Трейд"
    assert данные["company"]["tin"] == "301234567"
    assert данные["company"]["it_specializations"] == []
    assert (данные["changed_at"], данные["locked_until"]) == смена
    assert данные["cooldown_months"] == 6
    assert данные["countries"] == [
        {"id": данные["company"]["country_id"], "name": "Узбекистан", "code": "uz"}
    ]
    assert "web" in данные["serviceTypes"]
    # Сведения ничего не меняют
    assert итог["база"]["company"][0][9] is False


ТЕКУЩЕЕ = {"name": "Цемент Трейд", "tin": "301234567"}

#: Строка снимка companies: name, legal_name, tin, founded_year,
#: is_it_provider, it_specializations, address, search_text, метка смены, обновлено
ИСХОДНАЯ = ("Цемент Трейд", None, "301234567", None, False, None, None)


@pytest.mark.parametrize(
    ("body", "настройка", "статус", "стало", "метка"),
    [
        # Пустое заполнить можно всегда — без метки смены
        (
            {**ТЕКУЩЕЕ, "legal_name": "ООО «Цемент Трейд»", "founded_year": "2010"},
            {},
            200,
            ("Цемент Трейд", "ООО «Цемент Трейд»", "301234567", 2010, False, None, None),
            False,
        ),
        # Смена заполненного ставит метку
        (
            {**ТЕКУЩЕЕ, "name": "Цемент Плюс"},
            {},
            200,
            ("Цемент Плюс", None, "301234567", None, False, None, None),
            True,
        ),
        # Срок идёт — 422 с полем
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {"сменено": ЗАКРЫТО}, 422, {"name"}, True),
        # Срок прошёл — можно снова
        (
            {**ТЕКУЩЕЕ, "name": "Цемент Плюс"},
            {"сменено": "2025-01-31 10:00:00"},
            200,
            ("Цемент Плюс", None, "301234567", None, False, None, None),
            True,
        ),
        # Пустой адрес заполнить можно и пока срок идёт
        (
            {**ТЕКУЩЕЕ, "address": "Ташкент"},
            {"сменено": ЗАКРЫТО},
            200,
            ("Цемент Трейд", None, "301234567", None, False, None, "Ташкент"),
            True,
        ),
        (
            {**ТЕКУЩЕЕ, "is_it_provider": True, "it_specializations": ["web", "erp"]},
            {},
            200,
            ("Цемент Трейд", None, "301234567", None, True, '["web","erp"]', None),
            False,
        ),
        # ИНН другой компании, короткий ИНН, год и неизвестная специализация
        ({**ТЕКУЩЕЕ, "tin": "305123456"}, {}, 422, {"tin"}, False),
        ({**ТЕКУЩЕЕ, "tin": "30123"}, {}, 422, {"tin"}, False),
        (
            {**ТЕКУЩЕЕ, "founded_year": "1800", "it_specializations": ["nope"]},
            {},
            422,
            {"founded_year", "it_specializations.0"},
            False,
        ),
        ({"name": ""}, {}, 422, {"name"}, False),
        # Сотрудник площадки — с записью в журнал
        (
            {**ТЕКУЩЕЕ, "name": "Цемент Плюс"},
            {"admin": True},
            200,
            ("Цемент Плюс", None, "301234567", None, False, None, None),
            True,
        ),
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {"роль": "manager"}, 403, None, False),
    ],
)
def test_сохранение(сайт, body, настройка, статус, стало, метка):
    итог = запрос(сайт, "/cabinet/settings/company-info", "PATCH", body, **настройка)
    [строка] = итог["база"]["company"]

    assert итог["ответ"]["status"] == статус
    assert строка[8] is метка

    if статус == 200:
        данные = ответ(итог)
        assert строка[:7] == стало
        assert данные["company"]["name"] == стало[0]
        # Поисковый текст — из названия и юридического названия
        assert строка[7] == index(" ".join(x for x in стало[:2] if x))
        assert строка[9] is True

        if метка and "сменено" not in настройка:
            assert данные["changed_at"] and данные["locked_until"]

        if "address" in body:
            # Срок прежний — заполнение пустого его не сдвигает
            assert (данные["changed_at"], данные["locked_until"]) == ("01.08.2026", "01.02.2027")
    else:
        assert строка[:7] == ИСХОДНАЯ
        assert строка[9] is False

    if статус == 422:
        данные = ответ(итог)
        assert set(данные["errors"]) == стало

        if "сменено" in настройка:
            assert данные["message"].endswith("Следующая смена — с 01.02.2027.")
        else:
            # Сообщение — первая ошибка, как у Laravel
            assert данные["message"] == next(iter(данные["errors"].values()))[0]

    журнал = итог["база"]["journal"]
    assert [j[:2] for j in журнал] == ([("updated", "companies")] if "admin" in настройка else [])


@pytest.mark.parametrize(
    ("body", "настройка", "статус", "приписка"),
    [
        ({}, {}, 422, None),
        ({"message": "коротко"}, {}, 422, None),
        (
            {"message": "Поменяйте, пожалуйста, название — мы переименовались."},
            {},
            200,
            "— Компания #N «Цемент Трейд»",
        ),
        # Пока срок идёт — в обращении видно, с какого дня смена доступна
        (
            {"message": "Поменяйте, пожалуйста, название — мы переименовались."},
            {"сменено": ЗАКРЫТО},
            200,
            "— Компания #N «Цемент Трейд», смена данных доступна с 01.02.2027",
        ),
        ({"message": "Поменяйте, пожалуйста, название."}, {"роль": "manager"}, 403, None),
    ],
)
def test_обращение(сайт, body, настройка, статус, приписка):
    итог = запрос(сайт, "/cabinet/settings/company-info/support", "POST", body, **настройка)
    база = итог["база"]

    assert итог["ответ"]["status"] == статус

    if статус == 200:
        assert ответ(итог)["message"] == "Обращение отправлено. Мы ответим на вашу почту."
        assert база["tickets"] == [
            (
                "Смена данных компании: Цемент Трейд",
                "Покупатель info@savdex.uz",
                ПОЧТА,
                "open",
                "form",
                "normal",
                None,
                True,
            )
        ]
        assert база["messages"] == [(True, False, False, f"{body['message']}\n\n{приписка}")]
    else:
        assert база["tickets"] == [] and база["messages"] == []

    if статус == 422:
        assert list(ответ(итог)["errors"]) == ["message"]

    # Обращение данных не меняет
    assert база["company"][0][:7] == ИСХОДНАЯ
