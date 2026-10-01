"""
Этап 7, шаг 57: «Подписки» и «Промокоды» на Django вместо ресурсов Filament.

Подписки: «Назначить тариф», «Сменить или продлить» (пусто — период
тарифа, ноль — бессрочно) и «Отменить» — база и журнал после кнопки:
прежняя подписка истекла, новая — с периодом, основанием и тем, кто
выдал; кошелёк — на новый период; уведомление компании. Действия —
только с правом правки: поддержка раздел видит, но тариф не выдаёт.

Промокоды: выпуск пачкой (вид, тариф, срок или скидка, до какого дня,
префикс, повод; строка журнала на код, как AuditObserver), выключатель,
погашенный не трогается; массовое отключение.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

import pytest

from .factories import компания, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

SUBS = "/py/admin/finance/subscription/"
PROMO = "/py/admin/finance/promocode/"


def тарифы() -> None:
    """Тарифы из снимка savdex/bootstrap/seeds.json — как PlanSeeder."""
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        "seeds.seed(data={k: v if k == 'plans' else [] for k, v in data.items()})"
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
def люди() -> dict[str, int]:
    свежая_база()
    тарифы()
    c = компания(slug="buyer", name="ООО Покупатель", tin="301234567")
    пользователь(company_id=c)

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


def шаг(подготовка: Callable[[], None], django_шаг: Callable[[], Any]) -> tuple[Any, Any]:
    """Подготовка, шаг Django, снимок базы после него."""
    подготовка()
    ответ = django_шаг()

    return ответ, снимок()


def журнал(база: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Журнал из снимка: правки — разобранным JSON (метки времени — «T»)."""
    return [(*row[:6], json.loads(row[6])) for row in база["journal"]]


def до(дней: int) -> str:
    """«Действует до …»: дата через столько дней по Ташкенту."""
    return (datetime.now(ZoneInfo("Asia/Tashkent")) + timedelta(days=дней)).strftime("%d.%m.%Y")


#: Прежняя подписка (flash, 30 дней по оплате) — после новой истекла
ПРЕЖНЯЯ = ("expired", "payment", True, True, "30 days", None, None)


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
    _, база = шаг(
        lambda: сброс(кошелёк=кошелёк),
        lambda: django(
            uid,
            (
                "post",
                SUBS + "grant/",
                {"company": str(company), "plan": str(plan), "days": дни, "reason": "дебиторка"},
            ),
        ),
    )
    company_, flash, business = company, _id("plans", "code = 'flash'"), plan
    срок = {"": "30 days", "0": None, "14": "14 days"}[дни]

    # Пусто — период тарифа (30 дней), ноль — бессрочно
    assert база["subscriptions"] == [
        (company_, flash, *ПРЕЖНЯЯ),
        (company_, business, "active", "manual", False, False, срок, uid, "дебиторка"),
    ]
    # Кошелёк на новый период: кредиты остаются, единицы продвижения
    # тарифа (50) добавляются, счётчик раскрытий — с нуля; срок — дни
    # тарифа, у бессрочного — месяц
    assert база["wallets"] == (
        [(2, 3 + 50, 0, 14 * 24)] if кошелёк else [(0, 50, 0, 30 * 24)]
    )
    текст = "Действует бессрочно." if дни == "0" else f"Действует до {до(int(дни or 30))}."
    assert база["notifications"] == [
        ("billing", "Вам назначен тариф «Business»", текст, "success", "/cabinet/billing")
    ]
    assert база["events"] == [
        ("billing", "success", "Вам назначен тариф «Business»", "/cabinet/billing")
    ]
    assert журнал(база) == [
        (
            uid, "created", "subscriptions", "App\\Models\\Subscription", 2, "Subscription #2",
            {"after": {
                "company_id": company_, "plan_id": business, "status": "active",
                "started_at": "T", "ends_at": None if дни == "0" else "T", "auto_renew": False,
                "source": "manual", "granted_by": uid, "grant_reason": "дебиторка", "id": 2,
            }},
        )
    ]  # fmt: skip


def test_сменить_или_продлить(люди):
    uid = люди["superadmin"]
    plan = _id("plans", "code = 'premium'")
    _, база = шаг(
        сброс,
        lambda: django(
            uid,
            (
                "post",
                SUBS + "1/extend/",
                {"plan": str(plan), "days": "60", "reason": "компенсация"},
            ),
        ),
    )
    company, flash = _id("companies", "slug = 'buyer'"), _id("plans", "code = 'flash'")

    assert база["subscriptions"] == [
        (company, flash, *ПРЕЖНЯЯ),
        (company, plan, "active", "manual", False, False, "60 days", uid, "компенсация"),
    ]
    # Premium: 150 единиц продвижения, период кошелька — 60 дней
    assert база["wallets"] == [(0, 150, 0, 60 * 24)]
    assert база["notifications"] == [
        (
            "billing",
            "Вам назначен тариф «Premium»",
            f"Действует до {до(60)}.",
            "success",
            "/cabinet/billing",
        )
    ]
    assert [row[:6] for row in журнал(база)] == [
        (uid, "created", "subscriptions", "App\\Models\\Subscription", 2, "Subscription #2")
    ]


def test_отменить(люди):
    uid = люди["finance"]
    _, база = шаг(сброс, lambda: django(uid, ("post", SUBS + "1/cancel/", {})))
    assert база["subscriptions"][0][2:6] == ("cancelled", "payment", False, True)
    # Без уведомлений и без кошелька — только отметка и журнал
    assert база["wallets"] == база["notifications"] == база["events"] == []
    assert журнал(база) == [
        (
            uid, "updated", "subscriptions", "App\\Models\\Subscription", 1, "Subscription #1",
            {
                "before": {"status": "active", "auto_renew": True, "cancelled_at": None},
                "after": {"status": "cancelled", "auto_renew": False, "cancelled_at": "T"},
            },
        )
    ]  # fmt: skip


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

    _, база = шаг(подготовка, lambda: django(uid, ("post", PROMO + "1/toggle/", {})))
    premium = _id("plans", "code = 'premium'")

    assert база["promo"] == [("SVDX-TEST0001", premium, 30, None, None, not включён, None, None)]
    assert журнал(база) == [
        (
            uid, "updated", "promocodes", "App\\Models\\PromoCode", 1, "SVDX-TEST0001",
            {"before": {"is_active": включён}, "after": {"is_active": not включён}},
        )
    ]  # fmt: skip


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
