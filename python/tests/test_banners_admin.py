"""
Раздел «Баннеры» админки на Django — сквозь настоящую базу и страницы
сайта.

Проверяется то, ради чего раздел устроен именно так:

- картинка пересобирается в WebP по рамке макета и ложится на
  публичный диск, а витрина сайта (главная, каталог) её видит;
- прежние файлы удаляются при замене, снятии и удалении — и у
  языковых картинок тоже;
- время в форме — ташкентское, в базу ложится UTC;
- предпросмотр получает всё, что ему нужно.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from PIL import Image

from .pg_admin import (
    КОРЕНЬ,
    django,
    sql,
    журнал,
    нужна_база,
    свежая_база,
    сотрудник,
    файл,
)
from .web_site import адрес, открыть, страница

pytestmark = нужна_база

LIST = "/py/admin/site/banner/"
ADD = "/py/admin/site/banner/add/"
PUBLIC = КОРЕНЬ / "storage/app/public"


def _png(size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (30, 90, 200)).save(out, "PNG")

    return out.getvalue()


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "content_manager", "sales")}


@pytest.fixture(scope="module")
def сайт(люди) -> Iterator[str]:
    with адрес() as root:
        yield root


def баннер_на_сайте(сайт: str, path: str) -> dict[str, Any] | None:
    """Баннер, который показывает страница сайта (главная или каталог)."""
    д = открыть(сайт, path)
    assert д["status"] == 200, д["status"]

    return страница(д["body"])["props"]["banner"]


@pytest.fixture(autouse=True)
def картинки():
    """Файлы, которые тест положил на публичный диск, — убрать после."""
    before = set(PUBLIC.glob("banners/*"))

    yield

    for path in set(PUBLIC.glob("banners/*")) - before:
        path.unlink()


def _форма(**поля: Any) -> dict[str, Any]:
    data = {
        "name": "Осенняя акция",
        "placement": "home",
        "url": "",
        "alt": "Скидка 30% на годовой тариф",
        "starts_at": "",
        "ends_at": "",
        "sort": "0",
        "is_active": "on",
        "is_dismissible": "on",
        "focal_x": "50",
        "focal_y": "50",
        "images-TOTAL_FORMS": "0",
        "images-INITIAL_FORMS": "0",
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "5",
    }
    data.update({k: v for k, v in поля.items() if v is not None})

    return data


def _row(name: str) -> dict[str, Any]:
    [row] = sql(
        "select id, image_path, image_mobile_path, starts_at::text, ends_at::text "
        "from banners where name = %s",
        [name],
    )

    return dict(zip(("id", "image", "mobile", "starts", "ends"), row, strict=True))


def _создать(люди: dict[str, int], name: str, **поля: Any) -> dict[str, Any]:
    _, ответ = django(
        люди["content_manager"],
        ("post", ADD, _форма(name=name, image_upload=файл("wide.png", _png((3000, 1000))), **поля)),
    )
    assert ответ["status"] == 302, ответ["body"][:3000]

    return _row(name)


def test_заведение_картинка_и_время(люди):
    banner = _создать(
        люди,
        "Осенняя акция",
        starts_at="2026-10-01T09:00",
        ends_at="2026-10-07T23:59",
    )

    # Пересобрана в WebP и вписана в рамку 2400×1200
    assert banner["image"].startswith("banners/") and banner["image"].endswith(".webp")
    with Image.open(PUBLIC / banner["image"]) as picture:
        assert (picture.format, picture.size) == ("WEBP", (2400, 800))

    # 09:00 в Ташкенте — 04:00 UTC
    assert banner["starts"] == "2026-10-01 04:00:00"
    assert banner["ends"] == "2026-10-07 18:59:00"

    запись = журнал("created")
    assert запись["section"] == "content"
    assert запись["subject_type"] == "App\\Models\\Banner"
    assert запись["subject_label"] == "Осенняя акция"


def test_витрина_видит_баннер(люди, сайт):
    banner = _создать(люди, "Идёт сейчас", placement="catalog")
    витрина = баннер_на_сайте(сайт, "/catalog")

    assert витрина is not None
    assert витрина["key"] == f"banner-{banner['id']}"
    assert витрина["image"] == f"{сайт}/storage/{banner['image']}"
    assert витрина["alt"] == "Скидка 30% на годовой тариф"


@pytest.mark.parametrize(
    ("поля", "ошибка"),
    [
        ({"alt": ""}, "Обязательное поле."),
        (
            {"starts_at": "2026-10-07T10:00", "ends_at": "2026-10-01T10:00"},
            "Конец должен быть позже начала.",
        ),
        ({"focal_x": "140"}, "От 0 до 100."),
        ({"url": "не ссылка"}, "Введите правильный URL."),
    ],
)
def test_проверки_формы(люди, поля, ошибка):
    _, ответ = django(
        люди["content_manager"],
        (
            "post",
            ADD,
            _форма(name="Ошибочный", image_upload=файл("w.png", _png((800, 300))), **поля),
        ),
    )

    assert ответ["status"] == 200
    assert ошибка in ответ["body"]
    assert sql("select count(*) from banners where name = 'Ошибочный'") == [(0,)]


def test_без_картинки_и_с_не_картинкой_не_заводится(люди):
    _, пустой, мусор = django(
        люди["content_manager"],
        ("post", ADD, _форма(name="Без картинки")),
        ("post", ADD, _форма(name="Без картинки", image_upload=файл("x.png", b"<?php ?>"))),
    )

    assert "Нужна картинка для компьютера." in пустой["body"]
    assert "Файл не является изображением." in мусор["body"]
    assert sql("select count(*) from banners where name = 'Без картинки'") == [(0,)]


def test_замена_и_снятие_убирают_прежние_файлы(люди):
    banner = _создать(люди, "Меняется", image_mobile_upload=файл("narrow.png", _png((900, 1200))))
    old_wide, old_narrow = banner["image"], banner["mobile"]
    assert (PUBLIC / old_narrow).exists()

    _, замена = django(
        люди["content_manager"],
        (
            "post",
            f"{LIST}{banner['id']}/change/",
            _форма(
                name="Меняется",
                image_upload=файл("new.png", _png((2000, 700))),
                image_mobile_clear="on",
            ),
        ),
    )

    assert замена["status"] == 302, замена["body"][:3000]
    after = _row("Меняется")
    assert after["image"] != old_wide and (PUBLIC / after["image"]).exists()
    assert after["mobile"] is None
    assert not (PUBLIC / old_wide).exists(), "прежняя широкая картинка осталась на диске"
    assert not (PUBLIC / old_narrow).exists(), "снятая узкая картинка осталась на диске"


def test_картинки_под_языки_и_удаление(люди, сайт):
    banner = _создать(люди, "Многоязычный")
    pk = banner["id"]

    _, добавлена = django(
        люди["content_manager"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма(
                name="Многоязычный",
                **{
                    "images-TOTAL_FORMS": "1",
                    "images-0-locale": "zh",
                    "images-0-image_upload": файл("zh.png", _png((2400, 800))),
                },
            ),
        ),
    )
    assert добавлена["status"] == 302, добавлена["body"][:3000]

    [(image_id, zh_path)] = sql(
        "select id, image_path from banner_images where banner_id = %s and locale = 'zh'", [pk]
    )
    assert (PUBLIC / zh_path).exists()
    # Главная по-китайски — своя картинка языка, на прочих языках — основная
    витрина = баннер_на_сайте(сайт, "/zh")
    assert витрина is not None and витрина["key"] == f"banner-{pk}"
    assert витрина["image"] == f"{сайт}/storage/{zh_path}"
    assert баннер_на_сайте(сайт, "/")["image"] == f"{сайт}/storage/{banner['image']}"

    # Предпросмотр знает про язык и про основную картинку
    _, форма = django(люди["content_manager"], ("get", f"{LIST}{pk}/change/", None))
    data = json.loads(
        re.search(
            r'id="banner-preview-data" type="application/json">(.*?)</script>', форма["body"]
        ).group(1)
    )
    assert data["image"] == f"/storage/{banner['image']}"
    assert data["languages"]["zh"]["image"] == f"/storage/{zh_path}"
    assert "savdex/banner-preview.js" in форма["body"]

    # Убранный язык уносит свой файл
    _, убран = django(
        люди["content_manager"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма(
                name="Многоязычный",
                **{
                    "images-TOTAL_FORMS": "1",
                    "images-INITIAL_FORMS": "1",
                    "images-0-id": str(image_id),
                    "images-0-banner": str(pk),
                    "images-0-locale": "zh",
                    "images-0-DELETE": "on",
                },
            ),
        ),
    )
    assert убран["status"] == 302, убран["body"][:3000]
    assert sql("select count(*) from banner_images where banner_id = %s", [pk]) == [(0,)]
    assert not (PUBLIC / zh_path).exists()


def test_удаление_баннера_убирает_все_файлы(люди):
    banner = _создать(люди, "Снимается", image_mobile_upload=файл("n.png", _png((900, 1200))))
    pk = banner["id"]
    django(
        люди["content_manager"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма(
                name="Снимается",
                **{
                    "images-TOTAL_FORMS": "1",
                    "images-0-locale": "uz",
                    "images-0-image_upload": файл("uz.png", _png((2400, 800))),
                },
            ),
        ),
    )
    [(uz_path,)] = sql("select image_path from banner_images where banner_id = %s", [pk])
    files = [banner["image"], banner["mobile"], uz_path]

    _, удалён = django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))

    assert удалён["status"] == 302
    assert sql("select count(*) from banners where id = %s", [pk]) == [(0,)]
    assert [f for f in files if (PUBLIC / f).exists()] == []
    assert журнал("deleted")["subject_label"] == "Снимается"


def test_список_и_права(люди):
    _создать(люди, "В списке", ends_at="2099-01-01T00:00")

    _, список, живые = django(
        люди["content_manager"],
        ("get", LIST, None),
        ("get", f"{LIST}?live=yes", None),
    )
    assert "В списке" in список["body"] and "Главная страница" in список["body"]
    assert "осталось" in список["body"]
    assert "одна на все" in список["body"]
    assert "В списке" in живые["body"]

    _, чужой = django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403
