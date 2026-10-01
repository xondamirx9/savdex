"""
Этап 7, шаг 56: «Счета и оплаты» на Django вместо страницы Filament.

- раздел видят финансы и суперадмин; администратор, продажи и поддержка — нет;
  по умолчанию — ждущие оплаты, отбор «Все», «Просрочены», «За что»;
- «Деньги пришли» — та же выдача, что была у Laravel (OrderService::confirm):
  тариф — подпиской, которую выдал этот сотрудник, пакет — кредитами от
  его имени, скидочный промокод — к подписке; отметка — в admin_note;
  уведомление компании; строки журнала — как у AuditObserver;
- «Отменить счёт» — OrderService::cancel с причиной и тем, кто отменил;
- оплаченный и отменённый счёт кнопками не меняются, без права — 403.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .factories import компания, пользователь
from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/finance/payment/"


def тарифы() -> None:
    """PlanSeeder: тарифы из снимка справочников (savdex/bootstrap/seeds.json)."""
    from savdex.seeds import DATA

    for plan in json.loads(DATA.read_text(encoding="utf-8"))["plans"]:
        sql(
            f"insert into plans ({', '.join(plan)}, created_at, updated_at) "
            f"values ({', '.join(['%s'] * len(plan))}, now(), now())",
            list(plan.values()),
        )


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    тарифы()
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    c = компания(slug="buyer", name="ООО Покупатель", tin="301234567")
    пользователь(company_id=c)
    пользователь(company_id=c)

    return {
        role: сотрудник(role) for role in ("superadmin", "finance", "admin", "sales", "support")
    }


def _компания() -> int:
    return int(sql("select id from companies where slug = 'buyer'")[0][0])


def сброс(что: str = "plan", *, промокод: bool = False, кошелёк: bool = False) -> None:
    """Один ждущий счёт SVD-000001 на тариф business или на пакет, как от OrderService."""
    sql(
        "truncate payment_transactions, payments, promo_codes, subscriptions, wallets, "
        "wallet_transactions, user_notifications, activity_events, admin_actions "
        "restart identity cascade"
    )
    company = _компания()

    if кошелёк:
        sql(
            "insert into wallets (company_id, credits, promo_units, created_at, updated_at) "
            "values (%s, 3, 1, now() - interval '3 days', now() - interval '3 days')",
            [company],
        )

    if промокод:
        sql(
            "insert into promo_codes (code, plan_id, days, discount_percent, used_at, "
            "used_by_company_id, created_at, updated_at) select 'SALE', id, 0, 20, now(), %s, "
            "now() - interval '1 day', now() - interval '1 day' from plans where code = 'business'",
            [company],
        )

    sql(
        "insert into payments (company_id, purpose, plan_id, credit_pack_id, promo_code_id, "
        "number, description, amount, currency, provider, status, created_at, updated_at) "
        "values (%s, %s, (select id from plans where code = 'business' and %s), "
        "(select id from credit_packs where code = 'm' and %s), "
        "(select id from promo_codes where code = 'SALE'), 'SVD-000001', 'Тариф «Business»', "
        "1500000, 'UZS', 'invoice', 'pending', now() - interval '20 days', "
        "now() - interval '20 days')",
        [company, "credits" if что == "pack" else "subscription", что == "plan", что == "pack"],
    )


def снимок() -> dict[str, Any]:
    return {
        "payments": sql(
            "select number, status, paid_at is not null, confirmed_by, admin_note, "
            "subscription_id from payments order by id"
        ),
        "subscriptions": sql(
            "select company_id, plan_id, status, source, auto_renew, (ends_at - started_at)::text, "
            "granted_by, grant_reason from subscriptions order by id"
        ),
        "wallets": sql(
            "select credits, promo_units, contacts_used_this_period, "
            "round(extract(epoch from period_resets_at - now()) / 3600) from wallets"
        ),
        "wallet_log": sql(
            "select kind, amount, balance_after, reason, subject_type, subject_id, user_id "
            "from wallet_transactions order by id"
        ),
        "promo": sql("select code, subscription_id, used_by_company_id from promo_codes"),
        "notifications": sql(
            "select user_id, type, title, body, tone, url from user_notifications order by id"
        ),
        "events": sql("select type, tone, message, url from activity_events order by id"),
        "journal": sql(
            "select user_id, action, section, subject_type, subject_id, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g'), note "
            "from admin_actions order by id"
        ),
    }


# ── Кто видит ───────────────────────────────────────────────────────


def test_кто_видит_и_ждущие(люди):
    сброс()
    sql(
        "insert into payments (company_id, purpose, number, description, amount, status, "
        "paid_at, created_at, updated_at) values (%s, 'credits', 'SVD-000777', 'Старое', 1000, "
        "'paid', now(), now(), now())",
        [_компания()],
    )

    _, ждут, все, просрочены = django(
        люди["finance"],
        ("get", LIST, None),
        ("get", LIST + "?closed=1", None),
        ("get", LIST + "?overdue=1&closed=1", None),
    )

    assert ждут["status"] == 200
    assert "SVD-000001" in ждут["body"] and "SVD-000777" not in ждут["body"]
    assert "Деньги пришли" in ждут["body"] and "301234567" in ждут["body"]
    assert "SVD-000777" in все["body"]
    assert "SVD-000001" in просрочены["body"] and "SVD-000777" not in просрочены["body"]

    for role in ("admin", "sales", "support"):
        assert django(люди[role], ("get", LIST, None))[1]["status"] == 403, role


# ── Деньги пришли ───────────────────────────────────────────────────

PAYMENT = "App\\Models\\Payment"
ОПЛАЧЕН = ("billing", "Оплата счёта SVD-000001 зачислена", "Тариф «Business»")
ТАРИФ = ("billing", "Тариф «Business» активирован")


def журнал_() -> list[tuple[Any, ...]]:
    """Журнал из снимка: изменения — разобранным JSON."""
    return [(*r[:6], json.loads(r[6]) if r[6] else None, r[7]) for r in снимок()["journal"]]


def уведомления(*строки: tuple[str, ...]) -> list[tuple[Any, ...]]:
    """Уведомление — каждому из двух сотрудников компании."""
    сотрудники = [uid for (uid,) in sql("select id from users where company_id is not null")]

    return [
        (uid, type_, title, body, "success", "/cabinet/billing")
        for type_, title, body in строки
        for uid in сотрудники
    ]


def _оплата(uid: int, note: str | None) -> tuple[Any, ...]:
    """Строка журнала AuditObserver о том, что счёт оплачен."""
    before = {"status": "pending", "paid_at": None, "confirmed_by": None}
    after = {"status": "paid", "paid_at": "T", "confirmed_by": uid}

    if note is not None:
        before, after = before | {"admin_note": None}, after | {"admin_note": note}

    return (
        uid,
        "updated",
        "payments",
        PAYMENT,
        1,
        "Payment #1",
        {"before": before, "after": after},
        None,
    )


def _подписка(uid: int) -> list[tuple[Any, ...]]:
    """Строки журнала о подписке, которую выдал сотрудник, и её привязке к счёту."""
    company = _компания()

    return [
        (
            uid, "created", "subscriptions", "App\\Models\\Subscription", 1, "Subscription #1",
            {"after": {"company_id": company, "plan_id": _тариф(), "status": "active",
                       "started_at": "T", "ends_at": "T", "auto_renew": True, "source": "payment",
                       "granted_by": uid, "grant_reason": "Оплата счёта SVD-000001", "id": 1}},
            None,
        ),
        (
            uid, "updated", "payments", PAYMENT, 1, "Payment #1",
            {"before": {"subscription_id": None}, "after": {"subscription_id": 1}},
            None,
        ),
    ]  # fmt: skip


def _тариф() -> int:
    return int(sql("select id from plans where code = 'business'")[0][0])


@pytest.mark.parametrize(
    ("что", "настройка"),
    [("plan", {}), ("plan", {"промокод": True}), ("pack", {}), ("pack", {"кошелёк": True})],
)
def test_деньги_пришли(люди, что, настройка):
    uid = люди["finance"]
    сброс(что, **настройка)

    _, страница, ответ = django(
        uid,
        ("get", f"{LIST}1/confirm/", None),
        ("post", f"{LIST}1/confirm/", {"note": "п/п 214", "back": LIST}),
    )
    база = снимок()
    company = _компания()

    assert "Подтвердить поступление?" in страница["body"]
    assert ответ["status"] == 302 and ответ["location"] == LIST

    if что == "plan":
        # Тариф — подпиской на 30 дней, которую выдал этот сотрудник;
        # кошелёк — с баллами продвижения тарифа и сбросом через 30 дней
        assert база["payments"] == [("SVD-000001", "paid", True, uid, "п/п 214", 1)]
        assert база["subscriptions"] == [
            (
                company,
                _тариф(),
                "active",
                "payment",
                True,
                "30 days",
                uid,
                "Оплата счёта SVD-000001",
            )
        ]
        assert база["wallets"] == [(0, 50, 0, 720)]
        assert база["wallet_log"] == []
        # Скидочный промокод — к подписке
        assert база["promo"] == ([("SALE", 1, company)] if настройка else [])
        assert база["notifications"] == уведомления(
            (*ТАРИФ, "Действует до " + _через_30_дней() + "."), ОПЛАЧЕН
        )
        assert база["events"] == [
            ("billing", "success", ТАРИФ[1], "/cabinet/billing"),
            ("billing", "success", ОПЛАЧЕН[1], "/cabinet/billing"),
        ]
        assert журнал_() == [_оплата(uid, "п/п 214"), *_подписка(uid)]
    else:
        # Пакет — кредитами от имени сотрудника; баллы кошелька не трогаются
        было = 3 if настройка else 0
        assert база["payments"] == [("SVD-000001", "paid", True, uid, "п/п 214", None)]
        assert база["subscriptions"] == []
        assert база["wallets"] == [(было + 50, 1 if настройка else 0, 0, None)]
        assert база["wallet_log"] == [("credits", 50, было + 50, "purchase", PAYMENT, 1, uid)]
        assert база["notifications"] == уведомления(ОПЛАЧЕН)
        assert база["events"] == [("billing", "success", ОПЛАЧЕН[1], "/cabinet/billing")]
        assert журнал_() == [_оплата(uid, "п/п 214")]


def _через_30_дней() -> str:
    [(дата,)] = sql("select to_char(ends_at, 'DD.MM.YYYY') from subscriptions")

    return str(дата)


def test_без_отметки(люди):
    uid = люди["superadmin"]
    сброс()

    _, ответ = django(uid, ("post", f"{LIST}1/confirm/", {"note": "  "}))

    assert ответ["status"] == 302
    # Пустая отметка — не отметка: admin_note остаётся пустым и в журнале его нет
    assert снимок()["payments"] == [("SVD-000001", "paid", True, uid, None, 1)]
    assert журнал_() == [_оплата(uid, None), *_подписка(uid)]


# ── Отменить ────────────────────────────────────────────────────────


@pytest.mark.parametrize("промокод", [False, True])
def test_отменить(люди, промокод):
    uid = люди["finance"]
    сброс(промокод=промокод)

    _, ответ = django(uid, ("post", f"{LIST}1/cancel/", {"note": "Клиент передумал"}))
    база = снимок()

    assert ответ["status"] == 302
    assert база["payments"] == [("SVD-000001", "failed", False, uid, "Клиент передумал", None)]
    # Промокод отменённого счёта освобождается
    assert база["promo"] == ([("SALE", None, None)] if промокод else [])
    assert база["subscriptions"] == база["wallets"] == база["wallet_log"] == []
    assert база["notifications"] == база["events"] == []
    assert журнал_() == [
        (
            uid, "updated", "payments", PAYMENT, 1, "Payment #1",
            {"before": {"status": "pending", "confirmed_by": None, "admin_note": None},
             "after": {"status": "failed", "confirmed_by": uid, "admin_note": "Клиент передумал"}},
            None,
        )
    ]  # fmt: skip


# ── Границы ─────────────────────────────────────────────────────────


def test_оплаченный_не_трогается(люди):
    сброс()
    sql("update payments set status = 'paid', paid_at = now()")
    до = снимок()

    _, ответ = django(люди["finance"], ("post", f"{LIST}1/confirm/", {"note": "x"}))

    assert ответ["status"] == 302 and снимок() == до


def test_без_права(люди):
    сброс()
    до = снимок()

    for role in ("admin", "support"):
        _, ответ = django(люди[role], ("post", f"{LIST}1/confirm/", {}))
        assert ответ["status"] == 403, role

    assert снимок() == до
