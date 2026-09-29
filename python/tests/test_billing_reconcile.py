"""
Этап 7, шаг 55: сверка денег.

Оплаты проводит сам Laravel (OrderService и PromoCodeService: тариф,
пакет, скидочный промокод, подтверждение администратором, отмена) —
сверка на Django не находит ни одного расхождения. Затем данные портятся
так, как их испортила бы ошибка выдачи, — и каждая порча находится.
Письмо о расхождении приходит один раз.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


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
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    php(
        "$orders = app(App\\Services\\OrderService::class);"
        "$promos = app(App\\Services\\PromoCodeService::class);"
        "$plan = App\\Models\\Plan::where('code', 'business')->first();"
        "$flash = App\\Models\\Plan::where('code', 'flash')->first();"
        "$pack = App\\Models\\CreditPack::where('code', 'm')->first();"
        "$admin = App\\Models\\User::factory()->create(['is_admin' => true,"
        " 'admin_role' => 'superadmin', 'email' => 'boss@savdex.uz']);"
        "foreach (['a', 'b', 'c', 'd'] as $slug) {"
        " $c[$slug] = App\\Models\\Company::factory()->create(['slug' => $slug]);"
        " $u[$slug] = App\\Models\\User::factory()->create(['company_id' => $c[$slug]->id]); }"
        # Тариф по колбэку кассы, пакет по колбэку, тариф — подтвердил администратор
        "$orders->markPaid($orders->orderPlan($c['a'], $plan, $u['a']),"
        " ['provider' => 'uzum', 'external_id' => 'T-1']);"
        "$orders->markPaid($orders->orderCredits($c['a'], $pack, $u['a']));"
        "$orders->confirm($orders->orderPlan($c['b'], $flash, $u['b']), $admin, 'перевод');"
        # Скидочный промокод: счёт на остаток, оплачен
        "App\\Models\\PromoCode::create(['code' => 'SALE', 'plan_id' => $plan->id, 'days' => 0,"
        " 'discount_percent' => 20]);"
        "$orders->markPaid($promos->redeem('SALE', $c['c'], $u['c']));"
        # Ждущий счёт со скидкой и отменённый
        "App\\Models\\PromoCode::create(['code' => 'WAIT', 'plan_id' => $plan->id, 'days' => 0,"
        " 'discount_percent' => 10]);"
        "$promos->redeem('WAIT', $c['d'], $u['d']);"
        "$orders->cancel($orders->orderCredits($c['d'], $pack, $u['d']));"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    yield


def test_проведённое_laravel_сходится(оплаты):
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
