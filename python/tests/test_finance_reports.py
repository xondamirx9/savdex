"""
Этап 7, шаг 60: «Финансовые отчёты» на Django вместо страницы Filament.

Выручка, по месяцам, по тарифам, по источникам, продления и отток — те
же числа, что у FinanceReport на Laravel, на одних данных: оплаты у
границы месяца по Ташкенту, полный и частичный возврат, возврат другого
месяца, подписки новые, продлённые, отменённые и истёкшие молча.
Страницу видят финансы и суперадмин, администратор — нет.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, django, php, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

PAGE = "/py/admin/finance/payment/reports/"
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}

PERIODS = [
    ("2026-08-01", "2026-08-31"),
    ("2026-09-01", "2026-09-30"),
    ("2026-07-15", "2026-10-15"),
    ("2026-01-01", "2026-12-31"),
]


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=str(PYTHON.parent),
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "foreach (['a', 'b', 'c', 'd'] as $s) { App\\Models\\Company::factory()->create(["
        "'slug' => $s]); } echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
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


def _php(start: str, end: str) -> dict[str, Any]:
    out = php(
        f"$f = App\\Support\\Business::startOfDay('{start}'); "
        f"$t = App\\Support\\Business::endOfDay('{end}');"
        "echo json_encode(['revenue' => App\\Support\\FinanceReport::revenue($f, $t),"
        " 'months' => App\\Support\\FinanceReport::byMonth($f, $t),"
        " 'plans' => App\\Support\\FinanceReport::byPlan($f, $t),"
        " 'sources' => App\\Support\\FinanceReport::bySource($f, $t),"
        " 'subscriptions' => App\\Support\\FinanceReport::subscriptions($f, $t)],"
        " JSON_UNESCAPED_UNICODE);",
        БЕЗ_ПЕРЕВОДА,
    )

    return json.loads(out.splitlines()[-1])


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
def test_числа_как_у_laravel(люди, start, end):
    л = _php(start, end)
    д = _python(start, end)

    # Подпись месяца — своя (у Carbon — «F Y» по-русски), числа — те же
    for side in (л, д):
        for month in side["months"]:
            month.pop("label")

    assert д == л, (д, л)


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
