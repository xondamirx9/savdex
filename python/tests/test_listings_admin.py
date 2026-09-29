"""
Объявления на Django, этап 6: раздел вместо Filament (разбор книги
Excel — tests/test_listing_workbook.py, здесь — страница загрузки).

- список без пустых черновиков мастера, отбор по статусу и корзине;
- решения: одобрить (дата публикации и срок — если не было), вернуть на
  исправление и отклонить — с причиной не короче 10 знаков; владельцу —
  уведомление, в журнале — «изменено»; решает модератор, загруженное из
  Excel — и тот, кто вправе загружать;
- правка формой: тексты по языкам (пустые переводы не хранятся),
  search_text заново, цена или «договорная»;
- фотографии: загрузить, обложка, удалить;
- корзина: удалить, вернуть, удалить насовсем — суперадмин;
- «Загрузить» — книги Excel, отчёт и образец; право listings.import.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник, файл

pytestmark = нужна_база

LIST = "/py/admin/data/listing/"
REASON = "В заголовке телефон — уберите его"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator", "support")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from user_notifications")
    sql("delete from activity_events")
    sql("delete from listing_images")
    sql("delete from listings")
    sql("delete from users where email like 'staff-%%'")
    sql("delete from companies")
    sql("delete from category_translations")
    sql("delete from categories")
    sql("delete from admin_actions where section = 'listings'")


def _компания() -> int:
    [(pk,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values ('Стройбаза', 'stroybaza-' || nextval('companies_id_seq'), 'active', now(), "
        "now()) returning id"
    )
    sql(
        "insert into users (name, email, password, company_id, status, created_at, updated_at) "
        "values ('Владелец', %s, 'x', %s, 'active', now(), now())",
        [f"staff-owner-{pk}@example.com", pk],
    )

    return int(pk)


def _категория() -> int:
    [(pk,)] = sql(
        "insert into categories (slug, sort, is_active, created_at, updated_at) "
        "values ('cement', 0, true, now(), now()) returning id"
    )
    sql(
        "insert into category_translations (category_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', 'Цемент', now(), now())",
        [pk],
    )

    return int(pk)


def _объявление(title: str = "Цемент М400 навалом", **поля: Any) -> int:
    company = поля.pop("company_id", None) or _компания()
    строка = {
        "type": "supply",
        "status": "moderation",
        "currency": "UZS",
        "description": "Цемент марки М400, навалом, доставка по городу.",
        "price": 950000,
        **поля,
    }
    columns = ["company_id", "title", *строка]
    [(pk,)] = sql(
        f"insert into listings ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [company, title, *строка.values()],
    )

    return int(pk)


def _решить(uid: int, pk: int, decision: str, note: str = "") -> dict[str, Any]:
    _, ответ = django(uid, ("post", f"{LIST}{pk}/decide/", {"decision": decision, "note": note}))

    return ответ


def _уведомления() -> list[tuple[Any, ...]]:
    return sql("select type, title, tone, body, url from user_notifications order by id")


# ── Список ──────────────────────────────────────────────────────────


def test_список_без_пустых_черновиков(люди):
    company = _компания()
    _объявление(company_id=company)
    _объявление("", status="draft", company_id=company)
    _объявление("Удалённое объявление", deleted_at="2026-09-01", company_id=company)

    _, список, корзина = django(
        люди["moderator"], ("get", LIST, None), ("get", LIST + "?trashed=1", None)
    )

    assert "Цемент М400 навалом" in список["body"] and "На проверке" in список["body"]
    assert "Удалённое объявление" not in список["body"]
    assert "Удалённое объявление" in корзина["body"]
    assert список["body"].count('class="field-listing"') == 1


# ── Решения ─────────────────────────────────────────────────────────


def test_одобрить(люди):
    pk = _объявление()

    ответ = _решить(люди["moderator"], pk, "approve")

    assert ответ["status"] == 302
    [(status, note, published, expires)] = sql(
        "select status, moderation_note, published_at is not null, "
        "extract(day from expires_at - published_at) from listings"
    )
    assert (status, note, published, int(expires)) == ("active", None, True, 90)
    assert _уведомления() == [
        (
            "moderation",
            "Объявление «Цемент М400 навалом» опубликовано",
            "success",
            None,
            "/cabinet/listings",
        )
    ]
    assert журнал("updated")["changes"]["after"]["status"] == "active"


def test_вернуть_и_отклонить_с_причиной(люди):
    pk = _объявление(status="active")

    _решить(люди["moderator"], pk, "return", "кратко")
    assert sql("select status from listings") == [("active",)], "без причины — нет"

    _решить(люди["moderator"], pk, "return", REASON)
    assert sql("select status, moderation_note from listings") == [("needs_changes", REASON)]

    второе = _объявление("Щебень фракции 5-20")
    _решить(люди["moderator"], второе, "reject", REASON)
    assert sql("select status from listings where id = %s", [второе]) == [("rejected",)]

    assert [(t, tone, url) for _, t, tone, _, url in _уведомления()] == [
        (
            "Объявление «Цемент М400 навалом» возвращено на исправление",
            "warning",
            "/cabinet/listings?status=needs_changes",
        ),
        (
            "Объявление «Щебень фракции 5-20» отклонено",
            "danger",
            "/cabinet/listings?status=rejected",
        ),
    ]


def test_решает_модератор_и_загружающий_загруженное(люди):
    своё = _объявление()
    company = sql("select company_id from listings")[0][0]
    из_excel = _объявление("Кирпич облицовочный", source="import", company_id=company)

    отказ = _решить(люди["admin"], своё, "approve")
    можно = _решить(люди["admin"], из_excel, "approve")
    поддержка = _решить(люди["support"], своё, "approve")

    assert отказ["status"] == 403 and поддержка["status"] == 403
    assert можно["status"] == 302
    assert sql("select title, status from listings order by id") == [
        ("Цемент М400 навалом", "moderation"),
        ("Кирпич облицовочный", "active"),
    ]


# ── Форма ───────────────────────────────────────────────────────────


def _форма(category: int, **поля: str) -> dict[str, str]:
    строка = {
        "type": "supply",
        "category_id": str(category),
        "title": "Цемент М500 в мешках",
        "description": "Цемент марки М500, мешки по 50 кг, доставка по городу.",
        "delivery_terms": "",
        "payment_terms": "",
        "price": "990000",
        "bundle_price": "",
        "currency": "UZS",
        "unit": "т",
        "min_order": "",
        "city_id": "",
        "expires_at": "",
        "moderation_note": "",
    }

    for name in ("title", "description", "delivery_terms", "payment_terms"):
        for code in ("uz", "en", "zh", "tr"):
            строка[f"{name}_{code}"] = ""

    return {**строка, **поля}


def test_правка_тексты_по_языкам(люди):
    category = _категория()
    pk = _объявление(title_i18n='{"en": "Old title"}')

    _, ответ = django(
        люди["admin"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма(category, title_en="Cement M500 in bags", description_uz="  "),
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:2000]
    [(title, i18n, description_i18n, search, category_id)] = sql(
        "select title, title_i18n::text, description_i18n, search_text, category_id from listings"
    )
    assert title == "Цемент М500 в мешках" and category_id == category
    assert "Cement M500 in bags" in i18n and description_i18n is None
    assert "cement" in search.lower() and "м500" in search.lower()
    assert журнал("updated")["section"] == "listings"


def test_цена_или_договорная(люди):
    category = _категория()
    pk = _объявление()

    _, без_цены, договорная = django(
        люди["admin"],
        ("post", f"{LIST}{pk}/change/", _форма(category, price="")),
        ("post", f"{LIST}{pk}/change/", _форма(category, price="", price_negotiable="on")),
    )

    assert без_цены["status"] == 200 and "Укажите цену" in без_цены["body"]
    assert договорная["status"] == 302, договорная["body"][:2000]
    assert sql("select price_negotiable, price from listings") == [(True, 950000)]


# ── Фотографии ──────────────────────────────────────────────────────


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 120, 40)).save(buffer, "PNG")

    return buffer.getvalue()


def test_фотографии(люди):
    pk = _объявление()

    _, загрузка = django(
        люди["admin"],
        (
            "post",
            f"{LIST}{pk}/photos/",
            {"photo_action": "upload", "photos": файл("a.png", _png())},
        ),
    )
    django(
        люди["admin"],
        (
            "post",
            f"{LIST}{pk}/photos/",
            {"photo_action": "upload", "photos": файл("b.png", _png())},
        ),
    )
    [(first, _), (second, _)] = sql("select id, sort from listing_images order by sort")

    django(
        люди["admin"],
        ("post", f"{LIST}{pk}/photos/", {"photo_action": "cover", "image": str(second)}),
    )
    assert sql("select id from listing_images order by sort") == [(second,), (first,)]

    django(
        люди["admin"],
        ("post", f"{LIST}{pk}/photos/", {"photo_action": "remove", "image": str(second)}),
    )

    assert загрузка["status"] == 302
    assert sql("select id, sort from listing_images") == [(first, 0)]


# ── Корзина ─────────────────────────────────────────────────────────


def test_корзина(люди):
    pk = _объявление()

    _, модератор = django(люди["moderator"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert модератор["status"] == 403

    django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert sql("select deleted_at is not null from listings") == [(True,)]

    django(люди["superadmin"], ("post", f"{LIST}{pk}/trash/", {"trash_action": "restore"}))
    assert sql("select deleted_at from listings") == [(None,)]
    assert журнал("restored")["section"] == "listings"

    django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    django(люди["superadmin"], ("post", f"{LIST}{pk}/trash/", {"trash_action": "force"}))
    assert sql("select count(*) from listings") == [(0,)]
    assert журнал("force_deleted")["section"] == "listings"


# ── Выгрузка ────────────────────────────────────────────────────────


def test_выгрузка(люди):
    _объявление()
    _объявление("Щебень фракции 5-20", status="active")

    _, модератор = django(люди["moderator"], ("get", LIST + "export/", None))
    # XLSX — двоичный файл, шаг проверки читает ответ текстом: сверяем CSV
    _, все, отобранные = django(
        люди["admin"],
        ("get", LIST + "export/?format=csv", None),
        ("get", LIST + "export/?status=active&format=csv", None),
    )

    assert модератор["status"] == 403, "выгрузка — отдельное право"
    assert "Номер,Заголовок,Компания" in все["body"]
    assert "Щебень фракции 5-20" in все["body"] and "Цемент М400 навалом" in все["body"]
    assert "Цемент М400 навалом" not in отобранные["body"], "с отборами, как на экране"
    assert журнал("exported")["section"] == "listings"


def _книга(*rows: list[str]) -> bytes:
    from openpyxl import Workbook

    from savdex.data.workbook import HEADERS

    book = Workbook()
    page: Any = book.active
    page.append(HEADERS)

    for row in rows:
        page.append(row)

    out = io.BytesIO()
    book.save(out)

    return out.getvalue()


def test_загрузка_книгами(люди):
    _компания()
    строка = ["", "Кирпич керамический М150", "Стройбаза", "", "Предложение", "1200", "UZS"]
    без_компании = ["", "Песок речной мытый", "Нет такой", "", "Предложение", "90", "UZS"]

    _, поддержка = django(люди["support"], ("get", LIST + "import/", None))
    _, страница, загрузка, образец = django(
        люди["admin"],
        ("get", LIST, None),
        (
            "post",
            LIST + "import/",
            {
                "workbooks": [
                    файл("stroy.xlsx", _книга(строка)),
                    файл("pesok.xlsx", _книга(без_компании)),
                ]
            },
        ),
        ("get", LIST + "import/template/", None),
    )
    _, не_книга = django(
        люди["admin"], ("post", LIST + "import/", {"workbooks": [файл("a.csv", b"x,y")]})
    )

    assert поддержка["status"] == 403, "загрузка — отдельное право"
    assert LIST + "import/" in страница["body"]
    assert загрузка["status"] == 200, загрузка["body"][:2000]
    assert "Создано: <b>1</b>" in загрузка["body"]
    # lcfirst у PHP кириллицу не трогает — «Строка» остаётся с заглавной
    assert "pesok.xlsx, Строка 2: компания «Нет такой» не найдена" in загрузка["body"]
    assert sql("select title, status, source from listings") == [
        ("Кирпич керамический М150", "moderation", "import")
    ]
    assert sql("select note from admin_actions where action = 'imported'") == [
        ("Книг: 2, создано: 1, обновлено: 0, фотографий: 0",)
    ]
    assert образец["status"] == 200 and образец["body"].startswith("PK")
    assert "нужна книга Excel" in не_книга["body"]
