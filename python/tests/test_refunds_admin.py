"""
Этап 7, шаг 58: «Возвраты» на Django вместо ресурса Filament.

Заявка, проведение и отказ — база и журнал после кнопки на Django такие
же, как после RefundService у Laravel: строка наблюдателя и строка
службы с пометкой; полный возврат переводит счёт в «Возвращён»,
частичный — нет, частичные складываются. Отказы службы (не оплачен,
больше остатка, решение уже принято) — сообщением, база не меняется.
Раздел видят финансы и суперадмин.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from .pg_admin import django, php, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/finance/refund/"
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'buyer', 'name' => 'ООО Покупатель']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    return {role: сотрудник(role) for role in ("superadmin", "finance", "admin", "support")}


def сброс(status: str = "paid", заявки: tuple[tuple[int, str], ...] = ()) -> None:
    sql("truncate refunds, payments, admin_actions restart identity cascade")
    sql(
        "insert into payments (company_id, purpose, number, description, amount, currency, "
        "status, paid_at, created_at, updated_at) select id, 'credits', 'SVD-000001', 'Пакет', "
        "1000000, 'UZS', %s, now(), now() - interval '3 days', now() - interval '3 days' "
        "from companies where slug = 'buyer'",
        [status],
    )

    for amount, state in заявки:
        sql(
            "insert into refunds (payment_id, company_id, amount, currency, reason, status, "
            "created_at, updated_at) select id, company_id, %s, 'UZS', 'Клиент недоволен', %s, "
            "now() - interval '1 day', now() - interval '1 day' from payments",
            [amount, state],
        )


def снимок() -> dict[str, Any]:
    return {
        "payments": sql("select number, status from payments"),
        "refunds": sql(
            "select payment_id, company_id, amount, currency, reason, status, created_by, "
            "decided_by, decided_at is not null, decision_note from refunds order by id"
        ),
        "journal": sql(
            "select user_id, action, section, subject_type, subject_id, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g'), note "
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


def _служба(uid: int, код: str) -> str:
    return (
        f"Illuminate\\Support\\Facades\\Auth::login($u = App\\Models\\User::find({uid}));"
        "$s = app(App\\Services\\Payments\\RefundService::class);"
        f" try {{ {код} }} catch (RuntimeException $e) {{}} echo 'ok';"
    )


def test_кто_видит(люди):
    сброс(заявки=((1000, "requested"), (2000, "done")))

    _, ждут, все = django(люди["finance"], ("get", LIST, None), ("get", LIST + "?closed=1", None))

    assert ждут["status"] == 200 and "Провести" in ждут["body"] and "SVD-000001" in ждут["body"]
    assert ждут["body"].count("Провести") == 1 and "Проведён" in все["body"]

    for role in ("admin", "support"):
        assert django(люди[role], ("get", LIST, None))[1]["status"] == 403, role


@pytest.mark.parametrize(
    ("сумма", "заявки", "status"),
    [
        ("250000", (), "paid"),
        ("1000000", (), "paid"),
        ("700000", ((400000, "done"),), "paid"),
        ("600000", ((400000, "done"),), "paid"),
        ("1000", (), "pending"),
    ],
)
def test_заявить(люди, сумма, заявки, status):
    uid = люди["finance"]
    по_сторонам(
        lambda: сброс(status, заявки),
        _служба(
            uid,
            f"$s->request(App\\Models\\Payment::firstOrFail(), $u, {сумма}, "
            "'Клиент отказался от пакета');",
        ),
        lambda: django(
            uid,
            (
                "post",
                LIST + "request/",
                {"payment": "1", "amount": сумма, "reason": "Клиент отказался от пакета"},
            ),
        ),
    )


@pytest.mark.parametrize(
    ("заявки", "примечание"),
    [
        (((1000000, "requested"),), ""),
        (((400000, "requested"),), "частично, по договорённости"),
        (((400000, "done"), (600000, "requested")), ""),
        (((1000000, "rejected"),), ""),
    ],
)
def test_провести(люди, заявки, примечание):
    uid = люди["superadmin"]
    last = len(заявки)
    note = "null" if примечание == "" else f"'{примечание}'"
    _, база = по_сторонам(
        lambda: сброс(заявки=заявки),
        _служба(uid, f"$s->approve(App\\Models\\Refund::find({last}), $u, {note});"),
        lambda: django(uid, ("post", f"{LIST}{last}/approve/", {"note": примечание})),
    )

    if заявки[-1][1] == "requested":
        full = sum(a for a, _ in заявки) >= 1000000
        assert база["payments"][0][1] == ("refunded" if full else "paid")


def test_отклонить(люди):
    uid = люди["finance"]
    по_сторонам(
        lambda: сброс(заявки=((1000, "requested"),)),
        _служба(
            uid, "$s->reject(App\\Models\\Refund::find(1), $u, 'Услуга уже оказана полностью');"
        ),
        lambda: django(uid, ("post", f"{LIST}1/reject/", {"note": "Услуга уже оказана полностью"})),
    )


def test_отказ_без_причины(люди):
    сброс(заявки=((1000, "requested"),))
    до = снимок()

    _, ответ = django(люди["finance"], ("post", f"{LIST}1/reject/", {"note": "нет"}))

    assert ответ["status"] == 200 and снимок() == до
