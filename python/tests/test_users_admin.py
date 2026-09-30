"""
Раздел «Пользователи» в админке Django: удаление аккаунта в два шага.

- отключение — deleted_at, как SoftDeletes; адрес почты сразу свободен
  для нового аккаунта (индекс уникальности — только среди действующих);
- отключённый находится отбором и поиском по почте;
- восстановление — если адрес не занял новый аккаунт;
- удаление навсегда — только отключённого и только суперадмином, с
  подтверждением; связанные строки база правит по внешним ключам;
- права — как у Filament: смотреть — users.view, отключать и
  восстанавливать — users.delete, навсегда — суперадмин;
- «Отключить» и «Восстановить» — и кнопками на странице пользователя;
- журнал admin_actions: deleted, restored, force_deleted.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/accounts/user/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "support")}


def _аккаунт(email: str, *, отключён: bool = False) -> int:
    [(uid,)] = sql(
        "insert into users (name, email, password, status, created_at, updated_at, deleted_at) "
        "values (%s, %s, 'x', 'active', now(), now(), "
        + ("'2026-09-01 10:00:00'" if отключён else "null")
        + ") returning id",
        [email.split("@")[0], email],
    )

    return int(uid)


def _действие(uid: int, action: str, ids: list[int], **extra: str) -> list[dict[str, object]]:
    return django(
        uid,
        ("post", LIST, {"action": action, "_selected_action": [str(i) for i in ids], **extra}),
        ("get", LIST + "?state=disabled", None),
    )[1:]


def _отключён(uid: int) -> bool | None:
    rows = sql("select deleted_at is not null from users where id = %s", [uid])

    return rows[0][0] if rows else None


def test_отключённый_находится_по_почте(люди):
    живой = _аккаунт("alive-find@company.uz")
    ушедший = _аккаунт("gone-find@company.uz", отключён=True)

    _, ответ = django(люди["support"], ("get", LIST + "?state=disabled&q=find@company", None))
    assert ответ["status"] == 200
    assert "gone-find@company.uz" in ответ["body"]
    assert "alive-find@company.uz" not in ответ["body"]
    assert "Отключён 01.09.2026" in ответ["body"]

    sql("delete from users where id in (%s, %s)", [живой, ушедший])


def test_права_как_у_filament(люди):
    """Поддержка только смотрит; администратор правит, но не удаляет — это суперадмин."""
    for role in ("support", "admin"):
        _, ответ = django(люди[role], ("get", LIST, None))
        assert ответ["status"] == 200
        assert "Отключить выбранные" not in ответ["body"], role
        assert "Удалить навсегда выбранные" not in ответ["body"], role

    _, ответ = django(люди["superadmin"], ("get", LIST, None))
    assert "Отключить выбранные" in ответ["body"]
    assert "Восстановить выбранные" in ответ["body"]
    assert "Удалить навсегда выбранные" in ответ["body"]


def test_отключение_освобождает_почту(люди):
    uid = _аккаунт("sher@company.uz")

    _действие(люди["superadmin"], "disable", [uid])

    assert _отключён(uid) is True
    assert журнал("deleted")["subject_label"] == "sher"
    assert журнал("deleted")["section"] == "users"

    # Адрес свободен: новый аккаунт на ту же почту заводится
    новый = _аккаунт("sher@company.uz")
    assert _отключён(новый) is False

    sql("delete from users where email = 'sher@company.uz'")


def test_себя_не_отключить(люди):
    _действие(люди["superadmin"], "disable", [люди["superadmin"]])

    assert _отключён(люди["superadmin"]) is False


def test_без_права_не_отключить(люди):
    uid = _аккаунт("keep@company.uz")

    _действие(люди["admin"], "disable", [uid])

    assert _отключён(uid) is False

    sql("delete from users where id = %s", [uid])


def test_восстановление(люди):
    uid = _аккаунт("back@company.uz", отключён=True)

    _действие(люди["superadmin"], "restore", [uid])

    assert _отключён(uid) is False
    assert журнал("restored")["subject_label"] == "back"

    sql("delete from users where id = %s", [uid])


def test_занятый_адрес_не_даёт_восстановить(люди):
    старый = _аккаунт("taken@company.uz", отключён=True)
    новый = _аккаунт("taken@company.uz")

    [_, список] = _действие(люди["superadmin"], "restore", [старый])

    assert _отключён(старый) is True
    assert "уже занят другим аккаунтом" in str(список["body"])

    sql("delete from users where id in (%s, %s)", [старый, новый])


def test_удаление_навсегда_с_подтверждением(люди):
    uid = _аккаунт("forever@company.uz", отключён=True)
    sql(
        "insert into notification_preferences (user_id, event, email, telegram, created_at, "
        "updated_at) values (%s, 'digest', true, false, now(), now())",
        [uid],
    )

    # Первый шаг — страница подтверждения, ничего не удалено
    _, подтверждение = django(
        люди["superadmin"],
        ("post", LIST, {"action": "force_delete", "_selected_action": [str(uid)]}),
    )
    assert подтверждение["status"] == 200
    assert "Отменить нельзя" in подтверждение["body"]
    assert _отключён(uid) is True

    _действие(люди["superadmin"], "force_delete", [uid], post="yes")

    assert _отключён(uid) is None
    assert sql("select count(*) from notification_preferences where user_id = %s", [uid]) == [(0,)]
    assert журнал("force_deleted")["subject_label"] == "forever"


def test_действующий_навсегда_не_удаляется(люди):
    uid = _аккаунт("live@company.uz")

    _действие(люди["superadmin"], "force_delete", [uid], post="yes")

    assert _отключён(uid) is False

    sql("delete from users where id = %s", [uid])


def test_не_суперадмин_навсегда_не_удаляет(люди):
    uid = _аккаунт("admin-try@company.uz", отключён=True)

    _действие(люди["admin"], "force_delete", [uid], post="yes")

    assert _отключён(uid) is True

    sql("delete from users where id = %s", [uid])


def test_без_права_правки_поля_не_меняются(люди):
    """
    С этапа 6 поля правятся здесь (tests/test_users_editing_admin.py) — но
    только с правом users.edit: поддержка смотрит.
    """
    uid = _аккаунт("readonly@company.uz")

    _, ответ = django(
        люди["support"],
        ("post", f"{LIST}{uid}/change/", {"name": "Другое имя", "email": "x@company.uz"}),
    )

    assert ответ["status"] == 403
    assert sql("select name, email from users where id = %s", [uid]) == [
        ("readonly", "readonly@company.uz")
    ]

    sql("delete from users where id = %s", [uid])


def test_кнопки_на_странице_пользователя(люди):
    """
    «Отключить» и «Восстановить» — и на странице пользователя, не только над
    отмеченными в списке; права и правила те же.
    """
    uid = _аккаунт("button@company.uz")
    страница = f"{LIST}{uid}/change/"

    _, суперадмин = django(люди["superadmin"], ("get", страница, None))
    _, админ = django(люди["admin"], ("get", страница, None))
    assert 'value="disable"' in суперадмин["body"]
    assert 'value="disable"' not in админ["body"], "право users.delete — у суперадмина"

    _, чужой = django(люди["admin"], ("post", f"{LIST}{uid}/act/", {"act": "disable"}))
    assert чужой["status"] == 403
    assert _отключён(uid) is False

    _, отключили, отключённый = django(
        люди["superadmin"],
        ("post", f"{LIST}{uid}/act/", {"act": "disable"}),
        ("get", страница, None),
    )
    assert отключили["status"] == 302
    assert _отключён(uid) is True
    assert журнал("deleted")["subject_label"] == "button"
    assert "Отключён" in отключённый["body"] and 'value="restore"' in отключённый["body"]

    _, вернули = django(люди["superadmin"], ("post", f"{LIST}{uid}/act/", {"act": "restore"}))
    assert вернули["status"] == 302
    assert _отключён(uid) is False
    assert журнал("restored")["subject_label"] == "button"

    sql("delete from users where id = %s", [uid])


def test_кнопки_не_обходят_правила(люди):
    """Себя не отключить, занятую почту не восстановить — и кнопкой тоже."""
    сам = люди["superadmin"]
    _, своя, себя = django(
        сам,
        ("get", f"{LIST}{сам}/change/", None),
        ("post", f"{LIST}{сам}/act/", {"act": "disable"}),
    )
    assert 'value="disable"' not in своя["body"]
    assert себя["status"] == 302 and _отключён(сам) is False

    старый = _аккаунт("busy@company.uz", отключён=True)
    новый = _аккаунт("busy@company.uz")
    _, ответ, страница = django(
        сам,
        ("post", f"{LIST}{старый}/act/", {"act": "restore"}),
        ("get", f"{LIST}{старый}/change/", None),
    )
    assert ответ["status"] == 302
    assert _отключён(старый) is True
    assert "уже занят другим аккаунтом" in страница["body"]

    sql("delete from users where id in (%s, %s)", [старый, новый])
