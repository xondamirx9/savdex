"""
Заблокированная компания и автор, которого больше нет, — на публичном сайте.

У заблокированной компании нет визитки, объявлений, файлов и откликов
(в каталоге её давно нет — теперь и по прямому адресу); сама компания
своё видит: причина блокировки — в кабинете. В карте сайта — только
адреса, которые открываются. Резюме удалённого или заблокированного
человека не показывается: контакты в нём — его.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from . import factories
from .factories import it_задача, компания, объявление
from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/private"
ФАЙЛ = "blocked-test/price.pdf"


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

    живая = компания(slug="alive")
    закрытая = компания(slug="blocked", status="blocked", blocked_reason="Жалобы")
    объявление(slug="alive-cement", company_id=живая)
    объявление(slug="blocked-cement", company_id=закрытая)
    it_задача(slug="blocked-task", company_id=закрытая)

    (ДИСК / ФАЙЛ).parent.mkdir(parents=True, exist_ok=True)
    (ДИСК / ФАЙЛ).write_bytes(b"%PDF-1.4\n%%EOF\n")
    sql(
        "insert into company_documents (company_id, type, title, file_path, file_size, mime, "
        "is_public, moderation_status, created_at, updated_at) values "
        "(%s, 'price_list', 'Прайс', %s, 15, 'application/pdf', true, 'approved', now(), now())",
        [закрытая, ФАЙЛ],
    )

    # Резюме: живого автора, удалённого и заблокированного
    for slug, поля in (
        ("alive-cv", {}),
        ("deleted-cv", {"deleted_at": factories.Выражение("now()")}),
        ("blocked-cv", {"status": "blocked"}),
    ):
        uid = factories.пользователь(**поля)
        sql(
            "insert into resumes (user_id, slug, title, status, published_at, created_at, "
            "updated_at) values (%s, %s, 'Снабженец', 'published', now(), now(), now())",
            [uid, slug],
        )

    try:
        with адрес() as root:
            yield root
    finally:
        shutil.rmtree(ДИСК / "blocked-test", ignore_errors=True)


def _id(table: str, slug: str) -> int:
    return int(sql(f"select id from {table} where slug = %s", [slug])[0][0])


def _сотрудник(email: str, company_slug: str) -> dict[str, str]:
    return вход(пользователь(email, company_id=_id("companies", company_slug)))


def test_визитка_только_самой_компании(сайт):
    assert открыть(сайт, "/company/alive")["status"] == 200
    assert открыть(сайт, "/company/blocked")["status"] == 404
    assert открыть(сайт, "/company/blocked", _сотрудник("viewer1@x.uz", "alive"))["status"] == 404

    своя = открыть(сайт, "/company/blocked", _сотрудник("owner1@x.uz", "blocked"))
    assert своя["status"] == 200
    assert страница(своя["body"])["component"] == "companies/Show"


def test_объявление_только_самой_компании(сайт):
    assert открыть(сайт, "/listing/alive-cement")["status"] == 200
    assert открыть(сайт, "/listing/blocked-cement")["status"] == 404

    своё = открыть(сайт, "/listing/blocked-cement", _сотрудник("owner2@x.uz", "blocked"))
    assert своё["status"] == 200


def test_файл_только_самой_компании(сайт):
    [(номер,)] = sql("select id from company_documents where file_path = %s", [ФАЙЛ])

    assert открыть(сайт, f"/files/{номер}")["status"] == 404
    свой = открыть(сайт, f"/files/{номер}", _сотрудник("owner3@x.uz", "blocked"))
    assert свой["status"] == 200


def test_карта_сайта_без_заблокированных(сайт):
    карта = открыть(сайт, "/sitemap.xml")["body"]
    объявления = открыть(сайт, "/sitemap-listings-1.xml")["body"]

    # Единственная IT-задача — у заблокированной: части it-tasks в карте нет
    assert "sitemap-it-tasks.xml" not in карта
    assert "/listing/alive-cement" in объявления
    assert "/listing/blocked-cement" not in объявления


def test_резюме_только_живых_авторов(сайт):
    стр = страница(открыть(сайт, "/resumes")["body"])
    адреса = [r["slug"] for r in стр["props"]["resumes"]["data"]]

    assert адреса == ["alive-cv"]
    assert открыть(сайт, "/resume/alive-cv")["status"] == 200
    assert открыть(сайт, "/resume/deleted-cv")["status"] == 404
    assert открыть(сайт, "/resume/blocked-cv")["status"] == 404
