"""
Компании на Django, этап 6: раздел вместо Filament (рисунок эмблемы и
разбор таблицы — tests/test_company_emblem.py, test_company_import.py;
здесь — кнопки и страница загрузки).

- список: ИНН под названием, вкладки «Поставщики» и «Покупатели» (у
  «оба» — в обеих), менеджер поставщиков открывает свою по умолчанию;
- новая компания: адрес и search_text сами; правка формой — строка журнала;
- верификация — владельцу уведомление; партнёрство — вид и порядок;
- логотип: загрузить и снять;
- блокировка с причиной (объявления уходят из выдачи) и разблокировка;
- корзина: удалить, вернуть, удалить насовсем — суперадмин;
- эмблема: кнопкой у компании, массово — только без логотипа;
- выгрузка — право companies.export, загрузка таблицей — companies.import.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник, файл

pytestmark = нужна_база

LIST = "/py/admin/data/companyrecord/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {
        role: сотрудник(role)
        for role in ("superadmin", "admin", "moderator", "supplier_manager", "sales")
    }


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from user_notifications")
    sql("delete from activity_events")
    sql("delete from listings")
    sql("delete from users where email like 'staff-%%'")
    sql("delete from companies")
    sql("delete from admin_actions where section = 'companies'")


def _компания(name: str = "Стройбаза", **поля: Any) -> int:
    строка = {"primary_role": "both", "status": "active", **поля}
    columns = ["name", "slug", *строка]
    [(pk,)] = sql(
        f"insert into companies ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [name, name.lower().replace(" ", "-"), *строка.values()],
    )
    sql(
        "insert into users (name, email, password, company_id, status, created_at, updated_at) "
        "values ('Владелец', %s, 'x', %s, 'active', now(), now())",
        [f"staff-{pk}@example.com", pk],
    )

    return int(pk)


def _действие(uid: int, pk: int, **данные: Any) -> dict[str, Any]:
    _, ответ = django(uid, ("post", f"{LIST}{pk}/act/", данные))

    return ответ


def test_список_и_вкладки(люди):
    _компания("Поставщик Цемента", primary_role="supplier", tin="123456789")
    _компания("Закупщик Кирпича", primary_role="buyer")
    _компания("Торговый Дом", primary_role="both")

    _, все, покупатели = django(
        люди["admin"], ("get", LIST, None), ("get", LIST + "?tab=buyers", None)
    )
    _, менеджер = django(люди["supplier_manager"], ("get", LIST, None))

    assert "ИНН 123456789" in все["body"] and "ИНН не указан" in все["body"]
    assert "Поставщик Цемента" not in покупатели["body"]
    assert "Закупщик Кирпича" in покупатели["body"] and "Торговый Дом" in покупатели["body"]
    assert "Закупщик Кирпича" not in менеджер["body"], "своя вкладка по умолчанию"
    assert "Торговый Дом" in менеджер["body"]


def _форма(**поля: str) -> dict[str, str]:
    return {
        "name": "Новая Стройка",
        "legal_form": "legal",
        "legal_name": "",
        "tin": "",
        "type": "",
        "primary_role": "both",
        "founded_year": "",
        "country_id": "",
        "city_id": "",
        "address": "",
        "phone": "",
        "email": "",
        "website": "",
        "contact_person": "",
        "telegram": "",
        "whatsapp": "",
        "description": "",
        "source_note": "",
        "employees_range": "",
        "response_time_hours": "",
        **поля,
    }


def test_новая_и_правка(люди):
    _, создана = django(
        люди["admin"], ("post", LIST + "add/", _форма(legal_name="ООО Новая Стройка"))
    )
    assert создана["status"] == 302, создана["body"][:2000]
    [(pk, slug, search, tin)] = sql("select id, slug, search_text, tin from companies")
    assert slug == "novaia-stroika" or slug.startswith("novaya") or "stro" in slug
    assert "стройка" in search and tin is None
    assert журнал("created")["section"] == "companies"

    _, правка, год = django(
        люди["admin"],
        ("post", f"{LIST}{pk}/change/", _форма(tin="123456789", legal_name="ООО Новая Стройка")),
        ("post", f"{LIST}{pk}/change/", _форма(founded_year="1700")),
    )
    assert правка["status"] == 302
    assert год["status"] == 200, "год основания — от 1800"
    assert журнал("updated")["changes"]["after"] == {"tin": "123456789"}


def test_верификация_и_партнёрство(люди):
    pk = _компания()

    _действие(люди["moderator"], pk, act="verify", level="2")
    _действие(люди["moderator"], pk, act="partner", tier="multi", sort="5")

    assert sql(
        "select verification_level, verified_by is not null, partner_tier, partner_sort "
        "from companies"
    ) == [(2, True, "multi", 5)]
    assert sql("select title, tone, url from user_notifications") == [
        ("Компания прошла проверку: Проверена", "success", "/cabinet/company")
    ]

    _действие(люди["moderator"], pk, act="verify", level="0")
    _действие(люди["moderator"], pk, act="partner", tier="none", sort="")
    assert sql("select verification_level, verified_at, partner_tier from companies") == [
        (0, None, None)
    ]
    assert журнал("updated")["section"] == "companies"


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (20, 120, 200)).save(buffer, "PNG")

    return buffer.getvalue()


def test_логотип(люди):
    pk = _компания()

    django(
        люди["admin"], ("post", f"{LIST}{pk}/act/", {"act": "logo", "file": файл("l.png", _png())})
    )
    [(path,)] = sql("select logo_path from companies")
    assert path and path.startswith(f"companies/{pk}/")

    _действие(люди["admin"], pk, act="logo")
    assert sql("select logo_path from companies") == [(None,)]


def test_блокировка(люди):
    pk = _компания()
    sql(
        "insert into listings (company_id, type, title, status, currency, created_at, "
        "updated_at) values (%s, 'supply', 'Цемент', 'active', 'UZS', now(), now())",
        [pk],
    )

    _действие(люди["admin"], pk, act="block", reason="кратко")
    assert sql("select status from companies") == [("active",)], "без причины — нет"

    _действие(люди["admin"], pk, act="block", reason="Продавал чужой товар под своим именем")
    assert sql("select status, blocked_at is not null from companies") == [("blocked", True)]
    assert sql("select status from listings") == [("archived",)]

    _действие(люди["admin"], pk, act="block")
    assert sql("select status, blocked_reason, blocked_at from companies") == [
        ("active", None, None)
    ]


def test_продажи_смотрят_но_не_решают(люди):
    pk = _компания()

    _, список = django(люди["sales"], ("get", LIST, None))
    ответ = _действие(люди["sales"], pk, act="verify", level="2")

    assert список["status"] == 200
    assert ответ["status"] == 403
    assert sql("select verification_level from companies") == [(0,)]


def test_корзина(люди):
    pk = _компания()

    _, админ = django(люди["admin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert админ["status"] == 403

    django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert sql("select deleted_at is not null from companies") == [(True,)]

    _действие(люди["superadmin"], pk, act="restore")
    assert sql("select deleted_at from companies") == [(None,)]

    django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    _действие(люди["superadmin"], pk, act="force")
    assert sql("select count(*) from companies") == [(0,)]
    assert журнал("force_deleted")["section"] == "companies"


def test_выгрузка(люди):
    _компания("Стройбаза", tin="123456789")

    _, модератор = django(люди["moderator"], ("get", LIST + "export/", None))
    _, csv = django(люди["admin"], ("get", LIST + "export/?format=csv", None))

    assert модератор["status"] == 403
    assert "ИНН,Название" in csv["body"] and "123456789,Стройбаза" in csv["body"]
    assert журнал("exported")["section"] == "companies"


def test_эмблема(люди):
    без_логотипа = _компания("Стройбаза")
    с_логотипом = _компания("Кирпичный Двор", logo_path="companies/x/logo.webp")

    django(
        люди["admin"],
        (
            "post",
            LIST,
            {"action": "emblems_selected", "_selected_action": [без_логотипа, с_логотипом]},
        ),
    )
    assert sql("select id, logo_path from companies order by id") == [
        (без_логотипа, f"companies/{без_логотипа}/emblem.svg"),
        (с_логотипом, "companies/x/logo.webp"),
    ], "массово занятые логотипы не трогаются"

    _действие(люди["admin"], с_логотипом, act="emblem")
    assert sql("select logo_path from companies where id = %s", [с_логотипом]) == [
        (f"companies/{с_логотипом}/emblem.svg",)
    ], "кнопкой у компании — заменяет"
    assert _действие(люди["sales"], без_логотипа, act="emblem")["status"] == 403


def test_загрузка_таблицей(люди):
    _компания("Стройбаза", tin="123456789")
    таблица = "Название,ИНН,Телефон\nСтройбаза,123456789,+998 90 123 45 67\nНовый Двор,,\n"

    _, продажи = django(люди["sales"], ("get", LIST + "import/", None))
    _, список, загрузка = django(
        люди["admin"],
        ("get", LIST, None),
        ("post", LIST + "import/", {"file": файл("c.csv", таблица.encode())}),
    )

    assert продажи["status"] == 403
    assert LIST + "import/" in список["body"]
    assert загрузка["status"] == 200
    assert "Новых: <b>1</b>" in загрузка["body"] and "обновлено: <b>1</b>" in загрузка["body"]
    assert sql("select name, phone from companies order by id") == [
        ("Стройбаза", "+998 90 123 45 67"),
        ("Новый Двор", None),
    ]
    assert журнал("imported")["section"] == "companies"
