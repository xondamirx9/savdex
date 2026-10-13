"""
Адреса страниц латиницей (ТЗ-02 §4): manage.py reslug переписывает
/company/company и /listing/-N, старый адрес отвечает 301 на новый.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator

import pytest

from savdex.tenders.slug import numbered_slug, slugify

from .factories import компания, объявление
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, открыть

pytestmark = нужна_база


def test_транслитерация():
    assert slugify("四川省昊铂明悦商贸有限公司") == (
        "si-chuan-sheng-hao-bo-ming-yue-shang-mao-you-xian-gong-si"
    )
    assert slugify("测试公司") == "ce-shi-gong-si"
    assert slugify("Şişli Ticaret A.Ş.") == "sisli-ticaret-as"
    assert slugify("ООО «Цемент Плюс»") == "ooo-tsement-plius"
    # Без латиницы — один номер, без ведущего дефиса
    assert numbered_slug("!!!", 864) == "864"
    assert numbered_slug("Цемент М400", 7) == "tsement-m400-7"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def reslug() -> str:
    return subprocess.run(
        [sys.executable, "manage.py", "reslug"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def адрес_записи(table: str, key: int) -> str:
    return str(sql(f"select slug from {table} where id = %s", [key])[0][0])


def test_старые_адреса(сайт):
    китайская = компания(name="四川省昊铂明悦商贸有限公司", slug="company")
    вторая = компания(name="测试公司", slug="company-2")
    своя = компания(name="Company Group", slug="company-3")
    товар = объявление(company_id=китайская, title="水龙头", slug="-861")

    assert "компаний 2, объявлений 1" in reslug()

    assert адрес_записи("companies", китайская) == (
        "si-chuan-sheng-hao-bo-ming-yue-shang-mao-you-xian-gong-si"
    )
    assert адрес_записи("companies", вторая) == "ce-shi-gong-si"
    # «Company Group» — адрес и так подходит названию
    assert адрес_записи("companies", своя) == "company-3"
    assert адрес_записи("listings", товар) == f"shui-long-tou-{товар}"

    # Повторный запуск ничего не трогает
    assert "компаний 0, объявлений 0" in reslug()

    # Старые адреса — 301 на новые, с языком
    ответ = открыть(сайт, "/company/company")
    assert ответ["status"] == 301
    assert ответ["headers"]["location"].endswith(
        "/company/si-chuan-sheng-hao-bo-ming-yue-shang-mao-you-xian-gong-si"
    )
    ответ = открыть(сайт, "/uz/listing/-861")
    assert ответ["status"] == 301
    assert ответ["headers"]["location"].endswith(f"/uz/listing/shui-long-tou-{товар}")

    # Неизвестный адрес — по-прежнему 404
    assert открыть(сайт, "/company/no-such-company")["status"] == 404


ВЫЧИСЛИТЬ = """
import json, sys
import django
django.setup()
from savdex.web.company_profile_actions import slug_fields
print(json.dumps([slug_fields(name) for name in sys.argv[1:]]))
"""


def test_новые_адреса_с_номером(сайт):
    # Свободный адрес — латиницей; занятый или без латиницы — с номером компании,
    # взятым заранее (приёмка ТЗ-02: второй «测试公司» без конфликта)
    компания(name="测试公司 Trade", slug="ce-shi-gong-si-trade")
    out = subprocess.run(
        [sys.executable, "-c", ВЫЧИСЛИТЬ, "测试公司 Plus", "测试公司 Trade", "!!"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    свободный, занятый, пустой = json.loads(out.strip().splitlines()[-1])

    assert свободный == {"slug": "ce-shi-gong-si-plus"}
    assert занятый["slug"] == f"ce-shi-gong-si-trade-{занятый['id']}"
    assert пустой["slug"] == f"company-{пустой['id']}"
    assert пустой["id"] > занятый["id"]
