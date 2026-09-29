"""
Скачивание файлов на Django неотличимо от Laravel: файлы компании
(/files/<номер>: своим — всё, прочим — показанное на визитке,
фотографии — inline) и файлы IT-задачи (/it-services/files/<номер>:
только вошедшим; закрытой задачи — только заказчику). Сверяются статус,
тип, размер, Content-Disposition (ASCII-запас и filename*) и байты.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import КОРЕНЬ, php, sql, нужна_база, свежая_база
from .test_web_company_file_actions import DOCX, PDF
from .test_web_company_profile_actions import картинка
from .test_web_forms import SID, ТОКЕН, учётка
from .test_web_session import СЕССИЯ, завести, кука
from .web_site import laravel, из_django, из_laravel

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/private"

#: (путь на диске, содержимое)
ФАЙЛЫ = {
    "docs/a.pdf": PDF,
    "docs/b.docx": DOCX,
    "docs/c.png": картинка(20, 10),
    "docs/d.txt": "Прайс на цемент".encode(),
    "docs/e.zip": b"PK\x05\x06" + b"\0" * 18,
}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    for путь, данные in ФАЙЛЫ.items():
        (ДИСК / путь).parent.mkdir(parents=True, exist_ok=True)
        (ДИСК / путь).write_bytes(данные)

    mine, other = (_id(s) for s in ("mine", "other"))
    строки = [
        (other, "catalog", "Каталог «Цемент» 2027", "docs/a.pdf", True, "approved"),
        (other, "license", "Лицензия/ТЗ", "docs/b.docx", True, "pending"),
        (other, "certificate", "Сертификат", "docs/c.png", True, "approved"),
        (other, "price_list", "Прайс", "docs/d.txt", False, "approved"),
        (other, "other", "..", "docs/e.zip", True, "approved"),
        (mine, "license", "Своя лицензия", "docs/b.docx", False, "pending"),
        (other, "catalog", "Нет файла", "docs/missing.pdf", True, "approved"),
    ]

    for company, kind, title, path, public, status in строки:
        sql(
            "insert into company_documents (company_id, type, title, file_path, file_size, "
            "mime, is_public, moderation_status, created_at, updated_at) values "
            "(%s, %s, %s, %s, 10, 'x', %s, %s, now(), now())",
            [company, kind, title, path, public, status],
        )

    for company, status, title, path in [
        (other, "active", "ТЗ проекта.pdf", "docs/a.pdf"),
        (other, "closed", "Смета.docx", "docs/b.docx"),
        (mine, "closed", "Моя смета.txt", "docs/d.txt"),
    ]:
        sql(
            "insert into it_tasks (company_id, slug, title, description, service_type, "
            "budget_type, currency, status, created_at, updated_at) values "
            "(%s, %s, 'Задача', 'Описание', 'web', 'negotiable', 'UZS', %s, now(), now())",
            [company, f"task-{title}", status],
        )
        sql(
            "insert into it_task_files (it_task_id, title, file_path, file_size, mime, "
            "created_at, updated_at) values ((select max(id) from it_tasks), %s, %s, 10, 'x', "
            "now(), now())",
            [title, path],
        )

    with laravel() as root:
        yield root


def _id(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def _запрос(сайт: str, path: str, гость: bool) -> dict[str, Any]:
    итог = {}

    for имя, сторона in (("django", из_django), ("laravel", из_laravel)):
        cookies = {}

        if not гость:
            uid = учётка("owner@savdex.uz", company_id=_id("mine"))
            завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})
            cookies = {СЕССИЯ: кука(СЕССИЯ, SID)}

        ответ = сторона(сайт, path, cookies, {"Accept": "text/html"})
        итог[имя] = {
            "status": ответ["status"],
            "type": ответ["headers"].get("content-type"),
            "length": ответ["headers"].get("content-length"),
            "disposition": ответ["headers"].get("content-disposition"),
            "location": ответ["headers"].get("location"),
            "sha256": ответ["sha256"] if ответ["status"] == 200 else None,
        }

    return итог


def _документ(title: str, company: str = "other") -> int:
    return int(
        sql(
            "select id from company_documents where title = %s and company_id = %s",
            [title, _id(company)],
        )[0][0]
    )


@pytest.mark.parametrize(
    ("title", "company"),
    [
        ("Каталог «Цемент» 2027", "other"),
        ("Лицензия/ТЗ", "other"),
        ("Сертификат", "other"),
        ("Прайс", "other"),
        ("..", "other"),
        ("Своя лицензия", "mine"),
        ("Нет файла", "other"),
    ],
)
@pytest.mark.parametrize("гость", [True, False])
def test_файл_компании(сайт, title, company, гость):
    итог = _запрос(сайт, f"/files/{_документ(title, company)}", гость)

    assert итог["django"] == итог["laravel"]


def test_нет_такого(сайт):
    итог = _запрос(сайт, "/files/999999", True)

    assert итог["django"] == итог["laravel"]


@pytest.mark.parametrize("title", ["ТЗ проекта.pdf", "Смета.docx", "Моя смета.txt"])
@pytest.mark.parametrize("гость", [True, False])
def test_файл_задачи(сайт, title, гость):
    номер = int(sql("select id from it_task_files where title = %s", [title])[0][0])
    итог = _запрос(сайт, f"/it-services/files/{номер}", гость)

    assert итог["django"] == итог["laravel"]
