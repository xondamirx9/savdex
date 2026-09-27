"""
Права админки: Python против PHP.

Python-разделы админки (этап 2) решают, что человеку можно, по копии
AdminAccess в savdex/access.py. Право, которого нет в PHP, открыло бы
лишнее; недостающее — закрыло бы нужное. Поэтому ответы сверяются
с самим PHP (tests/fixtures/access_dump.php): наборы прав всех ролей,
«только свои записи» и итоговое «можно ли» по каждому из прав для
сотрудников с разными ролями, статусами, выдачами и отзывами.

Нужен только php с vendor/ — база не нужна.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from savdex import access

КОРЕНЬ = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    shutil.which("php") is None or not (КОРЕНЬ / "vendor" / "autoload.php").exists(),
    reason="нет php с зависимостями — сверка с PHP невозможна",
)

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


@pytest.fixture(scope="module")
def php() -> dict:
    return json.loads(
        subprocess.run(
            ["php", "python/tests/fixtures/access_dump.php"],
            cwd=КОРЕНЬ,
            input=json.dumps(СОТРУДНИКИ),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


def test_все_права(php):
    assert access.all_abilities() == php["all"]


def test_права_каждой_роли(php):
    for роль, права in php["roles"].items():
        role = None if роль == "(null)" else роль

        assert access.abilities_for(role) == права, роль


def test_только_свои_записи(php):
    for роль in php["roles"]:
        role = None if роль == "(null)" else роль
        свои = [s for s in access.SECTIONS if access.scope_is_own(role, s)]

        assert свои == php["own"].get(роль, []), роль


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


@pytest.mark.parametrize("номер", range(len(СОТРУДНИКИ)))
def test_итог_можно_ли(php, номер):
    admin = _admin(СОТРУДНИКИ[номер])
    ответ = php["cases"][номер]

    assert [a for a in access.all_abilities() if admin.can(a)] == ответ["allowed"]
    assert sorted(admin.abilities()) == sorted(ответ["abilities"])
    assert admin.is_superadmin == ответ["superadmin"]
    assert admin.role_label == ответ["label"]
    assert [s for s in access.SECTIONS if admin.scope_is_own(s)] == ответ["own"]


def test_сверка_различает(php):
    """Проверка слепа, если все сотрудники получают одно и то же."""
    итоги = {len(c["allowed"]) for c in php["cases"]}

    assert 0 in итоги and len(access.all_abilities()) in итоги and len(итоги) >= 6
