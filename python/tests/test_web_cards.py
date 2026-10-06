"""
Визитки для QR: кабинет «Визитки» (список, новая — фото или из полей,
удалить) и страница визитки /card/<token> без входа.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from .factories import компания
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_cabinet import зайти, куки_входа
from .test_web_company_profile_actions import multipart, картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ПОЛЯ = {
    "kind": "generated",
    "company_name": "ООО «Цемент»",
    "full_name": "Каримов Рустам Алишерович",
    "email": "rustam@cement.uz",
    "phone": "+998 90 123-45-67",
}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="mine", name="ООО «Цемент»")
    компания(slug="other")

    with адрес() as root:
        yield root


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def владелец() -> int:
    return учётка("owner@savdex.uz", company_id=_компания("mine"), name="Рустам Каримов")


def _чисто() -> None:
    sql("delete from company_cards")


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return json.loads(итог["сессия"]["payload"])


def _ошибки(итог: dict[str, Any]) -> set[str]:
    return set(_сессия(итог).get("errors", {}).get("default", {}).get("messages", {}))


def _визитка(slug: str = "mine", **поля: Any) -> str:
    данные = {"token": "A" * 15 + str(len(sql("select id from company_cards"))), **поля}
    sql(
        "insert into company_cards (company_id, token, kind, company_name, full_name, email, "
        "phone, image_path, created_at, updated_at) values (%s, %s, %s, %s, %s, %s, %s, %s, "
        "now(), now())",
        [
            _компания(slug),
            данные["token"],
            данные.get("kind", "generated"),
            данные.get("company_name", "ООО «Цемент»"),
            данные.get("full_name", "Рустам"),
            данные.get("email", "r@cement.uz"),
            данные.get("phone", "+998901234567"),
            данные.get("image_path"),
        ],
    )

    return str(данные["token"])


def test_страница_кабинета(сайт):
    _чисто()
    uid = владелец()
    _визитка()
    _, стр = зайти(сайт, "/cabinet/cards", куки_входа("owner@savdex.uz"))
    props = стр["props"]

    assert стр["component"] == "cabinet/Cards"
    assert props["hasCompany"] is True and props["limit"] == 20
    assert props["defaults"]["company_name"] == "ООО «Цемент»"
    assert props["defaults"]["full_name"] == "Рустам Каримов"
    [card] = props["cards"]
    assert card["kind"] == "generated" and card["url"].endswith("/card/" + "A" * 15 + "0")
    assert uid


def test_без_компании(сайт):
    учётка("nobody@savdex.uz", company_id=None)
    _, стр = зайти(сайт, "/cabinet/cards", куки_входа("nobody@savdex.uz"))

    assert стр["props"]["hasCompany"] is False and стр["props"]["cards"] == []


def test_новая_из_полей(сайт):
    итог = отправить(сайт, "/cabinet/cards", _чисто, uid=владелец(), body=ПОЛЯ, headers=inertia())

    assert итог["ответ"]["status"] == 302 and _ошибки(итог) == set()
    [(kind, token, name, email)] = sql("select kind, token, full_name, email from company_cards")
    assert kind == "generated" and name == ПОЛЯ["full_name"] and email == ПОЛЯ["email"]
    # Код адреса — 16 случайных букв и цифр: перебором номеров визитку не найти
    assert re.fullmatch(r"[A-Za-z0-9]{16}", token)
    assert _сессия(итог)["success"] == "Визитка добавлена — QR-код готов."


@pytest.mark.parametrize(
    ("body", "поля"),
    [
        ({"kind": "generated"}, {"company_name", "full_name", "email", "phone"}),
        ({**ПОЛЯ, "email": "не почта", "phone": "12"}, {"email", "phone"}),
        ({"kind": "photo"}, {"photo"}),
        # Неизвестный вид проверяется как визитка из полей
        ({"kind": "other"}, {"kind", "company_name", "full_name", "email", "phone"}),
    ],
)
def test_проверка_полей(сайт, body, поля):
    итог = отправить(сайт, "/cabinet/cards", _чисто, uid=владелец(), body=body, headers=inertia())

    assert _ошибки(итог) == поля
    assert sql("select count(*) from company_cards")[0][0] == 0


def test_новая_фото(сайт):
    тело, тип = multipart({"kind": "photo", "photo": ("card.jpg", картинка(1600, 889, "JPEG"))})
    итог = отправить(
        сайт,
        "/cabinet/cards",
        _чисто,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )

    assert _ошибки(итог) == set()
    [(kind, путь, name)] = sql("select kind, image_path, full_name from company_cards")
    # Фото — без полей: всё нужное на самом снимке
    assert kind == "photo" and name is None
    assert re.fullmatch(rf"companies/{_компания('mine')}/cards/[A-Za-z0-9]{{40}}\.webp", путь)
    assert (Path(КОРЕНЬ) / "storage/app/public" / путь).exists()


def test_предел(сайт):
    def двадцать() -> None:
        _чисто()

        for i in range(20):
            _визитка(token=f"B{i:015d}")

    итог = отправить(сайт, "/cabinet/cards", двадцать, uid=владелец(), body=ПОЛЯ, headers=inertia())

    assert "20" in _сессия(итог)["error"]
    assert sql("select count(*) from company_cards")[0][0] == 20


def test_удалить_свою_и_не_чужую(сайт):
    def две() -> None:
        _чисто()
        _визитка(token="C" * 16)
        _визитка("other", token="D" * 16)

    свою = lambda: sql("select id from company_cards where token = %s", ["C" * 16])[0][0]  # noqa: E731
    чужую = lambda: sql("select id from company_cards where token = %s", ["D" * 16])[0][0]  # noqa: E731

    две()
    итог = отправить(
        сайт, f"/cabinet/cards/{чужую()}", lambda: None, uid=владелец(), method="DELETE"
    )
    assert итог["ответ"]["status"] == 404

    итог = отправить(
        сайт, f"/cabinet/cards/{свою()}", lambda: None, uid=владелец(), method="DELETE"
    )
    assert итог["ответ"]["status"] in (302, 303)
    assert sql("select token from company_cards") == [("D" * 16,)]


@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_страница_визитки(сайт, prefix):
    _чисто()
    token = _визитка(token="E" * 16)
    ответ, стр = зайти(сайт, f"{prefix}/card/{token}")

    assert ответ["status"] == 200 and стр["component"] == "cards/Show"
    card, company = стр["props"]["card"], стр["props"]["company"]
    # Почта и телефон — открыто: владелец сам раздаёт свой QR
    assert card["email"] == "r@cement.uz" and card["phone"] == "+998901234567"
    assert company["name"] == "ООО «Цемент»"
    assert company["url"] == сайт + prefix + "/company/mine"
    # Гость — +1 к просмотрам
    assert sql("select views_count from company_cards")[0][0] == 1


def test_визитка_не_найдена(сайт):
    _чисто()
    assert зайти(сайт, "/card/" + "Z" * 16)[0]["status"] == 404


def test_визитка_заблокированной_компании(сайт):
    _чисто()
    token = _визитка("other", token="F" * 16)
    sql("update companies set status = 'blocked' where slug = 'other'")

    try:
        assert зайти(сайт, f"/card/{token}")[0]["status"] == 404
    finally:
        sql("update companies set status = 'active' where slug = 'other'")
