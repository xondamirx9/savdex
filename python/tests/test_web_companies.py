"""
Этап 4, шаг 3: каталог компаний /companies на Django.

Поиск (обе графики и ИНН), фильтры типа, страны, проверки и возраста,
счётчики вариантов каждого фильтра при остальных, постраничный вывод
по 12, карточка (заполненность профиля, «на площадке с», сайт).
Ограничение частоты — 120 в минуту, счётчик в файловом кэше.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any

import pytest

from .factories import Выражение, компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_catalog import ГЕО, справочники, файл_кэша
from .web_site import адрес, открыть, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники(*ГЕО)
    # 30 активных (три страницы по 12) в двух странах, разных типов,
    # возрастов и проверки; заблокированная и удалённая — не в каталоге
    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(kz,)] = sql("select id from countries where code = 'kz'")
    [(city,)] = sql("select id from cities where country_id = %s order by id limit 1", [uz])
    types = ["importer", "manufacturer", "distributor", None]

    for i in range(1, 31):
        pk = компания(
            name=f"ООО Цемент {i}" if i % 5 else f"Sement Savdo {i}",
            tin=str(300_000_000 + i),
            country_id=uz if i % 4 else kz,
            city_id=city if i % 3 else None,
            type=types[i % 4],
            legal_form="legal" if i % 7 else "individual",
            verification_level=i % 3,
            rating=(i % 5) + 0.5,
            website=None if i % 6 else (f"savdo{i}.uz" if i % 4 else f"https://x{i}.uz"),
            description="Поставки цемента. " * 8 if i % 2 else None,
            created_at=Выражение(f"now() - interval '{i * 3} months 1 day'"),
        )

        if i % 8 == 0:
            sql(
                "insert into company_documents (company_id, type, title, file_path, "
                "moderation_status, created_at, updated_at) values (%s, 'registration', "
                "'Свидетельство', %s, 'approved', now(), now())",
                [pk, f"docs/{i}.pdf"],
            )

    компания(status="blocked")
    компания(deleted_at=Выражение("now()"))

    with адрес() as root:
        yield root


def компании_на(сайт: str, path: str) -> dict[str, Any]:
    д = открыть(сайт, path)
    стр = страница(д["body"])

    assert д["status"] == 200
    assert стр["component"] == "companies/Index"

    return dict(стр["props"])


# Тип по номеру i: 0 — импортёр (он же Казахстан), 1 — производитель,
# 2 — дистрибьютор, 3 — без типа; проверены i % 3 = 2; «Sement» — каждая пятая
@pytest.mark.parametrize(
    ("path", "total", "на_странице", "фильтры"),
    [
        ("/companies", 30, 12, []),
        ("/companies?page=2", 30, 12, []),
        ("/companies?page=3", 30, 6, []),
        ("/companies?page=4", 30, 0, []),
        ("/en/companies?page=2", 30, 12, []),
        ("/uz/companies", 30, 12, []),
        ("/zh/companies?type=importer", 7, 7, {"type": "importer"}),
        ("/tr/companies?country=KZ", 7, 7, {"country": "KZ"}),
        # Кириллица находит только «Цемент», латиница — обе графики
        ("/companies?q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82", 24, 12, {"q": "цемент"}),
        ("/companies?q=sement", 30, 12, {"q": "sement"}),
        ("/companies?q=%20300000012%20", 1, 1, {"q": "300000012"}),
        ("/companies?q=0", 30, 12, {"q": "0"}),
        ("/companies?q=", 30, 12, {"q": None}),
        ("/companies?verified=1", 10, 10, {"verified": "1"}),
        # i ≡ 2 (mod 3) и ≡ 1 (mod 4): 5, 17, 29
        (
            "/companies?verified=1&type=manufacturer&country=uz",
            3,
            3,
            {"type": "manufacturer", "verified": "1", "country": "uz"},
        ),
        # Возраст — 3·i месяцев и день: до года — 1…3, больше пяти лет — 20…30
        ("/companies?age=lt1", 3, 3, {"age": "lt1"}),
        ("/companies?age=1to5&page=2", 16, 4, {"age": "1to5"}),
        ("/companies?age=gt5", 11, 11, {"age": "gt5"}),
        ("/companies?age=old", 30, 12, {"age": "old"}),
        ("/companies?type=nonsense", 0, 0, {"type": "nonsense"}),
        ("/companies?country=hu", 0, 0, {"country": "hu"}),
        ("/companies?z=1&age=&verified=0", 30, 12, {"verified": "0", "age": None}),
    ],
)
def test_каталог(сайт, path, total, на_странице, фильтры):
    props = компании_на(сайт, path)

    assert props["companies"]["total"] == total
    assert len(props["companies"]["data"]) == на_странице
    assert props["filters"] == фильтры
    # Заблокированная и удалённая — не в каталоге и не в счётчике
    assert props["stats"] == {"total": 30, "verified": 10}


def test_фильтры_считают_варианты(сайт):
    props = компании_на(сайт, "/companies?country=uz")

    # Страна выбрана, а счётчик стран — без неё: видно, что даст другая
    assert {c["code"]: c["count"] for c in props["countries"]} == {"uz": 23, "kz": 7}
    assert props["filters"] == {"country": "uz"}
    assert props["companies"]["total"] == 23
    assert sum(props["facets"]["ages"].values()) == props["companies"]["total"]
    # Типы — внутри выбранной страны: импортёры все в Казахстане
    assert {t["value"]: t["count"] for t in props["types"]} == {
        "manufacturer": 8,
        "distributor": 8,
    }
    # Неизвестная страна в списке остаётся — выбранной, с нулём
    hu = компании_на(сайт, "/companies?country=hu")
    assert {c["code"]: c["count"] for c in hu["countries"]} == {"uz": 23, "kz": 7, "hu": 0}


def test_без_фильтров_пустой_список(сайт):
    props = компании_на(сайт, "/companies")

    assert props["filters"] == []
    assert props["facets"] == {"ages": {"lt1": 3, "1to5": 16, "gt5": 11}, "verified": 10}


def test_карточка(сайт):
    """Заполненность профиля, сайт со схемой, тип или правовая форма."""
    [шестая] = компании_на(сайт, "/companies?q=300000006")["companies"]["data"]
    [седьмая] = компании_на(сайт, "/companies?q=300000007")["companies"]["data"]
    [двадцать_четвёртая] = компании_на(сайт, "/companies?q=300000024")["companies"]["data"]

    # Название, тип, ИНН из десяти пунктов
    assert шестая["trust"] == 30
    assert шестая["website"] == "https://savdo6.uz"
    assert (шестая["type"], шестая["country"], шестая["city"]) == ("distributor", "uz", None)
    # Без типа, но ИП; город и описание длиннее 100 знаков
    assert седьмая["trust"] == 50
    assert седьмая["type"] is None and седьмая["website"] is None
    assert седьмая["city"]
    # Документ одобрен — тоже пункт; адрес со схемой — как есть
    assert двадцать_четвёртая["trust"] == 40
    assert двадцать_четвёртая["website"] == "https://x24.uz"
    assert двадцать_четвёртая["country"] == "kz"


def test_ограничение_частоты(сайт):
    """Лимит 120 — свой у маршрута, счётчик — в файловом кэше (общий у всего сайта)."""
    файловый = {"CACHE_STORE": "file"}
    ip = "192.0.2.147"
    key = hashlib.sha1(f"|{ip}".encode()).hexdigest()

    for name in (key, key + ":timer"):
        файл_кэша(name).unlink(missing_ok=True)

    try:
        первый = открыть(сайт, "/companies", headers={"X-Forwarded-For": ip}, env=файловый)
        второй = открыть(сайт, "/companies", headers={"X-Forwarded-For": ip}, env=файловый)
    finally:
        for name in (key, key + ":timer"):
            файл_кэша(name).unlink(missing_ok=True)

    assert первый["headers"]["x-ratelimit-limit"] == второй["headers"]["x-ratelimit-limit"] == "120"
    assert первый["headers"]["x-ratelimit-remaining"] == "119"
    assert второй["headers"]["x-ratelimit-remaining"] == "118"
