"""
Мини-сайт на Django неотличим от Laravel: сохранение адреса и
оформления (адрес: строчные, шаблон, занятые и зарезервированные;
оформление — SiteTheme::normalize, фон из формы не принимается),
публикация (черновик — на сайт, прежний фон удаляется, если не нужен),
снятие, фон первого экрана. Без тарифа с мини-сайтом — отказ.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_company_profile_actions import multipart, картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

ФОН = "sites/1/old-hero.webp"
ДИСК = Path(КОРЕНЬ) / "storage/app/public"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "App\\Models\\CompanySite::create(['company_id' => $o->id, 'subdomain' => 'taken',"
        " 'theme' => []]);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


def владелец() -> int:
    cid = int(sql("select id from companies where slug = 'mine'")[0][0])

    return учётка("owner@savdex.uz", company_id=cid)


def сброс(
    *, тариф: bool = True, сайт: str | None = "draft", фон: str | None = None
) -> Callable[[], None]:
    """Тариф Free с мини-сайтом или без; сайт компании (статус, фон черновика)."""

    def run() -> None:
        sql("update plans set has_microsite = %s where code = 'free'", [тариф])
        sql("update companies set status = 'active' where slug = 'mine'")
        sql(
            "delete from company_sites where company_id = "
            "(select id from companies where slug = 'mine')"
        )
        sql("select setval('company_sites_id_seq', (select max(id) from company_sites) + 1, false)")
        (ДИСК / ФОН).parent.mkdir(parents=True, exist_ok=True)
        (ДИСК / ФОН).write_bytes(b"old")

        if сайт is not None:
            тема = (
                '{"template":"bold","primary":"#112233","accent":"#445566","mode":"dark",'
                '"heading_font":"manrope","body_font":"manrope","radius":"round",'
                f'"hero_image":{"null" if фон is None else chr(34) + фон + chr(34)}}}'
            )
            sql(
                "insert into company_sites (company_id, subdomain, status, theme, "
                "published_theme, created_at, updated_at) values ((select id from companies "
                "where slug = 'mine'), 'mine', %s, %s, %s, now() - interval '1 day', "
                "now() - interval '1 day')",
                [сайт, тема, тема],
            )

    return run


def снимок() -> Any:
    rows = sql(
        "select s.subdomain, s.status, s.theme::text, s.published_theme::text, "
        "s.published_at is not null, "
        "s.updated_at > now() - interval '1 hour' from company_sites s join companies c "
        "on c.id = s.company_id where c.slug = 'mine'"
    )

    return {
        "sites": [
            tuple(re.sub(r"sites\\/\d+\\/[A-Za-z0-9]{40}\.webp", "<random>", str(v)) for v in r)
            for r in rows
        ],
        "old_hero": (ДИСК / ФОН).exists(),
    }


ТЕМА = {
    "template": "minimal",
    "primary": "#AABBCC",
    "accent": "#0f0f0f",
    "mode": "light",
    "heading_font": "manrope",
    "body_font": "manrope",
    "radius": "sharp",
    "hero_image": "sites/1/hacked.webp",
    "extra": "x",
}


@pytest.mark.parametrize(
    "body",
    [
        {"subdomain": "cement-trade", "theme": ТЕМА},
        {"subdomain": "mine", "theme": ТЕМА},
        {"subdomain": "Cement", "theme": ТЕМА},
        {"subdomain": "ab", "theme": ТЕМА},
        {"subdomain": "-bad-", "theme": ТЕМА},
        {"subdomain": "admin", "theme": ТЕМА},
        {"subdomain": "taken", "theme": ТЕМА},
        {"subdomain": "cement-trade", "theme": {**ТЕМА, "primary": "red", "mode": "neon"}},
        {"subdomain": "cement-trade"},
        {},
    ],
)
@pytest.mark.parametrize("было", ["есть", "нет", "без тарифа"])
def test_сохранить(сайт, body, было):
    подготовка = {
        "есть": сброс(фон=ФОН),
        "нет": сброс(сайт=None),
        "без тарифа": сброс(тариф=False),
    }[было]
    отправить(
        сайт,
        "/cabinet/site",
        подготовка,
        снимок,
        uid=владелец(),
        body=body,
        method="PATCH",
        headers=inertia(),
    )


@pytest.mark.parametrize("verb", ["publish", "unpublish"])
@pytest.mark.parametrize(
    "подготовка",
    [
        {},
        {"сайт": "published"},
        {"сайт": None},
        {"тариф": False},
        {"фон": ФОН},
    ],
)
def test_публикация(сайт, verb, подготовка):
    def run() -> None:
        сброс(**подготовка)()

        # Опубликован старый фон, в черновике другого нет: после публикации
        # старый не нужен — файл уходит
        if подготовка.get("фон") is None and подготовка.get("сайт", "draft"):
            sql(
                "update company_sites set published_theme = "
                "json_build_object('hero_image', %s::text) where subdomain = 'mine'",
                [ФОН],
            )

    итог = отправить(
        сайт,
        f"/cabinet/site/{verb}",
        run,
        снимок,
        uid=владелец(),
        headers=inertia(),
    )

    if verb == "publish" and not подготовка:
        assert итог["база"]["old_hero"] is False
        assert итог["база"]["sites"][0][1] == "published"


@pytest.mark.parametrize(
    "файл",
    [("hero.png", картинка(2400, 1200)), ("fake.png", b"nope"), None],
)
@pytest.mark.parametrize("было", ["есть", "нет"])
def test_фон(сайт, файл, было):
    поля: dict[str, tuple[str, bytes] | str] = {"note": "x"}

    if файл is not None:
        поля["hero"] = файл

    тело, тип = multipart(поля)
    отправить(
        сайт,
        "/cabinet/site/hero",
        сброс(фон=ФОН) if было == "есть" else сброс(сайт=None),
        снимок,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )


@pytest.mark.parametrize("опубликован", [False, True])
def test_убрать_фон(сайт, опубликован):
    итог = отправить(
        сайт,
        "/cabinet/site/hero",
        сброс(фон=ФОН, сайт="published" if опубликован else "draft"),
        снимок,
        uid=владелец(),
        method="DELETE",
        headers=inertia(),
    )

    # Опубликованный фон остаётся на сайте — файл не трогаем
    assert итог["база"]["old_hero"] is True


# ── Товары ──────────────────────────────────────────────────────────


def товары(число: int = 1, *, тариф: bool = True, фото: bool = True) -> Callable[[], None]:
    """Подготовка: товары компании (первый — с фото на диске)."""

    def run() -> None:
        сброс(тариф=тариф)()
        sql("delete from company_site_products")
        sql("select setval('company_site_products_id_seq', 1, false)")

        for i in range(число):
            sql(
                "insert into company_site_products (company_id, title, price, currency, "
                "image_path, thumb_path, created_at, updated_at) values ((select id from "
                "companies where slug = 'mine'), %s, 100, 'UZS', %s, %s, "
                "now() - interval '1 day', now() - interval '1 day')",
                [
                    f"Цемент {i}",
                    ФОН if фото and i == 0 else None,
                    "sites/1/products/thumb/old.webp" if фото and i == 0 else None,
                ],
            )

    return run


def снимок_товаров() -> Any:
    rows = sql(
        "select id, title, description, price::text, currency, unit, image_path, thumb_path, "
        "sort, updated_at > now() - interval '1 hour' from company_site_products order by id"
    )

    return {
        "products": [
            tuple(
                re.sub(r"products/(thumb/)?[A-Za-z0-9]{40}\.webp$", r"products/\1<random>", str(v))
                for v in r
            )
            for r in rows
        ],
        "old_image": (ДИСК / ФОН).exists(),
    }


ТОВАР = {"title": "Цемент М400", "price": "52000.5", "currency": "UZS", "unit": "мешок"}


@pytest.mark.parametrize(
    "поля",
    [
        ТОВАР,
        {**ТОВАР, "image": ("photo.jpg", картинка(2400, 1800, "JPEG"))},
        {**ТОВАР, "image": ("fake.png", b"nope")},
        {**ТОВАР, "price": "abc", "currency": "BTC"},
        {**ТОВАР, "title": ""},
        {**ТОВАР, "price": "-1"},
        {"title": "Ц"},
    ],
)
@pytest.mark.parametrize("было", [1, 60, "без тарифа"])
def test_добавить_товар(сайт, поля, было):
    подготовка = товары(1, тариф=False) if было == "без тарифа" else товары(int(было))
    тело, тип = multipart(dict(поля))
    отправить(
        сайт,
        "/cabinet/site/products",
        подготовка,
        снимок_товаров,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )


@pytest.mark.parametrize(
    "поля",
    [
        {"title": "Цемент 0", "price": "100", "currency": "UZS"},
        {"title": "Цемент 0", "price": "100.00", "currency": "UZS"},
        {**ТОВАР, "description": "Мешки по 50 кг"},
        {**ТОВАР, "image": ("photo.png", картинка(300, 200))},
        {**ТОВАР, "title": ""},
    ],
)
@pytest.mark.parametrize("номер", [1, 999])
def test_изменить_товар(сайт, поля, номер):
    тело, тип = multipart(dict(поля))
    отправить(
        сайт,
        f"/cabinet/site/products/{номер}",
        товары(1),
        снимок_товаров,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )


@pytest.mark.parametrize(("номер", "тариф"), [(1, True), (1, False), (999, True)])
def test_удалить_товар(сайт, номер, тариф):
    итог = отправить(
        сайт,
        f"/cabinet/site/products/{номер}",
        товары(1, тариф=тариф),
        снимок_товаров,
        uid=владелец(),
        method="DELETE",
        headers=inertia(),
    )

    if номер == 1:
        assert not итог["база"]["products"] and not итог["база"]["old_image"]
