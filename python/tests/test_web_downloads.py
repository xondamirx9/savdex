"""
Скачивание файлов на Django: файлы компании
(/files/<номер>: своим — всё, прочим — показанное на визитке,
фотографии — inline) и файлы IT-задачи (/it-services/files/<номер>:
только вошедшим; закрытой задачи — только заказчику). Проверяются статус,
тип, размер, Content-Disposition (ASCII-запас и filename*) и байты.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import hashlib

import pytest

from savdex import laravel_session

from .factories import компания
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_company_file_actions import DOCX, PDF
from .test_web_company_profile_actions import картинка
from .test_web_forms import SID, ТОКЕН, учётка
from .web_site import СЕССИЯ, адрес, завести, кука, открыть

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
    компания(slug="mine")
    компания(slug="other")

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

    with адрес() as root:
        yield root


def _id(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def _запрос(сайт: str, path: str, гость: bool) -> dict[str, Any]:
    cookies = {}

    if not гость:
        uid = учётка("owner@savdex.uz", company_id=_id("mine"))
        завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})
        cookies = {СЕССИЯ: кука(СЕССИЯ, SID)}

    ответ = открыть(сайт, path, cookies, {"Accept": "text/html"})

    return {
        "status": ответ["status"],
        "type": ответ["headers"].get("content-type"),
        "length": ответ["headers"].get("content-length"),
        "disposition": ответ["headers"].get("content-disposition"),
        "location": ответ["headers"].get("location"),
        "sha256": ответ["sha256"] if ответ["status"] == 200 else None,
    }


def _документ(title: str, company: str = "other") -> int:
    return int(
        sql(
            "select id from company_documents where title = %s and company_id = %s",
            [title, _id(company)],
        )[0][0]
    )


#: Заголовок Content-Disposition с ASCII-запасом (Str::ascii) и filename*
КАТАЛОГ = (
    'attachment; filename="Katalog <<Cement>> 2027.pdf"; filename*=utf-8\'\''
    "%D0%9A%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3%20%C2%AB%D0%A6%D0%B5%D0%BC%D0%B5%D0%BD%D1%82"
    "%C2%BB%202027.pdf"
)
СВОЯ = (
    'attachment; filename="Svoia licenziia.docx"; filename*=utf-8\'\''
    "%D0%A1%D0%B2%D0%BE%D1%8F%20%D0%BB%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F.docx"
)
ТЗ = (
    'attachment; filename="TZ proekta.pdf"; filename*=utf-8\'\''
    "%D0%A2%D0%97%20%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D0%B0.pdf"
)
СМЕТА = (
    'attachment; filename="Moia smeta.txt"; filename*=utf-8\'\''
    "%D0%9C%D0%BE%D1%8F%20%D1%81%D0%BC%D0%B5%D1%82%D0%B0.txt"
)
DOCX_ТИП = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _файл(путь: str, тип: str, disposition: str) -> dict[str, Any]:
    """Ожидаемый ответ-файл: тип, размер, заголовок и байты с диска."""
    данные = ФАЙЛЫ[путь]

    return {
        "status": 200,
        "type": тип,
        "length": str(len(данные)),
        "disposition": disposition,
        "location": None,
        "sha256": hashlib.sha256(данные).hexdigest(),
    }


def _нет() -> dict[str, Any]:
    return {
        "status": 404,
        "type": "text/html; charset=utf-8",
        "length": None,
        "disposition": None,
        "location": None,
        "sha256": None,
    }


#: Документ компании → (гостю, владельцу «mine»)
ДОКУМЕНТЫ = {
    # Материал на визитке — всем; название с кавычками и пробелами
    ("Каталог «Цемент» 2027", "other"): (
        _файл("docs/a.pdf", "application/pdf", КАТАЛОГ),
        _файл("docs/a.pdf", "application/pdf", КАТАЛОГ),
    ),
    # Лицензия на проверке у чужой компании — никому, кроме её людей
    ("Лицензия/ТЗ", "other"): (_нет(), _нет()),
    # Фотография — inline, имя файла с диска
    ("Сертификат", "other"): (
        _файл("docs/c.png", "image/png", "inline; filename=c.png"),
        _файл("docs/c.png", "image/png", "inline; filename=c.png"),
    ),
    # Скрыт с визитки
    ("Прайс", "other"): (_нет(), _нет()),
    # Название из одних точек — «file»
    ("..", "other"): (
        _файл("docs/e.zip", "application/zip", "attachment; filename=file.zip"),
        _файл("docs/e.zip", "application/zip", "attachment; filename=file.zip"),
    ),
    # Свой скрытый документ — только своим
    ("Своя лицензия", "mine"): (_нет(), _файл("docs/b.docx", DOCX_ТИП, СВОЯ)),
    # Файла нет на диске
    ("Нет файла", "other"): (_нет(), _нет()),
}


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

    assert итог == ДОКУМЕНТЫ[(title, company)][0 if гость else 1]


def test_нет_такого(сайт):
    итог = _запрос(сайт, "/files/999999", True)

    assert итог == _нет()


#: Файл задачи → ответ вошедшему из «mine»
ЗАДАЧИ = {
    # Открытая чужая задача — всем вошедшим
    "ТЗ проекта.pdf": _файл("docs/a.pdf", "application/pdf", ТЗ),
    # Закрытая чужая — нет
    "Смета.docx": _нет(),
    # Закрытая своя — заказчику да; текст — с кодировкой
    "Моя смета.txt": _файл("docs/d.txt", "text/plain; charset=utf-8", СМЕТА),
}


@pytest.mark.parametrize("title", list(ЗАДАЧИ))
@pytest.mark.parametrize("гость", [True, False])
def test_файл_задачи(сайт, title, гость):
    номер = int(sql("select id from it_task_files where title = %s", [title])[0][0])
    итог = _запрос(сайт, f"/it-services/files/{номер}", гость)

    if гость:
        # Только вошедшим — гостя на вход
        assert (итог["status"], итог["location"]) == (302, сайт + "/login")
    else:
        assert итог == ЗАДАЧИ[title]
