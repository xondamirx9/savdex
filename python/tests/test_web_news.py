"""
Новости на Django неотличимы от новостей Laravel (этап 3).

Лента и новость: опубликованные и только они (черновик, будущая —
не видны), порядок, рубрики, даты на пяти языках, время чтения,
машинный перевод, соседние новости, 404, обложка.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import laravel, сверить, страница

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

    with laravel() as root:
        yield root


@pytest.mark.parametrize("path", ["/news", "/uz/news", "/en/news", "/zh/news", "/tr/news"])
def test_лента(сайт, path):
    д, _ = сверить(сайт, path)
    slugs = [p["slug"] for p in страница(д["body"])["props"]["posts"]]

    assert "chernovik" not in slugs and "budushchaya" not in slugs
    assert slugs[-1] == "bez-daty", "без даты — в конце"


@pytest.mark.parametrize(
    "path",
    [
        "/news/perevedennaya",
        "/en/news/perevedennaya",
        "/uz/news/perevedennaya",
        "/zh/news/pervaya",
        "/tr/news/svoya-rubrika",
        "/news/s-vremenem",
        "/news/dlinnaya",
        "/news/oblozhka-propala",
        "/en/news/oblozhka-ssylkoj",
        "/news/bez-daty",
    ],
)
def test_новость(сайт, path):
    сверить(сайт, path)


@pytest.mark.parametrize("path", ["/news/chernovik", "/news/budushchaya", "/uz/news/net-takoy"])
def test_не_найдена(сайт, path):
    д, _ = сверить(сайт, path)

    assert д["status"] == 404
