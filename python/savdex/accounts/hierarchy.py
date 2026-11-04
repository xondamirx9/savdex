"""
Кто кого повышает и снижает в админке — одно правило для всех мест.

Ступени: мегаадмин → суперадмин → остальные роли.

- Мегаадмина в панели не назначить и не снять никому, даже другому
  мегаадмину: только на сервере, командой `manage.py admin --role
  megaadmin`. Его учётку (почту, пароль, статус, доступ) в панели меняет
  только он сам.
- Суперадмина назначает и снимает только мегаадмин. Суперадмин не
  снижает другого суперадмина и не трогает его учётку: блокировка, новый
  пароль или почта — тот же захват.
- Панель не остаётся без суперадмина: последнего действующего (или
  мегаадмина) не снять и не заблокировать.

Раньше защита была только в разделе «Роли и права», а форма раздела
«Пользователи» писала роль, доступ и статус мимо неё. Теперь оба раздела
спрашивают здесь (refusal) до записи.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from savdex import access
from savdex.accounts.models import User

#: Ступени: чем больше, тем выше
_RANK = {access.MEGAADMIN: 2, access.SUPERADMIN: 1}

#: Учётка суперадмина: это меняет только тот, кто выше (или он сам)
_ACCOUNT = frozenset({"email", "password", "status", "admin_permissions"})

MEGA_ONLY_CLI = "Мегаадмина назначают и снимают только на сервере командой manage.py admin."
SUPER_BY_MEGA = "Назначать и снимать суперадминов может только мегаадмин."
ACCOUNT_BY_MEGA = "Учётку суперадмина меняет только мегаадмин."
ACCOUNT_OF_MEGA = "Учётку мегаадмина в панели меняет только он сам."
LAST_ONE = (
    "Это последний суперадмин. Сначала назначьте суперадминов кого-то ещё, "
    "иначе панель останется без владельца."
)


def _norm(key: str, value: Any) -> Any:  # noqa: ANN401
    """Пустые личные права — пустые, как бы их ни записали (None, {}, списки)."""
    if key != "admin_permissions":
        return value

    raw = value if isinstance(value, dict) else {}

    return {k: sorted(raw.get(k) or []) for k in ("grant", "revoke")}


def rank(is_admin: bool, role: str | None) -> int:
    return _RANK.get(role or "", 0) if is_admin else 0


def _owners_besides(user: User) -> bool:
    """Есть ли, кроме него, действующий суперадмин или мегаадмин."""
    return (
        User.objects.filter(
            is_admin=True,
            admin_role__in=list(_RANK),
            status="active",
            deleted_at__isnull=True,
        )
        .exclude(pk=user.pk)
        .exists()
    )


def refusal(actor: access.Admin, user: User, values: Mapping[str, Any]) -> str | None:
    """
    Почему actor не может записать values в учётку user — или None.

    values — столбцы users, как их пишет editing.write (is_admin,
    admin_role, status, email, admin_permissions); "password" — выдача
    пароля, "deleted" — отключение аккаунта.
    """
    new = user.pk is None
    before = 0 if new else rank(user.is_admin, user.admin_role)
    after = rank(
        bool(values.get("is_admin", user.is_admin)),
        values.get("admin_role", user.admin_role),
    )
    mine = rank(actor.is_admin, actor.role)

    if after != before:
        if 2 in (before, after):
            return MEGA_ONLY_CLI

        if mine < 2:
            return SUPER_BY_MEGA

    changes = {
        key
        for key, value in values.items()
        if key in ("password", "deleted")
        or (key in _ACCOUNT and _norm(key, value) != _norm(key, getattr(user, key, None)))
    }

    if not new and before > 0 and changes and user.pk != actor.id:
        if before == 2:
            return ACCOUNT_OF_MEGA

        if mine < 2:
            return ACCOUNT_BY_MEGA

    # Ушёл бы последний владелец панели: снят, заблокирован или отключён
    leaves = after == 0 or values.get("status", user.status) != "active" or "deleted" in values

    if not new and before > 0 and leaves and not _owners_besides(user):
        return LAST_ONE

    return None
