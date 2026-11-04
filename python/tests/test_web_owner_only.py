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
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="mine", name="Цемент Трейд", tin="301234567")

    with адрес() as root:
        yield root


def _компания() -> int:
    return int(sql("select id from companies where slug = 'mine'")[0][0])


def снимок() -> dict[str, Any]:
    return {
        "contacts": sql("select count(*) from company_contacts")[0][0],
        "documents": sql("select count(*) from company_documents")[0][0],
        "subscriptions": sql("select status, auto_renew from subscriptions order by id"),
        "sites": sql("select status from company_sites order by id"),
    }


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
    assert итог["база"] == снимок()
