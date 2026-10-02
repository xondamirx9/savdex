"""
Права в админке — копия App\\Support\\AdminAccess и User::hasAdminAbility.

Кто какой раздел видит и что в нём может. Нужна Django-разделам
админки (этап 2): право, которого нет в PHP, открыло бы человеку лишнее,
а недостающее — закрыло бы нужное. Поэтому это не пересказ, а копия
буква в букву, и совпадение с PHP проверяет tests/test_access_parity.py:
наборы прав каждой роли, «только свои записи» и выдачи/отзывы поштучно.

Правите матрицу в PHP — правьте и здесь; тест покажет, что забыли.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

SUPERADMIN = "superadmin"
MODERATOR = "moderator"

#: AdminAccess::ROLES — порядок тоже, он печатается в подсказках
ROLES: dict[str, str] = {
    "superadmin": "Суперадмин",
    "admin": "Администратор",
    "sales": "Отдел продаж",
    "supplier_manager": "Менеджер поставщиков",
    "buyer_manager": "Менеджер покупателей",
    "moderator": "Модератор",
    "finance": "Финансы",
    "support": "Поддержка",
    "content_manager": "Контент-менеджер",
}

#: AdminAccess::ACTIONS
ACTIONS: dict[str, str] = {
    "view": "Смотреть",
    "create": "Создавать",
    "edit": "Изменять",
    "delete": "Удалять",
    "moderate": "Модерировать",
    "export": "Выгружать",
    "import": "Загружать",
}

#: AdminAccess::SECTIONS
SECTIONS: dict[str, str] = {
    "users": "Пользователи",
    "roles": "Роли и права",
    "audit": "Журнал действий",
    "dashboard": "Показатели площадки",
    "companies": "Компании",
    "listings": "Объявления и товары",
    "tenders": "Тендеры и потребности",
    "ittasks": "Заказы на услуги",
    "documents": "Документы на проверку",
    "resumes": "Резюме соискателей",
    "reviews": "Отзывы",
    "complaints": "Жалобы на контакты",
    "leads": "Лиды",
    "deals": "Сделки",
    "contacts": "Контакты",
    "tasks": "Задачи",
    "communications": "Коммуникации",
    "pipelines": "Этапы воронки",
    "support": "Обращения в поддержку",
    "payments": "Счета и оплаты",
    "subscriptions": "Подписки",
    "refunds": "Возвраты и финансовые операции",
    "plans": "Тарифы",
    "promocodes": "Промокоды",
    "creditpacks": "Пакеты контактов",
    "finreports": "Финансовые отчёты",
    "content": "Страницы, новости, баннеры",
    "catalogs": "Справочники",
    "broadcasts": "Рассылки",
    "settings": "Настройки площадки",
    "backups": "Выгрузка базы",
}

#: AdminAccess::LEVELS — каждый следующий включает предыдущий
_LEVELS: dict[str, tuple[str, ...]] = {
    "r": ("view",),
    "w": ("view", "create", "edit"),
    "m": ("view", "create", "edit", "moderate"),
    "f": ("view", "create", "edit", "moderate", "delete"),
}

#: AdminAccess::MATRIX. Суффикс «o» — только свои записи
_MATRIX: dict[str, dict[str, str]] = {
    "admin": {
        "users": "w", "audit": "r", "dashboard": "r",
        "companies": "w", "listings": "w", "tenders": "w", "ittasks": "w",
        "documents": "r", "resumes": "m", "reviews": "w", "complaints": "w",
        "leads": "w", "deals": "w", "contacts": "w", "tasks": "w", "communications": "w",
        # Этапы воронки: заводить, переименовывать, удалять
        "pipelines": "f",
        "support": "w",
        "content": "w", "catalogs": "w", "broadcasts": "r",
    },
    "sales": {
        "companies": "r", "listings": "r", "tenders": "r",
        "leads": "wo", "deals": "wo", "contacts": "w",
        "tasks": "wo", "communications": "wo",
        "promocodes": "w",
    },
    "supplier_manager": {
        "companies": "w", "listings": "r", "tenders": "r",
        "documents": "r",
        "leads": "w", "deals": "w", "contacts": "w",
        "tasks": "wo", "communications": "wo",
    },
    "buyer_manager": {
        "companies": "w", "listings": "r", "tenders": "w",
        "documents": "r",
        "leads": "w", "deals": "w", "contacts": "w",
        "tasks": "wo", "communications": "wo",
    },
    "moderator": {
        "companies": "m", "listings": "m", "tenders": "m", "ittasks": "m",
        "documents": "m", "resumes": "m", "reviews": "m", "complaints": "m",
        # Доски лидов и сделок — все, но только смотреть: переводить
        # карточки по этапам модератор не может
        "leads": "r", "deals": "r",
        "catalogs": "r",
    },
    "finance": {
        "audit": "r", "companies": "r",
        "payments": "w", "subscriptions": "w", "refunds": "w",
        "plans": "r", "promocodes": "w", "creditpacks": "w", "finreports": "r",
    },
    "support": {
        "users": "r", "companies": "r", "listings": "r", "ittasks": "r",
        "resumes": "r", "reviews": "r", "complaints": "r",
        "contacts": "r", "tasks": "wo", "communications": "wo",
        "support": "w", "subscriptions": "r",
    },
    "content_manager": {
        "content": "w", "catalogs": "w", "broadcasts": "r",
    },
}  # fmt: skip

#: AdminAccess::EXTRAS — выгрузка и загрузка поимённо
_EXTRAS: dict[str, tuple[str, ...]] = {
    "admin": (
        "companies.export", "companies.import",
        "listings.export", "listings.import", "users.export",
        "tenders.export", "tenders.import",
        "reviews.import",
    ),
    "finance": ("payments.export", "subscriptions.export", "finreports.export"),
}  # fmt: skip


def all_abilities() -> list[str]:
    """AdminAccess::all(): все мыслимые права, раздел × действие."""
    return [f"{section}.{action}" for section in SECTIONS for action in ACTIONS]


def abilities_for(role: str | None) -> list[str]:
    """AdminAccess::abilitiesFor(): права роли; неизвестная — ничего."""
    if role == SUPERADMIN:
        return all_abilities()

    abilities: list[str] = []

    for section, level in _MATRIX.get(role or "", {}).items():
        abilities += [f"{section}.{action}" for action in _LEVELS.get(level.rstrip("o"), ())]

    return list(dict.fromkeys([*abilities, *_EXTRAS.get(role or "", ())]))


def scope_is_own(role: str | None, section: str) -> bool:
    """AdminAccess::scopeIsOwn(): видит ли роль в разделе только свои записи."""
    return _MATRIX.get(role or "", {}).get(section, "").endswith("o")


def _strings(value: Any) -> list[str]:  # noqa: ANN401
    """`array_filter((array) $value, 'is_string')` из PHP."""
    if value is None:
        return []

    items: Iterable[Any] = (
        value.values()
        if isinstance(value, Mapping)
        else (value if isinstance(value, list | tuple) else [value])
    )

    return [item for item in items if isinstance(item, str)]


@dataclass(frozen=True)
class Admin:
    """
    Сотрудник админки — то, что о нём нужно, чтобы решать про права.

    Читается из users заново на каждом запросе: снятая роль или
    блокировка действует сразу, а не когда истечёт вход.
    """

    id: int
    name: str
    email: str
    is_admin: bool
    role: str | None
    status: str
    permissions: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_superadmin(self) -> bool:
        return self.is_admin and self.role == SUPERADMIN

    @property
    def role_label(self) -> str | None:
        """User::adminRoleLabel(): у не-администратора роли нет вовсе."""
        if not self.is_admin:
            return None

        return ROLES.get(self.role or "", "Роль не назначена")

    def abilities(self) -> list[str]:
        """User::adminAbilities(): роль плюс выданные лично, минус отозванные."""
        granted = [*abilities_for(self.role), *_strings(self.permissions.get("grant"))]
        revoked = set(_strings(self.permissions.get("revoke")))

        return [a for a in dict.fromkeys(granted) if a not in revoked]

    def can(self, ability: str) -> bool:
        """User::hasAdminAbility(): заблокированный не может ничего."""
        if not self.is_admin or self.status != "active":
            return False

        if self.is_superadmin:
            return True

        return ability in self.abilities()

    def scope_is_own(self, section: str) -> bool:
        """User::adminScopeIsOwn()."""
        return not self.is_superadmin and scope_is_own(self.role, section)
