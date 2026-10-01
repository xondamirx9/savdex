"""
Этап 7, шаг 60: «Финансовые отчёты» на Django вместо страницы Filament.

Выручка, по месяцам, по тарифам, по источникам, продления и отток — те
же числа, что давал FinanceReport на Laravel, на одних данных: оплаты у
границы месяца по Ташкенту, полный и частичный возврат, возврат другого
месяца, подписки новые, продлённые, отменённые и истёкшие молча.
Страницу видят финансы и суперадмин, администратор — нет.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from .factories import компания
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

PAGE = "/py/admin/finance/payment/reports/"


def _месяц(
    month: str, gross: int = 0, refunded: int = 0, net: int = 0, count: int = 0
) -> dict[str, Any]:
    return {"month": month, "gross": gross, "refunded": refunded, "net": net, "count": count}


def _пустые(*months: str) -> list[dict[str, Any]]:
    return [_месяц(m) for m in months]


АВГУСТ = _месяц("2026-08", 350000, 0, 350000, 1)
# Возврат 300 000 решён 1 октября по Ташкенту — он октябрьский
СЕНТЯБРЬ = _месяц("2026-09", 4500000, 2500000, 2000000, 3)
ОКТЯБРЬ = _месяц("2026-10", 350000, 300000, 50000, 1)
ТАРИФЫ_ВСЕ = [
    {"name": "Premium", "count": 1, "gross": 2500000},
    {"name": "Business", "count": 2, "gross": 2000000},
    {"name": "Без тарифа", "count": 2, "gross": 700000},
]
ИСТОЧНИКИ_ВСЕ = [
    {"purpose": "Подписка", "provider": "invoice", "count": 1, "gross": 2500000},
    {"purpose": "Подписка", "provider": "uzum", "count": 2, "gross": 2000000},
    {"purpose": "Пакет контактов", "provider": "не указан", "count": 1, "gross": 350000},
    {"purpose": "Пакет контактов", "provider": "invoice", "count": 1, "gross": 350000},
]

#: Период → отчёт (без подписи месяца); такие же числа давал FinanceReport
PERIODS = {
    ("2026-08-01", "2026-08-31"): {
        "revenue": {"UZS": {"gross": 350000, "refunded": 0, "net": 350000, "count": 1}},
        "months": [АВГУСТ],
        "plans": [{"name": "Без тарифа", "count": 1, "gross": 350000}],
        "sources": [
            {"purpose": "Пакет контактов", "provider": "не указан", "count": 1, "gross": 350000}
        ],
        # В августе начата только c/business — первая подписка c
        "subscriptions": {"new": 1, "renewed": 0, "cancelled": 0, "expired": 0, "active": 0},
    },
    ("2026-09-01", "2026-09-30"): {
        "revenue": {"UZS": {"gross": 4500000, "refunded": 2500000, "net": 2000000, "count": 3}},
        "months": [СЕНТЯБРЬ],
        "plans": ТАРИФЫ_ВСЕ[:2],
        "sources": ИСТОЧНИКИ_ВСЕ[:2],
        # Начаты a/business (продление), b, d; b отменена; c истекла молча
        "subscriptions": {"new": 2, "renewed": 1, "cancelled": 1, "expired": 1, "active": 2},
    },
    ("2026-07-15", "2026-10-15"): {
        "revenue": {"UZS": {"gross": 5200000, "refunded": 2800000, "net": 2400000, "count": 5}},
        "months": [*_пустые("2026-07"), АВГУСТ, СЕНТЯБРЬ, ОКТЯБРЬ],
        "plans": ТАРИФЫ_ВСЕ,
        "sources": ИСТОЧНИКИ_ВСЕ,
        # a/flash истекла, но a продлилась — это не отток
        "subscriptions": {"new": 3, "renewed": 1, "cancelled": 1, "expired": 1, "active": 1},
    },
    ("2026-01-01", "2026-12-31"): {
        "revenue": {"UZS": {"gross": 5200000, "refunded": 2800000, "net": 2400000, "count": 5}},
        "months": [
            *_пустые(*(f"2026-{m:02d}" for m in range(1, 8))),
            АВГУСТ,
            СЕНТЯБРЬ,
            ОКТЯБРЬ,
            *_пустые("2026-11", "2026-12"),
        ],
        "plans": ТАРИФЫ_ВСЕ,
        "sources": ИСТОЧНИКИ_ВСЕ,
        "subscriptions": {"new": 4, "renewed": 1, "cancelled": 1, "expired": 1, "active": 1},
    },
}


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    # Тарифы, как при деплое (вместо PlanSeeder) — под владельцем базы
    subprocess.run(
        [sys.executable, "manage.py", "seed"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        check=True,
        capture_output=True,
    )

    for slug in ("a", "b", "c", "d"):
        компания(slug=slug)

    ids = {r[0]: r[1] for r in sql("select slug, id from companies")}
    plan = {r[0]: r[1] for r in sql("select code, id from plans")}

    # Оплаты: 31 августа 20:00 UTC — уже 1 сентября в Ташкенте
    for company, plan_code, purpose, provider, amount, status, paid in (
        ("a", "business", "subscription", "uzum", 1000000, "paid", "2026-08-31 20:00:00"),
        ("a", None, "credits", None, 350000, "paid", "2026-08-31 18:00:00"),
        ("b", "premium", "subscription", "invoice", 2500000, "refunded", "2026-09-10 10:00:00"),
        ("c", "business", "subscription", "uzum", 1000000, "paid", "2026-09-20 10:00:00"),
        ("c", None, "credits", "invoice", 350000, "paid", "2026-10-02 10:00:00"),
        ("d", "flash", "subscription", "invoice", 499000, "pending", None),
        ("d", "flash", "subscription", "invoice", 499000, "failed", None),
    ):
        sql(
            "insert into payments (company_id, plan_id, purpose, provider, description, amount, "
            "currency, status, paid_at, created_at, updated_at) values (%s, %s, %s, %s, 'x', %s, "
            "'UZS', %s, %s, now(), now())",
            [ids[company], plan.get(plan_code), purpose, provider, amount, status, paid],
        )

    for payment_amount, amount, decided in (
        (2500000, 2500000, "2026-09-12 10:00:00"),
        (1000000, 300000, "2026-10-01 03:00:00"),
    ):
        sql(
            "insert into refunds (payment_id, company_id, amount, currency, reason, status, "
            "decided_at, created_at, updated_at) select id, company_id, %s, 'UZS', 'x', 'done', "
            "%s, now(), now() from payments where amount = %s order by id limit 1",
            [amount, decided, payment_amount],
        )

    # Подписки: у a — вторая (продление), у b — отменённая, у c — истекла молча
    for company, plan_code, status, started, ends, cancelled in (
        ("a", "flash", "expired", "2026-07-01 10:00:00", "2026-08-01 10:00:00", None),
        ("a", "business", "active", "2026-09-01 10:00:00", "2026-10-01 10:00:00", None),
        ("b", "premium", "cancelled", "2026-09-10 10:00:00", "2026-10-10 10:00:00",
         "2026-09-12 10:00:00"),
        ("c", "business", "expired", "2026-08-20 10:00:00", "2026-09-19 10:00:00", None),
        ("d", "flash", "active", "2026-09-05 10:00:00", None, None),
    ):  # fmt: skip
        sql(
            "insert into subscriptions (company_id, plan_id, status, source, auto_renew, "
            "started_at, ends_at, cancelled_at, created_at, updated_at) values (%s, %s, %s, "
            "'payment', true, %s, %s, %s, now(), now())",
            [ids[company], plan[plan_code], status, started, ends, cancelled],
        )

    return {role: сотрудник(role) for role in ("superadmin", "finance", "admin")}


def _python(start: str, end: str) -> dict[str, Any]:
    code = (
        "import json; from datetime import date; from savdex.finance import reports as r;"
        f"f = r.start_of_day(date.fromisoformat('{start}'));"
        f"t = r.end_of_day(date.fromisoformat('{end}'));"
        "print(json.dumps({'revenue': r.revenue(f, t), 'months': r.by_month(f, t),"
        " 'plans': r.by_plan(f, t), 'sources': r.by_source(f, t),"
        " 'subscriptions': r.subscriptions(f, t)}, ensure_ascii=False))"
    )
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", code],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(out.stdout.splitlines()[-1])


@pytest.mark.parametrize(("start", "end"), PERIODS)
def test_числа_отчёта(люди, start, end):
    д = _python(start, end)

    # Подпись месяца проверяет test_граница_месяца_по_ташкенту
    for month in д["months"]:
        month.pop("label")

    assert д == PERIODS[(start, end)]


def test_граница_месяца_по_ташкенту(люди):
    д = _python("2026-09-01", "2026-09-30")

    # Оплата 31 августа 20:00 UTC — сентябрьская, 18:00 UTC — августовская
    assert д["revenue"]["UZS"]["count"] == 3
    assert [m["label"] for m in д["months"]] == ["сентябрь 2026"]


def test_страница(люди):
    _, финансы, период = django(
        люди["finance"],
        ("get", PAGE, None),
        ("get", PAGE + "?from=2026-09-01&to=2026-09-30", None),
    )
    _, админ = django(люди["admin"], ("get", PAGE, None))

    assert финансы["status"] == 200 and "Продления и отток" in финансы["body"]
    assert "4 500 000 сум" in период["body"] and "сентябрь 2026" in период["body"]
    assert админ["status"] == 403
