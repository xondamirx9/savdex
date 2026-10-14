"""
Одна проверка «компания жива и видима» для всех страниц площадки.

Раньше она была своей в каждом модуле и разъехалась: мини-сайт пускал
скрытую компанию (смотрел только «не заблокирована»), тендеры
заблокированной компании оставались с контактами. Теперь правило одно:

- компания видна посетителям, если она активна (status = 'active') и не
  удалена — не заблокирована, не скрыта, не на проверке;
- её объявления, задачи, отзывы и мини-сайт — только у видимой компании;
- закупка — пока виден её автор: не заблокирован, не удалён, а его
  компания (если есть) видима. Закупки администратора без компании и
  загруженные из Excel без автора видны как есть.

SQL — условия для where; Python — для строки, уже прочитанной из базы.
Себя компания видит всегда — это решает вызывающий (owner), не здесь.
"""

from __future__ import annotations

from typing import Any

ACTIVE = "active"


def company_sql(alias: str = "c") -> str:
    """Условие where «компания alias видна»."""
    return f"({alias}.status = '{ACTIVE}' and {alias}.deleted_at is null)"


def live_company(table: str, column: str = "company_id") -> str:
    """Условие where «у строки table видимая компания» (exists, без join)."""
    return (
        f"exists (select 1 from companies co where co.id = {table}.{column} "
        f"and {company_sql('co')})"
    )


def author_visible(alias: str = "t") -> str:
    """Условие where для закупки alias: её автор и его компания видны."""
    return (
        "not exists (select 1 from users au left join companies ac on ac.id = au.company_id "
        f"where au.id = {alias}.author_id and (au.status = 'blocked' "
        "or au.deleted_at is not null or ac.deleted_at is not null "
        f"or (ac.id is not null and ac.status <> '{ACTIVE}')))"
    )


def company_visible(company: dict[str, Any] | None) -> bool:
    """Строка companies: видна ли компания посетителям."""
    return (
        company is not None
        and company.get("status") == ACTIVE
        and company.get("deleted_at") is None
    )
