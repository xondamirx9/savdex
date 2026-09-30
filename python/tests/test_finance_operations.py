"""
Этап 7, шаг 61: «Финансовые операции» на Django вместо страницы Filament.

Движения по кошелькам только читаются: знак у суммы, остаток после,
основание по-русски, «автоматически» без сотрудника, «удалена» у
удалённой компании, отключённый сотрудник — по имени. Фильтры
основания, вида, направления, периода; «Итого» по отфильтрованному.
Видят финансы и суперадмин, администратор — нет; править нечего.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import pytest

from .pg_admin import django, php, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/finance/wallettransaction/"
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'a', 'name' => 'ООО Альфа']);"
        "App\\Models\\Company::factory()->create(['slug' => 'gone', 'name' => 'ООО Ушедшая']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    люди = {role: сотрудник(role) for role in ("finance", "superadmin", "admin")}
    sql("update users set name = 'Бухгалтер Анна' where id = %s", [люди["finance"]])

    for company, user, kind, amount, balance, reason, comment, ago in (
        ("a", None, "credits", 1500, 1500, "purchase", "Пакет «1500»", "40 days"),
        ("a", None, "credits", -1, 1499, "unlock", None, "3 days"),
        ("a", "finance", "credits", 1, 1500, "complaint_refund", "Контакт не отвечал", "2 days"),
        ("a", None, "promo_units", 5, 5, "plan_grant", None, "1 day"),
        ("gone", None, "credits", -2, 8, "unlock", None, "1 day"),
    ):  # fmt: skip
        sql(
            "insert into wallet_transactions (company_id, user_id, kind, amount, balance_after, "
            "reason, comment, created_at, updated_at) select id, %s, %s, %s, %s, %s, %s, "
            "now() - %s::interval, now() from companies where slug = %s",
            [люди.get(user) if user else None, kind, amount, balance, reason, comment, ago,
             company],
        )  # fmt: skip

    sql("update companies set deleted_at = now() where slug = 'gone'")
    # Отключённый сотрудник остаётся в истории по имени (withTrashed у Laravel)
    sql("update users set deleted_at = now() where id = %s", [люди["finance"]])

    return люди


def test_список(люди):
    _, ответ = django(люди["superadmin"], ("get", LIST, None))
    body = ответ["body"]

    assert ответ["status"] == 200
    assert "+1 500" in body and "-1<" in body and "Возврат по жалобе" in body
    assert "Начисление по тарифу" in body and "Продвижение" in body
    assert "удалена" in body and "ООО Ушедшая" not in body
    assert "автоматически" in body and "Бухгалтер Анна" in body
    assert "Итого: 1 503" in body
    assert LIST + "add/" not in body


@pytest.mark.parametrize(
    ("query", "итого"),
    [
        ("?direction=grants", "1 506"),
        ("?direction=spends", "-3"),
        ("?reason=unlock", "-3"),
        ("?kind=promo_units", "5"),
        ("?period=month", "3"),
        ("?q=Альфа", "1 505"),
    ],
)
def test_фильтры(люди, query, итого):
    _, ответ = django(люди["superadmin"], ("get", LIST + query, None))

    assert f"Итого: {итого}<" in ответ["body"], ответ["body"][-3000:]


def test_права(люди):
    _, админ = django(люди["admin"], ("get", LIST, None))
    _, правка = django(люди["superadmin"], ("get", LIST + "1/change/", None))

    assert админ["status"] == 403
    # Карточка — только просмотр: сохранить нечего
    assert правка["status"] == 200 and 'name="_save"' not in правка["body"]
