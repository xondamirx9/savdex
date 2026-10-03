"""
Этап 8: Django отвечает на все адреса (savdex/web/fallback.py).

Проверки Django: страница 404 на адресах без маршрута (с языковым
префиксом и без) — без сессии, как было у обработчика исключений
Laravel; переход со служебного адреса Render на домен (CanonicalHost);
бывшая панель Filament ведёт в админку Django, служебные адреса
Livewire и Filament — 404, страница 500 не роняет ответ, даже если не
собирается сама.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .pg_admin import нужна_база, свежая_база
from .web_site import адрес, из_django, открыть, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "/nope",
        "/uz/nope",
        "/en/cabinet/nope?x=1",
        "/company/x/y/z",
    ],
)
def test_404_без_маршрута(сайт, path):
    д = открыть(сайт, path)

    assert д["status"] == 404
    стр = страница(д["body"])
    assert стр["component"] == "Error" and стр["props"]["status"] == 404
    # Без сессии: посредники группы web на несовпавшем маршруте не работают
    assert not д["cookies"]
    # Общие пропсы есть (без них страница была пустой), адрес — как в браузере
    assert "support" in стр["props"] and стр["props"]["auth"]["user"] is None
    assert стр["url"] == path


@pytest.mark.parametrize("path", ["/help", "/uz/catalog?q=a", "/"])
def test_служебный_адрес_render_на_домен(сайт, path):
    host = {"Host": "savdex-abc.onrender.com"}
    д = открыть(сайт, path, headers=host)

    assert д["status"] == 301
    assert д["headers"]["location"] == сайт + path


def test_up_на_служебном_адресе_не_уводит(сайт):
    ответ = из_django(сайт, "/up", headers={"Host": "savdex-abc.onrender.com"})

    assert ответ["status"] == 200


@pytest.mark.parametrize(
    ("path", "куда"),
    [
        ("/admin", "/py/admin/"),
        ("/admin/", "/py/admin/"),
        ("/admin/login", "/py/admin/login/"),
        ("/admin/python?next=/py/admin/crm/lead/", "/py/admin/crm/lead/"),
        ("/admin/python?next=https://evil.example/", "/py/admin/"),
        ("/admin/excel-exports", "/py/admin/"),
    ],
)
def test_бывшая_панель_filament(сайт, path, куда):
    ответ = из_django(сайт, path)

    assert ответ["status"] == 302 and ответ["headers"]["location"] == куда


@pytest.mark.parametrize("path", ["/livewire-d643336e/livewire.js", "/filament/exports/1/download"])
def test_служебные_адреса_filament_404(сайт, path):
    assert из_django(сайт, path)["status"] == 404


def test_500_без_страницы_простой_текст(monkeypatch):
    from django.test import RequestFactory

    from savdex.web import fallback

    def сбой(*args, **kwargs):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(fallback, "_bare_error", сбой)
    ответ = fallback.server_error(RequestFactory().get("/catalog"))

    assert ответ.status_code == 500 and "Ошибка сервера" in ответ.content.decode()
