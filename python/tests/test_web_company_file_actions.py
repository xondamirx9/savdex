"""
Файлы компании на Django неотличимы от Laravel: загрузка (тип по
содержимому — libmagic, как finfo у PHP; расширение имени на диске — по
типу; файл с расширением PHP отвергается; срок действия — дата позже
сегодняшней; документы ждут модератора, материалы — нет), показ на
визитке, удаление с файлом. Чужой файл — 404, без компании — отказ.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import io
import shutil
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, php, sql, нужна_база, свежая_база
from .test_web_company_profile_actions import картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/private"
СТАРЫЙ = "companies/{id}/documents/old-file.pdf"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
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


ГОДНЫЕ: list[tuple[dict[str, str], str | None]] = [
    ({"type": "registration", "title": "Свидетельство"}, "pdf"),
    ({"type": "catalog", "title": "Каталог 2027", "is_public": "0"}, "docx"),
    ({"type": "price_list", "title": "Прайс", "valid_until": "2099-12-31"}, "xlsx"),
    ({"type": "other", "title": "Архив", "is_public": "1"}, "zip"),
    ({"type": "certificate", "title": "Сертификат", "valid_until": "31.12.2099"}, "png"),
    ({"type": "quality", "title": "Фото цеха"}, "jpg"),
]
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


@pytest.mark.parametrize(("поля", "файл"), ГОДНЫЕ + ОТКАЗЫ)
@pytest.mark.parametrize("admin", [False, True])
def test_загрузка(сайт, поля, файл, admin):
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

    assert len(итог["база"]["documents"]) == (3 if (поля, файл) in ГОДНЫЕ else 2)


def test_без_компании(сайт):
    тело, тип = multipart({"type": "license", "title": "Лицензия", "file": ФАЙЛЫ["pdf"]})
    отправить(
        сайт,
        "/cabinet/company/files",
        сброс(),
        снимок,
        uid=владелец(company=False),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )


@pytest.mark.parametrize("body", [{"is_public": True}, {"is_public": "0"}, {}])
@pytest.mark.parametrize(("номер", "admin"), [(1, False), (1, True), (2, False)])
def test_показ(сайт, body, номер, admin):
    отправить(
        сайт,
        f"/cabinet/company/files/{номер}",
        сброс(),
        снимок,
        uid=владелец(admin=admin),
        body=body,
        method="PATCH",
        headers=inertia(),
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

    if номер == 1:
        assert итог["база"]["disk"]["mine"] == []


def test_тип_как_у_php():
    """finfo(FILEINFO_MIME_TYPE)->buffer у PHP и filetype.mime_type на одних байтах."""
    import json

    from savdex.web import filetype

    данные = [data for _, data, _ in ФАЙЛЫ.values()] + [b"", b"\x00\x01\x02", "Привет".encode()]
    закодировано = json.dumps([base64.b64encode(d).decode() for d in данные])
    php_types = json.loads(
        php(
            "$f = new finfo(FILEINFO_MIME_TYPE); echo json_encode(array_map("
            f"fn ($b) => $f->buffer(base64_decode($b)), json_decode('{закодировано}')));"
        )
    )

    assert [filetype.mime_type(d) for d in данные] == php_types
