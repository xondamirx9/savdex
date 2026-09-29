"""
Профиль своей компании на Django неотличим от Laravel: правка (ИНН по
правилу Tin и одна компания на ИНН, год основания, IT-направления,
search_text), создание компании пользователем без неё (адрес из
названия, владелец, переход в профиль); у администратора — журнал.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база, страна
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    страна("kz", {"ru": "Казахстан"})
    php(
        f"App\\Models\\Company::factory()->create(['slug' => 'mine', 'country_id' => {uz},"
        " 'name' => 'Цемент Трейд', 'tin' => '301234567']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other', 'tin' => '305123456']);"
        "App\\Models\\Company::factory()->create(['slug' => 'cement-plus'])->delete();"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


def _страна(code: str) -> int:
    return int(sql("select id from countries where code = %s", [code])[0][0])


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def сброс(admin: bool = False, без_компании: bool = False) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions where section in ('companies', 'users')")
        # Созданная прошлой стороной компания — прочь, номер — тот же
        sql("update users set company_id = null where email = 'owner@savdex.uz'")
        sql("delete from companies where slug not in ('mine', 'other') and deleted_at is null")
        sql("select setval('companies_id_seq', (select max(id) from companies) + 1, false)")
        sql(
            "update companies set name = 'Цемент Трейд', legal_name = null, tin = '301234567', "
            "country_id = %s, founded_year = null, is_it_provider = false, "
            "it_specializations = null, search_text = 'цемент трейд sement treyd', "
            "updated_at = now() - interval '1 day' where slug = 'mine'",
            [_страна("uz")],
        )
        учётка(
            "owner@savdex.uz",
            company_id=None if без_компании else _компания("mine"),
            company_role="owner",
            is_admin=admin,
        )

    return run


def снимок() -> Any:
    журнал = [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions "
            "where section in ('companies', 'users') order by id"
        )
    ]

    return {
        "companies": sql(
            "select id, slug, name, legal_name, tin, country_id, founded_year, is_it_provider, "
            "it_specializations::text, search_text, status, deleted_at is not null, "
            "updated_at > now() - interval '1 hour' from companies order by id"
        ),
        "owner": sql("select company_id, company_role from users where email = 'owner@savdex.uz'"),
        "journal": журнал,
    }


ВЕРНО = {
    "name": "Цемент Плюс",
    "legal_name": "ООО «Цемент Плюс»",
    "tin": "302345678",
    "founded_year": "2010",
    "is_it_provider": True,
    "it_specializations": ["web", "erp"],
    "primary_role": "supplier",
    "website": "https://cement.uz",
}


@pytest.mark.parametrize(
    "body",
    [
        ВЕРНО,
        {"name": "Цемент Трейд", "tin": "301234567"},
        {**ВЕРНО, "tin": "30234567"},
        {**ВЕРНО, "tin": "30234567a"},
        {**ВЕРНО, "tin": "111111111"},
        {**ВЕРНО, "tin": "123456789"},
        {**ВЕРНО, "tin": "305123456"},
        {**ВЕРНО, "tin": "1234567", "country_id": "kz"},
        {**ВЕРНО, "tin": "12345", "country_id": "kz"},
        {**ВЕРНО, "founded_year": "1800"},
        {**ВЕРНО, "it_specializations": ["web", "space"], "primary_role": "boss"},
        {**ВЕРНО, "name": ""},
        {**ВЕРНО, "tin": None, "legal_name": None},
        # Заполненное здесь не меняется (раз в полгода — из настроек),
        # пустое заполняется: название и ИНН те же, остальное — впервые
        {
            **ВЕРНО,
            "name": "Цемент Трейд",
            "tin": "301234567",
            "it_specializations": ["erp", "web"],
        },
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_правка(сайт, body, admin):
    body = dict(body)

    if body.get("country_id") == "kz":
        body["country_id"] = _страна("kz")

    отправить(
        сайт,
        "/cabinet/company",
        сброс(admin),
        снимок,
        uid=учётка("owner@savdex.uz"),
        body=body,
        method="PATCH",
        headers=inertia(),
    )


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_новая_компания(сайт, admin, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/company",
        сброс(admin, без_компании=True),
        снимок,
        uid=учётка("owner@savdex.uz"),
        body={**ВЕРНО, "tin": "309876543"},
        method="PATCH",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303
    assert итог["база"]["owner"][0][1] == "owner"


# ── Логотип и обложка ───────────────────────────────────────────────


def картинка(width: int, height: int, fmt: str = "PNG", alpha: bool = False) -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", (width, height), (200, 30, 30, 128)).save(out, fmt)

    return out.getvalue()


def multipart(поля: dict[str, tuple[str, bytes] | str]) -> tuple[str, str]:
    """Тело multipart/form-data (base64 для помощника) и его Content-Type."""
    import base64

    граница = "----savdexparity"
    части = []

    for name, value in поля.items():
        if isinstance(value, tuple):
            filename, data = value
            части.append(
                f'--{граница}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
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


СТАРЫЙ = "companies/old/logo.webp"


def с_картинкой(field: str) -> Callable[[], None]:
    def run() -> None:
        from .pg_admin import КОРЕНЬ

        сброс()()
        путь = Path(КОРЕНЬ) / "storage/app/public" / СТАРЫЙ
        путь.parent.mkdir(parents=True, exist_ok=True)
        путь.write_bytes(b"old")
        sql(f"update companies set {field}_path = %s where slug = 'mine'", [СТАРЫЙ])

    return run


def снимок_картинки(field: str) -> Callable[[], Any]:
    def run() -> Any:
        from PIL import Image

        from .pg_admin import КОРЕНЬ

        [(путь,)] = sql(f"select {field}_path from companies where slug = 'mine'")
        файл = None

        if путь and путь != СТАРЫЙ:
            with Image.open(Path(КОРЕНЬ) / "storage/app/public" / путь) as img:
                файл = (img.format, img.size)

        return {
            "path": re.sub(r"/[A-Za-z0-9]{40}\.webp$", "/<random>.webp", путь or ""),
            "file": файл,
            "old": (Path(КОРЕНЬ) / "storage/app/public" / СТАРЫЙ).exists(),
            "journal": снимок()["journal"],
        }

    return run


@pytest.mark.parametrize("field", ["logo", "cover"])
@pytest.mark.parametrize(
    "файл",
    [
        ("big.png", картинка(1200, 600)),
        ("small.png", картинка(100, 80, alpha=True)),
        ("photo.jpg", картинка(3000, 2001, "JPEG")),
        ("photo.webp", картинка(700, 700, "WEBP")),
        ("anim.gif", картинка(50, 50, "GIF")),
        ("fake.png", b"not an image at all"),
        ("empty.png", b""),
        None,
    ],
)
def test_картинка(сайт, field, файл):
    поля: dict[str, tuple[str, bytes] | str] = {"note": "x"}

    if файл is not None:
        поля[field] = файл

    тело, тип = multipart(поля)
    итог = отправить(
        сайт,
        f"/cabinet/company/{field}",
        с_картинкой(field),
        снимок_картинки(field),
        uid=учётка("owner@savdex.uz"),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )

    if файл is not None and файл[0] == "big.png":
        assert итог["база"]["file"] == ("WEBP", (512, 256) if field == "logo" else (1200, 600))
        assert not итог["база"]["old"]


@pytest.mark.parametrize("field", ["logo", "cover"])
@pytest.mark.parametrize("admin", [False, True])
def test_убрать_картинку(сайт, field, admin):
    def подготовка() -> None:
        с_картинкой(field)()
        sql("update users set is_admin = %s where email = 'owner@savdex.uz'", [admin])

    итог = отправить(
        сайт,
        f"/cabinet/company/{field}",
        подготовка,
        снимок_картинки(field),
        uid=учётка("owner@savdex.uz"),
        method="DELETE",
        headers=inertia(),
    )

    assert итог["база"]["path"] == "" and not итог["база"]["old"]
