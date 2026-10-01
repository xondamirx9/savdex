"""
Шаг 72: денежные задачи расписания Django (savdex/payments/periods.py)
вместо команд Laravel promotions:finish и billing:reset-periods.

Проверяются продвижения (статус, показы, active_key), подписки,
кошельки, выставленные счета на продление, уведомления и лента событий
компании:
- продвижение с истёкшим сроком завершается, показы — объявления на момент
  завершения (удалённого объявления нет — прежние);
- счёт на продление — за неделю до конца подписки с автопродлением, не
  второй раз; истёкшая подписка закрывается с уведомлением (у удалённой
  компании — без); кошелёк с наступившим периодом — счётчики в ноль,
  единицы продвижения по тарифу, новый период по сроку тарифа.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from .factories import компания, объявление, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (PlanSeeder).
    """
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"seeds.seed(data={{k: v if k in {list(таблицы)!r} else [] for k, v in data.items()}})"
    )
    subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            # Справочники заводит владелец базы, как миграции
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        check=True,
    )


@pytest.fixture(scope="module")
def мир() -> dict[str, Any]:
    свежая_база()
    справочники("plans")
    # Сумовая цена своя: курс ЦБ не нужен
    sql("update plans set price_uzs = 100000 + id * 1000")

    for s in ("c1", "c2", "c3", "c4", "c5"):
        cid = компания(slug=s, name=f"ООО {s}")
        пользователь(email=f"{s}@savdex.uz", company_id=cid, company_role="owner")

    c1 = sql("select id from companies where slug = 'c1'")[0][0]

    for t in ("one", "two", "gone"):
        объявление(company_id=c1, title=t)

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
            # Новый период — сколько дней от «сейчас» до него
            "round(extract(epoch from period_resets_at - now()) / 86400)::int, "
            "updated_at > '2026-01-02' "
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


def test_задачи_расписания(мир, tmp_path):
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
    к, о, т = мир["companies"], мир["listings"], мир["plans"]

    assert "Завершено продвижений: 2." in выводы[0]
    assert "счетов на продление: 1. Закрыто подписок: 2. Сброшено кошельков: 3." in выводы[1]

    # Истёкшие завершены: показы — объявления сейчас, у удалённого — прежние
    assert д["promotions"] == [
        (о["one"], "finished", 50, None, True),
        (о["two"], "active", None, f"{о['two']}:{мир['type']}", False),
        (о["gone"], "finished", 10, None, True),
    ]
    # Истёкшие подписки закрыты (и у удалённой компании), прочие не тронуты
    assert д["subscriptions"] == [
        (к["c1"], "active", False),
        (к["c2"], "active", False),
        (к["c3"], "expired", True),
        (к["c4"], "active", False),
        (к["c5"], "expired", True),
    ]
    # Наступивший период: счётчики в ноль, единицы — по тарифу (Business — 50,
    # Free после конца подписки и у удалённой — 0), кредиты не сгорают,
    # новый период — 30 дней; у c2 период не наступил
    assert д["wallets"] == [
        (к["c1"], 7, 50, 0, 0, 30, True),
        (к["c2"], 7, 99, 5, 4, 5, False),
        (к["c3"], 7, 0, 0, 0, 30, True),
        (к["c5"], 7, 0, 0, 0, 30, True),
    ]
    # Счёт на продление — только у c1: у c2 уже есть, у c5 подписка истекла
    [прежний, счёт] = д["payments"]
    assert прежний[0] == к["c2"] and прежний[7] == "SVD-X"
    [(цена,)] = sql("select price_uzs from plans where code = 'business'")
    assert счёт == (
        к["c1"], "subscription", "Тариф «Business» на 30 дн.", цена, "UZS", "invoice",
        "pending", "SVD-000002", т["business"],
    )  # fmt: skip
    # Уведомления: о счёте — c1, об истёкшем тарифе — c3 (у удалённой c5 — нет)
    [о_счёте, об_истечении] = д["notifications"]
    assert (о_счёте[1], о_счёте[2], о_счёте[3]) == (
        к["c1"],
        "billing",
        "Счёт SVD-000002 сформирован",
    )
    assert об_истечении[1:] == (
        к["c3"],
        "payment",
        "Срок тарифа истёк — вы перешли на Free",
        "Объявления и контакты сохранены. Лимиты теперь действуют по бесплатному тарифу.",
        "warning",
        "/cabinet/billing",
    )
    assert д["events"] == [
        (
            к["c3"],
            "payment",
            "warning",
            "Срок тарифа истёк — вы перешли на Free",
            "/cabinet/billing",
        )
    ]
