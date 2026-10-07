"""
Срок тендеров из кабинета (savdex/tender_expiry.py, каждый час из
расписания): за три дня — предупреждение автору, один раз на срок; по
сроку — «Истёк» и уведомление; тендеры администратора не трогаются.
Истёкший тендер на сайте не виден.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from .factories import компания, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

ПРОХОД = """
import json
import django
django.setup()
from savdex import tender_expiry
print(json.dumps(tender_expiry.run()))
"""


@pytest.fixture(scope="module", autouse=True)
def база() -> None:
    свежая_база()


def проход() -> list[int]:
    out = subprocess.run(
        [sys.executable, "-c", ПРОХОД],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    )

    return list(json.loads(out.stdout.strip().splitlines()[-1]))


@pytest.fixture
def автор() -> int:
    sql("delete from tenders")
    sql("delete from user_notifications")

    return пользователь(company_id=компания(), locale="ru")


def тендер(author: int, срок: str, *, source: str = "cabinet", status: str = "published") -> int:
    rows = sql(
        "insert into tenders (slug, title, currency, status, source, author_id, published_at, "
        "deadline_at, created_at, updated_at) values "
        "(%s, %s, 'UZS', %s, %s, %s, now() at time zone 'utc' - interval '20 days', "
        f"now() at time zone 'utc' + interval '{срок}', now(), now()) returning id",
        [f"t-{срок_адрес(срок)}-{source}-{status}", f"Закупка {срок}", status, source, author],
    )

    return int(rows[0][0])


def срок_адрес(срок: str) -> str:
    return срок.replace(" ", "").replace("-", "m")


def уведомления(author: int) -> list[Any]:
    return sql(
        "select type, title, url from user_notifications where user_id = %s order by id", [author]
    )


def состояние(tid: int) -> Any:
    return sql("select status, expiry_warned_at is not null from tenders where id = %s", [tid])[0]


def test_предупреждение_за_три_дня(автор):
    скоро = тендер(автор, "2 days")
    нескоро = тендер(автор, "10 days")

    assert проход() == [0, 1]
    assert уведомления(автор) == [
        ("tender_expiring", "Через 3 дня истекает тендер «Закупка 2 days»", "/cabinet/tenders")
    ]
    assert состояние(скоро) == ("published", True)
    assert состояние(нескоро) == ("published", False)

    # Второй проход — без повтора
    assert проход() == [0, 0]
    assert len(уведомления(автор)) == 1

    # Продлили, и срок снова подошёл — новое предупреждение
    sql("update tenders set expiry_warned_at = null where id = %s", [скоро])
    assert проход() == [0, 1]


def test_истёк(автор):
    прошёл = тендер(автор, "-1 hour")

    assert проход() == [1, 0]
    assert состояние(прошёл) == ("expired", False)
    assert уведомления(автор)[0][:2] == (
        "tender_expiring",
        "Срок тендера «Закупка -1 hour» истёк",
    )
    assert проход() == [0, 0]


def test_чужие_правила_не_трогаются(автор):
    # Тендер администратора живёт по своему сроку; завершённый — уже не на витрине
    админ = тендер(автор, "-1 hour", source="admin")
    завершён = тендер(автор, "-1 hour", status="archived")
    скоро_админ = тендер(автор, "2 days", source="admin")

    assert проход() == [0, 0]
    assert состояние(админ)[0] == "published"
    assert состояние(завершён)[0] == "archived"
    assert состояние(скоро_админ) == ("published", False)
    assert уведомления(автор) == []


def test_удалённому_автору_не_пишется(автор):
    sql("update users set deleted_at = now() where id = %s", [автор])
    tid = тендер(автор, "-1 hour")

    assert проход() == [1, 0]
    assert состояние(tid)[0] == "expired"
    assert уведомления(автор) == []
