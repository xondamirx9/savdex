"""
Этап 7, шаг 55: сверка денег.

Оплаты проводит сама Django (savdex/web/orders.py и settlement.py: тариф,
пакет, скидочный промокод, подтверждение администратором, отмена) —
сверка не находит ни одного расхождения. Затем данные портятся
так, как их испортила бы ошибка выдачи, — и каждая порча находится.
Письмо о расхождении приходит один раз.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from .factories import компания, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

ЗАПУСК = {
    **ОКРУЖЕНИЕ,
    "MACHINE_TRANSLATION_ENABLED": "false",
    "DJANGO_SETTINGS_MODULE": "savdex.settings",
    "PYTHONPATH": str(PYTHON),
}

#: Оплаты, как их проводит сайт: заказ из кабинета, колбэк кассы,
#: подтверждение администратором, промокоды и отмена счёта
ОПЛАТЫ = """
import json, sys
import django
django.setup()
from django.test import RequestFactory

from savdex import laravel_session
from savdex.moderation.services import AdminContext
from savdex.web import orders, settlement
from savdex.web.shared import Context, _rows

ids = json.loads(sys.argv[1])
ctx = Context(
    request=RequestFactory().post("/cabinet/billing"), root="http://127.0.0.1",
    path="/cabinet/billing", query="", locale="ru", visitor=laravel_session.GUEST,
)

def one(query, params):
    return _rows(query, params)[0]

def company(slug):
    return one("select * from companies where id = %s", [ids["companies"][slug]])

def user(slug):
    return one("select * from users where id = %s", [ids["users"][slug]])

def fresh(payment):
    return one("select * from payments where id = %s", [payment["id"]])

plan = one("select * from plans where code = 'business'", [])
flash = one("select * from plans where code = 'flash'", [])
pack = one("select * from credit_packs where code = 'm'", [])
admin = one("select id, name, email from users where id = %s", [ids["admin"]])
staff = AdminContext(request=RequestFactory().post("/py/admin/"), user={**admin, "is_admin": True})

# Тариф по колбэку кассы, пакет по колбэку, тариф — подтвердил администратор
# (сайт берёт счёт из базы целиком — fresh)
settlement.mark_paid(
    ctx, fresh(orders.order_plan(ctx, company("a"), plan, user("a"))),
    {"provider": "uzum", "external_id": "T-1"},
)
settlement.mark_paid(ctx, fresh(orders.order_credits(ctx, company("a"), pack, user("a"))), {})
settlement.confirm(
    staff, fresh(orders.order_plan(ctx, company("b"), flash, user("b"))), admin, "перевод"
)
# Скидочный промокод: счёт на остаток, оплачен
kind, payment = orders.redeem(ctx, "SALE", company("c"), user("c"))
assert kind == "payment"
settlement.mark_paid(ctx, fresh(payment), {})
# Ждущий счёт со скидкой и отменённый
kind, _ = orders.redeem(ctx, "WAIT", company("d"), user("d"))
assert kind == "payment"
orders.cancel(ctx, fresh(orders.order_credits(ctx, company("d"), pack, user("d"))))
print("ok")
"""


def справочники(*таблицы: str) -> None:
    """Справочники из снимка savdex/bootstrap/seeds.json — только эти таблицы (PlanSeeder)."""
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"seeds.seed(data={{k: v if k in {list(таблицы)!r} else [] for k, v in data.items()}})"
    )
    subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        # Справочники заводит владелец базы, как миграции
        env={**ЗАПУСК, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"]},
        capture_output=True,
        check=True,
    )


def сверка(*args: str, env: dict[str, str] | None = None) -> tuple[int, list[tuple[str, str]]]:
    вывод = subprocess.run(
        [sys.executable, "manage.py", "reconcile_billing", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, **(env or {}), "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
    )
    строки = [line.split("\t") for line in вывод.stdout.splitlines() if "\t" in line]

    return вывод.returncode, [(s[0], s[1]) for s in строки]


@pytest.fixture(scope="module")
def оплаты() -> Iterator[None]:
    свежая_база()
    справочники("plans")
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    admin = пользователь(is_admin=True, admin_role="superadmin", email="boss@savdex.uz")
    companies = {slug: компания(slug=slug) for slug in "abcd"}
    users = {slug: пользователь(company_id=c) for slug, c in companies.items()}
    [(plan,)] = sql("select id from plans where code = 'business'")
    sql(
        "insert into promo_codes (code, plan_id, days, discount_percent, created_at, updated_at) "
        "values ('SALE', %s, 0, 20, now(), now()), ('WAIT', %s, 0, 10, now(), now())",
        [plan, plan],
    )
    вывод = subprocess.run(
        [
            sys.executable,
            "-c",
            ОПЛАТЫ,
            json.dumps({"admin": admin, "companies": companies, "users": users}),
        ],
        cwd=PYTHON,
        env=ЗАПУСК,
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0 and "ok" in вывод.stdout, вывод.stderr[-3000:]

    yield


def test_проведённое_сходится(оплаты):
    код, найдено = сверка("--all")

    assert (код, найдено) == (0, [])
    assert sql("select count(*) from payments where status = 'paid'")[0][0] == 4


def _номер(purpose: str, status: str, company: str) -> str:
    return str(
        sql(
            "select p.number from payments p join companies c on c.id = p.company_id "
            "where p.purpose = %s and p.status = %s and c.slug = %s order by p.id limit 1",
            [purpose, status, company],
        )[0][0]
    )


@pytest.mark.parametrize(
    ("порча", "откат", "номер", "код"),
    [
        (
            "update subscriptions set ends_at = ends_at + interval '1 day' "
            "where grant_reason = 'Оплата счёта {n}'",
            "update subscriptions set ends_at = ends_at - interval '1 day' "
            "where grant_reason = 'Оплата счёта {n}'",
            ("subscription", "paid", "a"),
            "plan_period",
        ),
        (
            "insert into subscriptions (company_id, plan_id, status, started_at, source, "
            "grant_reason, created_at, updated_at) select company_id, plan_id, 'expired', now(), "
            "'payment', grant_reason, now(), now() from subscriptions "
            "where grant_reason = 'Оплата счёта {n}'",
            "delete from subscriptions where grant_reason = 'Оплата счёта {n}' "
            "and status = 'expired' and id = (select max(id) from subscriptions)",
            ("subscription", "paid", "a"),
            "plan_count",
        ),
        (
            "update wallet_transactions set amount = 49 where subject_id = "
            "(select id from payments where number = '{n}')",
            "update wallet_transactions set amount = 50 where subject_id = "
            "(select id from payments where number = '{n}')",
            ("credits", "paid", "a"),
            "credits_amount",
        ),
        (
            "update subscriptions set granted_by = null where grant_reason = 'Оплата счёта {n}'",
            "update subscriptions set granted_by = (select id from users where "
            "email = 'boss@savdex.uz') where grant_reason = 'Оплата счёта {n}'",
            ("subscription", "paid", "b"),
            "plan_source",
        ),
        (
            "update promo_codes set subscription_id = null where code = 'SALE'",
            "update promo_codes set subscription_id = (select subscription_id from payments "
            "where number = '{n}') where code = 'SALE'",
            ("subscription", "paid", "c"),
            "plan_promo",
        ),
        (
            "update promo_codes set used_by_company_id = null where code = 'WAIT'",
            "update promo_codes set used_by_company_id = (select company_id from payments "
            "where number = '{n}') where code = 'WAIT'",
            ("subscription", "pending", "d"),
            "promo_pending",
        ),
        (
            "insert into wallet_transactions (company_id, kind, amount, balance_after, reason, "
            "subject_type, subject_id, created_at, updated_at) select company_id, 'credits', 50, "
            "50, 'purchase', 'App\\Models\\Payment', id, now(), now() from payments "
            "where number = '{n}'",
            "delete from wallet_transactions where subject_id = "
            "(select id from payments where number = '{n}')",
            ("credits", "failed", "d"),
            "credited_unpaid",
        ),
        (
            "insert into payment_transactions (payment_id, provider, provider_transaction_id, "
            "state, amount_minor, currency, created_at, updated_at) select id, 'uzum', 'X-1', "
            "'performed', amount * 100 + 1, 'UZS', now(), now() from payments "
            "where number = '{n}'",
            "delete from payment_transactions where provider_transaction_id = 'X-1'",
            ("subscription", "paid", "a"),
            "tx_amount",
        ),
    ],
)
def test_порча_находится(оплаты, порча, откат, номер, код):
    n = _номер(*номер)
    sql(порча.format(n=n))

    try:
        выход, найдено = сверка("--all")
    finally:
        sql(откат.format(n=n))

    assert выход == 1 and (n, код) in найдено, найдено
    assert сверка("--all") == (0, [])


def test_письмо_один_раз(оплаты, tmp_path: Path):
    n = _номер("credits", "paid", "a")
    письма = tmp_path / "mail.log"
    env = {
        "MAIL_MAILER": "log",
        "MAIL_LOG_PATH": str(письма),
        "BILLING_RECONCILE_STATE": str(tmp_path / "state.json"),
    }
    sql(
        "update wallet_transactions set amount = 1 where subject_id = "
        "(select id from payments where number = %s)",
        [n],
    )

    try:
        первый, _ = сверка("--once", "--days", "0", env=env)
        второй, _ = сверка("--once", "--days", "0", env=env)
    finally:
        sql(
            "update wallet_transactions set amount = 50 where subject_id = "
            "(select id from payments where number = %s)",
            [n],
        )

    текст = письма.read_text()

    assert первый == второй == 1
    assert текст.count("Subject:") == 1 and "boss@savdex.uz" in текст
