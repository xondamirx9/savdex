"""
Фото объявления на Django: загрузка пачкой (не
больше 10, лишние отсекаются, битые пропускаются, проверка файлов),
удаление и «сделать обложкой» с перенумерацией, чужое — 404,
неподтверждённая почта — на подтверждение.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .factories import компания, объявление
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_company_profile_actions import картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/public"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    # Номера объявлений — свои: папки listings/<номер> на общем диске
    # storage/ не пересекаются с объявлениями других проверок
    sql("select setval('listings_id_seq', 4100000)")

    for slug in ("mine", "other"):
        объявление(company_id=компания(slug=slug), title="Цемент", description="Мешки")

    try:
        with адрес() as root:
            yield root
    finally:
        for slug in ("mine", "other"):
            shutil.rmtree(ДИСК / f"listings/{_объявление(slug)}", ignore_errors=True)


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
        shutil.rmtree(ДИСК / f"listings/{lid}", ignore_errors=True)

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

    папка = ДИСК / f"listings/{_объявление()}"

    return {
        "images": [tuple(norm(v) for v in r) for r in rows],
        "disk": sorted(str(p.relative_to(папка)) for p in папка.rglob("*") if p.is_file()),
        # Файлы и миниатюры, на которые ссылаются строки, — на диске
        "files": all((ДИСК / r[2]).is_file() for r in rows)
        and all((ДИСК / r[3]).is_file() for r in rows if r[3]),
        "sorts": [r[4] for r in rows],
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


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


ДОПУСТИМЫ = "Допустимы JPG, PNG и WebP"


@pytest.mark.parametrize(
    ("файлы", "было", "сообщение", "ошибки", "стало"),
    [
        ([PNG], 0, "Загружено фотографий: 1", None, 1),
        ([PNG, JPG], 3, "Загружено фотографий: 2", None, 5),
        # Битый файл в пачке — проверка ввода не пропускает всю пачку
        ([PNG, BAD], 0, None, {"images.1": [ДОПУСТИМЫ]}, 0),
        ([BAD], 0, None, {"images.0": [ДОПУСТИМЫ]}, 0),
        # Мест два — лишнее отсекается
        ([PNG, JPG, PNG], 8, "Загружено фотографий: 2. Пропущено: 1.", None, 10),
        ([PNG], 10, None, None, 10),
        ([("doc.gif", картинка(10, 10, "GIF"))], 0, None, {"images.0": [ДОПУСТИМЫ]}, 0),
        ([], 0, None, {"images": ["Выберите фотографии"]}, 0),
        # Больше 10 за раз — ошибка проверки ввода (текста для max.array в
        # словаре нет — выводится ключ, как и у Laravel)
        ([PNG] * 11, 0, None, {"images": ["validation.max.array"]}, 0),
    ],
)
def test_загрузка(сайт, файлы, было, сообщение, ошибки, стало):
    тело, тип = multipart_файлы(файлы)
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images",
        фото(было),
        снимок,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )
    данные = сессия(итог)
    база = итог["база"]

    assert итог["ответ"]["status"] == 302
    assert len(база["images"]) == стало
    assert база["sorts"] == list(range(стало))
    assert база["files"]

    if сообщение is not None:
        assert данные["success"] == сообщение
        # Новые — webp со случайным именем и миниатюрой
        новые = база["images"][было:]
        assert all(r[2].endswith("/<random>") and "/thumb/" in r[3] for r in новые)
        assert len(база["disk"]) == было + 2 * (стало - было)
    elif ошибки is not None:
        assert данные["errors"]["default"]["messages"] == ошибки
    else:
        assert данные["error"] == "Больше 10 фотографий к одному объявлению не прикрепить"


@pytest.mark.parametrize("номер", [1, 2, 3, 99])
def test_удалить(сайт, номер):
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images/{номер}",
        фото(3),
        снимок,
        uid=владелец(),
        method="DELETE",
        headers=inertia(),
    )
    база = итог["база"]

    if номер == 99:
        assert итог["ответ"]["status"] == 404
        assert база["disk"] == ["p0.webp", "p1.webp", "p2.webp"]

        return

    # Inertia и DELETE — 303; остальные перенумерованы с нуля, файл — с диска
    assert итог["ответ"]["status"] == 303
    assert сессия(итог)["success"] == "Фотография удалена"
    assert [int(r[0]) for r in база["images"]] == [n for n in (1, 2, 3) if n != номер]
    assert база["sorts"] == [0, 1]
    assert база["disk"] == [f"p{n - 1}.webp" for n in (1, 2, 3) if n != номер]


@pytest.mark.parametrize(
    ("номер", "порядок"), [(1, [0, 1, 2]), (3, [1, 2, 0]), (99, None)]
)
def test_обложка(сайт, номер, порядок):
    итог = отправить(
        сайт,
        f"/cabinet/listings/{_объявление()}/images/{номер}/cover",
        фото(3),
        снимок,
        uid=владелец(),
        headers=inertia(),
    )

    if порядок is None:
        assert итог["ответ"]["status"] == 404
        assert итог["база"]["sorts"] == [0, 1, 2]

        return

    # Обложка — первой (sort 0), остальные за ней по прежнему порядку
    assert итог["ответ"]["status"] == 302
    assert сессия(итог)["success"] == "Фотография стала обложкой"
    assert итог["база"]["sorts"] == порядок


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
    assert итог["ответ"]["headers"]["location"].endswith("/verify-email")
    # Куда вернуться после подтверждения — в сессии
    assert сессия(итог)["url"]["intended"].endswith("/cabinet/settings")
