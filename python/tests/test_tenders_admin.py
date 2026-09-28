"""
Госзакупки: раздел «Закупки» админки на Django, загрузка файлом и
значок «Госзакупка» на сайте.

- файл Excel и CSV, заголовки на разных языках, как у загрузки Filament;
- галочка «все — госзакупки» и столбец «Госзакупка»;
- повторная загрузка обновляет, а не дублирует (по ссылке на источник,
  без неё — по заголовку и заказчику);
- строка без заголовка или с неверной датой не загружается, остальные —
  да; незнакомая категория — пустая ячейка, а не потерянная закупка;
- адрес из заголовка и номера, search_text, журнал действий;
- права: смотреть может sales, загружать — buyer_manager;
- на сайте у госзакупки government = true.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник, страна, файл

pytestmark = нужна_база

LIST = "/py/admin/tenders/tender/"
IMPORT = LIST + "import/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    страна("uz", {"ru": "Узбекистан", "en": "Uzbekistan", "uz": "O‘zbekiston"})

    return {role: сотрудник(role) for role in ("buyer_manager", "sales")}


def _xlsx(rows: list[list[Any]]) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    assert sheet is not None

    for row in rows:
        sheet.append(row)

    buffer = io.BytesIO()
    book.save(buffer)

    return buffer.getvalue()


def _csv(rows: list[list[Any]], sep: str = ";") -> bytes:
    return "\n".join(sep.join(str(c) for c in row) for row in rows).encode("utf-8-sig")


def _загрузить(uid: int, name: str, content: bytes, all_government: bool = False) -> str:
    data: dict[str, Any] = {"file": файл(name, content)}

    if all_government:
        data["all_government"] = "on"

    _, ответ = django(uid, ("post", IMPORT, data))
    assert ответ["status"] == 200, ответ["body"][:2000]

    return str(ответ["body"])


def _закупки() -> list[dict[str, Any]]:
    keys = (
        "title", "customer", "is_government", "status", "currency", "budget", "deadline",
        "country_id", "source_url", "slug", "search_text", "author_id", "published",
    )  # fmt: skip
    rows = sql(
        "select title, customer, is_government, status, currency, budget, "
        "to_char(deadline_at, 'YYYY-MM-DD HH24:MI:SS'), country_id, source_url, slug, "
        "search_text, author_id, published_at is not null from tenders order by id"
    )

    return [dict(zip(keys, r, strict=True)) for r in rows]


def test_загрузка_excel_с_галочкой(люди):
    sql("delete from tenders")
    sql("delete from admin_actions where section = 'tenders'")
    body = _загрузить(
        люди["buyer_manager"],
        "gos.xlsx",
        _xlsx(
            [
                [
                    "Наименование закупки",
                    "Заказчик",
                    "Сумма",
                    "Валюта",
                    "Срок подачи",
                    "Страна",
                    "Опубликовать",
                    "Ссылка",
                    "Непонятный столбец",
                ],
                [
                    "Поставка цемента М400",
                    "ГУП «Тошкент»",
                    "от 100 до 200 млн",
                    "сум",
                    "30.10.2026",
                    "uz",
                    "да",
                    "https://xarid.uzex.uz/lot/1",
                    "x",
                ],
                [
                    "Трубы стальные",
                    "Хокимият",
                    2500000,
                    "USD",
                    "30 октября 2026",
                    "Узбекистан",
                    "нет",
                    "-",
                    "y",
                ],
                ["", "Без заголовка", 1, "", "", "", "", "", ""],
                ["Плохая дата", "Кто-то", 1, "", "когда-нибудь", "", "", "", ""],
            ]
        ),
        all_government=True,
    )
    закупки = _закупки()

    assert [t["title"] for t in закупки] == ["Поставка цемента М400", "Трубы стальные"]
    assert all(t["is_government"] for t in закупки)
    first, second = закупки
    assert (first["status"], first["currency"], float(first["budget"])) == (
        "published", "UZS", 100_000_000.0,
    )  # fmt: skip
    assert first["deadline"] == "2026-10-30 23:59:59" and first["published"]
    assert first["country_id"] is not None and second["country_id"] == first["country_id"]
    assert second["status"] == "draft" and second["source_url"] is None
    assert first["slug"].startswith("postavka-tsementa-m400-")
    assert "sement" in first["search_text"] and first["author_id"] == люди["buyer_manager"]
    assert "Непонятный столбец" in body and "нет заголовка" in body and "не дата" in body
    assert sql(
        "select count(*) from admin_actions where section = 'tenders' and action = 'created'"
    ) == [(2,)]


def test_столбец_госзакупки_и_повторная_загрузка(люди):
    sql("delete from tenders")
    строки = [
        ["Title", "Customer", "Government tender", "Source", "Budget"],
        ["Road repair", "City hall", "yes", "https://example.com/1", "1 000 000"],
        ["Office chairs", "Bank", "no", "", "500"],
    ]
    _загрузить(люди["buyer_manager"], "tenders.csv", _csv(строки, ","))
    assert [(t["title"], t["is_government"]) for t in _закупки()] == [
        ("Road repair", True),
        ("Office chairs", False),
    ]

    # Та же ссылка — обновление; тот же заголовок и заказчик — тоже
    строки[1][4] = "2 000 000"
    строки[2][2] = "да"
    body = _загрузить(люди["buyer_manager"], "tenders.csv", _csv(строки, ","))
    закупки = _закупки()

    assert len(закупки) == 2
    assert float(закупки[0]["budget"]) == 2_000_000.0 and закупки[1]["is_government"]
    assert "обновлено: <b>2</b>" in body


def test_без_галочки_и_столбца_признак_остаётся(люди):
    sql("update tenders set is_government = true where title = 'Office chairs'")
    _загрузить(
        люди["buyer_manager"],
        "again.csv",
        _csv([["Заголовок", "Заказчик", "Бюджет"], ["Office chairs", "Bank", "700"]]),
    )
    [chairs] = [t for t in _закупки() if t["title"] == "Office chairs"]

    assert chairs["is_government"] and float(chairs["budget"]) == 700.0


def test_права(люди):
    _, список, загрузка = django(люди["sales"], ("get", LIST, None), ("get", IMPORT, None))

    assert список["status"] == 200 and "Загрузить из файла" not in список["body"]
    assert загрузка["status"] == 403

    _, список = django(люди["buyer_manager"], ("get", LIST, None))
    assert "Загрузить из файла" in список["body"]


def test_битый_файл(люди):
    body = _загрузить(люди["buyer_manager"], "broken.xlsx", b"not a workbook")

    assert "Не удалось прочитать файл" in body


def test_правка_признака_в_разделе(люди):
    [(tid,)] = sql("select id from tenders where title = 'Road repair'")
    sql("update tenders set title_i18n = %s::json, views_count = 7 where id = %s",
        ['{"en":"Road repair EN"}', tid])  # fmt: skip
    _, форма = django(люди["buyer_manager"], ("get", f"{LIST}{tid}/change/", None))
    assert форма["status"] == 200 and "is_government" in форма["body"]

    _, сохранено = django(
        люди["buyer_manager"],
        (
            "post",
            f"{LIST}{tid}/change/",
            {
                "title": "Road repair",
                "customer": "City hall",
                "currency": "UZS",
                "status": "published",
                "source_url": "https://example.com/1",
            },
        ),
    )
    assert сохранено["status"] == 302, сохранено["body"][:2000]

    # Галочку сняли; перевод и просмотры — не тронуты
    [(gov, i18n, views)] = sql(
        "select is_government, title_i18n::text, views_count from tenders where id = %s", [tid]
    )
    assert (gov, json.loads(i18n), views) == (False, {"en": "Road repair EN"}, 7)
    assert (
        sql(
            "select changes::text from admin_actions where section = 'tenders' "
            "and action = 'updated' order by id desc limit 1"
        )[0][0].count("is_government")
        == 2
    )


def test_значок_на_сайте(люди):
    """Страница закупки на Django: у госзакупки government = true."""
    from .web_site import laravel, из_django, страница

    # На минуту раньше: Django сравнивает с текущим временем без долей секунды
    [(slug,)] = sql(
        "update tenders set is_government = true, status = 'published', "
        "published_at = now() - interval '1 minute' where title = 'Road repair' returning slug"
    )

    # laravel() выгружает словари и манифест сборки, без них страница не рисуется
    with laravel() as root:
        ответ = из_django(root, f"/tenders/{slug}")

    assert ответ["status"] == 200, ответ["body"][:1000]
    assert страница(ответ["body"])["props"]["tender"]["government"] is True
