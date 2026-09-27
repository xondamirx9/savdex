"""
Раздел «Города» админки на Django — сквозь настоящую базу.

Как у стран (test_countries_admin.py): сотрудники с разными ролями
работают с разделом, проверяются права, правила City (адрес города,
координаты, русское название, запрет удаления при ссылках) и строки
журнала admin_actions.

Нужны PHP (миграции) и PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник, страна

pytestmark = нужна_база

LIST = "/py/admin/geo/city/"
ADD = "/py/admin/geo/city/add/"


@pytest.fixture(scope="module")
def места() -> dict[str, int]:
    свежая_база()

    uz = страна("uz", {"ru": "Узбекистан"})
    kz = страна("kz", {"ru": "Казахстан"})
    [(tashkent,)] = sql(
        "insert into cities (country_id, slug, sort, is_active, created_at, updated_at) "
        "values (%s, 'tashkent', 0, true, now(), now()) returning id",
        [uz],
    )
    sql(
        "insert into city_translations (city_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', 'Ташкент', now(), now())",
        [tashkent],
    )
    sql(
        "insert into companies (name, slug, country_id, city_id, created_at, updated_at) "
        "values ('ООО «Стройбаза»', 'stroybaza', %s, %s, now(), now())",
        [uz, tashkent],
    )

    return {
        "uz": uz,
        "kz": kz,
        "tashkent": int(tashkent),
        **{
            role: сотрудник(role)
            for role in ("superadmin", "content_manager", "moderator", "sales")
        },
    }


def _форма(
    country: int,
    slug: str,
    names: dict[str, str],
    *,
    city_id: int | None = None,
    lat: str = "",
    lng: str = "",
) -> dict[str, Any]:
    """Поля формы города вместе с формами переводов — как их шлёт браузер."""
    ids = {}
    if city_id is not None:
        ids = dict(sql("select locale, id from city_translations where city_id = %s", [city_id]))

    data: dict[str, Any] = {
        "country": str(country),
        "slug": slug,
        "sort": "3",
        "is_active": "on",
        "lat": lat,
        "lng": lng,
        "translations-TOTAL_FORMS": str(len(names)),
        "translations-INITIAL_FORMS": str(len(ids)),
        "translations-MIN_NUM_FORMS": "1",
        "translations-MAX_NUM_FORMS": "5",
    }

    for i, (locale, name) in enumerate(names.items()):
        data[f"translations-{i}-locale"] = locale
        data[f"translations-{i}-name"] = name
        if locale in ids:
            data[f"translations-{i}-id"] = str(ids[locale])
            data[f"translations-{i}-city"] = str(city_id)

    return data


def _город(slug: str) -> int:
    [(pk,)] = sql("select id from cities where slug = %s", [slug])

    return int(pk)


def test_список_фильтр_и_права(места):
    вход, список, по_стране = django(
        места["moderator"],
        ("get", LIST, None),
        ("get", f"{LIST}?country={места['kz']}", None),
    )

    assert вход == 302
    assert список["status"] == 200
    assert "Ташкент · tashkent" in список["body"]
    # Фильтр стран — названиями, не кодами и не номерами
    assert f"?country={места['kz']}" in список["body"]
    assert "Казахстан" in список["body"]
    # В Казахстане городов нет
    assert "Ташкент · tashkent" not in по_стране["body"]

    # Модератор смотрит, но не заводит
    _, заведение = django(места["moderator"], ("get", ADD, None))
    assert заведение["status"] == 403

    # Отделу продаж справочники не выданы
    _, чужой = django(места["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_заведение_города_и_журнал(места):
    _, ответ = django(
        места["content_manager"],
        (
            "post",
            ADD,
            _форма(
                места["uz"],
                "samarkand",
                {"ru": "Самарканд", "en": "Samarkand"},
                lat="39.6542",
                lng="66.9597",
            ),
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    [(country_id, lat, sort)] = sql(
        "select country_id, lat::text, sort from cities where slug = 'samarkand'"
    )
    assert (country_id, lat, sort) == (места["uz"], "39.6542000", 3)

    names = dict(
        sql(
            "select locale, name from city_translations where city_id = %s",
            [_город("samarkand")],
        )
    )
    assert names == {"ru": "Самарканд", "en": "Samarkand"}

    запись = журнал("created")
    assert запись["user_role"] == "content_manager"
    assert запись["section"] == "catalogs"
    assert запись["subject_type"] == "App\\Models\\City"
    assert запись["subject_label"] == "samarkand"
    after = запись["changes"]["after"]
    # Координаты — строкой, как их пишет Laravel, а не числом с плавающей точкой
    assert after["lat"] == "39.6542000" and after["name:ru"] == "Самарканд"
    assert "created_at" not in after


@pytest.mark.parametrize("slug", ["Samarkand", "samar kand", "самарканд", "-bukhara", "a--b"])
def test_адрес_только_латиницей_через_дефис(места, slug):
    _, ответ = django(
        места["content_manager"], ("post", ADD, _форма(места["uz"], slug, {"ru": "Город"}))
    )

    assert ответ["status"] == 200
    assert "Только латиница в нижнем регистре" in ответ["body"]


def test_адрес_не_повторяется_внутри_страны(места):
    """
    Filament пускал второй «tashkent» в тот же Узбекистан. В другой
    стране тот же адрес — другой город, и он разрешён.
    """
    _, дубль = django(
        места["content_manager"],
        ("post", ADD, _форма(места["uz"], "tashkent", {"ru": "Ещё Ташкент"})),
    )

    assert дубль["status"] == 200
    assert "В этой стране уже есть город с таким адресом" in дубль["body"]
    assert sql("select count(*) from cities where slug = 'tashkent'") == [(1,)]

    _, другая = django(
        места["content_manager"],
        ("post", ADD, _форма(места["kz"], "tashkent", {"ru": "Ташкент (Казахстан)"})),
    )

    assert другая["status"] == 302, другая["body"][:3000]
    assert sql("select count(*) from cities where slug = 'tashkent'") == [(2,)]


def test_координаты_в_своих_пределах(места):
    _, ответ = django(
        места["content_manager"],
        ("post", ADD, _форма(места["uz"], "nukus", {"ru": "Нукус"}, lat="91", lng="-181")),
    )

    assert ответ["status"] == 200
    assert "От −90 до 90." in ответ["body"]
    assert "От −180 до 180." in ответ["body"]
    assert sql("select count(*) from cities where slug = 'nukus'") == [(0,)]


def test_без_русского_названия_не_сохраняется(места):
    _, ответ = django(
        места["content_manager"],
        ("post", ADD, _форма(места["uz"], "bukhara", {"en": "Bukhara"})),
    )

    assert ответ["status"] == 200
    assert "Нужно русское название" in ответ["body"]
    assert sql("select count(*) from cities where slug = 'bukhara'") == [(0,)]


def test_правка_и_переименование_попадают_в_журнал(места):
    pk = _город("samarkand")
    данные = _форма(
        места["uz"],
        "samarkand",
        {"ru": "Самарканд-сити", "en": "Samarkand"},
        city_id=pk,
        lat="39.6500",
        lng="66.9597",
    )

    _, ответ = django(места["content_manager"], ("post", f"{LIST}{pk}/change/", данные))

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert журнал("updated")["changes"] == {
        "before": {"lat": "39.6542000", "name:ru": "Самарканд"},
        "after": {"lat": "39.6500000", "name:ru": "Самарканд-сити"},
    }


def test_нетронутые_координаты_не_попадают_в_журнал(места):
    """Из формы приходит «39.65», из базы «39.6500000» — это не правка."""
    pk = _город("samarkand")
    данные = _форма(
        места["uz"],
        "samarkand",
        {"ru": "Самарканд-сити", "en": "Samarkand"},
        city_id=pk,
        lat="39.65",
        lng="66.9597",
    )
    данные["sort"] = "7"

    _, ответ = django(места["content_manager"], ("post", f"{LIST}{pk}/change/", данные))

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert журнал("updated")["changes"] == {"before": {"sort": 3}, "after": {"sort": 7}}


def test_удаление(места):
    pk = _город("samarkand")
    tashkent = места["tashkent"]

    # Контент-менеджеру удаление не выдано
    _, чужое = django(места["content_manager"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert чужое["status"] == 403

    # В Ташкенте компания — удалить нельзя даже суперадмину, форма объясняет почему
    _, форма, занятый = django(
        места["superadmin"],
        ("get", f"{LIST}{tashkent}/change/", None),
        ("post", f"{LIST}{tashkent}/delete/", {"post": "yes"}),
    )
    assert "Нельзя, на город ссылаются: компании — 1" in форма["body"]
    assert занятый["status"] == 403
    assert sql("select count(*) from cities where id = %s", [tashkent]) == [(1,)]

    # Свободный — можно, вместе с переводами; удаление — в журнале
    _, свободный = django(места["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert свободный["status"] == 302
    assert sql("select count(*) from cities where id = %s", [pk]) == [(0,)]
    assert sql("select count(*) from city_translations where city_id = %s", [pk]) == [(0,)]
    assert журнал("deleted")["subject_label"] == "samarkand"


@pytest.mark.parametrize(
    ("таблица", "подпись"),
    [("listings", "объявления"), ("resumes", "резюме")],
)
def test_объявления_и_резюме_тоже_удерживают_город(места, таблица, подпись):
    """
    Резюме PHP-версия не считала: удаление города молча обнуляло его
    у резюме. Удалённые в корзину тоже держат — внешний ключ задел бы и их.
    """
    [(pk,)] = sql(
        "insert into cities (country_id, slug, created_at, updated_at) "
        "values (%s, %s, now(), now()) returning id",
        [места["uz"], f"held-by-{таблица}"],
    )

    if таблица == "listings":
        [(company,)] = sql("select id from companies limit 1")
        sql(
            "insert into listings (company_id, title, city_id, deleted_at, created_at, "
            "updated_at) values (%s, 'Цемент', %s, now(), now(), now())",
            [company, pk],
        )
    else:
        sql(
            "insert into resumes (user_id, title, city_id, created_at, updated_at) "
            "values (%s, 'Инженер', %s, now(), now())",
            [места["sales"], pk],
        )

    _, форма, удаление = django(
        места["superadmin"],
        ("get", f"{LIST}{pk}/change/", None),
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
    )

    assert f"Нельзя, на город ссылаются: {подпись} — 1" in форма["body"]
    assert удаление["status"] == 403
    assert sql("select count(*) from cities where id = %s", [pk]) == [(1,)]
