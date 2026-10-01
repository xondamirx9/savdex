"""
Этап 4, шаг 1: счётчик частоты, «Показать ещё» на странице стран и
старый адрес /tenders.

Счётчик throttle — в файловом кэше (общий формат с Laravel), ключ —
посетитель, а не адрес: 60-й запрос в минуту проходит, 61-й — 429.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

import pytest

from savdex import laravel_cache

from .factories import компания, объявление
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

#: Посетители проверок: адрес (X-Forwarded-For) — у каждого свой счётчик
АДРЕСА = [f"198.51.100.{i}" for i in range(1, 10)] + [f"203.0.113.{i}" for i in (77, 78, 90, 91)]


def ключ_гостя(ip: str) -> str:
    """ThrottleRequests: sha1(«домен маршрута|IP»), домена у маршрутов нет."""
    return hashlib.sha1(f"|{ip}".encode()).hexdigest()


def очистить_кэш(*ключи: str) -> None:
    """Счётчики проверок прочь (Cache::forget каждого и его :timer)."""
    for ключ in ключи or [ключ_гостя(ip) for ip in АДРЕСА]:
        for имя in (ключ, f"{ключ}:timer"):
            laravel_cache.file_path(имя).unlink(missing_ok=True)


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (GeoSeeder).
    """
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"seeds.seed(data={{k: v if k in {list(таблицы)!r} else [] for k, v in data.items()}})"
    )
    subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            # Справочники заводит владелец базы, как миграции
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        check=True,
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники("countries", "country_translations", "cities", "city_translations")
    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(city,)] = sql("select id from cities where country_id = %s order by id limit 1", [uz])

    for i in range(1, 10):
        c = компания(
            country_id=uz,
            city_id=city if i % 2 else None,
            rating=i % 4,
            verification_level=i % 3,
            type=None if i == 3 else "importer",
            legal_form="freelancer" if i == 3 else "legal",
        )

        for _ in range(i % 3):
            объявление(company_id=c)

    очистить_кэш()

    try:
        with адрес() as root:
            yield root
    finally:
        очистить_кэш()


def json_ответ(сайт: str, path: str, headers: dict[str, str]) -> dict[str, Any]:
    д = открыть(сайт, path, headers=headers, env=ФАЙЛОВЫЙ)

    assert д["status"] == 200, д["status"]
    assert д["headers"]["content-type"].startswith("application/json")

    return dict(json.loads(д["body"]))


@pytest.mark.parametrize(
    ("path", "ip", "сдвиг"),
    [
        ("/countries/uz/companies", "198.51.100.1", 0),
        # Код страны — без учёта регистра
        ("/countries/UZ/companies?offset=3", "198.51.100.2", 3),
        # (int) у PHP: «2abc» — 2, отрицательный — с начала
        ("/en/countries/uz/companies?offset=2abc", "198.51.100.3", 2),
        ("/zh/countries/uz/companies?offset=-5", "198.51.100.4", 0),
        ("/tr/countries/uz/companies?offset=100", "198.51.100.5", 100),
    ],
)
def test_показать_ещё(сайт, path, ip, сдвиг):
    все = json_ответ(сайт, "/countries/uz/companies", {"X-Forwarded-For": "198.51.100.6"})
    данные = json_ответ(сайт, path, {"X-Forwarded-For": ip})

    # Все девять компаний страны, «ещё» — продолжение того же списка
    assert len(все["items"]) == 9
    assert [c["slug"] for c in данные["items"]] == [c["slug"] for c in все["items"]][сдвиг:]


def test_нет_такой_страны(сайт):
    д = открыть(
        сайт, "/countries/xx/companies", headers={"X-Forwarded-For": "198.51.100.9"}, env=ФАЙЛОВЫЙ
    )

    assert д["status"] == 404


@pytest.mark.parametrize(
    ("path", "куда"),
    [
        ("/tenders", "/catalog?type=tender"),
        # Поиск без пробелов по краям, раздел — числом, «закрытые» — 1
        (
            "/tenders?q=%20цемент%20м400%20&category=12abc&closed=yes",
            "/catalog?type=tender&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82+%D0%BC400"
            "&category=12&closed=1",
        ),
        # Нулевые раздел и «закрытые» выпадают
        ("/tenders?q=a~b&closed=0&category=0", "/catalog?type=tender&q=a%7Eb"),
        ("/uz/tenders?closed=on", "/uz/catalog?type=tender&closed=1"),
    ],
)
def test_старый_адрес_закупок(сайт, path, куда):
    д = открыть(сайт, path, env=ФАЙЛОВЫЙ)

    assert д["status"] == 301
    assert д["headers"]["location"] == сайт + куда


def test_счётчик_частоты(сайт):
    """60 запросов в минуту на посетителя: 60-й проходит, 61-й — 429."""
    ip = {"X-Forwarded-For": "203.0.113.77"}
    path = "/countries/uz/companies"
    ключ = ключ_гостя("203.0.113.77")
    очистить_кэш(ключ)
    # 58 запросов уже засчитаны в этом окне (так же их засчитал бы и Laravel)
    laravel_cache.put(ключ, 58, 60)
    laravel_cache.put(f"{ключ}:timer", int(time.time()) + 60, 60)

    д = открыть(сайт, path, headers=ip, env=ФАЙЛОВЫЙ)
    assert (д["status"], д["headers"]["x-ratelimit-remaining"]) == (200, "1")
    assert д["headers"]["x-ratelimit-limit"] == "60"

    д = открыть(сайт, path, headers=ip, env=ФАЙЛОВЫЙ)
    assert (д["status"], д["headers"]["x-ratelimit-remaining"]) == (200, "0")

    # 61-й — отказ
    д = открыть(сайт, path, headers=ip, env=ФАЙЛОВЫЙ)
    assert д["status"] == 429
    assert страница(д["body"])["component"] == "Error"

    # Страница ошибки Inertia теряет заголовки исключения (как у Laravel)
    for header in ("retry-after", "x-ratelimit-limit", "x-ratelimit-reset"):
        assert header not in д["headers"], header

    # Другой посетитель считается отдельно
    д = открыть(сайт, path, headers={"X-Forwarded-For": "203.0.113.78"}, env=ФАЙЛОВЫЙ)
    assert (д["status"], д["headers"]["x-ratelimit-remaining"]) == (200, "59")


def test_вошедший_считается_по_учётной_записи(сайт):
    uid = пользователь("throttle@savdex.uz")
    куки = вход(uid)
    path = "/countries/uz/companies"
    очистить_кэш(hashlib.sha1(str(uid).encode()).hexdigest())

    первый = открыть(сайт, path, куки, {"X-Forwarded-For": "203.0.113.90"}, env=ФАЙЛОВЫЙ)
    # Другой адрес, та же учётная запись — тот же счётчик
    второй = открыть(сайт, path, куки, {"X-Forwarded-For": "203.0.113.91"}, env=ФАЙЛОВЫЙ)

    assert первый["headers"]["x-ratelimit-remaining"] == "59"
    assert второй["headers"]["x-ratelimit-remaining"] == "58"
