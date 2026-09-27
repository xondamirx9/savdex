"""
Страницы сайта на Django неотличимы от страниц Laravel (этап 3).

Один и тот же запрос — к Laravel (php artisan serve) и к Django —
и ответы сравниваются целиком: статус, объект страницы Inertia (все
пропсы, включая общие: вошедший, его компания, остаток контактов,
колокольчик, словарь, ссылки языков) и теги <head> для поисковика.

Порядок: сначала Django, потом Laravel. Laravel на странице с языковым
префиксом запоминает язык в сессии и в профиле — это запись, которой
Django не делает, и обратный порядок сравнивал бы разные состояния.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from .pg_admin import sql, нужна_база, свежая_база
from .web_site import laravel, войти, гость, из_django, из_laravel, пользователь, страница, шапка

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel() as root:
        yield root


def сверить(
    сайт: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Django, затем Laravel; статус, страница и шапка должны совпасть."""
    д = из_django(сайт, path, cookies, headers)
    л = из_laravel(сайт, path, cookies, headers)

    assert д["status"] == л["status"], (д["status"], л["status"], д["body"][:500])

    if л["status"] in (301, 302, 409):
        for header in ("location", "x-inertia-location"):
            assert д["headers"].get(header) == л["headers"].get(header), header

        return д, л

    стр_д, стр_л = страница(д["body"]), страница(л["body"])

    for key in ("component", "url", "version", "sharedProps"):
        assert стр_д.get(key) == стр_л.get(key), key

    for prop in стр_л["props"]:
        assert стр_д["props"].get(prop) == стр_л["props"][prop], f"проп {prop}"

    assert list(стр_д["props"]) == list(стр_л["props"])
    assert set(стр_д) == set(стр_л)

    if "<head>" in л["body"]:
        assert шапка(д["body"]) == шапка(л["body"])
        assert д["headers"].get("link") == л["headers"].get("link")

    assert д["headers"].get("vary") == л["headers"].get("vary")

    return д, л


@pytest.mark.parametrize(
    "path", ["/help", "/guide", "/rules", "/uz/help", "/en/guide", "/zh/rules", "/tr/help"]
)
def test_гость_без_сессии(сайт, path):
    сверить(сайт, path)


def test_гость_с_сессией_и_языком_браузера(сайт):
    куки = гость(сайт)

    сверить(сайт, "/help", куки, {"Accept-Language": "uz-UZ,uz;q=0.9,en;q=0.8"})
    сверить(сайт, "/guide", куки, {"Accept-Language": "zh-Hans-CN;q=0.5, tr;q=0.7"})
    сверить(сайт, "/rules", куки, {"Accept-Language": "de-DE"})


def test_переход_inertia(сайт):
    версия = страница(из_laravel(сайт, "/help")["body"])["version"]

    сверить(сайт, "/guide", headers={"X-Inertia": "true", "X-Inertia-Version": версия})
    # Частичная перезагрузка — только запрошенное и errors
    сверить(
        сайт,
        "/help",
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": версия,
            "X-Inertia-Partial-Component": "DocPage",
            "X-Inertia-Partial-Data": "faq,nav",
        },
    )
    # Сборка сменилась — полная перезагрузка
    сверить(сайт, "/rules", headers={"X-Inertia": "true", "X-Inertia-Version": "old"})


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

    куки = войти(сайт, "owner@savdex.uz")

    д, _ = сверить(сайт, "/help", куки)
    props = страница(д["body"])["props"]
    assert props["auth"]["user"]["id"] == uid
    assert props["auth"]["company"]["initials"] == "СЮ"
    assert props["contactsLeft"]["credits"] == 7
    assert len(props["bell"]["latest"]) == 5

    # Язык из профиля: без префикса — переход на свой язык
    sql("update users set locale = 'uz' where id = %s", [uid])
    сверить(сайт, "/help", куки)
    сверить(сайт, "/uz/guide", куки)


def test_скрытая_страница_404(сайт):
    sql("update pages set is_published = false where key = 'rules'")

    try:
        сверить(сайт, "/rules")
        сверить(сайт, "/en/rules")
    finally:
        sql("update pages set is_published = true where key = 'rules'")


def test_машинный_перевод_когда_язык_не_заполнен(сайт):
    sql("update pages set body_i18n = null, title_i18n = null where key = 'guide'")

    д, _ = сверить(сайт, "/en/guide")

    # Непереведённое встало в очередь — Django, как и Laravel
    assert sql("select count(*) from content_translations where locale = 'en'")[0][0] > 0
    assert json.dumps(страница(д["body"])["props"]["page"])


def test_гость_с_запомненным_языком(сайт):
    """Язык запомнил Laravel (страница с префиксом) — без префикса уводит на него."""
    куки = гость(сайт)
    из_laravel(сайт, "/tr/help", куки)

    д, _ = сверить(сайт, "/guide", куки)
    assert д["headers"]["location"].endswith("/tr/guide")

    # Переход Inertia тоже уводит — как у Laravel
    сверить(сайт, "/rules?x=1", куки, {"X-Inertia": "true", "X-Requested-With": "XMLHttpRequest"})


def test_робот_seo_отказ(сайт):
    ua = {"User-Agent": "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)"}
    д = из_django(сайт, "/help", headers=ua)
    л = из_laravel(сайт, "/help", headers=ua)

    assert (
        (д["status"], д["body"])
        == (л["status"], л["body"])
        == (403, "Crawling is not allowed for this user agent.\n")
    )
