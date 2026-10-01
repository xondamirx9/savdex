"""
Права админки: матрица ролей, выдачи и отзывы.

Python-разделы админки решают, что человеку можно, по savdex/access.py.
Право сверх задуманного открыло бы лишнее; недостающее — закрыло бы
нужное. Поэтому ожидания записаны явно: сколько прав у каждой роли,
что именно может узкая роль, где видны только свои записи и чем
кончаются выдачи, отзывы и блокировка для сотрудников с разными
ролями и статусами.

База не нужна.
"""

from __future__ import annotations

import pytest

from savdex import access

#: Сотрудники, на которых правила легко разойтись
СОТРУДНИКИ = [
    {"is_admin": True, "admin_role": "superadmin", "status": "active"},
    {"is_admin": True, "admin_role": "superadmin", "status": "blocked"},
    {"is_admin": False, "admin_role": "superadmin", "status": "active"},
    {"is_admin": True, "admin_role": "admin", "status": "active"},
    {"is_admin": True, "admin_role": "sales", "status": "active"},
    {"is_admin": True, "admin_role": "finance", "status": "active"},
    {"is_admin": True, "admin_role": "content_manager", "status": "active"},
    {"is_admin": True, "admin_role": None, "status": "active"},
    {"is_admin": True, "admin_role": "нет-такой", "status": "active"},
    # Выдано лично
    {
        "is_admin": True,
        "admin_role": "moderator",
        "status": "active",
        "admin_permissions": {"grant": ["catalogs.edit", "backups.export"]},
    },
    # Отозвано — сильнее выдачи, даже если право в обоих списках
    {
        "is_admin": True,
        "admin_role": "admin",
        "status": "active",
        "admin_permissions": {
            "grant": ["settings.view"],
            "revoke": ["catalogs.edit", "settings.view", "companies.export"],
        },
    },
    # Мусор в выдачах: не строки, строка вместо списка
    {
        "is_admin": True,
        "admin_role": "support",
        "status": "active",
        "admin_permissions": {"grant": "plans.view", "revoke": [1, None, "support.edit"]},
    },
    # Продавцу выдали чужие сделки поштучно — «только свои» не расширяется
    {
        "is_admin": True,
        "admin_role": "sales",
        "status": "active",
        "admin_permissions": {"grant": ["deals.delete"]},
    },
    # Заблокированный с выдачами
    {
        "is_admin": True,
        "admin_role": "admin",
        "status": "blocked",
        "admin_permissions": {"grant": ["settings.view"]},
    },
]

#: 30 разделов × 7 действий
ВСЕГО = 210

#: Сколько прав даёт роль: уровни матрицы (r — 1, w — 3, m — 4, f — 5)
#: плюс выгрузки и загрузки поимённо
ЧИСЛО_ПРАВ = {
    "superadmin": ВСЕГО,
    # 15 разделов w, 4 — r, резюме — m, 8 выгрузок/загрузок
    "admin": 15 * 3 + 4 + 4 + 8,
    # 3 r, 6 w (4 из них только свои)
    "sales": 3 + 6 * 3,
    # 3 r (объявления, тендеры, документы), 6 w
    "supplier_manager": 3 + 6 * 3,
    # тендеры у него w, а не r
    "buyer_manager": 2 + 7 * 3,
    # 8 разделов m, справочники — r
    "moderator": 8 * 4 + 1,
    # 4 r, 5 w, 3 выгрузки
    "finance": 4 + 5 * 3 + 3,
    # 9 r, 3 w
    "support": 9 + 3 * 3,
    "content_manager": 3 + 3 + 1,
    "нет-такой": 0,
    None: 0,
}

#: Где роль видит только свои записи (суффикс «o» в матрице)
ТОЛЬКО_СВОИ = {
    "sales": ["leads", "deals", "tasks", "communications"],
    "supplier_manager": ["tasks", "communications"],
    "buyer_manager": ["tasks", "communications"],
    "support": ["tasks", "communications"],
}


def test_все_права():
    права = access.all_abilities()

    assert len(права) == len(set(права)) == ВСЕГО
    assert права[:7] == [
        "users.view",
        "users.create",
        "users.edit",
        "users.delete",
        "users.moderate",
        "users.export",
        "users.import",
    ]
    assert права[-1] == "backups.import"


def test_права_каждой_роли():
    for роль, число in ЧИСЛО_ПРАВ.items():
        права = access.abilities_for(роль)

        assert len(права) == len(set(права)) == число, роль
        assert set(права) <= set(access.all_abilities()), роль

    assert access.abilities_for("superadmin") == access.all_abilities()
    assert set(access.ROLES) | {"нет-такой", None} == set(ЧИСЛО_ПРАВ)


def test_узкие_роли_поимённо():
    assert access.abilities_for("content_manager") == [
        "content.view",
        "content.create",
        "content.edit",
        "catalogs.view",
        "catalogs.create",
        "catalogs.edit",
        "broadcasts.view",
    ]
    assert "payments.export" in access.abilities_for("finance")
    assert "payments.delete" not in access.abilities_for("finance")
    assert "companies.delete" not in access.abilities_for("admin")
    assert "companies.moderate" in access.abilities_for("moderator")
    assert "companies.export" not in access.abilities_for("moderator")
    assert "settings.view" not in access.abilities_for("admin")


def test_только_свои_записи():
    for роль in [*access.ROLES, "нет-такой", None]:
        свои = [s for s in access.SECTIONS if access.scope_is_own(роль, s)]

        assert свои == ТОЛЬКО_СВОИ.get(роль, []), роль


def _admin(case: dict) -> access.Admin:
    return access.Admin(
        id=1,
        name="x",
        email="x@savdex.uz",
        is_admin=case["is_admin"],
        role=case["admin_role"],
        status=case["status"],
        permissions=case.get("admin_permissions") or {},
    )


#: (можно — сколько, права — сколько, суперадмин, подпись роли, только свои)
ИТОГИ = [
    (ВСЕГО, ВСЕГО, True, "Суперадмин", []),
    # Заблокированный суперадмин не может ничего
    (0, ВСЕГО, True, "Суперадмин", []),
    # Не сотрудник: роль в записи ничего не значит
    (0, ВСЕГО, False, None, []),
    (ЧИСЛО_ПРАВ["admin"], ЧИСЛО_ПРАВ["admin"], False, "Администратор", []),
    (ЧИСЛО_ПРАВ["sales"], ЧИСЛО_ПРАВ["sales"], False, "Отдел продаж", ТОЛЬКО_СВОИ["sales"]),
    (ЧИСЛО_ПРАВ["finance"], ЧИСЛО_ПРАВ["finance"], False, "Финансы", []),
    (7, 7, False, "Контент-менеджер", []),
    (0, 0, False, "Роль не назначена", []),
    (0, 0, False, "Роль не назначена", []),
    # Модератор и два выданных права
    (ЧИСЛО_ПРАВ["moderator"] + 2, ЧИСЛО_ПРАВ["moderator"] + 2, False, "Модератор", []),
    # Администратор без двух отозванных; выданное и отозванное — нет
    (ЧИСЛО_ПРАВ["admin"] - 2, ЧИСЛО_ПРАВ["admin"] - 2, False, "Администратор", []),
    # Поддержка: +plans.view (строка вместо списка), −support.edit
    (ЧИСЛО_ПРАВ["support"], ЧИСЛО_ПРАВ["support"], False, "Поддержка", ТОЛЬКО_СВОИ["support"]),
    (ЧИСЛО_ПРАВ["sales"] + 1, ЧИСЛО_ПРАВ["sales"] + 1, False, "Отдел продаж", ТОЛЬКО_СВОИ["sales"]),
    # Заблокирован: права на бумаге есть, можно — ничего
    (0, ЧИСЛО_ПРАВ["admin"] + 1, False, "Администратор", []),
]


@pytest.mark.parametrize("номер", range(len(СОТРУДНИКИ)))
def test_итог_можно_ли(номер):
    admin = _admin(СОТРУДНИКИ[номер])
    можно, права, суперадмин, подпись, свои = ИТОГИ[номер]
    разрешено = [a for a in access.all_abilities() if admin.can(a)]

    assert len(разрешено) == можно
    assert len(admin.abilities()) == len(set(admin.abilities())) == права
    assert admin.is_superadmin is суперадмин
    assert admin.role_label == подпись
    assert [s for s in access.SECTIONS if admin.scope_is_own(s)] == свои


def test_выдачи_и_отзывы():
    модератор, админ, поддержка, продавец, заблокированный = (
        _admin(СОТРУДНИКИ[i]) for i in (9, 10, 11, 12, 13)
    )

    assert модератор.can("catalogs.edit") and модератор.can("backups.export")
    assert not модератор.can("backups.view")
    # Отзыв сильнее выдачи
    assert not админ.can("settings.view")
    assert not админ.can("catalogs.edit") and not админ.can("companies.export")
    assert админ.can("catalogs.view") and админ.can("companies.import")
    # Строка вместо списка — тоже выдача; не строки в отзыве пропущены
    assert поддержка.can("plans.view") and not поддержка.can("support.edit")
    assert поддержка.can("support.view")
    # Выданное поштучно не делает раздел «чужим»
    assert продавец.can("deals.delete") and продавец.scope_is_own("deals")
    assert "settings.view" in заблокированный.abilities()
    assert not заблокированный.can("settings.view") and not заблокированный.can("users.view")


def test_сверка_различает():
    """Проверка слепа, если все сотрудники получают одно и то же."""
    итоги = {можно for можно, *_ in ИТОГИ}

    assert 0 in итоги and ВСЕГО in итоги and len(итоги) >= 6
