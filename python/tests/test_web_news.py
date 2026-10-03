"""
Новости на Django (этап 3).

Лента и новость: опубликованные и только они (черновик, будущая —
не видны), порядок, рубрики, даты на пяти языках, время чтения,
машинный перевод, соседние новости, 404, обложка.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть, страница

pytestmark = нужна_база


def _новость(slug: str, **поля: object) -> None:
    data = {
        "slug": slug,
        "category": "Полезное",
        "title": f"Заголовок {slug}",
        "excerpt": f"Кратко о {slug}",
        "body": f"Первый абзац {slug}.\n\nВторой абзац — подробнее.",
        "is_published": True,
        "published_at": "2026-08-15 10:00:00",
        "sort": 0,
        **поля,
    }
    columns = ", ".join(data)
    marks = ", ".join(["%s"] * len(data))
    sql(
        f"insert into news_posts ({columns}, created_at, updated_at) "
        f"values ({marks}, now(), now())",
        [json.dumps(v) if isinstance(v, dict) else v for v in data.values()],
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    _новость("pervaya", published_at="2026-01-05 09:00:00", category="Обновления сервиса")
    _новость(
        "perevedennaya",
        published_at="2026-09-01 08:00:00",
        category="Тарифы и оплата",
        title_i18n={"uz": "Tariflar yangilandi", "en": "Pricing updated"},
        excerpt_i18n={"en": "  "},
        body_i18n={"en": "First.\r\n\r\nSecond."},
    )
    _новость("s-vremenem", read_time="7 мин", sort=5, published_at="2026-09-01 08:00:00")
    _новость("bez-daty", published_at=None, category="Аналитика рынка")
    _новость("svoya-rubrika", category="Неизвестная рубрика", published_at="2026-03-31 23:30:00")
    _новость("oblozhka-propala", image_path="news/net-takogo.webp")
    _новость("oblozhka-ssylkoj", image_path="https://cdn.example.com/x.jpg")
    _новость("dlinnaya", body=" ".join(["слово"] * 900) + "\n\nhello-world it's done")
    _новость("chernovik", is_published=False)
    _новость("budushchaya", published_at="2099-01-01 00:00:00")

    with адрес() as root:
        yield root


def новости(сайт: str, path: str) -> dict[str, Any]:
    д = открыть(сайт, path)

    assert д["status"] == 200, д["status"]

    return страница(д["body"])


@pytest.mark.parametrize(
    ("path", "дата", "время", "рубрика", "заголовок"),
    [
        ("/news", "1 сентября 2026", "1 мин", "Тарифы и оплата", "Заголовок perevedennaya"),
        ("/uz/news", "1 sentabr 2026", "1 daq.", "Tariflar va to‘lov", "Tariflar yangilandi"),
        ("/en/news", "1 September 2026", "1 min", "Plans and payment", "Pricing updated"),
        ("/zh/news", "1 九月 2026", "1 分钟", "资费与支付", "Заголовок perevedennaya"),
        ("/tr/news", "1 Eylül 2026", "1 dk", "Tarifeler ve ödeme", "Заголовок perevedennaya"),
    ],
)
def test_лента(сайт, path, дата, время, рубрика, заголовок):
    стр = новости(сайт, path)
    posts = {p["slug"]: p for p in стр["props"]["posts"]}
    slugs = list(posts)

    assert стр["component"] == "news/Index"
    assert "chernovik" not in slugs and "budushchaya" not in slugs
    assert len(slugs) == 8
    # Свежие сверху, при одной дате — по sort; без даты — в конце
    assert slugs[:2] == ["s-vremenem", "perevedennaya"]
    assert slugs[-2:] == ["pervaya", "bez-daty"], "без даты — в конце"
    # Дата, время чтения, рубрика и заголовок — на языке страницы
    свежая = posts["perevedennaya"]
    assert (свежая["date"], свежая["read"], свежая["category_label"], свежая["title"]) == (
        дата,
        время,
        рубрика,
        заголовок,
    )
    # Своё время чтения — как записано
    assert posts["s-vremenem"]["read"] == "7 мин"
    # Обложка: ссылка — как есть, пропавший файл — без обложки
    assert posts["oblozhka-ssylkoj"]["image"] == "https://cdn.example.com/x.jpg"
    assert posts["oblozhka-propala"]["image"] is None


@pytest.mark.parametrize(
    ("path", "поля"),
    [
        (
            "/news/perevedennaya",
            {"title": "Заголовок perevedennaya", "date": "1 сентября 2026", "read": "1 мин"},
        ),
        # Машинный перевод; пустой перевод краткого — русский текст
        (
            "/en/news/perevedennaya",
            {
                "title": "Pricing updated",
                "excerpt": "Кратко о perevedennaya",
                "body": ["First.", "Second."],
                "category_label": "Plans and payment",
            },
        ),
        (
            "/uz/news/perevedennaya",
            {
                "title": "Tariflar yangilandi",
                "body": ["Первый абзац perevedennaya.", "Второй абзац — подробнее."],
            },
        ),
        ("/zh/news/pervaya", {"date": "5 一月 2026", "category_label": "服务更新"}),
        # Неизвестная рубрика — как записана; 23:30 31 марта — ещё 31-е
        (
            "/tr/news/svoya-rubrika",
            {"category_label": "Неизвестная рубрика", "date": "31 Mart 2026"},
        ),
        ("/news/s-vremenem", {"read": "7 мин", "sort": 5}),
        # 900 слов — шесть минут; абзацы — по пустой строке
        ("/news/dlinnaya", {"read": "6 мин"}),
        ("/news/oblozhka-propala", {"image": None}),
        ("/en/news/oblozhka-ssylkoj", {"image": "https://cdn.example.com/x.jpg"}),
        ("/news/bez-daty", {"date": "", "category_label": "Аналитика рынка"}),
    ],
)
def test_новость(сайт, path, поля):
    стр = новости(сайт, path)
    новость = стр["props"]["post"]
    slug = path.rsplit("/", 1)[1]

    assert стр["component"] == "news/Show"
    assert новость["slug"] == slug
    assert {k: новость[k] for k in поля} == поля
    # Соседние — три другие опубликованные
    соседние = [p["slug"] for p in стр["props"]["related"]]
    assert len(соседние) == 3 and slug not in соседние
    assert not {"chernovik", "budushchaya"} & set(соседние)

    if slug == "dlinnaya":
        assert новость["body"] == [" ".join(["слово"] * 900), "hello-world it's done"]


@pytest.mark.parametrize("path", ["/news/chernovik", "/news/budushchaya", "/uz/news/net-takoy"])
def test_не_найдена(сайт, path):
    assert открыть(сайт, path)["status"] == 404
