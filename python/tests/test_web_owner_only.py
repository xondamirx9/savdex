"""
Только владелец компании (savdex/web/company_profile_actions.not_owner):
контакты, документы проверки, карта и подписка, мини-сайт. Сотруднику —
403 и ничего не записано; владелец — как раньше (его сценарии — в тестах
каждого раздела).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from .factories import компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .test_web_site_actions import тарифы
from .web_site import адрес, вход, открыть, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    тарифы()
    компания(slug="mine", name="Цемент Трейд", tin="301234567")

    with адрес() as root:
        yield root


def _компания() -> int:
    return int(sql("select id from companies where slug = 'mine'")[0][0])


def снимок() -> dict[str, Any]:
    return {
        "contacts": sql("select id, type, value, label from company_contacts order by id"),
        "documents": sql("select id, type, title, is_public from company_documents order by id"),
        "subscriptions": sql("select status, auto_renew from subscriptions order by id"),
        "cards": sql("select id, last4 from payment_methods order by id"),
        "sites": sql("select status from company_sites order by id"),
    }


def данные() -> None:
    """У компании есть что менять: контакт, документ, подписка, карта, сайт — все с id 1."""
    cid = _компания()

    for table in (
        "company_contacts",
        "company_documents",
        "subscriptions",
        "payment_methods",
        "company_sites",
    ):
        sql(f"delete from {table}")
        sql(f"select setval('{table}_id_seq', 1, false)")

    sql(
        "insert into company_contacts (company_id, type, value, label, created_at, updated_at) "
        "values (%s, 'phone', '+998901112233', 'Офис', now(), now())",
        [cid],
    )
    sql(
        "insert into company_documents (company_id, type, title, file_path, is_public, "
        "created_at, updated_at) values (%s, 'license', 'Лицензия', 'docs/1.pdf', true, "
        "now(), now())",
        [cid],
    )
    sql(
        "insert into subscriptions (company_id, plan_id, status, started_at, ends_at, "
        "auto_renew, created_at, updated_at) values (%s, (select id from plans order by id "
        "limit 1), 'active', now(), now() + interval '20 days', true, now(), now())",
        [cid],
    )
    sql(
        "insert into payment_methods (company_id, provider, token, last4, is_default, "
        "created_at, updated_at) values (%s, 'uzum', 't', '4242', true, now(), now())",
        [cid],
    )
    sql(
        "insert into company_sites (company_id, subdomain, status, theme, created_at, "
        "updated_at) values (%s, 'mine', 'published', '[]', now(), now())",
        [cid],
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/cabinet/company/contacts", {"type": "phone", "value": "+998901234567"}),
        ("PATCH", "/cabinet/company/contacts/1", {"label": "Склад"}),
        ("DELETE", "/cabinet/company/contacts/1", None),
        ("POST", "/cabinet/company/files", {"type": "license", "title": "Лицензия"}),
        ("PATCH", "/cabinet/company/files/1", {"title": "Другое"}),
        ("DELETE", "/cabinet/company/files/1", None),
        ("POST", "/cabinet/billing/cancel", None),
        ("POST", "/cabinet/billing/resume", None),
        ("DELETE", "/cabinet/billing/card/1", None),
        ("POST", "/cabinet/site/unpublish", None),
    ],
)
def test_сотруднику_нельзя(сайт, method, path, body):
    cid = _компания()
    сотрудник = учётка("staff@savdex.uz", company_id=cid, company_role="manager")

    данные()
    # Снимок до запроса: после него сравнивать не с чем
    было = снимок()
    итог = отправить(
        сайт,
        path,
        lambda: None,
        снимок,
        uid=сотрудник,
        body=body,
        method=method,
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 403
    assert итог["база"] == было


@pytest.mark.parametrize(("role", "владелец"), [("owner", True), ("manager", False)])
def test_страница_знает_владельца(сайт, role, владелец):
    """По auth.company.is_owner кабинет прячет у сотрудника кнопки этих разделов."""
    uid = учётка(f"{role}@savdex.uz", company_id=_компания(), company_role=role)

    for path in ("/cabinet/company", "/cabinet/site", "/cabinet/billing"):
        ответ = открыть(сайт, path, вход(uid))
        assert ответ["status"] == 200, path
        assert страница(ответ["body"])["props"]["auth"]["company"]["is_owner"] is владелец
