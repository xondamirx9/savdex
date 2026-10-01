"""
CRM на Django, этап 6, шаг 2: разделы «Лиды» и «Сделки» вместо Filament.

- «только свои»: продавец видит свои лиды и нераспределённые, сделки —
  только свои; чужое по прямой ссылке не открывается и не правится;
- «Взять себе» — нераспределённый лид мне, новый — сразу в работу;
- «В сделку» — компания, контакт и ответственный в новую сделку, лид
  «Стал сделкой», в журнале — сделка «Из лида №N»; закрытый лид — нет;
- сделка: дата закрытия ставится и снимается сама, сумма «46 386 000 сум»,
  «Итого» по отобранным; проверки форм;
- по умолчанию в списках — только то, что в работе.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LEADS = "/py/admin/crm/lead/"
DEALS = "/py/admin/crm/deal/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    люди = {role: сотрудник(role) for role in ("superadmin", "admin", "support", "moderator")}
    люди["sales"] = сотрудник("sales")
    [(other,)] = sql(
        "insert into users (name, email, password, is_admin, admin_role, status, "
        "created_at, updated_at) values ('Другой продавец', 'sales2@savdex.uz', 'x', true, "
        "'sales', 'active', now(), now()) returning id"
    )
    люди["sales2"] = int(other)

    return люди


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from crm_deals")
    sql("delete from crm_leads")
    sql("delete from crm_contacts")
    sql("delete from companies")
    sql("delete from admin_actions where section in ('leads', 'deals')")


def _лид(title: str, owner: int | None, status: str = "new", **поля: Any) -> int:
    columns = ["title", "owner_id", "status", *поля]
    [(pk,)] = sql(
        f"insert into crm_leads ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [title, owner, status, *поля.values()],
    )

    return int(pk)


def _сделка(title: str, owner: int | None, stage: str = "new", **поля: Any) -> int:
    columns = ["title", "owner_id", "stage", *поля]
    [(pk,)] = sql(
        f"insert into crm_deals ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [title, owner, stage, *поля.values()],
    )

    return int(pk)


def _действие(uid: int, url: str, action: str, ids: list[int]) -> dict[str, Any]:
    _, ответ = django(
        uid, ("post", url, {"action": action, "_selected_action": [str(i) for i in ids]})
    )

    return ответ


# ── Кто что видит ───────────────────────────────────────────────────


def test_продавец_видит_свои_и_нераспределённые_лиды(люди):
    _лид("Мой лид", люди["sales"])
    _лид("Ничей лид", None)
    чужой = _лид("Чужой лид", люди["sales2"])

    _, продавец, руководитель, по_ссылке = (
        *django(люди["sales"], ("get", LEADS, None), ("get", f"{LEADS}{чужой}/change/", None))[:2],
        django(люди["admin"], ("get", LEADS, None))[1],
        django(люди["sales"], ("get", f"{LEADS}{чужой}/change/", None))[1],
    )

    assert "Мой лид" in продавец["body"] and "Ничей лид" in продавец["body"]
    assert "Чужой лид" not in продавец["body"]
    assert "Чужой лид" in руководитель["body"]
    # Чужой по ссылке не открывается: Django уводит с «не найдено»
    assert по_ссылке["status"] == 302


def test_чужой_лид_не_правится_по_ссылке(люди):
    чужой = _лид("Чужой лид", люди["sales2"])

    django(
        люди["sales"],
        (
            "post",
            f"{LEADS}{чужой}/change/",
            {"title": "Взломан", "source": "site", "status": "new"},
        ),
    )

    assert sql("select title from crm_leads where id = %s", [чужой]) == [("Чужой лид",)]


def test_продавец_видит_только_свои_сделки(люди):
    _сделка("Моя сделка", люди["sales"])
    _сделка("Ничья сделка", None)
    _сделка("Чужая сделка", люди["sales2"])

    _, список = django(люди["sales"], ("get", DEALS, None))

    assert "Моя сделка" in список["body"]
    assert "Ничья сделка" not in список["body"] and "Чужая сделка" not in список["body"]


def test_поддержка_лидов_не_видит(люди):
    _, лиды = django(люди["support"], ("get", LEADS, None))

    assert лиды["status"] == 403


# ── Взять себе ──────────────────────────────────────────────────────


def test_взять_себе_кнопкой(люди):
    pk = _лид("Цемент", None)

    _, ответ = django(люди["sales"], ("post", f"{LEADS}{pk}/claim/", {}))

    assert ответ["status"] == 302
    assert sql("select owner_id, status from crm_leads where id = %s", [pk]) == [
        (люди["sales"], "working")
    ]
    assert журнал("updated")["changes"]["after"] == {"owner_id": люди["sales"], "status": "working"}


def test_взять_себе_отмеченные_и_уже_занятый(люди):
    ничей = _лид("Ничей", None, status="qualified")
    занятый = _лид("Занятый", люди["sales2"])

    _действие(люди["admin"], LEADS, "claim_selected", [ничей, занятый])

    assert sql("select id, owner_id, status from crm_leads order by id") == [
        (ничей, люди["admin"], "qualified"),
        (занятый, люди["sales2"], "new"),
    ]


def test_взятый_пропадает_из_списка_другого_продавца(люди):
    pk = _лид("Цемент", None)

    django(люди["sales"], ("post", f"{LEADS}{pk}/claim/", {}))
    _, список = django(люди["sales2"], ("get", LEADS, None))

    assert "Цемент" not in список["body"]


# ── В сделку ────────────────────────────────────────────────────────


def test_лид_превращается_в_сделку(люди):
    [(company,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values ('Стройбаза', 'stroybaza', 'active', now(), now()) returning id"
    )
    [(contact,)] = sql(
        "insert into crm_contacts (name, company_id, created_at, updated_at) "
        "values ('Иван', %s, now(), now()) returning id",
        [company],
    )
    pk = _лид("Цемент М400", люди["sales"], company_id=company, contact_id=contact)

    _, ответ = django(люди["sales"], ("post", f"{LEADS}{pk}/convert/", {}))

    assert ответ["status"] == 302 and "/crm/deal/" in str(ответ["location"])
    assert sql(
        "select title, company_id, contact_id, lead_id, owner_id, stage, amount, currency "
        "from crm_deals"
    ) == [("Цемент М400", company, contact, pk, люди["sales"], "new", 0, "UZS")]
    assert sql("select status from crm_leads where id = %s", [pk]) == [("converted",)]
    # Одна строка о сделке, с пометкой — у Filament их было две
    assert sql(
        "select count(*), max(note) from admin_actions where section = 'deals' "
        "and action = 'created'"
    ) == [(1, f"Из лида №{pk}")]
    assert журнал("updated")["section"] == "leads"


def test_ничей_лид_в_сделку_получает_ответственного(люди):
    pk = _лид("Ничей", None)

    _действие(люди["admin"], LEADS, "convert_selected", [pk])

    assert sql("select owner_id from crm_deals") == [(люди["admin"],)]


def test_закрытый_лид_в_сделку_не_превращается(люди):
    pk = _лид("Отказ", люди["sales"], status="lost", lost_reason="дорого")

    django(люди["sales"], ("post", f"{LEADS}{pk}/convert/", {}))
    _, страница = django(люди["sales"], ("get", f"{LEADS}{pk}/change/", None))

    assert sql("select count(*) from crm_deals") == [(0,)]
    assert "В сделку" not in страница["body"]


# ── Формы ───────────────────────────────────────────────────────────


def test_отказ_без_причины_не_сохраняется(люди):
    _, ответ = django(
        люди["sales"],
        ("post", LEADS + "add/", {"title": "Лид", "source": "call", "status": "lost"}),
    )

    assert ответ["status"] == 200 and "Укажите причину отказа" in ответ["body"]
    assert sql("select count(*) from crm_leads") == [(0,)]


def test_новый_лид_с_пустыми_полями(люди):
    _, ответ = django(
        люди["sales"],
        (
            "post",
            LEADS + "add/",
            {
                "title": "Поставка цемента",
                "source": "call",
                "status": "new",
                "owner": "",
                "contact_name": "",
                "note": "",
            },
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql("select owner_id, contact_name, note from crm_leads") == [(None, None, None)]
    assert журнал("created")["subject_label"] == "Поставка цемента"


def test_в_ответственные_только_с_правом(люди):
    _, форма = django(люди["admin"], ("get", LEADS + "add/", None))

    assert "Другой продавец" in форма["body"]
    assert "Сотрудник moderator" not in форма["body"]


# ── Сделки ──────────────────────────────────────────────────────────


def _форма_сделки(owner: int, **поля: str) -> dict[str, str]:
    return {
        "title": "Цемент",
        "stage": "new",
        "owner": str(owner),
        "amount": "0",
        "currency": "UZS",
        **поля,
    }


def test_дата_закрытия_ставится_и_снимается(люди):
    _, создана = django(
        люди["sales"], ("post", DEALS + "add/", _форма_сделки(люди["sales"], stage="won"))
    )
    assert создана["status"] == 302, создана["body"][:1500]
    [(pk, закрыта)] = sql("select id, closed_at is not null from crm_deals")
    assert закрыта

    django(
        люди["sales"],
        ("post", f"{DEALS}{pk}/change/", _форма_сделки(люди["sales"], stage="negotiation")),
    )

    assert sql("select closed_at from crm_deals where id = %s", [pk]) == [(None,)]


def test_проверки_формы_сделки(люди):
    _, без_причины, минус, без_ответственного = django(
        люди["sales"],
        ("post", DEALS + "add/", _форма_сделки(люди["sales"], stage="lost")),
        ("post", DEALS + "add/", _форма_сделки(люди["sales"], amount="-5")),
        ("post", DEALS + "add/", {**_форма_сделки(люди["sales"]), "owner": ""}),
    )

    assert "Укажите причину проигрыша" in без_причины["body"]
    assert "не может быть отрицательной" in минус["body"]
    assert без_ответственного["status"] == 200
    assert sql("select count(*) from crm_deals") == [(0,)]


def test_сумма_итого_и_открытые_по_умолчанию(люди):
    _сделка("Большая", люди["admin"], amount=46386000)
    _сделка("Малая", люди["admin"], amount=14000)
    _сделка("Закрытая сделка", люди["admin"], stage="won", amount=1000)

    _, открытые, все = django(
        люди["admin"], ("get", DEALS, None), ("get", DEALS + "?closed=1", None)
    )

    assert "46 386 000 сум" in открытые["body"]
    assert "Закрытая сделка" not in открытые["body"]
    assert "46 400 000" in открытые["body"], "итого по отобранным"
    assert "Закрытая сделка" in все["body"]
