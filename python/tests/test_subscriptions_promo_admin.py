"""
Этап 7, шаг 57: «Подписки» и «Промокоды» на Django вместо ресурсов Filament.

Подписки: «Назначить тариф», «Сменить или продлить» (пусто — период
тарифа, ноль — бессрочно) и «Отменить» — база и журнал после кнопки на
Django такие же, как после SubscriptionService::assign и forceFill у
Laravel. Действия — только с правом правки: поддержка раздел видит, но
тариф не выдаёт.

Промокоды: выпуск пачкой (вид, тариф, срок или скидка, до какого дня,
префикс, повод; строка журнала на код, как AuditObserver), выключатель —
как у Laravel, погашенный не трогается; массовое отключение.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, django, php, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

SUBS = "/py/admin/finance/subscription/"
PROMO = "/py/admin/finance/promocode/"
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
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'buyer',"
        " 'name' => 'ООО Покупатель', 'tin' => '301234567']);"
        "App\\Models\\User::factory()->create(['company_id' => $c->id]);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    return {
        role: сотрудник(role) for role in ("superadmin", "finance", "support", "sales", "admin")
    }


def _id(table: str, where: str) -> int:
    return int(sql(f"select id from {table} where {where}")[0][0])


def сброс(*, подписка: bool = True, кошелёк: bool = False) -> None:
    sql(
        "truncate subscriptions, wallets, wallet_transactions, user_notifications, "
        "activity_events, admin_actions, promo_codes restart identity cascade"
    )
    company = _id("companies", "slug = 'buyer'")

    if подписка:
        sql(
            "insert into subscriptions (company_id, plan_id, status, source, auto_renew, "
            "started_at, ends_at, created_at, updated_at) select %s, id, 'active', 'payment', "
            "true, now() - interval '25 days', now() + interval '5 days', "
            "now() - interval '25 days', "
            "now() - interval '25 days' from plans where code = 'flash'",
            [company],
        )

    if кошелёк:
        sql(
            "insert into wallets (company_id, credits, promo_units, contacts_used_this_period, "
            "created_at, updated_at) values (%s, 2, 3, 4, now() - interval '9 days', "
            "now() - interval '9 days')",
            [company],
        )


def снимок() -> dict[str, Any]:
    return {
        "subscriptions": sql(
            "select company_id, plan_id, status, source, auto_renew, cancelled_at is not null, "
            "(ends_at - started_at)::text, granted_by, grant_reason from subscriptions order by id"
        ),
        "wallets": sql(
            "select credits, promo_units, contacts_used_this_period, "
            "round(extract(epoch from period_resets_at - now()) / 3600) from wallets"
        ),
        "notifications": sql("select type, title, body, tone, url from user_notifications"),
        "events": sql("select type, tone, message, url from activity_events"),
        "promo": sql(
            "select code, plan_id, days, discount_percent, expires_at, is_active, note, "
            "created_by from promo_codes order by id"
        ),
        "journal": sql(
            "select user_id, action, section, subject_type, subject_id, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g') "
            "from admin_actions order by id"
        ),
    }


def по_сторонам(подготовка: Callable[[], None], laravel: str, django_шаг: Callable[[], Any]) -> Any:
    подготовка()
    php(laravel, БЕЗ_ПЕРЕВОДА)
    л = снимок()

    подготовка()
    ответ = django_шаг()
    д = снимок()

    assert д == л, (д, л)

    return ответ, д


def _от_имени(uid: int, код: str) -> str:
    return (
        f"Illuminate\\Support\\Facades\\Auth::login(App\\Models\\User::find({uid}));"
        f" {код} echo 'ok';"
    )


# ── Подписки ────────────────────────────────────────────────────────


def test_список_и_права(люди):
    сброс()

    _, финансы = django(люди["finance"], ("get", SUBS, None))
    _, поддержка, выдать = django(
        люди["support"], ("get", SUBS, None), ("get", SUBS + "grant/", None)
    )
    _, продажи = django(люди["sales"], ("get", SUBS, None))

    assert финансы["status"] == 200
    assert "ООО Покупатель" in финансы["body"] and "5 дн." in финансы["body"]
    assert "Назначить тариф" in финансы["body"] and "Сменить или продлить" in финансы["body"]
    assert поддержка["status"] == 200 and "Назначить тариф" not in поддержка["body"]
    assert выдать["status"] == 403
    assert продажи["status"] == 403


@pytest.mark.parametrize(("дни", "кошелёк"), [("", False), ("0", False), ("14", True)])
def test_назначить(люди, дни, кошелёк):
    uid = люди["finance"]
    company = _id("companies", "slug = 'buyer'")
    plan = _id("plans", "code = 'business'")
    php_days = "null" if дни == "" else дни
    по_сторонам(
        lambda: сброс(кошелёк=кошелёк),
        _от_имени(
            uid,
            "app(App\\Services\\SubscriptionService::class)->assign("
            f"App\\Models\\Company::find({company}), App\\Models\\Plan::find({plan}), "
            f"days: {php_days}, source: 'manual', grantedBy: App\\Models\\User::find({uid}), "
            "reason: 'дебиторка');",
        ),
        lambda: django(
            uid,
            (
                "post",
                SUBS + "grant/",
                {"company": str(company), "plan": str(plan), "days": дни, "reason": "дебиторка"},
            ),
        ),
    )


def test_сменить_или_продлить(люди):
    uid = люди["superadmin"]
    plan = _id("plans", "code = 'premium'")
    _, база = по_сторонам(
        сброс,
        _от_имени(
            uid,
            "$s = App\\Models\\Subscription::firstOrFail();"
            "app(App\\Services\\SubscriptionService::class)->assign($s->company, "
            f"App\\Models\\Plan::find({plan}), days: 60, source: 'manual', "
            f"grantedBy: App\\Models\\User::find({uid}), reason: 'компенсация');",
        ),
        lambda: django(
            uid,
            (
                "post",
                SUBS + "1/extend/",
                {"plan": str(plan), "days": "60", "reason": "компенсация"},
            ),
        ),
    )

    assert [row[2] for row in база["subscriptions"]] == ["expired", "active"]


def test_отменить(люди):
    uid = люди["finance"]
    _, база = по_сторонам(
        сброс,
        _от_имени(
            uid,
            "App\\Models\\Subscription::firstOrFail()->forceFill(['status' => 'cancelled',"
            " 'cancelled_at' => now(), 'auto_renew' => false])->save();",
        ),
        lambda: django(uid, ("post", SUBS + "1/cancel/", {})),
    )

    assert база["subscriptions"][0][2:6] == ("cancelled", "payment", False, True)


def test_без_основания_не_выдаётся(люди):
    сброс()
    до = снимок()
    _, ответ = django(
        люди["finance"],
        ("post", SUBS + "1/extend/", {"plan": str(_id("plans", "code = 'premium'")), "reason": ""}),
    )

    assert ответ["status"] == 200 and снимок() == до


# ── Промокоды ───────────────────────────────────────────────────────


def test_выпуск(люди):
    сброс(подписка=False)
    uid = люди["sales"]
    plan = _id("plans", "code = 'premium'")
    _, форма, ответ, список = django(
        uid,
        ("get", PROMO + "issue/", None),
        (
            "post",
            PROMO + "issue/",
            {
                "kind": "free",
                "count": "3",
                "plan": str(plan),
                "days": "30",
                "discount_percent": "",
                "expires_at": "2026-12-31",
                "code_prefix": "expo",
                "note": "UzBuild",
            },
        ),
        ("get", PROMO, None),
    )

    assert форма["status"] == 200 and ответ["status"] == 302
    codes = sql(
        "select code, plan_id, days, discount_percent, expires_at::text, is_active, note, "
        "created_by from promo_codes order by id"
    )

    assert len(codes) == 3 and len({c[0] for c in codes}) == 3
    assert all(c[0].startswith("EXPO-") and len(c[0]) == 13 for c in codes)
    # Конец 31 декабря по Ташкенту
    assert codes[0][1:] == (plan, 30, None, "2026-12-31 18:59:59", True, "UzBuild", uid)
    assert codes[0][0] in список["body"] and "Действует" in список["body"]
    assert sql(
        "select count(*), min(action), min(section) from admin_actions where subject_type = "
        "'App\\Models\\PromoCode'"
    ) == [(3, "created", "promocodes")]


def test_выпуск_скидочных_без_префикса(люди):
    сброс(подписка=False)
    django(
        люди["finance"],
        (
            "post",
            PROMO + "issue/",
            {"kind": "discount", "count": "2", "plan": str(_id("plans", "code = 'business'")),
             "days": "", "discount_percent": "25", "expires_at": "", "code_prefix": "", "note": ""},
        ),
    )  # fmt: skip

    codes = sql("select code, days, discount_percent, expires_at, note from promo_codes")

    assert [c[1:] for c in codes] == [(0, 25, None, None)] * 2
    assert all(len(c[0]) == 8 and "-" not in c[0] for c in codes)


def _код(**поля: Any) -> None:
    sql(
        "insert into promo_codes (code, plan_id, days, is_active, used_at, created_at, updated_at) "
        "select %s, id, 30, %s, %s, now() - interval '1 day', now() - interval '1 day' "
        "from plans where code = 'premium'",
        [поля.get("code", "SVDX-TEST0001"), поля.get("is_active", True), поля.get("used_at")],
    )


@pytest.mark.parametrize("включён", [True, False])
def test_выключатель(люди, включён):
    uid = люди["finance"]

    def подготовка() -> None:
        сброс(подписка=False)
        _код(is_active=включён)

    по_сторонам(
        подготовка,
        _от_имени(
            uid,
            "$r = App\\Models\\PromoCode::firstOrFail();"
            " $r->forceFill(['is_active' => ! $r->is_active])->save();",
        ),
        lambda: django(uid, ("post", PROMO + "1/toggle/", {})),
    )


def test_погашенный_и_массовое_отключение(люди):
    сброс(подписка=False)
    _код(code="SVDX-USED0001", used_at="2026-09-01 10:00:00")
    _код(code="SVDX-FREE0001")

    _, погашенный, массово = django(
        люди["finance"],
        ("post", PROMO + "1/toggle/", {}),
        (
            "post",
            PROMO,
            {"action": "disable_selected", "_selected_action": ["1", "2"], "index": "0"},
        ),
    )

    assert погашенный["status"] == 302 and массово["status"] == 302
    assert sql("select code, is_active from promo_codes order by id") == [
        ("SVDX-USED0001", True),
        ("SVDX-FREE0001", False),
    ]


def test_промокоды_видят(люди):
    сброс(подписка=False)

    for role, status in (("sales", 200), ("finance", 200), ("support", 403), ("admin", 403)):
        assert django(люди[role], ("get", PROMO, None))[1]["status"] == status, role
