"""
Фото объявления на Django неотличимы от Laravel: загрузка пачкой (не
больше 10, лишние отсекаются, битые пропускаются, проверка файлов),
удаление и «сделать обложкой» с перенумерацией, чужое — 404,
неподтверждённая почта — на подтверждение.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, php, sql, нужна_база, свежая_база
from .test_web_company_profile_actions import картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/public"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "foreach ([$c, $o] as $co) { App\\Models\\Listing::factory()->create(["
        "'company_id' => $co->id, 'title' => 'Цемент', 'description' => 'Мешки']); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def _объявление(slug: str = "mine") -> int:
    return int(
        sql(
            "select l.id from listings l join companies c on c.id = l.company_id where c.slug = %s",
            [slug],
        )[0][0]
    )


def владелец(verified: bool = True) -> int:
    cid = int(sql("select id from companies where slug = 'mine'")[0][0])

    return учётка(
        "owner@savdex.uz",
        company_id=cid,
        email_verified_at="2026-09-01 10:00:00" if verified else None,
    )


def фото(число: int, slug: str = "mine") -> Callable[[], None]:
    """Подготовка: у объявления столько фото, файлы на диске."""

    def run() -> None:
        sql("delete from listing_images")
        sql("select setval('listing_images_id_seq', 1, false)")
        lid = _объявление(slug)

        for i in range(число):
            путь = f"listings/{lid}/p{i}.webp"
            (ДИСК / путь).parent.mkdir(parents=True, exist_ok=True)
            (ДИСК / путь).write_bytes(b"x")
            sql(
                "insert into listing_images (listing_id, path, thumb_path, sort, created_at, "
                "updated_at) values (%s, %s, null, %s, now() - interval '1 day', "
                "now() - interval '1 day')",
                [lid, путь, i],
            )

    return run


def снимок() -> Any:
    rows = sql(
        "select id, listing_id, path, thumb_path, sort, updated_at > now() - interval '1 hour' "
        "from listing_images order by id"
    )

    def norm(v: Any) -> str:
        return re.sub(r"/(thumb/)?[A-Za-z0-9]{40}\.webp$", r"/\1<random>", str(v))

    return {
        "images": [tuple(norm(v) for v in r) for r in rows],
        "disk": sorted(p.name for p in (ДИСК / f"listings/{_объявление()}").glob("p*.webp")),
    }


def multipart_файлы(файлы: list[tuple[str, bytes]], поле: str = "images[]") -> tuple[str, str]:
    import base64

    граница = "----savdexparity"
    части = [
        f'--{граница}\r\nContent-Disposition: form-data; name="{поле}"; filename="{имя}"'
        f"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        + data
        + b"\r\n"
        for имя, data in файлы
    ]
    части.append(f'--{граница}\r\nContent-Disposition: form-data; name="x"\r\n\r\n1\r\n'.encode())
    тело = b"".join(части) + f"--{граница}--\r\n".encode()

    return "base64:" + base64.b64encode(тело).decode(), f"multipart/form-data; boundary={граница}"


PNG = ("a.png", картинка(800, 600))
JPG = ("b.jpg", картинка(2000, 3000, "JPEG"))
BAD = ("bad.png", b"not an image")


@pytest.mark.parametrize(
    ("файлы", "было"),
    [
        ([PNG], 0),
        ([PNG, JPG], 3),
        ([PNG, BAD], 0),
        ([BAD], 0),
        ([PNG, JPG, PNG], 8),
        ([PNG], 10),
        ([("doc.gif", картинка(10, 10, "GIF"))], 0),
        ([], 0),
        ([PNG] * 11, 0),
    ],
)
def test_загрузка(сайт, файлы, было):
    тело, тип = multipart_файлы(файлы)
    отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images",
        фото(было),
        снимок,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )


@pytest.mark.parametrize("номер", [1, 2, 3, 99])
def test_удалить(сайт, номер):
    отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images/{номер}",
        фото(3),
        снимок,
        uid=владелец(),
        method="DELETE",
        headers=inertia(),
    )


@pytest.mark.parametrize("номер", [1, 3, 99])
def test_обложка(сайт, номер):
    отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images/{номер}/cover",
        фото(3),
        снимок,
        uid=владелец(),
        headers=inertia(),
    )


def test_чужое_объявление_404(сайт):
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_объявление('other')}/images/1/cover",
        фото(1, "other"),
        снимок,
        uid=владелец(),
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 404


def test_почта_не_подтверждена(сайт):
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images/1/cover",
        фото(1),
        снимок,
        uid=владелец(verified=False),
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 302
