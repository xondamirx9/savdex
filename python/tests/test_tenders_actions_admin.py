"""
Раздел «Тендеры» на Django вместо Filament (этап 6): то, что было только
в TendersTable.

- список: заказчик под заголовком, бюджет «1 500 000 UZS», «На сайте» у
  опубликованной и «Опубликовать» у остальных;
- «Опубликовать» — кнопкой и над отмеченными: дата публикации остаётся,
  если была; «В архив» над отмеченными; строки журнала «изменено»;
- удаление над отмеченными — только с правом удалять (суперадмин);
- загрузка файлом пишет строку журнала «Загрузка».

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник, файл

pytestmark = нужна_база

LIST = "/py/admin/tenders/tender/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "moderator", "sales")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from tenders")
    sql("delete from admin_actions where section = 'tenders'")


def _тендер(title: str, **поля: Any) -> int:
    строка = {"status": "draft", "currency": "UZS", "slug": title.lower().replace(" ", "-"), **поля}
    columns = ["title", *строка]
    [(pk,)] = sql(
        f"insert into tenders ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [title, *строка.values()],
    )

    return int(pk)


def test_список_и_кнопки(люди):
    черновик = _тендер("Кирпич", customer="Стройтрест", budget=1500000)
    _тендер("Цемент", status="published")

    _, модератор = django(люди["moderator"], ("get", LIST, None))
    _, продажи = django(люди["sales"], ("get", LIST, None))

    body = модератор["body"]
    assert "Стройтрест" in body and "1 500 000 UZS" in body
    assert 'href="/tenders/цемент"' in body
    assert f"{LIST}{черновик}/publish/" in body
    assert f"{LIST}{черновик}/publish/" not in продажи["body"], "без правки — без кнопки"


def test_опубликовать_кнопкой(люди):
    pk = _тендер("Кирпич")

    _, ответ = django(люди["moderator"], ("post", f"{LIST}{pk}/publish/", {}))

    assert ответ["status"] == 302
    assert sql("select status, published_at is not null from tenders") == [("published", True)]
    assert журнал("updated")["changes"]["after"]["status"] == "published"


def test_опубликовать_и_в_архив_отмеченные(люди):
    давний = _тендер("Кирпич", published_at="2026-01-02 03:04:05")
    новый = _тендер("Цемент")
    в_архив = _тендер("Арматура", status="published")

    django(
        люди["moderator"],
        (
            "post",
            LIST,
            {"action": "publish_selected", "_selected_action": [str(давний), str(новый)]},
        ),
        ("post", LIST, {"action": "archive_selected", "_selected_action": [str(в_архив)]}),
    )

    assert sql("select title, status, to_char(published_at, 'YYYY') from tenders order by id") == [
        ("Кирпич", "published", "2026"),
        ("Цемент", "published", sql("select to_char(now(), 'YYYY')")[0][0]),
        ("Арматура", "archived", None),
    ]


def test_удаление_только_суперадмин(люди):
    pk = _тендер("Кирпич")

    django(
        люди["moderator"],
        ("post", LIST, {"action": "delete_selected", "_selected_action": [str(pk)], "post": "yes"}),
    )
    assert sql("select count(*) from tenders") == [(1,)]

    django(
        люди["superadmin"],
        ("post", LIST, {"action": "delete_selected", "_selected_action": [str(pk)], "post": "yes"}),
    )
    assert sql("select count(*) from tenders") == [(0,)]


def test_загрузка_пишет_строку_журнала(люди):
    csv = "Заголовок;Заказчик\nКирпич М150;Стройтрест\n".encode("utf-8-sig")

    _, ответ = django(люди["superadmin"], ("post", LIST + "import/", {"file": файл("t.csv", csv)}))

    assert ответ["status"] == 200
    assert журнал("imported")["section"] == "tenders"
