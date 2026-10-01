"""
Страницы сайта на Django (этап 3): справка, инструкция, правила.

Запрос к Django — и проверяется то, что раньше сверялось с Laravel:
статус, объект страницы Inertia (компонент, язык, сама страница, общие
пропсы: вошедший, его компания, остаток контактов, колокольчик) и
теги <head> для поисковика; язык из адреса, браузера, сессии и профиля;
переходы Inertia; скрытая страница; машинный перевод; отказ роботам.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, вход, гостевая, открыть, пользователь, страница, шапка

pytestmark = нужна_база

#: Адрес → (страница, язык, её заголовок на этом языке)
СТРАНИЦЫ = {
    "/help": ("help", "ru", "Помощь"),
    "/guide": ("guide", "ru", "Инструкция использования"),
    "/rules": ("rules", "ru", "Правила размещения"),
    "/uz/help": ("help", "uz", "Yordam"),
    "/en/guide": ("guide", "en", "How to use the platform"),
    "/zh/rules": ("rules", "zh", "发布规则"),
    "/tr/help": ("help", "tr", "Yardım"),
}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def _страница(ответ: dict) -> dict:
    assert ответ["status"] == 200, (ответ["status"], ответ["body"][:500])

    return страница(ответ["body"])


@pytest.mark.parametrize("path", list(СТРАНИЦЫ))
def test_гость_без_сессии(сайт, path):
    key, locale, title = СТРАНИЦЫ[path]
    д = открыть(сайт, path)
    page = _страница(д)

    assert page["component"] == "DocPage"
    assert page["url"] == path
    assert page["props"]["locale"] == locale
    assert page["props"]["page"]["key"] == key
    assert page["props"]["page"]["title"] == title
    assert page["props"]["auth"]["user"] is None
    теги = шапка(д["body"])
    assert f"<title inertia>{title} · SAVDEX</title>" in теги
    assert f'<link rel="alternate" hreflang="uz" href="{сайт}/uz/{key}">' in теги


def test_гость_с_сессией_и_языком_браузера(сайт):
    """Язык браузера не переключает страницу — только предлагает свой язык."""
    куки = гостевая(сайт)

    for path, accept, suggest in (
        ("/help", "uz-UZ,uz;q=0.9,en;q=0.8", "uz"),
        ("/guide", "zh-Hans-CN;q=0.5, tr;q=0.7", "tr"),
        ("/rules", "de-DE", None),
    ):
        page = _страница(открыть(сайт, path, куки, {"Accept-Language": accept}))

        assert page["props"]["locale"] == "ru"
        assert page["props"]["localeSuggest"] == suggest, path


def test_переход_inertia(сайт):
    версия = страница(открыть(сайт, "/help")["body"])["version"]

    д = открыть(сайт, "/guide", headers={"X-Inertia": "true", "X-Inertia-Version": версия})
    assert д["status"] == 200
    assert д["headers"]["x-inertia"] == "true"
    assert д["headers"]["vary"] == "X-Inertia"
    page = json.loads(д["body"])
    assert (page["component"], page["url"]) == ("DocPage", "/guide")
    assert page["props"]["page"]["key"] == "guide"

    # Частичная перезагрузка — только запрошенное и errors
    д = открыть(
        сайт,
        "/help",
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": версия,
            "X-Inertia-Partial-Component": "DocPage",
            "X-Inertia-Partial-Data": "faq,nav",
        },
    )
    assert д["status"] == 200
    props = json.loads(д["body"])["props"]
    assert sorted(props) == ["errors", "faq", "nav"]
    assert props["faq"]

    # Сборка сменилась — полная перезагрузка
    д = открыть(сайт, "/rules", headers={"X-Inertia": "true", "X-Inertia-Version": "old"})
    assert д["status"] == 409
    assert д["headers"]["x-inertia-location"] == f"{сайт}/rules"


def test_вошедший_с_компанией_и_колокольчиком(сайт):
    [(company,)] = sql(
        "insert into companies (name, slug, status, verification_level, phone, tin, "
        "created_at, updated_at) values ('ООО «Стройбаза Юг»', 'stroybaza-yug', 'active', 1, "
        "'+998 90 000 00 00', '123456789', now(), now()) returning id"
    )
    uid = пользователь("owner@savdex.uz", company_id=company, is_admin=False)
    sql(
        "insert into wallets (company_id, credits, contacts_used_this_period, period_resets_at, "
        "created_at, updated_at) values (%s, 7, 1, '2026-10-15 00:00:00', now(), now())",
        [company],
    )

    for minutes, read in (
        (3, False),
        (95, True),
        (60 * 26, False),
        (60 * 24 * 9, False),
        (60 * 24 * 70, True),
    ):
        sql(
            "insert into user_notifications (user_id, type, tone, title, read_at, created_at, "
            "updated_at) values (%s, 'system', 'info', %s, %s, "
            "now() - make_interval(secs => %s), now())",
            [uid, f"Уведомление {minutes}", "2026-01-01" if read else None, minutes * 60 + 30],
        )

    куки = вход(uid)

    props = _страница(открыть(сайт, "/help", куки))["props"]
    assert props["auth"]["user"]["id"] == uid
    assert props["auth"]["company"]["initials"] == "СЮ"
    assert props["contactsLeft"]["credits"] == 7
    assert len(props["bell"]["latest"]) == 5
    # Сначала свежие
    assert props["bell"]["latest"][0]["title"] == "Уведомление 3"

    # Язык из профиля: без префикса — переход на свой язык
    sql("update users set locale = 'uz' where id = %s", [uid])
    д = открыть(сайт, "/help", куки)
    assert д["status"] == 302
    assert д["headers"]["location"] == f"{сайт}/uz/help"
    props = _страница(открыть(сайт, "/uz/guide", куки))["props"]
    assert props["locale"] == "uz"
    assert props["auth"]["user"]["id"] == uid


def test_скрытая_страница_404(сайт):
    sql("update pages set is_published = false where key = 'rules'")

    try:
        assert открыть(сайт, "/rules")["status"] == 404
        assert открыть(сайт, "/en/rules")["status"] == 404
        # Остальные страницы на месте
        assert открыть(сайт, "/help")["status"] == 200
    finally:
        sql("update pages set is_published = true where key = 'rules'")


def test_машинный_перевод_когда_язык_не_заполнен(сайт):
    sql("update pages set body_i18n = null, title_i18n = null where key = 'guide'")

    page = _страница(открыть(сайт, "/en/guide"))

    # Непереведённое встало в очередь, страница — на русском, пока перевода нет
    assert sql("select count(*) from content_translations where locale = 'en'")[0][0] > 0
    assert page["props"]["locale"] == "en"
    assert page["props"]["page"]["key"] == "guide"
    assert page["props"]["page"]["title"] == "Инструкция использования"


def test_гость_с_запомненным_языком(сайт):
    """Язык запомнила страница с префиксом — без префикса уводит на него."""
    куки = гостевая(сайт)
    assert открыть(сайт, "/tr/help", куки)["status"] == 200

    д = открыть(сайт, "/guide", куки)
    assert д["status"] == 302
    assert д["headers"]["location"] == f"{сайт}/tr/guide"

    # Переход Inertia без версии сборки — полная загрузка того же адреса,
    # а она уже уводит на запомненный язык
    д = открыть(
        сайт, "/rules?x=1", куки, {"X-Inertia": "true", "X-Requested-With": "XMLHttpRequest"}
    )
    assert д["status"] == 409
    assert д["headers"]["x-inertia-location"] == f"{сайт}/rules?x=1"
    assert открыть(сайт, "/rules?x=1", куки)["headers"]["location"] == f"{сайт}/tr/rules?x=1"


def test_робот_seo_отказ(сайт):
    ua = {"User-Agent": "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)"}
    д = открыть(сайт, "/help", headers=ua)

    assert (д["status"], д["body"]) == (403, "Crawling is not allowed for this user agent.\n")
