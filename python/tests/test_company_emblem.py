"""
Эмблемы компаний — перенос tests/Feature/Admin/CompanyEmblemTest.php.

Плашка с инициалами вместо чужого логотипа: стабильная (одна компания —
один цвет), с инициалами, цвет — по региону; встаёт обычным логотипом
и показывается на визитке без отдельного кода.

Сценарии PHP:
- эмблема_становится_логотипом_и_несёт_инициалы — test_эмблема_становится_логотипом_и_несёт_инициалы
  (и без базы — test_инициалы_и_цвет_региона);
- публичная_страница_компании_отдаёт_эмблему — test_публичная_страница_компании_отдаёт_эмблему;
- цвет_стабилен_между_генерациями — test_цвет_стабилен_между_генерациями
  (и без базы — test_цвет_без_региона_стабилен).

Сверх них — файл эмблемы (город — русское название или адрес города,
адрес, название) и журнал. Проверки с базой требуют PostgreSQL
(SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py. Компании — с
большими номерами: файлы эмблем пишутся в storage/app/public и после
проверки удаляются.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import zlib
from collections.abc import Iterator
from typing import Any

import pytest

from savdex.data import emblem

from .factories import компания
from .pg_admin import (
    PYTHON,
    КОРЕНЬ,
    ОКРУЖЕНИЕ,
    sql,
    нужна_база,
    свежая_база,
    сотрудник,
    страна,
)

ДИСК = КОРЕНЬ / "storage/app/public"

#: assign() в отдельном процессе Django, как на сервере
ПРОБА = """
import json, sys
import django
django.setup()
from savdex.data import emblem

calls = json.loads(sys.argv[1])
print(json.dumps([emblem.assign(company, admin_id=admin) for company, admin in calls]))
"""


# ── Без базы: цвет, инициалы, кегль ─────────────────────────────────


def test_инициалы_и_цвет_региона():
    svg = emblem.svg("Samarqand Fruit Export")

    assert svg.startswith("<svg")
    assert ">SF</text>" in svg
    # Компания самаркандская — палитра своего региона
    assert "#1d5f9e" in svg


def test_регион_по_городу_и_адресу():
    assert emblem.palette("Acme", city="Ташкент") == emblem.PALETTES["tashkent"]
    assert emblem.palette("Acme", address="г. Нукус, ул. Дослик 1") == emblem.PALETTES["karakalpak"]
    # Регистр не важен; первая найденная примета решает — порядок словаря
    assert emblem.palette("BUXORO Tekstil", city="Самарканд") == emblem.PALETTES["samarkand"]


def test_цвет_без_региона_стабилен():
    colours = list(emblem.PALETTES.values())
    expected = colours[zlib.crc32(b"no region trading") % len(colours)]

    assert emblem.palette("No Region Trading") == expected
    assert emblem.svg("No Region Trading") == emblem.svg("No Region Trading")


def test_кегль_и_экранирование():
    # Две буквы — кегль меньше; «&» экранируется, как htmlspecialchars
    assert 'font-size="96"' in emblem.svg("A & B")
    assert ">A&amp;</text>" in emblem.svg("A & B")
    assert 'font-size="120"' in emblem.svg("Z")
    # Одна правовая форма — знак вопроса
    assert ">?</text>" in emblem.svg("ООО")


# ── С базой ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def база() -> dict[str, int]:
    свежая_база()

    return {"админ": сотрудник("superadmin"), "страна": страна("uz", {"ru": "Узбекистан"})}


@pytest.fixture
def админ(база) -> int:
    return база["админ"]


@pytest.fixture
def компании() -> Iterator[list[int]]:
    """Номера созданных компаний; их эмблемы удаляются после проверки."""
    номера: list[int] = []

    yield номера

    for номер in номера:
        (ДИСК / emblem.path_of(номер)).unlink(missing_ok=True)

        # Каталог — только если опустел: в нём могут быть чужие файлы
        with contextlib.suppress(OSError):
            (ДИСК / f"companies/{номер}").rmdir()


def _компания(номера: list[int], id_: int, name: str, **поля: Any) -> int:
    columns = {"id": id_, "slug": f"emblem-{id_}", "name": name, **поля}
    sql(
        f"insert into companies ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now())",
        list(columns.values()),
    )
    номера.append(id_)

    return id_


def _django(*calls: tuple[int, int | None]) -> list[str]:
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, json.dumps(calls)],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return list(json.loads(вывод.stdout))


def _журнал(company_id: int) -> list[tuple[Any, ...]]:
    return sql(
        "select action, section, subject_type, subject_label, changes, user_role "
        "from admin_actions where subject_id = %s and subject_type = 'App\\Models\\Company' "
        "order by id",
        [company_id],
    )


@нужна_база
def test_эмблема_становится_логотипом_и_несёт_инициалы(админ, компании):
    номер = _компания(компании, 990101, "Samarqand Fruit Export", logo_path=None)

    [путь] = _django((номер, админ))

    assert путь == f"companies/{номер}/emblem.svg"
    assert sql("select logo_path from companies where id = %s", [номер]) == [(путь,)]

    svg = (ДИСК / путь).read_text()

    assert svg.startswith("<svg")
    assert ">SF</text>" in svg
    assert "#1d5f9e" in svg

    # Правка администратора — строка журнала, как AuditObserver
    [строка] = _журнал(номер)
    assert строка[:4] == ("updated", "companies", "App\\Models\\Company", "Samarqand Fruit Export")
    assert строка[4] == {"before": {"logo_path": None}, "after": {"logo_path": путь}}
    assert строка[5] == "superadmin"


@нужна_база
def test_цвет_стабилен_между_генерациями(админ, компании):
    номер = _компания(компании, 990102, "No Region Trading", address=None, city_id=None)

    [путь] = _django((номер, админ))
    первая = (ДИСК / путь).read_bytes()
    _django((номер, админ))
    вторая = (ДИСК / путь).read_bytes()

    assert первая == вторая
    # Путь тот же — Eloquent нечего сохранять, второй строки журнала нет
    assert len(_журнал(номер)) == 1


@нужна_база
def test_заменяет_логотип_и_не_пишет_журнал_без_администратора(админ, компании):
    номер = _компания(компании, 990103, "Toshkent Matras", logo_path="companies/x.webp")

    [путь] = _django((номер, None))

    assert sql("select logo_path from companies where id = %s", [номер]) == [(путь,)]
    assert "#2563ab" in (ДИСК / путь).read_text()
    assert _журнал(номер) == []


@нужна_база
def test_svg_файла(база, компании):
    """
    Файл эмблемы: город — русское название (без перевода — адрес города),
    адрес («0» — пусто, как у PHP), регион по приметам, иначе цвет по crc32.
    """
    [(город,)] = sql(
        "insert into cities (country_id, slug, created_at, updated_at) values "
        "(%s, 'fergana-emblem', now(), now()) returning id",
        [база["страна"]],
    )
    sql(
        "insert into city_translations (city_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', 'Фергана', now(), now())",
        [город],
    )
    [(без_перевода,)] = sql(
        "insert into cities (country_id, slug, created_at, updated_at) values "
        "(%s, 'termez-city', now(), now()) returning id",
        [база["страна"]],
    )
    цвета = list(emblem.PALETTES.values())

    def по_crc(name: str) -> str:
        return цвета[zlib.crc32(name.lower().encode()) % len(цвета)][0]

    # (номер, название, поля, город и адрес для рисунка, цвет, кегль, инициалы)
    случаи = [
        (990111, "ООО «Стройбаза»", {"city_id": город}, ("Фергана", None), "#b02a4c", 96, "СТ"),
        (
            990112,
            "Ромашка",
            {"address": "г. Бухара, ул. Навои 5"},
            (None, "г. Бухара, ул. Навои 5"),
            emblem.PALETTES["bukhara"][0],
            96,
            "РО",
        ),
        # Латинское «termez» — не примета региона; «&» и «<» экранированы
        (
            990113,
            "A & B <Trade>",
            {"city_id": без_перевода},
            ("termez-city", None),
            по_crc("A & B <Trade>"),
            96,
            "A&amp;",
        ),
        # Одна правовая форма — знак вопроса
        (990114, "МЧЖ", {}, (None, None), по_crc("МЧЖ"), 120, "?"),
        (990115, "Z", {"address": "0"}, (None, "0"), по_crc("Z"), 120, "Z"),
        (
            990116,
            "Zeta Global Logistics O'zbekiston",
            {},
            (None, None),
            по_crc("Zeta Global Logistics O'zbekiston"),
            96,
            "ZG",
        ),
    ]
    номера = [_компания(компании, n, name, **поля) for n, name, поля, *_ in случаи]

    пути = _django(*((n, None) for n in номера))

    for путь, (_, name, _, (город_, адрес), цвет, кегль, буквы) in zip(пути, случаи, strict=True):
        файл = (ДИСК / путь).read_text()

        assert файл == emblem.svg(name, город_, адрес), путь
        assert f'<stop offset="0" stop-color="{цвет}"/>' in файл, путь
        assert f'font-size="{кегль}"' in файл and f">{буквы}</text>" in файл, путь


@нужна_база
def test_публичная_страница_компании_отдаёт_эмблему(админ, компании):
    """Витрина отдаёт эмблему фронту — адресом на публичном диске."""
    from .web_site import адрес, открыть, страница

    номер = 990121
    компания(id=номер, logo_path=None)
    [(slug,)] = sql("select slug from companies where id = %s", [номер])
    компании.append(номер)

    [путь] = _django((номер, админ))

    with адрес() as сайт:
        д = открыть(сайт, f"/company/{slug}")

    assert д["status"] == 200
    assert страница(д["body"])["props"]["company"]["logo"] == f"{сайт}/storage/{путь}"
