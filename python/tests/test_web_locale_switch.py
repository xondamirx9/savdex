"""
Шаг 70: смена языка ?hl=<язык> на Django неотличима от Laravel (SetLocale).

Выбор — в сессию и в профиль вошедшего, маркер снимается переходом на
чистый адрес выбранного языка: префикс страницы, с которой уходят, не
возвращается, остальные параметры — как их собирает http_build_query
после TrimStrings и ConvertEmptyStringsToNull. Неизвестный язык, пустой
и массив — страница как обычно.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import sql, нужна_база, свежая_база
from .test_web_session import СЕССИЯ, завести, кука, одинаково, по_сторонам
from .web_site import laravel, пользователь

pytestmark = нужна_база

SID = "H" * 40


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel() as root:
        yield root


def сверить(сайт: str, path: str, uid: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    payload: dict[str, Any] = {"_token": "t" * 40}

    if uid is not None:
        payload[laravel_session.LOGIN_KEY] = uid

    def подготовить() -> None:
        if uid is not None:
            sql("update users set locale = 'ru' where id = %s", [uid])

        завести(SID, payload)

    стороны = по_сторонам(сайт, path, подготовить, cookies={СЕССИЯ: кука(СЕССИЯ, SID)})

    return стороны["django"][0], одинаково(стороны)


@pytest.mark.parametrize(
    ("path", "куда"),
    [
        ("/help?hl=uz", "/uz/help"),
        ("/uz/help?hl=ru", "/help"),
        ("/en/news?hl=zh", "/zh/news"),
        ("/?hl=tr", "/tr"),
        ("/uz?hl=ru", ""),
        ("/catalog?q=%20a%20b%20&page=&hl=en&x[]=1&y=~z", "/en/catalog?q=a+b&x%5B0%5D=1&y=%7Ez"),
        ("/catalog?hl=uz&hl=en", "/en/catalog"),
        ("/pricing?hl=ru&promo=", "/pricing?"),
    ],
)
def test_смена_языка(сайт, path, куда):
    ответ, итог = сверить(сайт, path)

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == сайт + куда
    assert '"locale":' in итог["payload"]


@pytest.mark.parametrize("path", ["/help?hl=de", "/help?hl=", "/help?hl[]=uz", "/help?hl=UZ"])
def test_чужой_язык_страница_как_обычно(сайт, path):
    ответ, _ = сверить(сайт, path)

    assert ответ["status"] == 200


def test_вошедшему_язык_в_профиль(сайт):
    uid = пользователь("hl@savdex.uz", locale="ru")

    ответ, итог = сверить(сайт, "/about?hl=uz", uid)

    assert ответ["headers"]["location"] == сайт + "/uz/about"
    assert sql("select locale from users where id = %s", [uid]) == [("uz",)]
    assert '"locale":"uz"' in итог["payload"]
