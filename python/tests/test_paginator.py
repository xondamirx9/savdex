"""
Постраничный вывод — копия LengthAwarePaginator (toArray) у Laravel.

Окно номеров с «...» (UrlWindow) появляется только от 14 страниц —
в тестах страниц сайта столько данных нет, поэтому окно проверяется
здесь, на самом построителе: по три номера вокруг текущей, первые и
последние два, «...» между ними. Ожидания — правила UrlWindow
(onEachSide = 3): до 14 страниц — все номера; текущая до 7-й — первые
десять; ближе семи к концу — последние десять; иначе — окно ±3.
"""

from __future__ import annotations

import pytest

from savdex.web import paginator

PATH = "http://savdex.test/uz/resumes"
ЗАПРОС = "page=3&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82&a%5B%5D=1&a%5B%5D=2&b=~"


def построить(total: int, current: int, query: str = "", locale: str = "ru") -> dict:
    начало = (current - 1) * 20
    items = list(range(начало, min(начало + 20, total)))

    return paginator.build(PATH, query, locale, paginator.Page(items, total, 20, current))


def номера(страницы: dict) -> list[str]:
    """Подписи окна номеров — без «назад» и «вперёд»."""
    return [link["label"] for link in страницы["links"][1:-1]]


def по(начало: int, конец: int) -> list[str]:
    return [str(n) for n in range(начало, конец + 1)]


@pytest.mark.parametrize(
    ("total", "current", "окно"),
    [
        (0, 1, ["1"]),
        (1, 1, ["1"]),
        (20, 1, ["1"]),
        (21, 2, ["1", "2"]),
        # 13 страниц — все номера, без «...»
        (260, 1, по(1, 13)),
        (260, 7, по(1, 13)),
        (260, 13, по(1, 13)),
        # 15 страниц: у начала — первые десять и последние две
        (281, 1, [*по(1, 10), "...", "14", "15"]),
        (281, 7, [*по(1, 10), "...", "14", "15"]),
        # Середина — окно ±3 между двумя «...»
        (281, 8, ["1", "2", "...", *по(5, 11), "...", "14", "15"]),
        # Ближе семи к концу — последние десять
        (281, 9, ["1", "2", "...", *по(6, 15)]),
        (281, 15, ["1", "2", "...", *по(6, 15)]),
        (1000, 14, ["1", "2", "...", *по(11, 17), "...", "49", "50"]),
        (1000, 50, ["1", "2", "...", *по(41, 50)]),
        # Страница за последней — окно последней, ссылки «вперёд» нет
        (300, 50, ["1", "2", "...", *по(6, 15)]),
    ],
)
def test_окно_номеров(total, current, окно):
    страницы = построить(total, current)

    assert номера(страницы) == окно
    assert страницы["last_page"] == max(1, -(-total // 20))
    assert [link["label"] for link in страницы["links"] if link["active"]] == (
        [str(current)] if str(current) in окно else []
    )
    # «...» — без адреса и номера
    for link in страницы["links"]:
        if link["label"] == "...":
            assert link == {"url": None, "label": "...", "active": False}

    assert (страницы["prev_page_url"] is None) is (current == 1)
    assert (страницы["next_page_url"] is None) is (current >= страницы["last_page"])


@pytest.mark.parametrize(
    ("total", "current", "с", "по_"),
    [(0, 1, None, None), (95, 1, 1, 20), (95, 5, 81, 95), (95, 6, None, None), (21, 2, 21, 21)],
)
def test_с_по(total, current, с, по_):
    страницы = построить(total, current)

    assert (страницы["from"], страницы["to"], страницы["total"]) == (с, по_, total)
    assert страницы["per_page"] == 20 and страницы["current_page"] == current


def test_адреса_страниц():
    """
    withQueryString(): параметры — в порядке запроса, page — последним,
    массивы — a[0], a[1] (http_build_query), «~» не кодируется (RFC 3986).
    """
    страницы = построить(95, 2, ЗАПРОС, "en")
    запрос = "q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82&a%5B0%5D=1&a%5B1%5D=2&b=~"

    assert страницы["path"] == PATH
    assert страницы["first_page_url"] == f"{PATH}?{запрос}&page=1"
    assert страницы["last_page_url"] == f"{PATH}?{запрос}&page=5"
    assert страницы["prev_page_url"] == f"{PATH}?{запрос}&page=1"
    assert страницы["next_page_url"] == f"{PATH}?{запрос}&page=3"
    assert страницы["links"][3] == {
        "url": f"{PATH}?{запрос}&page=3",
        "label": "3",
        "page": 3,
        "active": False,
    }


@pytest.mark.parametrize(
    ("locale", "назад", "вперёд"),
    [
        # Английский — подписи самого фреймворка; остальные языки — из
        # словаря интерфейса (common.prev_page/next_page) с теми же «»
        ("en", "&laquo; Previous", "Next &raquo;"),
        ("ru", "&laquo; Назад", "Вперёд &raquo;"),
        ("uz", "&laquo; Orqaga", "Oldinga &raquo;"),
        ("tr", "&laquo; Önceki", "Sonraki &raquo;"),
        ("zh", "&laquo; 上一页", "下一页 &raquo;"),
    ],
)
def test_подписи(locale, назад, вперёд):
    страницы = построить(95, 2, "", locale)

    assert страницы["links"][0] == {
        "url": f"{PATH}?page=1",
        "label": назад,
        "page": 1,
        "active": False,
    }
    assert страницы["links"][-1] == {
        "url": f"{PATH}?page=3",
        "label": вперёд,
        "page": 3,
        "active": False,
    }

    первая = построить(95, 1, "", locale)
    assert первая["links"][0] == {"url": None, "label": назад, "page": None, "active": False}
