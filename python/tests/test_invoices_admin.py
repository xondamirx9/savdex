"""
Этап 7, шаг 56: «Счета и оплаты» на Django вместо страницы Filament.

- раздел видят финансы и суперадмин; администратор, продажи и поддержка — нет;
  по умолчанию — ждущие оплаты, отбор «Все», «Просрочены», «За что»;
- «Деньги пришли» — та же выдача, что у Laravel (OrderService::confirm):
  тариф — подпиской, которую выдал этот сотрудник, пакет — кредитами от
  его имени, скидочный промокод — к подписке; отметка — в admin_note;
  уведомление компании; строки журнала — как у AuditObserver. База после
  кнопки на Django и после службы Laravel — одна и та же;
- «Отменить счёт» — OrderService::cancel с причиной и тем, кто отменил;
- оплаченный и отменённый счёт кнопками не меняются, без права — 403.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, django, php, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/finance/payment/"
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
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
        "$c = App\\Models\\Company::factory()->create(['slug' => 'buyer',"
        " 'name' => 'ООО Покупатель', 'tin' => '301234567']);"
        "foreach (range(1, 2) as $i) {"
        " App\\Models\\User::factory()->create(['company_id' => $c->id]); }"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

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


def по_сторонам(
    подготовка: Callable[[], None], laravel: str, django_шаг: Callable[[], Any]
) -> dict[str, Any]:
    """Одно и то же действие: служба Laravel и кнопка на Django — база одинакова."""
    подготовка()
    php(laravel, БЕЗ_ПЕРЕВОДА)
    л = снимок()

    подготовка()
    ответ = django_шаг()
    д = снимок()

    assert д == л, (д, л)

    return {"ответ": ответ, "база": д}


def _служба(uid: int, код: str) -> str:
    return (
        f"Illuminate\\Support\\Facades\\Auth::login(App\\Models\\User::find({uid}));"
        "$orders = app(App\\Services\\OrderService::class);"
        f"$p = App\\Models\\Payment::firstOrFail(); {код} echo 'ok';"
    )


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


@pytest.mark.parametrize(
    ("что", "настройка"),
    [("plan", {}), ("plan", {"промокод": True}), ("pack", {}), ("pack", {"кошелёк": True})],
)
def test_деньги_пришли(люди, что, настройка):
    uid = люди["finance"]
    итог = по_сторонам(
        lambda: сброс(что, **настройка),
        _служба(uid, "$orders->confirm($p, App\\Models\\User::find(" + str(uid) + "), 'п/п 214');"),
        lambda: django(
            uid,
            ("get", f"{LIST}1/confirm/", None),
            ("post", f"{LIST}1/confirm/", {"note": "п/п 214", "back": LIST}),
        ),
    )
    _, страница, ответ = итог["ответ"]
    база = итог["база"]

    assert "Подтвердить поступление?" in страница["body"]
    assert ответ["status"] == 302
    assert база["payments"][0][:5] == ("SVD-000001", "paid", True, uid, "п/п 214")

    if что == "plan":
        assert база["subscriptions"][0][6] == uid
    else:
        assert база["wallet_log"][0][6] == uid

    assert база["journal"], "строки журнала — как у AuditObserver"


def test_без_отметки(люди):
    uid = люди["superadmin"]
    по_сторонам(
        сброс,
        _служба(uid, "$orders->confirm($p, App\\Models\\User::find(" + str(uid) + "), null);"),
        lambda: django(uid, ("post", f"{LIST}1/confirm/", {"note": "  "})),
    )


# ── Отменить ────────────────────────────────────────────────────────


@pytest.mark.parametrize("промокод", [False, True])
def test_отменить(люди, промокод):
    uid = люди["finance"]
    итог = по_сторонам(
        lambda: сброс(промокод=промокод),
        _служба(
            uid,
            "$orders->cancel($p, App\\Models\\User::find(" + str(uid) + "), 'Клиент передумал');",
        ),
        lambda: django(uid, ("post", f"{LIST}1/cancel/", {"note": "Клиент передумал"})),
    )

    assert итог["база"]["payments"][0][:5] == (
        "SVD-000001",
        "failed",
        False,
        uid,
        "Клиент передумал",
    )


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
