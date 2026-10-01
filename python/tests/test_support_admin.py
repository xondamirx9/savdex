"""
Обращения в поддержку на Django, этап 6: раздел «Обращения» вместо Filament.

- раздел видят поддержка, администратор и суперадмин, продажи — нет;
  по умолчанию только открытые;
- «Взять» — ничьё мне, открытое — «В работе»; строка журнала;
- ответ клиенту — «Ждёт ответа клиента», внутренняя заметка статус не
  трогает и клиенту не видна; одна строка журнала с пометкой;
- «Закрыть» и «Открыть снова» — дата закрытия ставится и снимается сама;
- переписка видна на странице обращения;
- новое обращение: пустые поля — NULL; удаление — в корзину, суперадмином.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/support/ticket/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "support", "sales")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from support_messages")
    sql("delete from support_tickets")
    sql("delete from admin_actions where section = 'support'")


def _обращение(subject: str, **поля: Any) -> int:
    columns = ["subject", *поля]
    [(pk,)] = sql(
        f"insert into support_tickets ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [subject, *поля.values()],
    )

    return int(pk)


def test_кто_видит_и_только_открытые(люди):
    _обращение("Не приходит письмо")
    _обращение("Старый вопрос", status="closed", closed_at="2026-01-01")

    _, открытые, все = django(
        люди["support"], ("get", LIST, None), ("get", LIST + "?closed=1", None)
    )
    _, продажи = django(люди["sales"], ("get", LIST, None))

    assert открытые["status"] == 200
    assert "Не приходит письмо" in открытые["body"] and "Старый вопрос" not in открытые["body"]
    assert "Старый вопрос" in все["body"]
    assert продажи["status"] == 403


def test_взять(люди):
    pk = _обращение("Не приходит письмо")

    _, список, ответ = django(
        люди["support"], ("get", LIST, None), ("post", f"{LIST}{pk}/take/", {})
    )

    assert f"{LIST}{pk}/take/" in список["body"], "кнопка «Взять» у ничьего"
    assert ответ["status"] == 302
    assert sql("select assignee_id, status from support_tickets") == [(люди["support"], "working")]
    assert журнал("updated")["changes"]["after"] == {
        "assignee_id": люди["support"],
        "status": "working",
    }


def test_ответ_клиенту(люди):
    pk = _обращение("Не приходит письмо", status="working")

    _, ответ = django(
        люди["support"],
        ("post", f"{LIST}{pk}/reply/", {"body": "Письмо отправлено повторно."}),
    )

    assert ответ["status"] == 302
    assert sql("select status, last_reply_at is not null from support_tickets") == [
        ("waiting", True)
    ]
    assert sql("select author_id, from_staff, is_internal, body from support_messages") == [
        (люди["support"], True, False, "Письмо отправлено повторно.")
    ]
    assert sql("select count(*), max(note) from admin_actions where section = 'support'") == [
        (1, "Ответ клиенту")
    ]
    assert журнал("updated")["changes"]["after"]["status"] == "waiting"


def test_внутренняя_заметка(люди):
    pk = _обращение("Третий раз пишет", status="working")

    _, ответ, страница = django(
        люди["support"],
        (
            "post",
            f"{LIST}{pk}/reply/",
            {"body": "Вести аккуратно.", "is_internal": "1"},
        ),
        ("get", f"{LIST}{pk}/change/", None),
    )

    assert ответ["status"] == 302
    assert sql("select status from support_tickets") == [("working",)], "статус не меняется"
    assert sql("select is_internal from support_messages") == [(True,)]
    assert set(журнал("updated")["changes"]["after"]) == {"last_reply_at"}
    assert sql("select max(note) from admin_actions where section = 'support'") == [
        ("Внутренняя заметка",)
    ]
    assert "Вести аккуратно." in страница["body"]
    assert "внутренняя заметка — клиент её не видит" in страница["body"]


def test_пустой_ответ_не_пишется(люди):
    pk = _обращение("Вопрос")

    django(люди["support"], ("post", f"{LIST}{pk}/reply/", {"body": "   "}))

    assert sql("select count(*) from support_messages") == [(0,)]


def test_закрыть_и_открыть_снова(люди):
    pk = _обращение("Вопрос", status="working")

    django(люди["support"], ("post", f"{LIST}{pk}/toggle/", {}))
    assert sql("select status, closed_at is not null from support_tickets") == [("closed", True)]

    django(люди["support"], ("post", f"{LIST}{pk}/toggle/", {}))
    assert sql("select status, closed_at from support_tickets") == [("working", None)]


def test_переписка_на_странице(люди):
    pk = _обращение("Не приходит письмо", author_name="Пётр", author_email="petr@example.com")
    sql(
        "insert into support_messages (ticket_id, from_staff, is_internal, body, created_at, "
        "updated_at) values (%s, false, false, 'Письмо не пришло', now(), now())",
        [pk],
    )

    _, список, страница = django(
        люди["support"], ("get", LIST, None), ("get", f"{LIST}{pk}/change/", None)
    )

    assert "Пётр" in список["body"]
    assert '<td class="field-count">1</td>' in список["body"]
    assert "Письмо не пришло" in страница["body"] and "Клиент" in страница["body"]


def test_новое_обращение(люди):
    _, ответ = django(
        люди["admin"],
        (
            "post",
            LIST + "add/",
            {
                "subject": "Звонил клиент",
                "status": "open",
                "priority": "high",
                "channel": "phone",
                "assignee": "",
                "user": "",
                "company": "",
                "author_name": "Пётр",
                "author_email": "",
            },
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql(
        "select subject, priority, channel, assignee_id, author_name, author_email, closed_at "
        "from support_tickets"
    ) == [("Звонил клиент", "high", "phone", None, "Пётр", None, None)]
    assert журнал("created")["subject_type"] == "App\\Models\\Support\\Ticket"


def test_удаление_в_корзину_суперадмином(люди):
    pk = _обращение("Спам")

    _, поддержка = django(люди["support"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    _, суперадмин = django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))

    assert поддержка["status"] == 403
    assert суперадмин["status"] == 302
    assert sql("select deleted_at is not null from support_tickets") == [(True,)]
