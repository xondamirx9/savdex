"""
CRM на Django, этап 6, шаг 3: разделы «Задачи» и «Коммуникации» вместо Filament.

- «только свои»: задачи — по исполнителю (завёл, но делать не ему — не
  видно), разговоры — по тому, кто записал; чужое по ссылке не открывается;
- задача: исполнитель по умолчанию — тот, кто ставит, created_by, срок
  по-ташкентски — в базе UTC; «Выполнена» и «Вернуть в работу» кнопкой и
  над отмеченными — строка журнала; по умолчанию только невыполненные;
- привязка к лиду или сделке — из видимых сотруднику; чужой лид не
  выбрать, прежняя привязка остаётся;
- разговор: автор — сам, «когда» — обязательно, удаление насовсем и
  только суперадмином, в журнале — номер удалённой записи (подпись —
  «Communication #N», как у AdminLog::label).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

TASKS = "/py/admin/crm/task/"
TALKS = "/py/admin/crm/communication/"
LEAD = "App\\Models\\Crm\\Lead"
DEAL = "App\\Models\\Crm\\Deal"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    люди = {
        role: сотрудник(role) for role in ("superadmin", "admin", "sales", "support", "moderator")
    }
    [(other,)] = sql(
        "insert into users (name, email, password, is_admin, admin_role, status, "
        "created_at, updated_at) values ('Другой продавец', 'sales2@savdex.uz', 'x', true, "
        "'sales', 'active', now(), now()) returning id"
    )
    люди["sales2"] = int(other)

    return люди


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from crm_communications")
    sql("delete from crm_tasks")
    sql("delete from crm_deals")
    sql("delete from crm_leads")
    sql("delete from crm_contacts")
    sql("delete from admin_actions where section in ('tasks', 'communications')")


def _строка(table: str, **поля: Any) -> int:
    columns = list(поля)
    [(pk,)] = sql(
        f"insert into {table} ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        list(поля.values()),
    )

    return int(pk)


def _задача(title: str, assignee: int | None, **поля: Any) -> int:
    return _строка("crm_tasks", title=title, assignee_id=assignee, **поля)


def _разговор(summary: str, author: int | None, **поля: Any) -> int:
    return _строка(
        "crm_communications",
        summary=summary,
        author_id=author,
        type=поля.pop("type", "call"),
        happened_at=поля.pop("happened_at", "2026-09-20 07:00:00"),
        **поля,
    )


def _форма_задачи(assignee: int, **поля: str) -> dict[str, str]:
    return {
        "title": "Позвонить",
        "assignee": str(assignee),
        "due_at": "",
        "done_at": "",
        "subject": "",
        "description": "",
        **поля,
    }


# ── Задачи: кто что видит ───────────────────────────────────────────


def test_задачи_по_исполнителю(люди):
    _задача("Моя задача", люди["sales"])
    # Завёл он, а делать не ему — в его списке дел быть не должно
    чужая = _задача("Чужая задача", люди["sales2"], created_by=люди["sales"])
    _задача("Ничья задача", None)

    _, продавец, по_ссылке = django(
        люди["sales"], ("get", TASKS, None), ("get", f"{TASKS}{чужая}/change/", None)
    )
    _, руководитель = django(люди["admin"], ("get", TASKS, None))

    assert "Моя задача" in продавец["body"]
    assert "Чужая задача" not in продавец["body"] and "Ничья задача" not in продавец["body"]
    assert по_ссылке["status"] == 302
    assert "Чужая задача" in руководитель["body"] and "Ничья задача" in руководитель["body"]


def test_модератор_задач_не_видит(люди):
    _, задачи, разговоры = django(люди["moderator"], ("get", TASKS, None), ("get", TALKS, None))

    assert (задачи["status"], разговоры["status"]) == (403, 403)


# ── Задачи: форма ───────────────────────────────────────────────────


def test_новая_задача_срок_по_ташкенту(люди):
    лид = _строка("crm_leads", title="Цемент", owner_id=люди["sales"], status="new")

    _, форма, ответ = django(
        люди["sales"],
        ("get", TASKS + "add/", None),
        (
            "post",
            TASKS + "add/",
            _форма_задачи(люди["sales"], due_at="2026-10-05T15:00", subject=f"{LEAD}:{лид}"),
        ),
    )

    # Исполнитель по умолчанию — тот, кто ставит
    assert f'<option value="{люди["sales"]}" selected>' in форма["body"]
    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql(
        "select title, assignee_id, created_by, to_char(due_at, 'YYYY-MM-DD HH24:MI'), "
        "done_at, subject_type, subject_id, description from crm_tasks"
    ) == [("Позвонить", люди["sales"], люди["sales"], "2026-10-05 10:00", None, LEAD, лид, None)]
    строка = журнал("created")
    assert (строка["section"], строка["subject_type"]) == ("tasks", "App\\Models\\Crm\\Task")


def test_чужой_лид_не_выбрать(люди):
    свой = _строка("crm_leads", title="Свой лид", owner_id=люди["sales"], status="new")
    чужой = _строка("crm_leads", title="Чужой лид", owner_id=люди["sales2"], status="new")
    _строка("crm_leads", title="Ничей лид", owner_id=None, status="new")
    _строка("crm_deals", title="Чужая сделка", owner_id=люди["sales2"], stage="new")

    _, форма, подделка = django(
        люди["sales"],
        ("get", TASKS + "add/", None),
        (
            "post",
            TASKS + "add/",
            _форма_задачи(люди["sales"], subject=f"{LEAD}:{чужой}"),
        ),
    )

    assert f"{LEAD}:{свой}" in форма["body"] and "Ничей лид" in форма["body"]
    assert "Чужой лид" not in форма["body"] and "Чужая сделка" not in форма["body"]
    assert подделка["status"] == 200
    assert sql("select count(*) from crm_tasks") == [(0,)]


def test_прежняя_привязка_остаётся(люди):
    чужой = _строка("crm_leads", title="Чужой лид", owner_id=люди["sales2"], status="new")
    pk = _задача("Задача", люди["sales"], subject_type=LEAD, subject_id=чужой)

    _, форма, ответ = django(
        люди["sales"],
        ("get", f"{TASKS}{pk}/change/", None),
        (
            "post",
            f"{TASKS}{pk}/change/",
            _форма_задачи(люди["sales"], title="Задача", subject=f"{LEAD}:{чужой}"),
        ),
    )

    assert "Лид: Чужой лид" in форма["body"]
    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql("select subject_type, subject_id from crm_tasks") == [(LEAD, чужой)]


def test_поддержка_без_лидов_в_выборе(люди):
    _строка("crm_leads", title="Какой-то лид", owner_id=None, status="new")

    _, форма = django(люди["support"], ("get", TASKS + "add/", None))

    assert форма["status"] == 200
    assert "Какой-то лид" not in форма["body"]


# ── Задачи: выполнена ───────────────────────────────────────────────


def test_выполнена_кнопкой_и_обратно(люди):
    pk = _задача("Позвонить", люди["sales"])

    _, выполнена = django(люди["sales"], ("post", f"{TASKS}{pk}/done/", {}))

    assert выполнена["status"] == 302
    assert sql("select done_at is not null from crm_tasks") == [(True,)]
    assert set(журнал("updated")["changes"]["after"]) == {"done_at"}

    _, список, все, обратно = django(
        люди["sales"],
        ("get", TASKS, None),
        ("get", TASKS + "?closed=1", None),
        ("post", f"{TASKS}{pk}/done/", {}),
    )

    # Выполненная уходит из списка по умолчанию
    assert "Позвонить" not in список["body"]
    assert "Вернуть в работу" in все["body"]
    assert обратно["status"] == 302
    assert sql("select done_at from crm_tasks") == [(None,)]


def test_чужую_не_отметить(люди):
    pk = _задача("Чужая", люди["sales2"])

    django(люди["sales"], ("post", f"{TASKS}{pk}/done/", {}))

    assert sql("select done_at from crm_tasks") == [(None,)]


def test_выполнены_отмеченные(люди):
    первая = _задача("Первая", люди["admin"])
    вторая = _задача("Вторая", люди["admin"])

    django(
        люди["admin"],
        (
            "post",
            TASKS,
            {"action": "done_selected", "_selected_action": [str(первая), str(вторая)]},
        ),
    )

    assert sql("select count(*) from crm_tasks where done_at is not null") == [(2,)]


def test_просроченная_в_списке(люди):
    _задача("Горит", люди["admin"], due_at="2020-01-01 06:00:00")
    _задача("Сделана поздно", люди["admin"], due_at="2020-01-01 06:00:00", done_at="2020-02-01")
    _задача("Без срока", люди["admin"])

    _, список, просроченные = django(
        люди["admin"], ("get", TASKS, None), ("get", TASKS + "?due=overdue", None)
    )

    assert "01.01.2020 11:00" in список["body"], "срок — по Ташкенту"
    assert "просрочена" in список["body"] and "без срока" in список["body"]
    assert "Горит" in просроченные["body"]
    assert "Без срока" not in просроченные["body"]
    assert "Сделана поздно" not in просроченные["body"]


# ── Коммуникации ────────────────────────────────────────────────────


def test_разговор_автор_и_привязка(люди):
    [(contact,)] = sql(
        "insert into crm_contacts (name, created_at, updated_at) "
        "values ('Иван', now(), now()) returning id"
    )
    сделка = _строка("crm_deals", title="Цемент", owner_id=люди["sales"], stage="new")

    _, форма, ответ = django(
        люди["sales"],
        ("get", TALKS + "add/", None),
        (
            "post",
            TALKS + "add/",
            {
                "type": "meeting",
                "happened_at": "2026-09-28T09:30",
                "contact": str(contact),
                "summary": "Договорились о пробной партии",
                "subject": f"{DEAL}:{сделка}",
                "body": "",
            },
        ),
    )

    assert 'value="call" selected' in форма["body"]
    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql(
        "select type, to_char(happened_at, 'YYYY-MM-DD HH24:MI'), contact_id, summary, body, "
        "author_id, subject_type, subject_id from crm_communications"
    ) == [
        (
            "meeting",
            "2026-09-28 04:30",
            contact,
            "Договорились о пробной партии",
            None,
            люди["sales"],
            DEAL,
            сделка,
        )
    ]
    assert журнал("created")["section"] == "communications"


def test_разговор_без_времени_не_сохраняется(люди):
    _, ответ = django(
        люди["sales"],
        ("post", TALKS + "add/", {"type": "call", "happened_at": "", "summary": "Звонок"}),
    )

    assert ответ["status"] == 200
    assert sql("select count(*) from crm_communications") == [(0,)]


def test_разговоры_по_автору(люди):
    _разговор("Мой звонок", люди["sales"])
    _разговор("Чужой звонок", люди["sales2"])

    _, продавец = django(люди["sales"], ("get", TALKS, None))
    _, руководитель = django(люди["admin"], ("get", TALKS + "?type=call", None))

    assert "Мой звонок" in продавец["body"] and "Чужой звонок" not in продавец["body"]
    assert "Мой звонок" in руководитель["body"] and "Чужой звонок" in руководитель["body"]


def test_разговор_удаляется_насовсем_суперадмином(люди):
    pk = _разговор("Звонок", люди["sales"])

    _, продавец = django(люди["sales"], ("post", f"{TALKS}{pk}/delete/", {"post": "yes"}))
    assert продавец["status"] == 403

    _, удалено = django(люди["superadmin"], ("post", f"{TALKS}{pk}/delete/", {"post": "yes"}))

    assert удалено["status"] == 302
    assert sql("select count(*) from crm_communications") == [(0,)]
    assert sql(
        "select subject_id, subject_label from admin_actions where action = 'deleted' "
        "and section = 'communications'"
    ) == [(pk, f"Communication #{pk}")], "подпись как у AdminLog::label: summary там нет"
