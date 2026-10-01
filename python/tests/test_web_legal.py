"""
Юридические документы на Django (этап 3).

Оферта, оплата, безопасность, конфиденциальность, возвраты — на всех
языках; наименование оператора, почта и реквизиты из настроек, в том
числе незаполненные (строка реквизита пропадает, краткое наименование
вместо полного).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть, страница

pytestmark = нужна_база

РЕКВИЗИТЫ = {
    "support_email": "help@savdex.uz",
    "legal_full_name": "Общество с ограниченной ответственностью «ANJIR-GROUP»",
    "legal_name": "ООО «ANJIR-GROUP»",
    "legal_brand": "SavdEx",
    "legal_tin": " 309 876 543 ",
    "legal_address": "г. Ташкент, ул. Навои, 1 & <офис 5>",
    "legal_phone": "+998 71 000 00 00",
    "legal_bank": "АКБ «Капиталбанк»",
    "legal_mfo": "00974",
    "legal_account": "2020 8000 0000 0000 0001",
    "legal_director": "",
}


def настройки(values: dict[str, str]) -> None:
    for key, value in values.items():
        sql(
            'insert into settings (key, "group", label, type, value, created_at, updated_at) '
            "values (%s, 'legal', %s, 'string', %s, now(), now()) "
            "on conflict (key) do update set value = excluded.value",
            [key, key, json.dumps(value)],
        )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    настройки(РЕКВИЗИТЫ)

    with адрес() as root:
        yield root


@pytest.mark.parametrize("doc", ["terms", "payment", "security", "privacy", "refunds"])
@pytest.mark.parametrize("prefix", ["", "/uz", "/en", "/zh", "/tr"])
def test_документ(сайт, doc, prefix):
    д = открыть(сайт, f"{prefix}/{doc}")
    стр = страница(д["body"])
    props = стр["props"]

    assert д["status"] == 200
    assert стр["component"] == "Legal"
    assert стр["url"] == f"{prefix}/{doc}"
    assert props["locale"] == (prefix.strip("/") or "ru")
    assert props["title"] and props["blocks"]
    # Соседние документы — все пять, текущий отмечен
    assert [s["href"] for s in props["siblings"]] == [
        "/terms",
        "/payment",
        "/security",
        "/privacy",
        "/refunds",
    ]
    assert [s["href"] for s in props["siblings"] if s["current"]] == [f"/{doc}"]


def test_реквизиты_из_настроек(сайт):
    д = открыть(сайт, "/terms")
    assert д["status"] == 200
    props = страница(д["body"])["props"]
    реквизиты = props["blocks"][-1]["content"][0]["list"]

    assert реквизиты[0] == РЕКВИЗИТЫ["legal_full_name"]
    assert "ИНН: 309 876 543" in реквизиты
    assert not any(r.startswith("Руководитель") for r in реквизиты)
    assert РЕКВИЗИТЫ["legal_full_name"] in props["preamble"][0]


def test_пустые_настройки(сайт):
    настройки({"legal_full_name": "  ", "legal_tin": "", "support_email": ""})

    try:
        д = открыть(сайт, "/terms")
        props = страница(д["body"])["props"]
        реквизиты = props["blocks"][-1]["content"][0]["list"]
        assert реквизиты[0] == РЕКВИЗИТЫ["legal_name"]
        # Пустой ИНН — строки реквизита нет
        assert not any(r.startswith("ИНН") for r in реквизиты)
        assert РЕКВИЗИТЫ["legal_name"] in props["preamble"][0]

        en = открыть(сайт, "/en/payment")
        assert en["status"] == 200
        assert страница(en["body"])["component"] == "Legal"
    finally:
        настройки(РЕКВИЗИТЫ)
