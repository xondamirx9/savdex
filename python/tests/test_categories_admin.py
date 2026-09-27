"""
Раздел «Категории» админки на Django — сквозь настоящую базу.

Дерево заводит настоящий CategorySeeder, на нём и проверяется: права
по ролям, дерево на два уровня, адрес, значки, русское название, запрет
удаления при ссылках и строки журнала admin_actions.

Нужны PHP (миграции, сидер) и PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/catalogs/category/"
ADD = "/py/admin/catalogs/category/add/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=CategorySeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        check=True,
    )

    return {
        role: сотрудник(role) for role in ("superadmin", "content_manager", "moderator", "sales")
    }


def _id(slug: str) -> int:
    [(pk,)] = sql("select id from categories where slug = %s", [slug])

    return int(pk)


def _форма(
    slug: str,
    names: dict[str, str],
    *,
    parent: int | None = None,
    icon: str = "",
    category_id: int | None = None,
) -> dict[str, Any]:
    """Поля формы категории вместе с формами переводов — как их шлёт браузер."""
    ids = {}
    if category_id is not None:
        ids = dict(
            sql(
                "select locale, id from category_translations where category_id = %s",
                [category_id],
            )
        )

    data: dict[str, Any] = {
        "parent": "" if parent is None else str(parent),
        "slug": slug,
        "icon": icon,
        "sort": "3",
        "is_active": "on",
        "translations-TOTAL_FORMS": str(len(names)),
        "translations-INITIAL_FORMS": str(len([loc for loc in names if loc in ids])),
        "translations-MIN_NUM_FORMS": "1",
        "translations-MAX_NUM_FORMS": "5",
    }

    for i, (locale, name) in enumerate(names.items()):
        data[f"translations-{i}-locale"] = locale
        data[f"translations-{i}-name"] = name
        if locale in ids:
            data[f"translations-{i}-id"] = str(ids[locale])
            data[f"translations-{i}-category"] = str(category_id)

    return data


def test_список_деревом_фильтр_и_права(люди):
    вход, список, разделы, металлы = django(
        люди["moderator"],
        ("get", LIST, None),
        ("get", f"{LIST}?section=top", None),
        ("get", f"{LIST}?section={_id('metally')}", None),
    )

    assert вход == 302
    body = список["body"]
    # Раздел, под ним его подкатегории
    assert body.index("Стройматериалы · stroymaterialy") < body.index(
        "↳ Цемент и бетон · cement-beton"
    )
    assert body.index("↳ Цемент и бетон · cement-beton") < body.index("Текстиль и одежда")
    # Фильтр разделов — названиями, не адресами
    assert "Только разделы" in body and ">Металлы<" in body

    assert "↳" not in разделы["body"].split('id="result_list"')[1]
    assert "↳ Чёрные металлы" in металлы["body"]
    assert "Цемент и бетон" not in металлы["body"].split('id="result_list"')[1]

    # Модератор смотрит, но не заводит; продажам справочники не выданы
    _, заведение = django(люди["moderator"], ("get", ADD, None))
    assert заведение["status"] == 403
    _, чужой = django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_заведение_подкатегории_и_журнал(люди):
    _, ответ = django(
        люди["content_manager"],
        (
            "post",
            ADD,
            _форма(
                "gazobeton",
                {"ru": "Газобетон", "en": "Aerated concrete"},
                parent=_id("stroymaterialy"),
            ),
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    [(parent, icon)] = sql("select parent_id, icon from categories where slug = 'gazobeton'")
    assert (parent, icon) == (_id("stroymaterialy"), None)

    запись = журнал("created")
    assert запись["user_role"] == "content_manager"
    assert запись["section"] == "catalogs"
    assert запись["subject_type"] == "App\\Models\\Category"
    assert запись["subject_label"] == "gazobeton"
    assert запись["changes"]["after"]["name:ru"] == "Газобетон"


def test_третьего_уровня_нет(люди):
    """
    Подкатегорию нельзя выбрать разделом, а раздел с подкатегориями
    нельзя вложить в другой раздел: и то и другое дало бы третий уровень.
    """
    _, в_подкатегорию = django(
        люди["content_manager"],
        ("post", ADD, _форма("glubzhe", {"ru": "Глубже"}, parent=_id("cement-beton"))),
    )
    assert в_подкатегорию["status"] == 200
    assert "Выберите корректный вариант" in в_подкатегорию["body"]

    metally = _id("metally")
    данные = _форма(
        "metally",
        {"ru": "Металлы"},
        parent=_id("stroymaterialy"),
        icon="layers",
        category_id=metally,
    )
    _, раздел_в_раздел = django(
        люди["content_manager"], ("post", f"{LIST}{metally}/change/", данные)
    )
    assert раздел_в_раздел["status"] == 200
    assert "У этого раздела есть подкатегории" in раздел_в_раздел["body"]
    assert sql("select parent_id from categories where id = %s", [metally]) == [(None,)]


def test_раздел_не_раздел_самому_себе(люди):
    pk = _id("gazobeton")

    _, форма = django(люди["content_manager"], ("get", f"{LIST}{pk}/change/", None))
    options = re.findall(
        r'<option value="(\d+)"', форма["body"].split('name="parent"')[1].split("</select>")[0]
    )

    assert str(pk) not in options
    assert str(_id("cement-beton")) not in options, "подкатегория разделом быть не может"


@pytest.mark.parametrize("slug", ["Gazobeton", "газобетон", "gazo beton", "-x"])
def test_адрес_латиницей(люди, slug):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма(slug, {"ru": "Тест"})))

    assert ответ["status"] == 200
    assert "Только латиница в нижнем регистре" in ответ["body"]


def test_значок_только_из_известных_витрине(люди):
    _, ответ = django(
        люди["content_manager"], ("post", ADD, _форма("himiya", {"ru": "Химия"}, icon="flask"))
    )
    assert ответ["status"] == 200
    assert "Выберите корректный вариант" in ответ["body"]

    _, ок = django(
        люди["content_manager"], ("post", ADD, _форма("himiya", {"ru": "Химия"}, icon="chemistry"))
    )
    assert ок["status"] == 302, ок["body"][:3000]
    assert sql("select icon from categories where slug = 'himiya'") == [("chemistry",)]


def test_незнакомый_значок_из_filament_не_мешает_сохранить(люди):
    """Значок, заведённый в Filament словом наугад, остаётся и не ломает форму."""
    sql("update categories set icon = 'rocket' where slug = 'himiya'")
    pk = _id("himiya")

    _, форма, ответ = django(
        люди["content_manager"],
        ("get", f"{LIST}{pk}/change/", None),
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма("himiya", {"ru": "Химия и пластик"}, icon="rocket", category_id=pk),
        ),
    )

    assert "rocket — витрина не знает" in форма["body"]
    assert ответ["status"] == 302, ответ["body"][:3000]
    assert sql("select icon from categories where id = %s", [pk]) == [("rocket",)]


def test_без_русского_названия_не_сохраняется(люди):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма("plitka", {"en": "Tiles"})))

    assert ответ["status"] == 200
    assert "Нужно русское название" in ответ["body"]


def test_удаление(люди):
    stroy, gazobeton = _id("stroymaterialy"), _id("gazobeton")

    # Контент-менеджеру удаление не выдано
    _, чужое = django(
        люди["content_manager"], ("post", f"{LIST}{gazobeton}/delete/", {"post": "yes"})
    )
    assert чужое["status"] == 403

    # У раздела подкатегории — удалить нельзя даже суперадмину
    _, форма, занятый = django(
        люди["superadmin"],
        ("get", f"{LIST}{stroy}/change/", None),
        ("post", f"{LIST}{stroy}/delete/", {"post": "yes"}),
    )
    assert "Нельзя, на категорию ссылаются: подкатегории — 6" in форма["body"]
    assert занятый["status"] == 403
    assert sql("select count(*) from categories where parent_id = %s", [stroy]) == [(6,)]

    # Пустую — можно, вместе с переводами; удаление — в журнале
    _, свободная = django(
        люди["superadmin"], ("post", f"{LIST}{gazobeton}/delete/", {"post": "yes"})
    )
    assert свободная["status"] == 302
    assert sql("select count(*) from categories where id = %s", [gazobeton]) == [(0,)]
    assert sql(
        "select count(*) from category_translations where category_id = %s", [gazobeton]
    ) == [(0,)]
    assert журнал("deleted")["subject_label"] == "gazobeton"


@pytest.mark.parametrize(
    ("таблица", "подпись"),
    [("listings", "объявления"), ("company_category", "компании"), ("tenders", "тендеры")],
)
def test_ссылки_держат_категорию(люди, таблица, подпись):
    pk = _id("sukhofrukty")
    sql("delete from listings; delete from company_category; delete from tenders")
    [(company,)] = sql(
        "insert into companies (name, slug, created_at, updated_at) "
        "values ('ООО «Сад»', %s, now(), now()) returning id",
        [f"sad-{таблица}"],
    )

    if таблица == "listings":
        sql(
            "insert into listings (company_id, title, category_id, deleted_at, created_at, "
            "updated_at) values (%s, 'Курага', %s, now(), now(), now())",
            [company, pk],
        )
    elif таблица == "company_category":
        sql(
            "insert into company_category (company_id, category_id, created_at, updated_at) "
            "values (%s, %s, now(), now())",
            [company, pk],
        )
    else:
        sql(
            "insert into tenders (title, category_id, created_at, updated_at) "
            "values ('Закупка кураги', %s, now(), now())",
            [pk],
        )

    _, форма, удаление = django(
        люди["superadmin"],
        ("get", f"{LIST}{pk}/change/", None),
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
    )

    assert f"Нельзя, на категорию ссылаются: {подпись} — 1" in форма["body"]
    assert удаление["status"] == 403
