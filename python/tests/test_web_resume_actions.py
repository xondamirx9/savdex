"""
Своё резюме на Django неотличимо от Laravel: опубликовать (дата — если
не было, заблокированное — ошибка поля status), скрыть (только
опубликованное), удалить (мягко, фото — с диска, DELETE от Inertia —
303). Без резюме — 404.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

ФОТО = "resumes/parity.webp"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def соискатель() -> int:
    return учётка("seeker@savdex.uz")


def резюме(status: str | None, *, опубликовано: bool = True) -> Callable[[], None]:
    def run() -> None:
        sql("delete from resumes")

        if status is None:
            return

        sql(
            "insert into resumes (user_id, title, status, photo_path, published_at, created_at, "
            "updated_at) values (%s, 'Прораб', %s, %s, %s, now() - interval '1 day', "
            "now() - interval '1 day')",
            [
                соискатель(),
                status,
                ФОТО,
                "2026-09-01 10:00:00" if опубликовано else None,
            ],
        )
        путь = Path(КОРЕНЬ) / "storage/app/public" / ФОТО
        путь.parent.mkdir(parents=True, exist_ok=True)
        путь.write_bytes(b"webp")

    return run


def снимок() -> Any:
    return {
        "resumes": sql(
            "select status, published_at::text, published_at > now() - interval '1 hour', "
            "deleted_at is not null, updated_at > now() - interval '1 hour' from resumes"
        ),
        "photo": (Path(КОРЕНЬ) / "storage/app/public" / ФОТО).exists(),
    }


@pytest.mark.parametrize("verb", ["publish", "hide"])
@pytest.mark.parametrize(
    ("status", "опубликовано"),
    [
        ("draft", False),
        ("published", True),
        ("hidden", True),
        ("hidden", False),
        ("blocked", True),
        (None, False),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_опубликовать_и_скрыть(сайт, verb, status, опубликовано, prefix):
    отправить(
        сайт,
        f"{prefix}/cabinet/resume/{verb}",
        резюме(status, опубликовано=опубликовано),
        снимок,
        uid=соискатель(),
        headers=inertia(),
    )


@pytest.mark.parametrize("status", ["published", None])
def test_удалить(сайт, status):
    итог = отправить(
        сайт,
        "/cabinet/resume",
        резюме(status),
        снимок,
        uid=соискатель(),
        method="DELETE",
        headers=inertia(),
    )

    if status is not None:
        assert итог["ответ"]["status"] == 303
        assert итог["база"]["resumes"][0][3] is True and not итог["база"]["photo"]
