"""
Шаг 70: смена языка ?hl=<язык> на Django (как SetLocale у Laravel).

Выбор — в сессию и в профиль вошедшего, маркер снимается переходом на
чистый адрес выбранного языка: префикс страницы, с которой уходят, не
возвращается, остальные параметры — как их собирает http_build_query
после TrimStrings и ConvertEmptyStringsToNull. Неизвестный язык, пустой
и массив — страница как обычно.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import СЕССИЯ, адрес, завести, кука, куки_ответа, открыть, пользователь, строка

pytestmark = нужна_база

SID = "H" * 40


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def запрос(сайт: str, path: str, uid: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ответ Django и строка сессии после него (сессия заведена заранее)."""
    payload: dict[str, Any] = {"_token": "t" * 40}

    if uid is not None:
        payload[laravel_session.LOGIN_KEY] = uid
        sql("update users set locale = 'ru' where id = %s", [uid])

    завести(SID, payload)
    ответ = открыть(сайт, path, cookies={СЕССИЯ: кука(СЕССИЯ, SID)})
    sid = куки_ответа(ответ)[СЕССИЯ]["value"]
    итог = строка(sid)

    assert итог is not None

    return ответ, итог


@pytest.mark.parametrize(
    ("path", "куда", "язык"),
    [
        ("/help?hl=uz", "/uz/help", "uz"),
        ("/uz/help?hl=ru", "/help", "ru"),
        ("/en/news?hl=zh", "/zh/news", "zh"),
        ("/?hl=tr", "/tr", "tr"),
        ("/uz?hl=ru", "", "ru"),
        (
            "/catalog?q=%20a%20b%20&page=&hl=en&x[]=1&y=~z",
            "/en/catalog?q=a+b&x%5B0%5D=1&y=%7Ez",
            "en",
        ),
        ("/catalog?hl=uz&hl=en", "/en/catalog", "en"),
        ("/pricing?hl=ru&promo=", "/pricing?", "ru"),
    ],
)
def test_смена_языка(сайт, path, куда, язык):
    ответ, итог = запрос(сайт, path)

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == сайт + куда
    assert f'"locale":"{язык}"' in итог["payload"]
    assert куки_ответа(ответ)["XSRF-TOKEN"]["value"] == итог["token"]


@pytest.mark.parametrize("path", ["/help?hl=de", "/help?hl=", "/help?hl[]=uz", "/help?hl=UZ"])
def test_чужой_язык_страница_как_обычно(сайт, path):
    ответ, итог = запрос(сайт, path)

    assert ответ["status"] == 200
    assert '"locale":' not in итог["payload"]


def test_вошедшему_язык_в_профиль(сайт):
    uid = пользователь("hl@savdex.uz", locale="ru")

    ответ, итог = запрос(сайт, "/about?hl=uz", uid)

    assert ответ["headers"]["location"] == сайт + "/uz/about"
    assert sql("select locale from users where id = %s", [uid]) == [("uz",)]
    assert '"locale":"uz"' in итог["payload"]
    assert итог["user_id"] == uid
