"""
Этап 7, шаг 60: «Сверка со шлюзом» на Django вместо страницы Filament.

Расхождения те же, что у GatewayReconciliation на Laravel, на одних
данных: деньги взяты без закрытого счёта, двойное списание, суммы
расходятся (и в тийинах), закрыт без транзакции (вручную и нет),
возвращённый счёт, отменённая транзакция, счёт прошлого месяца,
оплаченный в этом, компания удалена. Страницу видят финансы, не
администратор.

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

PAGE = "/py/admin/finance/payment/reconciliation/"
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}
KINDS = [
    "performed_without_paid",
    "double_performed",
    "amount_mismatch",
    "paid_without_transaction",
]

PERIODS = [
    ("2026-08-01", "2026-08-31"),
    ("2026-09-01", "2026-09-30"),
    ("2026-01-01", "2026-12-31"),
    ("2025-01-01", "2025-01-31"),
]


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    php(
        "foreach (['a', 'b', 'gone'] as $s) { App\\Models\\Company::factory()->create(["
        "'slug' => $s, 'name' => 'ООО '.strtoupper($s)]); } echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    ids = {r[0]: r[1] for r in sql("select slug, id from companies")}
    admin = сотрудник("finance")

    # (номер, компания, статус, сумма, создан, оплачен, подтвердил, транзакции)
    # транзакция: (состояние, тийины, проведена, отменена)
    for number, company, status, amount, created, paid, confirmed, txs in (
        ("SD-1", "a", "paid", 100000, "2026-09-02 10:00:00", "2026-09-02 10:05:00", False,
         [("performed", 10000000, "2026-09-02 10:05:00", None)]),
        ("SD-2", "a", "pending", 250000, "2026-09-03 10:00:00", None, False,
         [("performed", 25000000, "2026-09-03 10:05:00", None)]),
        ("SD-3", "b", "paid", 300000, "2026-09-04 10:00:00", "2026-09-04 10:05:00", False,
         [("performed", 30000000, "2026-09-04 10:05:00", None),
          ("performed", 30000000, "2026-09-04 10:06:00", None)]),
        ("SD-4", "b", "paid", 100000, "2026-09-05 10:00:00", "2026-09-05 10:05:00", False,
         [("performed", 10000050, "2026-09-05 10:05:00", None)]),
        ("SD-5", "a", "paid", 499000, "2026-09-06 10:00:00", "2026-09-06 11:00:00", True, []),
        ("SD-6", "b", "paid", 499000, "2026-09-07 10:00:00", "2026-09-07 11:00:00", False, []),
        ("SD-7", "a", "refunded", 200000, "2026-09-08 10:00:00", "2026-09-08 10:05:00", False,
         [("performed", 20000000, "2026-09-08 10:05:00", None)]),
        ("SD-8", "b", "failed", 200000, "2026-09-09 10:00:00", None, False,
         [("cancelled", 20000000, None, "2026-09-09 10:05:00")]),
        # Выставлен в августе, оплачен в сентябре — виден в обоих месяцах
        ("SD-9", "a", "pending", 150000, "2026-08-30 10:00:00", None, False,
         [("performed", 15000000, "2026-09-01 08:00:00", None)]),
        ("SD-10", "gone", "paid", 350000, "2026-09-10 10:00:00", "2026-09-10 10:05:00", False,
         []),
        ("SD-11", "b", "paid", 100000, "2026-09-11 10:00:00", "2026-09-11 10:05:00", False,
         [("created", None, None, None)]),
    ):  # fmt: skip
        payment = sql(
            "insert into payments (company_id, number, purpose, provider, description, amount, "
            "currency, status, paid_at, confirmed_by, created_at, updated_at) values (%s, %s, "
            "'subscription', 'uzum', 'x', %s, 'UZS', %s, %s, %s, %s, %s) returning id",
            [ids[company], number, amount, status, paid, admin if confirmed else None, created,
             created],
        )[0][0]  # fmt: skip

        for n, (state, minor, performed, cancelled) in enumerate(txs):
            sql(
                "insert into payment_transactions (payment_id, provider, provider_transaction_id, "
                "state, amount_minor, currency, performed_at, cancelled_at, created_at, "
                "updated_at) values (%s, 'uzum', %s, %s, %s, 'UZS', %s, %s, now(), now())",
                [payment, f"{number}-{n}", state, minor, performed, cancelled],
            )

    sql("update companies set deleted_at = now() where slug = 'gone'")

    return {"finance": admin, "admin": сотрудник("admin")}


def _key(row: dict[str, Any]) -> tuple[int, int]:
    return KINDS.index(row["kind"]), row["payment_id"]


def _php(start: str, end: str) -> list[dict[str, Any]]:
    out = php(
        f"$f = App\\Support\\Business::startOfDay('{start}'); "
        f"$t = App\\Support\\Business::endOfDay('{end}');"
        "echo json_encode(array_map(fn ($r) => array_merge($r, ['at' => $r['at']?->format("
        "'Y-m-d H:i:s')]), App\\Support\\GatewayReconciliation::findings($f, $t)),"
        " JSON_UNESCAPED_UNICODE);",
        БЕЗ_ПЕРЕВОДА,
    )

    return sorted(json.loads(out.splitlines()[-1]), key=_key)


def _python(start: str, end: str) -> list[dict[str, Any]]:
    code = (
        "import json; from datetime import date; from savdex.finance import recon, reports as r;"
        f"f = r.start_of_day(date.fromisoformat('{start}'));"
        f"t = r.end_of_day(date.fromisoformat('{end}'));"
        "print(json.dumps([{**x, 'at': x['at'].strftime('%Y-%m-%d %H:%M:%S') if x['at'] "
        "else None} for x in recon.findings(f, t)], ensure_ascii=False))"
    )
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", code],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    )
    rows = json.loads(out.stdout.splitlines()[-1])

    # Внутри вида — порядок счетов; у Laravel он из кучи, у Django — по номеру
    assert rows == sorted(rows, key=_key)

    return rows


@pytest.mark.parametrize(("start", "end"), PERIODS)
def test_расхождения_как_у_laravel(люди, start, end):
    л = _php(start, end)
    д = _python(start, end)

    assert д == л, (д, л)


def test_что_найдено(люди):
    д = _python("2026-09-01", "2026-09-30")

    assert [(r["number"], r["kind"]) for r in д] == [
        ("SD-2", "performed_without_paid"),
        ("SD-9", "performed_without_paid"),
        ("SD-3", "double_performed"),
        ("SD-4", "amount_mismatch"),
        ("SD-5", "paid_without_transaction"),
        ("SD-6", "paid_without_transaction"),
        ("SD-10", "paid_without_transaction"),
        ("SD-11", "paid_without_transaction"),
    ]
    assert д[4]["note"] == "Подтверждён вручную администратором" and д[6]["company"] is None


def test_страница(люди):
    _, пусто, есть, счета = django(
        люди["finance"],
        ("get", PAGE + "?from=2025-01-01&to=2025-01-31", None),
        ("get", PAGE + "?from=2026-09-01&to=2026-09-30", None),
        ("get", "/py/admin/finance/payment/", None),
    )
    _, админ = django(люди["admin"], ("get", PAGE, None))

    assert пусто["status"] == 200 and "Расхождений нет" in пусто["body"]
    assert "Деньги взяты, счёт не закрыт" in есть["body"] and "SD-2" in есть["body"]
    assert "100 000,50 сум" in есть["body"] and "Расхождений нет" not in есть["body"]
    assert админ["status"] == 403

    # В меню Django страниц нет — ссылки в шапке «Счетов и оплат»
    assert PAGE in счета["body"] and "/py/admin/finance/payment/reports/" in счета["body"]
