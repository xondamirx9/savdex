"""
Отзыв о площадке на экранах входа и регистрации — проверки Django.

Левая панель тёмных экранов входа показывает один настоящий отзыв:
свежий опубликованный, с оценкой от 4 и разумной длины. Подходящего
нет — блока нет. На остальных страницах свойство пустое, чтобы не
делать лишний запрос.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть, страница

pytestmark = нужна_база


def отзыв(rating: int, body: str, status: str = "published", минут_назад: int = 0) -> None:
    sql(
        "insert into platform_reviews (user_id, company_id, rating, body, status, "
        "created_at, updated_at) values (null, null, %s, %s, %s, "
        "'2026-09-01 12:00:00'::timestamp - make_interval(mins => %s), now())",
        [rating, body, status, минут_назад],
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def props(сайт: str, path: str) -> dict[str, Any]:
    return dict(страница(открыть(сайт, path)["body"])["props"])


def test_без_подходящего_отзыва_блока_нет(сайт: str) -> None:
    assert props(сайт, "/login")["authReview"] is None


def test_берётся_свежий_хороший_отзыв(сайт: str) -> None:
    хороший = "Нашли поставщика упаковки за два дня, договорились напрямую."
    отзыв(5, хороший, минут_назад=30)
    отзыв(3, "Тройка: пользоваться можно, но поиск хотелось бы получше.", минут_назад=1)
    отзыв(5, "Коротко.", минут_назад=2)
    отзыв(5, "Черновик, ещё не прошёл модерацию, но длинный достаточно.", "pending", 0)

    review = props(сайт, "/register")["authReview"]

    assert review == {
        "body": хороший,
        "author": "Пользователь SavdEx",
        "initials": review["initials"],
        "rating": 5,
    }
    assert props(сайт, "/uz/login")["authReview"]["rating"] == 5
    assert props(сайт, "/forgot-password")["authReview"] is not None


def test_вне_экранов_входа_пусто(сайт: str) -> None:
    assert props(сайт, "/")["authReview"] is None
    assert props(сайт, "/reviews")["authReview"] is None
