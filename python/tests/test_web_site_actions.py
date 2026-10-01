"""
Мини-сайт — проверки Django: сохранение адреса и
оформления (адрес: строчные, шаблон, занятые и зарезервированные;
оформление — SiteTheme::normalize, фон из формы не принимается),
публикация (черновик — на сайт, прежний фон удаляется, если не нужен),
снятие, фон первого экрана. Без тарифа с мини-сайтом — отказ.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .factories import компания
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_company_profile_actions import multipart, картинка
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ФОН = "sites/1/old-hero.webp"
ДИСК = Path(КОРЕНЬ) / "storage/app/public"


def тарифы() -> None:
    """PlanSeeder: тарифы из снимка справочников (savdex/bootstrap/seeds.json)."""
    from savdex.seeds import DATA

    for plan in json.loads(DATA.read_text(encoding="utf-8"))["plans"]:
        sql(
            f"insert into plans ({', '.join(plan)}, created_at, updated_at) "
            f"values ({', '.join(['%s'] * len(plan))}, now(), now())",
            list(plan.values()),
        )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    тарифы()
    компания(slug="mine")
    other = компания(slug="other")
    # Адрес «taken» занят сайтом другой компании
    sql(
        "insert into company_sites (company_id, subdomain, theme, created_at, updated_at) "
        "values (%s, 'taken', '[]', now(), now())",
        [other],
    )

    with адрес() as root:
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


ПРАВИЛО = "Адрес: латиница, цифры и дефис, от 3 до 40 знаков, без дефиса в начале и в конце"
БЕЗ_ТАРИФА = "Мини-сайт доступен на тарифах Business, Premium и VIP"
ТЕМА_ОБЯЗАТЕЛЬНА = {
    f"theme{k}": ["validation.required"]
    for k in (
        "",
        ".template",
        ".primary",
        ".accent",
        ".mode",
        ".heading_font",
        ".body_font",
        ".radius",
    )
}
#: Тема черновика из сброс(): «bold», тёмная
ЖИРНАЯ = {
    "template": "bold",
    "primary": "#112233",
    "accent": "#445566",
    "mode": "dark",
    "heading_font": "manrope",
    "body_font": "manrope",
    "radius": "round",
}


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Строка сессии после ответа — разобранным JSON."""
    return dict(json.loads(итог["сессия"]["payload"]))


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]] | None:
    """Ошибки проверки, которые форма увидит после перехода назад."""
    errors = сессия(итог).get("errors")

    return None if errors is None else dict(errors["default"]["messages"])


def сайты(итог: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Сайт компании: адрес, статус, черновик и опубликованная тема (JSON), отметки."""
    return [
        (
            sub,
            status,
            json.loads(theme),
            None if published == "None" else json.loads(published),
            at == "True",
            fresh == "True",
        )
        for sub, status, theme, published, at, fresh in итог["база"]["sites"]
    ]


def назад(сайт: str, итог: dict[str, Any], status: int = 302) -> None:
    assert итог["ответ"]["status"] == status
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"


@pytest.mark.parametrize(
    ("body", "ошибки_"),
    [
        ({"subdomain": "cement-trade", "theme": ТЕМА}, None),
        ({"subdomain": "mine", "theme": ТЕМА}, None),
        # Адрес: строчные, шаблон, зарезервированные и занятые
        ({"subdomain": "Cement", "theme": ТЕМА}, {"subdomain": ["validation.lowercase", ПРАВИЛО]}),
        ({"subdomain": "ab", "theme": ТЕМА}, {"subdomain": [ПРАВИЛО]}),
        ({"subdomain": "-bad-", "theme": ТЕМА}, {"subdomain": [ПРАВИЛО]}),
        (
            {"subdomain": "admin", "theme": ТЕМА},
            {"subdomain": ["Этот адрес зарезервирован площадкой — выберите другой"]},
        ),
        ({"subdomain": "taken", "theme": ТЕМА}, {"subdomain": ["Этот адрес уже занят"]}),
        (
            {"subdomain": "cement-trade", "theme": {**ТЕМА, "primary": "red", "mode": "neon"}},
            {"theme.primary": ["validation.regex"], "theme.mode": ["validation.in"]},
        ),
        ({"subdomain": "cement-trade"}, ТЕМА_ОБЯЗАТЕЛЬНА),
        ({}, {"subdomain": ["validation.required"], **ТЕМА_ОБЯЗАТЕЛЬНА}),
    ],
)
@pytest.mark.parametrize("было", ["есть", "нет", "без тарифа"])
def test_сохранить(сайт, body, ошибки_, было):
    подготовка = {
        "есть": сброс(фон=ФОН),
        "нет": сброс(сайт=None),
        "без тарифа": сброс(тариф=False),
    }[было]
    итог = отправить(
        сайт,
        "/cabinet/site",
        подготовка,
        снимок,
        uid=владелец(),
        body=body,
        method="PATCH",
        headers=inertia(),
    )

    # PATCH от Inertia — 303 назад
    назад(сайт, итог, 303)
    фон = ФОН if было == "есть" else None
    прежний = {
        "есть": [
            (
                "mine",
                "draft",
                {**ЖИРНАЯ, "hero_image": ФОН},
                {**ЖИРНАЯ, "hero_image": ФОН},
                False,
                False,
            )
        ],
        "нет": [],
        "без тарифа": [
            (
                "mine",
                "draft",
                {**ЖИРНАЯ, "hero_image": None},
                {**ЖИРНАЯ, "hero_image": None},
                False,
                False,
            )
        ],
    }[было]

    if было == "без тарифа":
        assert сессия(итог)["error"] == БЕЗ_ТАРИФА and сайты(итог) == прежний
    elif ошибки_ is not None:
        assert ошибки(итог) == ошибки_ and сайты(итог) == прежний
    else:
        # Оформление нормализовано (цвет — строчными, лишнее отброшено),
        # фон из формы не принимается — остаётся фон черновика
        assert сессия(итог)["success"] == "Черновик сохранён"
        тема = {**ТЕМА, "primary": "#aabbcc", "hero_image": фон}
        del тема["extra"]
        опубликована = прежний[0][3] if прежний else None
        assert сайты(итог) == [(body["subdomain"], "draft", тема, опубликована, False, True)]

    assert итог["база"]["old_hero"] is True


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
    назад(сайт, итог)
    черновик = {**ЖИРНАЯ, "hero_image": подготовка.get("фон")}
    было = {"hero_image": ФОН} if подготовка.get("фон") is None else черновик

    if подготовка.get("сайт", "draft") is None:
        # Сайта нет: опубликовать нечего, снимать — тоже
        if verb == "publish":
            assert сессия(итог)["error"] == "Сначала сохраните черновик"
        else:
            assert сессия(итог)["success"] == "Сайт снят с публикации"
        assert сайты(итог) == []
    elif verb == "publish" and подготовка.get("тариф") is False:
        assert сессия(итог)["error"] == БЕЗ_ТАРИФА
        assert сайты(итог) == [("mine", "draft", черновик, было, False, False)]
    elif verb == "publish":
        # Черновик — на сайт; прежний фон удаляется, если больше не нужен
        assert сессия(итог)["success"] == "Сайт опубликован"
        assert сайты(итог) == [("mine", "published", черновик, черновик, True, True)]
    else:
        assert сессия(итог)["success"] == "Сайт снят с публикации"
        assert сайты(итог) == [
            ("mine", "draft", черновик, было, False, подготовка.get("сайт") == "published")
        ]

    assert итог["база"]["old_hero"] is not (
        verb == "publish" and подготовка in ({}, {"сайт": "published"})
    )


@pytest.mark.parametrize(
    ("файл", "ошибка"),
    [
        (("hero.png", картинка(2400, 1200)), None),
        (("fake.png", b"nope"), "Допустимы JPG, PNG и WebP"),
        (None, "Выберите файл"),
    ],
)
@pytest.mark.parametrize("было", ["есть", "нет"])
def test_фон(сайт, файл, ошибка, было):
    поля: dict[str, tuple[str, bytes] | str] = {"note": "x"}

    if файл is not None:
        поля["hero"] = файл

    тело, тип = multipart(поля)
    итог = отправить(
        сайт,
        "/cabinet/site/hero",
        сброс(фон=ФОН) if было == "есть" else сброс(сайт=None),
        снимок,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )
    назад(сайт, итог)
    тема = {**ЖИРНАЯ, "hero_image": ФОН}

    if было == "нет":
        assert сессия(итог)["error"] == "Сначала сохраните черновик" and сайты(итог) == []
    elif ошибка is not None:
        assert ошибки(итог) == {"hero": [ошибка]}
        assert сайты(итог) == [("mine", "draft", тема, тема, False, False)]
    else:
        # Новый фон — в черновик под случайным именем; опубликованный не тронут
        assert сессия(итог)["success"] == (
            "Фон загружен — опубликуйте сайт, чтобы его увидели посетители"
        )
        assert сайты(итог) == [
            ("mine", "draft", {**ЖИРНАЯ, "hero_image": "<random>"}, тема, False, True)
        ]

    assert итог["база"]["old_hero"] is True


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

    назад(сайт, итог, 303)
    assert сессия(итог)["success"] == "Фон убран"
    тема = {**ЖИРНАЯ, "hero_image": ФОН}
    assert сайты(итог) == [
        (
            "mine",
            "published" if опубликован else "draft",
            {**ЖИРНАЯ, "hero_image": None},
            тема,
            False,
            True,
        )
    ]
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
ПРЕЖНИЙ = (
    "1",
    "Цемент 0",
    "None",
    "100.00",
    "UZS",
    "None",
    ФОН,
    "sites/1/products/thumb/old.webp",
    "0",
    "False",
)
НОВЫЙ = ("Цемент М400", "None", "52000.50", "UZS", "мешок")
НОВОЕ_ФОТО = ("sites/1/products/<random>", "sites/1/products/thumb/<random>")


@pytest.mark.parametrize(
    ("поля", "ошибки_"),
    [
        (ТОВАР, None),
        ({**ТОВАР, "image": ("photo.jpg", картинка(2400, 1800, "JPEG"))}, None),
        ({**ТОВАР, "image": ("fake.png", b"nope")}, {"image": ["Допустимы JPG, PNG и WebP"]}),
        (
            {**ТОВАР, "price": "abc", "currency": "BTC"},
            {"price": ["validation.numeric"], "currency": ["validation.in"]},
        ),
        ({**ТОВАР, "title": ""}, {"title": ["Укажите название товара"]}),
        ({**ТОВАР, "price": "-1"}, {"price": ["validation.min.numeric"]}),
        (
            {"title": "Ц"},
            {"title": ["validation.min.string"], "currency": ["validation.required"]},
        ),
    ],
)
@pytest.mark.parametrize("было", [1, 60, "без тарифа"])
def test_добавить_товар(сайт, поля, ошибки_, было):
    подготовка = товары(1, тариф=False) if было == "без тарифа" else товары(int(было))
    тело, тип = multipart(dict(поля))
    итог = отправить(
        сайт,
        "/cabinet/site/products",
        подготовка,
        снимок_товаров,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )
    назад(сайт, итог)
    products = итог["база"]["products"]
    сколько = 1 if было == "без тарифа" else int(было)

    if было == "без тарифа":
        assert сессия(итог)["error"] == БЕЗ_ТАРИФА
    elif было == 60:
        assert сессия(итог)["error"] == "На сайте не больше 60 своих товаров"
    elif ошибки_ is not None:
        assert ошибки(итог) == ошибки_
    else:
        assert сессия(итог)["success"] == "Товар сохранён"
        фото = НОВОЕ_ФОТО if "image" in поля else ("None", "None")
        assert products[-1] == ("2", *НОВЫЙ, *фото, "0", "True")
        сколько += 1

    assert len(products) == сколько and products[0] == ПРЕЖНИЙ
    assert итог["база"]["old_image"] is True


@pytest.mark.parametrize(
    ("поля", "стало"),
    [
        # Ничего не изменилось — запись не трогается (100 и 100.00 — одно)
        ({"title": "Цемент 0", "price": "100", "currency": "UZS"}, ПРЕЖНИЙ),
        ({"title": "Цемент 0", "price": "100.00", "currency": "UZS"}, ПРЕЖНИЙ),
        (
            {**ТОВАР, "description": "Мешки по 50 кг"},
            (
                "1",
                "Цемент М400",
                "Мешки по 50 кг",
                "52000.50",
                "UZS",
                "мешок",
                *ПРЕЖНИЙ[6:9],
                "True",
            ),
        ),
        # Новое фото — прежнее уходит с диска
        (
            {**ТОВАР, "image": ("photo.png", картинка(300, 200))},
            ("1", *НОВЫЙ, *НОВОЕ_ФОТО, "0", "True"),
        ),
        ({**ТОВАР, "title": ""}, None),
    ],
)
@pytest.mark.parametrize("номер", [1, 999])
def test_изменить_товар(сайт, поля, стало, номер):
    тело, тип = multipart(dict(поля))
    итог = отправить(
        сайт,
        f"/cabinet/site/products/{номер}",
        товары(1),
        снимок_товаров,
        uid=владелец(),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )
    products = итог["база"]["products"]

    if номер == 999:
        assert итог["ответ"]["status"] == 404 and products == [ПРЕЖНИЙ]
        return

    назад(сайт, итог)

    if стало is None:
        assert ошибки(итог) == {"title": ["Укажите название товара"]}
        assert products == [ПРЕЖНИЙ]
    else:
        assert сессия(итог)["success"] == "Товар сохранён"
        assert products == [стало]

    assert итог["база"]["old_image"] is ("image" not in поля)


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
        # Свой товар удаляется и без тарифа — вместе с фото
        назад(сайт, итог, 303)
        assert сессия(итог)["success"] == "Товар удалён"
        assert not итог["база"]["products"] and not итог["база"]["old_image"]
    else:
        assert итог["ответ"]["status"] == 404
        assert итог["база"]["products"] == [ПРЕЖНИЙ] and итог["база"]["old_image"]
