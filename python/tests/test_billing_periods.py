"""
Шаг 72: денежные задачи расписания Django (savdex/payments/periods.py)
делают то же, что команды Laravel promotions:finish и billing:reset-periods.

На одних данных сверяются продвижения (статус, показы, active_key),
подписки, кошельки, выставленные счета на продление, уведомления и лента
событий компании:
- продвижение с истёкшим сроком завершается, показы — объявления на момент
  завершения (удалённого объявления нет — прежние);
- счёт на продление — за неделю до конца подписки с автопродлением, не
  второй раз; истёкшая подписка закрывается с уведомлением (у удалённой
  компании — без); кошелёк с наступившим периодом — счётчики в ноль,
  единицы продвижения по тарифу, новый период по сроку тарифа.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def мир() -> dict[str, Any]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=PYTHON.parent,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    # Сумовая цена своя: курс ЦБ не нужен ни одной стороне
    sql("update plans set price_uzs = 100000 + id * 1000")
    php(
        "foreach (['c1','c2','c3','c4','c5'] as $s) {"
        " $c = App\\Models\\Company::factory()->create(['slug' => $s, 'name' => 'ООО '.$s]);"
        " App\\Models\\User::factory()->create(['email' => $s.'@savdex.uz',"
        " 'company_id' => $c->id, 'company_role' => 'owner']); }"
        "$c1 = App\\Models\\Company::where('slug', 'c1')->first();"
        "foreach (['one', 'two', 'gone'] as $t) {"
        " App\\Models\\Listing::factory()->create(['company_id' => $c1->id, 'title' => $t]); }"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    [(тип,)] = sql(
        "insert into promotion_types (code, name, description, cost_units, duration_days, sort, "
        "is_active, created_at, updated_at) values ('top', 'ТОП', 'x', 1, 7, 1, true, now(), "
        "now()) returning id"
    )

    return {
        "companies": {s: i for s, i in sql("select slug, id from companies")},
        "listings": {t: i for t, i in sql("select title, id from listings")},
        "plans": {c: i for c, i in sql("select code, id from plans")},
        "type": тип,
    }


def подготовка(мир: dict[str, Any]) -> None:
    sql(
        "truncate promotions, subscriptions, wallets, payments, user_notifications, "
        "activity_events restart identity cascade"
    )
    к, о, т = мир["companies"], мир["listings"], мир["plans"]
    sql("update companies set deleted_at = null")
    sql("update listings set deleted_at = null, impressions_count = 50")
    sql("update listings set deleted_at = now() where id = %s", [о["gone"]])

    # (объявление, статус, конец относительно «сейчас» в часах)
    for listing, status, hours in (
        ("one", "active", -1),
        ("two", "active", 24),
        ("gone", "active", -2),
    ):
        sql(
            "insert into promotions (listing_id, company_id, promotion_type_id, units_spent, "
            "status, starts_at, ends_at, impressions_before, active_key, created_at, updated_at) "
            "values (%s, %s, %s, 1, %s, now() - interval '7 days', "
            "now() + make_interval(hours => %s), 10, %s, '2026-01-01', '2026-01-01')",
            [
                о[listing], к["c1"], мир["type"], status, hours,
                f"{о[listing]}:{мир['type']}",
            ],
        )  # fmt: skip

    # (компания, тариф, продление, конец в днях)
    for company, plan, renew, days in (
        ("c1", "business", True, 3),
        ("c2", "business", True, 3),
        ("c3", "premium", False, -1),
        ("c4", "business", False, 3),
        ("c5", "premium", True, -1),
    ):
        sql(
            "insert into subscriptions (company_id, plan_id, status, started_at, ends_at, "
            "auto_renew, source, created_at, updated_at) values (%s, %s, 'active', "
            "now() - interval '20 days', now() + make_interval(days => %s), %s, 'payment', "
            "'2026-01-01', '2026-01-01')",
            [к[company], т[plan], days, renew],
        )

    # У c2 счёт на продление уже есть
    sql(
        "insert into payments (company_id, purpose, description, amount, currency, provider, "
        "status, number, plan_id, created_at, updated_at) values (%s, 'subscription', 'x', 1, "
        "'UZS', 'invoice', 'pending', 'SVD-X', %s, now(), now())",
        [к["c2"], т["business"]],
    )

    # (компания, период наступил)
    for company, due in (("c1", True), ("c2", False), ("c3", True), ("c5", True)):
        sql(
            "insert into wallets (company_id, credits, promo_units, contacts_used_this_period, "
            "responses_used_this_period, period_resets_at, created_at, updated_at) values "
            "(%s, 7, 99, 5, 4, now() + make_interval(days => %s), '2026-01-01', '2026-01-01')",
            [к[company], -1 if due else 5],
        )

    sql("update companies set deleted_at = now() where slug = 'c5'")


def снимок() -> dict[str, Any]:
    return {
        "promotions": sql(
            "select listing_id, status, impressions_after, active_key, "
            "updated_at > '2026-01-02' from promotions order by id"
        ),
        "subscriptions": sql(
            "select company_id, status, updated_at > '2026-01-02' from subscriptions order by id"
        ),
        "wallets": sql(
            "select company_id, credits, promo_units, contacts_used_this_period, "
            "responses_used_this_period, "
            # Новый период — от «сейчас» каждой стороны: до минуты
            "date_trunc('hour', period_resets_at), updated_at > '2026-01-02' "
            "from wallets order by id"
        ),
        "payments": sql(
            "select company_id, purpose, description, amount, currency, provider, status, "
            "number, plan_id from payments order by id"
        ),
        "notifications": sql(
            "select user_id, company_id, type, title, body, tone, url from user_notifications "
            "order by id"
        ),
        "events": sql(
            "select company_id, type, tone, message, url from activity_events order by id"
        ),
    }


def test_как_у_laravel(мир, tmp_path):
    подготовка(мир)
    php(
        "Illuminate\\Support\\Facades\\Artisan::call('promotions:finish');"
        "Illuminate\\Support\\Facades\\Artisan::call('billing:reset-periods'); echo 'ok';",
        # Как на боевом: вне production Laravel запрещает ленивую загрузку,
        # и его же команда падает на $wallet->company->plan()
        {**БЕЗ_ПЕРЕВОДА, "APP_ENV": "production"},
    )
    л = снимок()

    подготовка(мир)
    выводы = [
        subprocess.run(
            [sys.executable, "manage.py", "schedule", "--once", name],
            cwd=PYTHON,
            env={
                **ОКРУЖЕНИЕ,
                "PYTHONPATH": str(PYTHON),
                "SAVDEX_SCHEDULE_STATE": str(tmp_path / "state"),
            },
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for name in ("promotions_finish", "billing_reset_periods")
    ]
    д = снимок()

    assert д == л, (д, л)
    assert "Завершено продвижений: 2." in выводы[0]
    assert "счетов на продление: 1. Закрыто подписок: 2. Сброшено кошельков: 3." in выводы[1]
    # Счёт на продление у c1, уведомление об истёкшем тарифе — у c3
    assert [p[0] for p in д["payments"]] == [мир["companies"]["c2"], мир["companies"]["c1"]]
    assert [e[0] for e in д["events"]] == [мир["companies"]["c3"]]
