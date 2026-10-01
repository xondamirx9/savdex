"""
Этап 7, шаг 59: «Жалобы на контакты» на Django вместо страницы Filament.

«Вернуть списанное» и «Отказать» — база и журнал после кнопки (как
было у ModerationService Laravel): кредит — в кошелёк с
историей «complaint_refund», контакт по тарифу — в месячный лимит,
дважды не возвращается; уведомление компании; строка журнала с
пометкой. Формулировка — от 15 знаков. Решает модератор и
администратор; поддержка раздел видит, но не решает.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .factories import компания, пользователь
from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/finance/complaint/"
ПРИЧИНА = "Контакт проверен, компания не отвечает — возвращаем"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    a = компания(slug="buyer", name="ООО Покупатель")
    компания(slug="seller", name="ООО Продавец")
    пользователь(company_id=a)

    return {role: сотрудник(role) for role in ("moderator", "admin", "support", "finance")}


def сброс(
    *, spent: int = 1, refunded: bool = False, кошелёк: bool = True, удалена: bool = False
) -> None:
    sql(
        "truncate contact_unlocks, wallets, wallet_transactions, user_notifications, "
        "activity_events, admin_actions restart identity cascade"
    )
    sql("update companies set deleted_at = %s where slug = 'buyer'", [
        "2026-09-01 00:00:00" if удалена else None
    ])  # fmt: skip
    sql(
        "insert into contact_unlocks (company_id, target_company_id, credits_spent, status, "
        "complaint_status, complaint_reason, complained_at, refunded, created_at, updated_at) "
        "select b.id, s.id, %s, 'new', 'pending', 'Телефон не отвечает третью неделю', "
        "now() - interval '2 days', %s, now() - interval '5 days', now() - interval '2 days' "
        "from companies b, companies s where b.slug = 'buyer' and s.slug = 'seller'",
        [spent, refunded],
    )

    if кошелёк:
        sql(
            "insert into wallets (company_id, credits, contacts_used_this_period, created_at, "
            "updated_at) select id, 2, 3, now() - interval '9 days', now() - interval '9 days' "
            "from companies where slug = 'buyer'"
        )


def снимок() -> dict[str, Any]:
    return {
        "unlocks": sql(
            "select complaint_status, refunded, moderator_note, moderated_by, "
            "moderated_at is not null from contact_unlocks"
        ),
        "wallets": sql("select credits, contacts_used_this_period from wallets"),
        "wallet_log": sql(
            "select kind, amount, balance_after, reason, subject_type, subject_id, user_id "
            "from wallet_transactions"
        ),
        "notifications": sql("select type, title, body, tone, url from user_notifications"),
        "events": sql("select type, tone, message, url from activity_events"),
        "journal": sql(
            "select user_id, action, section, subject_type, subject_id, subject_label, changes, "
            "note from admin_actions order by id"
        ),
    }


def test_кто_видит(люди):
    сброс()

    _, модератор = django(люди["moderator"], ("get", LIST, None))
    _, поддержка, решить = django(
        люди["support"], ("get", LIST, None), ("post", LIST + "1/accept/", {"note": ПРИЧИНА})
    )

    assert модератор["status"] == 200 and "ООО Покупатель" in модератор["body"]
    assert "Вернуть списанное" in модератор["body"] and "1 кред." in модератор["body"]
    assert поддержка["status"] == 200 and "Вернуть списанное" not in поддержка["body"]
    assert решить["status"] == 403
    assert django(люди["finance"], ("get", LIST, None))[1]["status"] == 403


UNLOCK = "App\\Models\\ContactUnlock"
ВЕРНУЛИ = "Жалоба на контакт подтверждена — потраченное вернули"


@pytest.mark.parametrize(
    ("настройка", "кошельки", "история", "уведомлена"),
    [
        # Потрачен кредит — вернулся в кошелёк с историей
        ({}, [(3, 3)], [("credits", 1, 3, "complaint_refund", UNLOCK, 1, "uid")], True),
        # Контакт по тарифу — вернулся в месячный лимит
        ({"spent": 0}, [(2, 2)], [], True),
        # Уже возвращали — дважды не возвращается
        ({"refunded": True}, [(2, 3)], [], True),
        ({"кошелёк": False}, [], [], True),
        # Удалённой компании ни возврата, ни уведомления
        ({"удалена": True}, [(2, 3)], [], False),
    ],
)
def test_вернуть(люди, настройка, кошельки, история, уведомлена):
    uid = люди["moderator"]
    сброс(**настройка)

    _, ответ = django(uid, ("post", LIST + "1/accept/", {"note": ПРИЧИНА}))
    база = снимок()

    assert ответ["status"] == 302 and ответ["location"] == LIST
    assert база["unlocks"] == [("accepted", True, ПРИЧИНА, uid, True)]
    assert база["wallets"] == кошельки
    assert база["wallet_log"] == [tuple(uid if v == "uid" else v for v in r) for r in история]
    assert база["notifications"] == (
        [("moderation", ВЕРНУЛИ, ПРИЧИНА, "success", "/cabinet/contacts")] if уведомлена else []
    )
    assert база["events"] == (
        [("moderation", "success", ВЕРНУЛИ, "/cabinet/contacts")] if уведомлена else []
    )
    assert база["journal"] == [
        (uid, "refunded", "complaints", UNLOCK, 1, "ContactUnlock #1", None, ПРИЧИНА)
    ]


def test_отказать(люди):
    uid = люди["admin"]
    note = "Контакт рабочий, дозвонились с первого раза"
    сброс()

    _, ответ = django(uid, ("post", LIST + "1/decline/", {"note": note}))

    assert ответ["status"] == 302 and ответ["location"] == LIST
    assert снимок() == {
        "unlocks": [("declined", False, note, uid, True)],
        "wallets": [(2, 3)],
        "wallet_log": [],
        "notifications": [
            ("moderation", "Жалоба на контакт отклонена", note, "warning", "/cabinet/contacts")
        ],
        "events": [("moderation", "warning", "Жалоба на контакт отклонена", "/cabinet/contacts")],
        "journal": [(uid, "rejected", "complaints", UNLOCK, 1, "ContactUnlock #1", None, note)],
    }


def test_короткая_формулировка(люди):
    сброс()
    до = снимок()

    _, ответ = django(люди["moderator"], ("post", LIST + "1/accept/", {"note": "вернули"}))

    assert ответ["status"] == 200 and снимок() == до
