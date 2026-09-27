"""
Юридические документы на Django неотличимы от Laravel (этап 3).

Оферта, оплата, безопасность, конфиденциальность, возвраты — на всех
языках; наименование оператора, почта и реквизиты из настроек, в том
числе незаполненные (строка реквизита пропадает, краткое наименование
вместо полного).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import laravel, сверить, страница

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

    with laravel() as root:
        yield root


@pytest.mark.parametrize("doc", ["terms", "payment", "security", "privacy", "refunds"])
@pytest.mark.parametrize("prefix", ["", "/uz", "/en", "/zh", "/tr"])
def test_документ(сайт, doc, prefix):
    сверить(сайт, f"{prefix}/{doc}")


def test_реквизиты_из_настроек(сайт):
    д, _ = сверить(сайт, "/terms")
    props = страница(д["body"])["props"]
    реквизиты = props["blocks"][-1]["content"][0]["list"]

    assert реквизиты[0] == РЕКВИЗИТЫ["legal_full_name"]
    assert "ИНН: 309 876 543" in реквизиты
    assert not any(r.startswith("Руководитель") for r in реквизиты)
    assert РЕКВИЗИТЫ["legal_full_name"] in props["preamble"][0]


def test_пустые_настройки(сайт):
    настройки({"legal_full_name": "  ", "legal_tin": "", "support_email": ""})

    try:
        д, _ = сверить(сайт, "/terms")
        сверить(сайт, "/en/payment")
        реквизиты = страница(д["body"])["props"]["blocks"][-1]["content"][0]["list"]
        assert реквизиты[0] == РЕКВИЗИТЫ["legal_name"]
    finally:
        настройки(РЕКВИЗИТЫ)
