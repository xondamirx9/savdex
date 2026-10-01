"""
Файлы компании на Django: загрузка (тип по
содержимому — libmagic, как finfo у PHP; расширение имени на диске — по
типу; файл с расширением PHP отвергается; срок действия — дата позже
сегодняшней; документы ждут модератора, материалы — нет), показ на
визитке, удаление с файлом. Чужой файл — 404, без компании — отказ.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .factories import компания
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_company_profile_actions import картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/private"
СТАРЫЙ = "companies/{id}/documents/old-file.pdf"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="mine")
    компания(slug="other")

    with адрес() as root:
        yield root


def _id(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def владелец(*, admin: bool = False, company: bool = True) -> int:
    return учётка("owner@savdex.uz", company_id=_id("mine") if company else None, is_admin=admin)


def _папка(slug: str) -> Path:
    return ДИСК / f"companies/{_id(slug)}/documents"


def сброс() -> Callable[[], None]:
    """Два файла: свой (материал, скрыт) и чужой; на диске — только они."""

    def run() -> None:
        sql("delete from company_documents")
        sql("delete from admin_actions")
        sql("select setval('company_documents_id_seq', 1, false)")

        for slug in ("mine", "other"):
            shutil.rmtree(_папка(slug), ignore_errors=True)
            _папка(slug).mkdir(parents=True)
            path = СТАРЫЙ.format(id=_id(slug))
            (ДИСК / path).write_bytes(b"%PDF-1.4 old")
            sql(
                "insert into company_documents (company_id, type, title, file_path, file_size, "
                "mime, is_public, moderation_status, created_at, updated_at) values "
                "(%s, 'catalog', 'Каталог', %s, 12, 'application/pdf', false, 'approved', "
                "now() - interval '1 day', now() - interval '1 day')",
                [_id(slug), path],
            )

    return run


def снимок() -> Any:
    random = r"[A-Za-z0-9]{40}"

    return {
        "documents": sql(
            "select company_id, type, title, "
            f"regexp_replace(file_path, '{random}', '<random>'), file_size, mime, "
            "valid_until::text, is_public, moderation_status, "
            "updated_at > now() - interval '1 hour' from company_documents order by id"
        ),
        "disk": {
            slug: sorted(
                f.name if f.name.startswith("old") else "<random>" + f.suffix
                for f in _папка(slug).iterdir()
            )
            for slug in ("mine", "other")
        },
        "journal": sql(
            "select action, section, subject_type, subject_label, "
            f"regexp_replace(regexp_replace(changes::text, '{random}', '<random>', 'g'), "
            "'\\d{4}-\\d\\d-\\d\\d \\d\\d:\\d\\d:\\d\\d', 'T', 'g') "
            "from admin_actions order by id"
        ),
    }


def multipart(поля: dict[str, Any]) -> tuple[str, str]:
    """Тело multipart/form-data; файл — (имя, байты, тип от браузера)."""
    граница = "----savdexparity"
    части = []

    for name, value in поля.items():
        if isinstance(value, tuple):
            filename, data, тип = value
            заголовок = f"\r\nContent-Type: {тип}" if тип else ""
            части.append(
                f'--{граница}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"{заголовок}\r\n\r\n'.encode()
                + data
                + b"\r\n"
            )
        else:
            части.append(
                f'--{граница}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n".encode()
            )

    тело = b"".join(части) + f"--{граница}--\r\n".encode()

    return "base64:" + base64.b64encode(тело).decode(), f"multipart/form-data; boundary={граница}"


def _ooxml(main: str, content_type: str) -> bytes:
    out = io.BytesIO()

    with zipfile.ZipFile(out, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/'
            f'2006/content-types"><Override PartName="/{main}" ContentType="{content_type}"/>'
            "</Types>",
        )
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships/>')
        z.writestr(main, '<?xml version="1.0"?><x/>')

    return out.getvalue()


def _zip() -> bytes:
    out = io.BytesIO()

    with zipfile.ZipFile(out, "w") as z:
        z.writestr("readme.txt", "Прайс внутри")

    return out.getvalue()


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
DOCX = _ooxml(
    "word/document.xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
)
XLSX = _ooxml(
    "xl/workbook.xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
)
ФАЙЛЫ: dict[str, tuple[str, bytes, str]] = {
    "pdf": ("Устав.pdf", PDF, "application/pdf"),
    "docx": ("Лицензия.docx", DOCX, "application/octet-stream"),
    "xlsx": ("Прайс.xlsx", XLSX, ""),
    "zip": ("Каталог.zip", _zip(), "application/zip"),
    "png": ("Сертификат.png", картинка(40, 30), "image/png"),
    "jpg": ("Фото.jpeg", картинка(40, 30, "JPEG"), "image/jpeg"),
    "txt": ("Заметка.pdf", "Просто текст".encode(), "application/pdf"),
    "exe": ("Программа.exe", b"MZ" + b"\0" * 200, "application/x-msdownload"),
    "php": ("shell.php", PDF, "application/pdf"),
    "phtml": ("shell.PHTML ", PDF, "application/pdf"),
}


#: (поля, файл) → (тип от браузера, срок, на визитке, модерация): документы
#: ждут модератора, материалы (каталог, прайс, прочее) — нет
ГОДНЫЕ: list[tuple[dict[str, str], str | None]] = [
    ({"type": "registration", "title": "Свидетельство"}, "pdf"),
    ({"type": "catalog", "title": "Каталог 2027", "is_public": "0"}, "docx"),
    ({"type": "price_list", "title": "Прайс", "valid_until": "2099-12-31"}, "xlsx"),
    ({"type": "other", "title": "Архив", "is_public": "1"}, "zip"),
    ({"type": "certificate", "title": "Сертификат", "valid_until": "31.12.2099"}, "png"),
    ({"type": "quality", "title": "Фото цеха"}, "jpg"),
]
СОХРАНЕНО: list[tuple[str, str | None, bool, str]] = [
    ("application/pdf", None, True, "pending"),
    # Тип в строке — от браузера; пустой — octet-stream
    ("application/octet-stream", None, False, "approved"),
    ("application/octet-stream", "2099-12-31", True, "approved"),
    ("application/zip", None, True, "approved"),
    ("image/png", "2099-12-31", True, "pending"),
    ("image/jpeg", None, True, "pending"),
]
НЕ_ТОТ_ТИП = {"file": ["Допустимы PDF, документы Word и Excel, презентации, изображения и ZIP"]}
ИСТЁК = "Срок действия уже истёк — такой документ не подтверждает ничего"
ОТКАЗЫ: list[tuple[dict[str, str], str | None]] = [
    ({"type": "license", "title": "Лицензия"}, "txt"),
    ({"type": "license", "title": "Лицензия"}, "exe"),
    ({"type": "license", "title": "Лицензия"}, "php"),
    ({"type": "license", "title": "Лицензия"}, "phtml"),
    ({"type": "license", "title": "Лицензия"}, None),
    ({"type": "passport", "title": ""}, "pdf"),
    ({"type": "license", "title": "Л" * 191}, "pdf"),
    ({"type": "license", "title": "Просрочен", "valid_until": "2020-01-01"}, "pdf"),
    ({"type": "license", "title": "Не дата", "valid_until": "скоро"}, "pdf"),
    ({"type": "license", "title": "30 февраля", "valid_until": "2099-02-30"}, "pdf"),
    ({"type": "license", "title": "Показ", "is_public": "yes"}, "pdf"),
]
ОШИБКИ: list[dict[str, list[str]]] = [
    # Текст под видом PDF, программа, файлы с расширением PHP — по содержимому
    # или имени не годятся
    НЕ_ТОТ_ТИП,
    НЕ_ТОТ_ТИП,
    НЕ_ТОТ_ТИП,
    НЕ_ТОТ_ТИП,
    {"file": ["Выберите файл"]},
    {
        "type": ["validation.in"],
        "title": ["Назовите файл — партнёр увидит именно это название"],
    },
    {"title": ["validation.max.string"]},
    {"valid_until": [ИСТЁК]},
    {"valid_until": ["validation.date", ИСТЁК]},
    {"valid_until": ["validation.date"]},
    {"is_public": ["validation.boolean"]},
]
ДОКУМЕНТ = "Документ загружен и отправлен на проверку"
МАТЕРИАЛ = "Файл загружен и виден партнёрам на визитке"


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


def _ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    return dict(((_сессия(итог).get("errors") or {}).get("default") or {}).get("messages") or {})


#: Два файла после сброс(): свой и чужой, оба нетронутые
ПРЕЖНИЕ = [
    (company, "catalog", "Каталог", f"companies/{company}/documents/old-file.pdf", 12,
     "application/pdf", None, False, "approved", False)
    for company in (1, 2)
]  # fmt: skip


@pytest.mark.parametrize(
    ("поля", "файл", "ждём"),
    [(*годный, сохранено) for годный, сохранено in zip(ГОДНЫЕ, СОХРАНЕНО, strict=True)]
    + [(*отказ, ошибки) for отказ, ошибки in zip(ОТКАЗЫ, ОШИБКИ, strict=True)],
)
@pytest.mark.parametrize("admin", [False, True])
def test_загрузка(сайт, поля, файл, ждём, admin):
    тело, тип = multipart({**поля, **({"file": ФАЙЛЫ[файл]} if файл else {})})
    итог = отправить(
        сайт,
        "/cabinet/company/files",
        сброс(),
        снимок,
        uid=владелец(admin=admin),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )
    база = итог["база"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
    assert база["documents"][:2] == ПРЕЖНИЕ

    if isinstance(ждём, dict):
        assert _ошибки(итог) == ждём
        assert len(база["documents"]) == 2
        assert база["disk"]["mine"] == ["old-file.pdf"]
        assert база["journal"] == []

        return

    mime, срок, показ, модерация = ждём
    [документ] = база["documents"][2:]
    # Имя на диске — случайное, расширение — по типу содержимого
    ext = файл
    assert документ[:4] == (1, поля["type"], поля["title"], f"companies/1/documents/<random>.{ext}")
    assert документ[4] == len(ФАЙЛЫ[файл][1])
    assert документ[5:] == (mime, срок, показ, модерация, True)
    assert база["disk"] == {"mine": sorted([f"<random>.{ext}", "old-file.pdf"]), "other": ["old-file.pdf"]}
    assert _сессия(итог)["success"] == (ДОКУМЕНТ if модерация == "pending" else МАТЕРИАЛ)
    # Журнал — только у сотрудника
    assert [j[:4] for j in база["journal"]] == (
        [("created", "documents", "App\\Models\\CompanyDocument", поля["title"])] if admin else []
    )


def test_без_компании(сайт):
    тело, тип = multipart({"type": "license", "title": "Лицензия", "file": ФАЙЛЫ["pdf"]})
    итог = отправить(
        сайт,
        "/cabinet/company/files",
        сброс(),
        снимок,
        uid=владелец(company=False),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 302
    assert _сессия(итог)["error"] == "Сначала заполните данные компании"
    assert итог["база"]["documents"] == ПРЕЖНИЕ
    assert итог["база"]["disk"]["mine"] == ["old-file.pdf"]


@pytest.mark.parametrize(
    ("body", "показ"), [({"is_public": True}, True), ({"is_public": "0"}, False), ({}, False)]
)
@pytest.mark.parametrize(("номер", "admin"), [(1, False), (1, True), (2, False)])
def test_показ(сайт, body, показ, номер, admin):
    итог = отправить(
        сайт,
        f"/cabinet/company/files/{номер}",
        сброс(),
        снимок,
        uid=владелец(admin=admin),
        body=body,
        method="PATCH",
        headers=inertia(),
    )
    база = итог["база"]

    if номер == 2:
        # Чужой файл — 404, ничего не тронуто
        assert итог["ответ"]["status"] == 404
        assert база["documents"] == ПРЕЖНИЕ

        return

    assert итог["ответ"]["status"] == 303
    assert _сессия(итог)["success"] == (
        "Файл показывается на визитке" if показ else "Файл скрыт с визитки"
    )
    свой = база["documents"][0]
    # Строка правится, только если показ меняется (было — скрыт)
    assert (свой[7], свой[9]) == (показ, показ)
    assert база["documents"][1] == ПРЕЖНИЕ[1]
    assert [j[:4] for j in база["journal"]] == (
        [("updated", "documents", "App\\Models\\CompanyDocument", "Каталог")]
        if admin and показ
        else []
    )


@pytest.mark.parametrize(("номер", "admin"), [(1, False), (1, True), (2, False), (99, False)])
def test_удаление(сайт, номер, admin):
    итог = отправить(
        сайт,
        f"/cabinet/company/files/{номер}",
        сброс(),
        снимок,
        uid=владелец(admin=admin),
        method="DELETE",
        headers=inertia(),
    )
    база = итог["база"]

    if номер != 1:
        assert итог["ответ"]["status"] == 404
        assert база["documents"] == ПРЕЖНИЕ
        assert база["disk"] == {"mine": ["old-file.pdf"], "other": ["old-file.pdf"]}

        return

    # Inertia: DELETE, ответивший переходом, — 303; файл уходит и с диска
    assert итог["ответ"]["status"] == 303
    assert _сессия(итог)["success"] == "Файл удалён"
    assert база["documents"] == ПРЕЖНИЕ[1:]
    assert база["disk"] == {"mine": [], "other": ["old-file.pdf"]}
    assert [j[:4] for j in база["journal"]] == (
        [("deleted", "documents", "App\\Models\\CompanyDocument", "Каталог")] if admin else []
    )


#: Тип по содержимому для ФАЙЛЫ (по порядку) и трёх особых случаев — то же,
#: что давал finfo(FILEINFO_MIME_TYPE)->buffer у PHP (обе — libmagic)
ТИПЫ = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "image/png",
    "image/jpeg",
    # Текст под именем .pdf
    "text/plain",
    "application/x-dosexec",
    "application/pdf",
    "application/pdf",
    # Пустой файл, двоичный мусор, текст
    "application/x-empty",
    "application/octet-stream",
    "text/plain",
]


def test_тип_по_содержимому():
    """filetype.mime_type: тип по байтам, а не по имени и не со слов браузера."""
    from savdex.web import filetype

    данные = [data for _, data, _ in ФАЙЛЫ.values()] + [b"", b"\x00\x01\x02", "Привет".encode()]

    assert [filetype.mime_type(d) for d in данные] == ТИПЫ
