"""
Этап 7, шаг 58: «Возвраты» на Django вместо ресурса Filament.

Заявка, проведение и отказ — база и журнал после кнопки (как было у
RefundService Laravel): строка наблюдателя и строка
службы с пометкой; полный возврат переводит счёт в «Возвращён»,
частичный — нет, частичные складываются. Отказы службы (не оплачен,
больше остатка, решение уже принято) — сообщением, база не меняется.
Раздел видят финансы и суперадмин.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .factories import компания
from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/finance/refund/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    компания(slug="buyer", name="ООО Покупатель")

    return {role: сотрудник(role) for role in ("superadmin", "finance", "admin", "support")}


def сброс(status: str = "paid", заявки: tuple[tuple[int, str], ...] = ()) -> None:
    sql("truncate refunds, payments, admin_actions restart identity cascade")
    sql(
        "insert into payments (company_id, purpose, number, description, amount, currency, "
        "status, paid_at, created_at, updated_at) select id, 'credits', 'SVD-000001', 'Пакет', "
        "1000000, 'UZS', %s, now(), now() - interval '3 days', now() - interval '3 days' "
        "from companies where slug = 'buyer'",
        [status],
    )

    for amount, state in заявки:
        sql(
            "insert into refunds (payment_id, company_id, amount, currency, reason, status, "
            "created_at, updated_at) select id, company_id, %s, 'UZS', 'Клиент недоволен', %s, "
            "now() - interval '1 day', now() - interval '1 day' from payments",
            [amount, state],
        )


def снимок() -> dict[str, Any]:
    return {
        "payments": sql("select number, status from payments"),
        "refunds": sql(
            "select payment_id, company_id, amount, currency, reason, status, created_by, "
            "decided_by, decided_at is not null, decision_note from refunds order by id"
        ),
        "journal": sql(
            "select user_id, action, section, subject_type, subject_id, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g'), note "
            "from admin_actions order by id"
        ),
    }


def test_кто_видит(люди):
    сброс(заявки=((1000, "requested"), (2000, "done")))

    _, ждут, все = django(люди["finance"], ("get", LIST, None), ("get", LIST + "?closed=1", None))

    assert ждут["status"] == 200 and "Провести" in ждут["body"] and "SVD-000001" in ждут["body"]
    assert ждут["body"].count("Провести") == 1 and "Проведён" in все["body"]

    for role in ("admin", "support"):
        assert django(люди[role], ("get", LIST, None))[1]["status"] == 403, role


REFUND = "App\\Models\\Refund"
ПРИЧИНА = "Клиент отказался от пакета"


def журнал_() -> list[tuple[Any, ...]]:
    """Журнал из снимка: изменения — разобранным JSON."""
    return [
        (*row[:6], json.loads(row[6]) if row[6] else None, row[7]) for row in снимок()["journal"]
    ]


@pytest.mark.parametrize(
    ("сумма", "заявки", "status", "заведена"),
    [
        ("250000", (), "paid", True),
        ("1000000", (), "paid", True),
        # Больше остатка (1 000 000 − 400 000) — отказ службы
        ("700000", ((400000, "done"),), "paid", False),
        ("600000", ((400000, "done"),), "paid", True),
        # Счёт не оплачен — отказ
        ("1000", (), "pending", False),
    ],
)
def test_заявить(люди, сумма, заявки, status, заведена):
    uid = люди["finance"]
    сброс(status, заявки)
    до = снимок()

    _, ответ = django(
        uid, ("post", LIST + "request/", {"payment": "1", "amount": сумма, "reason": ПРИЧИНА})
    )
    после = снимок()

    if not заведена:
        assert ответ["status"] in (200, 302) and после == до
        return

    pk = len(заявки) + 1
    assert ответ["status"] == 302 and ответ["location"] == LIST
    assert после["payments"] == [("SVD-000001", "paid")]
    assert после["refunds"][:-1] == до["refunds"]
    assert после["refunds"][-1] == (
        1,
        1,
        int(сумма),
        "UZS",
        ПРИЧИНА,
        "requested",
        uid,
        None,
        False,
        None,
    )
    видно = f"{int(сумма):,}".replace(",", " ") + " UZS"
    assert журнал_() == [
        # Строка наблюдателя — все поля новой заявки
        (
            uid,
            "created",
            "refunds",
            REFUND,
            pk,
            f"Refund #{pk}",
            {
                "after": {
                    "payment_id": 1,
                    "company_id": 1,
                    "amount": int(сумма),
                    "currency": "UZS",
                    "reason": ПРИЧИНА,
                    "status": "requested",
                    "created_by": uid,
                    "id": pk,
                }
            },
            None,
        ),
        # Строка службы — с пометкой
        (
            uid,
            "created",
            "refunds",
            REFUND,
            pk,
            f"Refund #{pk}",
            {"after": {"сумма": видно, "счёт": "SVD-000001"}},
            ПРИЧИНА,
        ),
    ]


@pytest.mark.parametrize(
    ("заявки", "примечание", "счёт"),
    [
        # Полный возврат — счёт «Возвращён»
        (((1000000, "requested"),), "", "refunded"),
        # Частичный — нет
        (((400000, "requested"),), "частично, по договорённости", "paid"),
        # Частичные складываются: 400 000 + 600 000 — полный
        (((400000, "done"), (600000, "requested")), "", "refunded"),
        # Решение уже принято — база не меняется
        (((1000000, "rejected"),), "", None),
        # Две заявки на весь счёт: после первой вернуть уже нечего —
        # вторая не проводится, больше оплаченного не вернуть
        (((1000000, "done"), (1000000, "requested")), "", None),
    ],
)
def test_провести(люди, заявки, примечание, счёт):
    uid = люди["superadmin"]
    last = len(заявки)
    сброс(заявки=заявки)
    до = снимок()

    _, ответ = django(uid, ("post", f"{LIST}{last}/approve/", {"note": примечание}))
    после = снимок()

    assert ответ["status"] == 302 and ответ["location"] == LIST

    if счёт is None:
        assert после == до
        return

    amount = заявки[-1][0]
    note = примечание or None
    assert после["payments"] == [("SVD-000001", счёт)]
    assert после["refunds"][:-1] == до["refunds"][:-1]
    assert после["refunds"][-1] == (
        1,
        1,
        amount,
        "UZS",
        "Клиент недоволен",
        "done",
        None,
        uid,
        True,
        note,
    )

    было = {"status": "requested", "decided_by": None, "decided_at": None}
    стало = {"status": "done", "decided_by": uid, "decided_at": "T"}
    if note:
        было, стало = было | {"decision_note": None}, стало | {"decision_note": note}
    строки = [
        (
            uid,
            "updated",
            "refunds",
            REFUND,
            last,
            f"Refund #{last}",
            {"before": было, "after": стало},
            None,
        )
    ]
    if счёт == "refunded":
        строки.append(
            (
                uid,
                "updated",
                "payments",
                "App\\Models\\Payment",
                1,
                "Payment #1",
                {"before": {"status": "paid"}, "after": {"status": "refunded"}},
                None,
            )
        )
    видно = f"{amount:,}".replace(",", " ") + " UZS"
    строки.append(
        (
            uid,
            "refunded",
            "refunds",
            REFUND,
            last,
            f"Refund #{last}",
            {"before": {"статус": "Заявлен"}, "after": {"статус": "Проведён", "сумма": видно}},
            note or "Клиент недоволен",
        )
    )
    assert журнал_() == строки


def test_отклонить(люди):
    uid = люди["finance"]
    note = "Услуга уже оказана полностью"
    сброс(заявки=((1000, "requested"),))

    _, ответ = django(uid, ("post", f"{LIST}1/reject/", {"note": note}))
    база = снимок()

    assert ответ["status"] == 302 and ответ["location"] == LIST
    assert база["payments"] == [("SVD-000001", "paid")]
    assert база["refunds"] == [
        (1, 1, 1000, "UZS", "Клиент недоволен", "rejected", None, uid, True, note)
    ]
    assert журнал_() == [
        (
            uid,
            "updated",
            "refunds",
            REFUND,
            1,
            "Refund #1",
            {
                "before": {
                    "status": "requested",
                    "decided_by": None,
                    "decided_at": None,
                    "decision_note": None,
                },
                "after": {
                    "status": "rejected",
                    "decided_by": uid,
                    "decided_at": "T",
                    "decision_note": note,
                },
            },
            None,
        ),
        (
            uid,
            "rejected",
            "refunds",
            REFUND,
            1,
            "Refund #1",
            {"before": {"статус": "Заявлен"}, "after": {"статус": "Отклонён"}},
            note,
        ),
    ]


def test_отказ_без_причины(люди):
    сброс(заявки=((1000, "requested"),))
    до = снимок()

    _, ответ = django(люди["finance"], ("post", f"{LIST}1/reject/", {"note": "нет"}))

    assert ответ["status"] == 200 and снимок() == до
