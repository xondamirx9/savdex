"""
Приём объявлений от MEYOS в JSON (savdex/data/json_import.py, страница
«Ссылка для MEYOS»).

- записи — объявлениями, как строки книги Excel: компания по названию
  или ИНН, категория «Раздел → Подраздел», город, тип, цена (и
  «договорная»), переводы; новые — на проверку, «Сразу опубликовать» —
  на витрину;
- повторная загрузка того же файла обновляет, а не плодит дубли;
- компании нет в справочнике — объявление достаётся компании из окна;
- запись без заголовка — в отчёт, остальные загружаются;
- фото по ссылке на внутренний адрес не скачивается — заметка;
- не JSON — ошибка формы, ничего не загружено;
- загружают те, у кого listings.import; строка журнала «imported».

Скачивание фото с публичного адреса — test_скачивание_фото, без базы.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import http.server
import io
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from savdex.data import json_import

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник, страна, файл

PAGE = "/py/admin/integrations/meyos/"


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 120, 40)).save(buffer, "PNG")

    return buffer.getvalue()


# ── Без базы ────────────────────────────────────────────────────────


def test_запись_в_поля_строки():
    fields, texts = json_import.fields_of(
        {
            "title": "Диван угловой",
            "type": "demand",
            "company": {"name": "Мебель Плюс", "tin": "301234567"},
            "category": {"name": "Мебель для дома", "parent": {"name": "Мебель"}},
            "price": None,
            "price_negotiable": True,
            "title_i18n": {"uz": "Burchak divan", "fr": "Canapé"},
        }
    )

    assert fields == {
        "title": "Диван угловой",
        "type": "Запрос",
        "company": "301234567",
        "category_id": "Мебель → Мебель для дома",
        "price": "договорная",
    }
    assert texts == {"uz": {"title": "Burchak divan"}}


def test_скачивание_фото(tmp_path, monkeypatch):
    """С публичного адреса — скачивается; внутренний — нет (без подмены проверки)."""
    png = _png()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/move":
                self.send_response(302)
                self.send_header("Location", "/a.png")
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(png)

        def log_message(self, *args: Any) -> None:
            return None

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    try:
        with pytest.raises(ValueError, match="не публичный"):
            json_import.download(base + "/a.png", tmp_path, 1)

        monkeypatch.setattr(json_import, "_public", lambda host: True)
        path = json_import.download(base + "/move", tmp_path, 2)
        assert Path(path).read_bytes() == png

        with pytest.raises(ValueError, match="не http"):
            json_import.download("file:///etc/passwd", tmp_path, 3)
    finally:
        server.shutdown()


# ── Загрузка ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    [(city,)] = sql(
        "insert into cities (country_id, slug, sort, is_active, created_at, updated_at) "
        "values (%s, 'tashkent', 0, true, now(), now()) returning id",
        [uz],
    )
    sql(
        "insert into city_translations (city_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', 'Ташкент', now(), now())",
        [city],
    )

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator")}


@pytest.fixture
def чисто(люди) -> dict[str, int]:
    sql("delete from listing_images")
    sql("delete from listings")
    sql("delete from companies")
    sql("delete from category_translations")
    sql("delete from categories")
    sql("delete from admin_actions where section = 'listings'")

    def категория(slug: str, name: str, parent: int | None = None) -> int:
        [(pk,)] = sql(
            "insert into categories (slug, parent_id, sort, is_active, created_at, updated_at) "
            "values (%s, %s, 0, true, now(), now()) returning id",
            [slug, parent],
        )
        sql(
            "insert into category_translations (category_id, locale, name, created_at, "
            "updated_at) values (%s, 'ru', %s, now(), now())",
            [pk, name],
        )

        return int(pk)

    мебель = категория("mebel", "Мебель")
    дом = категория("mebel-dlya-doma", "Мебель для дома", мебель)
    [(своя,)] = sql(
        "insert into companies (name, slug, tin, status, created_at, updated_at) values "
        "('Мебель Плюс', 'mebel-plus', '301234567', 'active', now(), now()) returning id"
    )
    [(запасная,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) values "
        "('MEYOS', 'meyos', 'active', now(), now()) returning id"
    )

    return {"дом": дом, "своя": int(своя), "запасная": int(запасная)}


ФАЙЛ = {
    "items": [
        {
            "title": "Диван угловой «Мадрид»",
            "description": "Ткань велюр, 280×180 см",
            "type": "supply",
            "company": {"name": "Мебель Плюс", "tin": "301234567"},
            "category": {"name": "Мебель для дома", "parent": {"name": "Мебель"}},
            "city": "Ташкент",
            "price": 7500000,
            "currency": "UZS",
            "unit": "шт",
            "title_i18n": {"uz": "Burchak divan «Madrid»"},
            "photos": ["http://127.0.0.1/inner.jpg"],
        },
        {
            "title": "Шкаф-купе на заказ",
            "company": "Фабрика, которой нет на площадке",
            "category": "Мебель → Мебель для дома",
            "price_negotiable": True,
        },
        {"description": "Без заголовка"},
    ]
}


def _загрузить(uid: int, data: Any = ФАЙЛ, **поля: str) -> dict[str, Any]:
    content = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
    _, ответ = django(
        uid,
        ("post", PAGE, {"act": "import", "file": файл("meyos.json", content), **поля}),
    )

    return ответ


@нужна_база
def test_загрузка_как_книга(люди, чисто):
    ответ = _загрузить(люди["admin"], default_company="MEYOS")

    assert ответ["status"] == 200, ответ["body"][:1500]
    assert "Записей: 3, создано: 2, обновлено: 0" in ответ["body"]
    assert "Запись 3: не заполнен заголовок" in ответ["body"]
    assert "адрес не публичный" in ответ["body"], "фото с внутреннего адреса не скачивается"

    rows = sql(
        "select title, company_id, category_id, city_id is not null, price, price_negotiable, "
        "status, source, title_i18n::text from listings order by id"
    )
    диван, шкаф = rows
    assert диван[:8] == (
        "Диван угловой «Мадрид»",
        чисто["своя"],
        чисто["дом"],
        True,
        7500000,
        False,
        "moderation",
        "import",
    )
    assert json.loads(диван[8]) == {"uz": "Burchak divan «Madrid»"}
    assert шкаф[1] == чисто["запасная"], "компании нет — достаётся компании из окна"
    assert шкаф[5] is True, "договорная"

    [(note,)] = sql("select note from admin_actions where action = 'imported'")
    assert note == "MEYOS, JSON: записей 3, создано: 2, обновлено: 0, фотографий: 0"


@нужна_база
def test_повторно_обновляет_и_публикует(люди, чисто):
    _загрузить(люди["admin"], default_company="MEYOS")
    ответ = _загрузить(люди["admin"], default_company="MEYOS", publish="on")

    assert "создано: 0, обновлено: 2" in ответ["body"]
    assert sql("select count(*) from listings") == [(2,)]
    assert {s for (s,) in sql("select status from listings")} == {"active"}


@нужна_база
def test_не_json_и_права(люди, чисто):
    битый = _загрузить(люди["admin"], b"{not json")
    _, модератор = django(
        люди["moderator"],
        ("post", PAGE, {"act": "import", "file": файл("a.json", b"[]")}),
    )

    assert "Файл не читается как JSON" in битый["body"]
    assert sql("select count(*) from listings") == [(0,)]
    assert модератор["status"] == 403
    assert sql("select count(*) from admin_actions where action = 'imported'") == [(0,)]
