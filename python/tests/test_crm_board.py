"""
Доски лидов и сделок и этапы воронки (savdex/crm/board.py, stages.py).

- доска вместо списка: колонки — этапы по порядку, закрытые — за неделю,
  старше — в архиве (список всех записей с отбором по итогу);
- продавец видит свои и ничьи лиды, модератор — все, но не двигает;
- перевод на этап спрашивает поля, выбранные для этапа: ответственный,
  комментарий (в заметку), следующий шаг (задача), причина отказа;
  строка журнала «изменено» с пометкой «Этап: «A» → «B»»;
- лид в «Стал сделкой» — только кнопкой «В сделку»;
- назначить ответственного может тот, кто видит раздел целиком;
- этапы правят суперадмин и администратор: добавить, переименовать,
  сдвинуть, удалить пустой несистемный — всё в журнале;
- дней на этапе дольше нормы — карточка красная.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LEADS = "/py/admin/crm/lead/"
DEALS = "/py/admin/crm/deal/"
STAGES = "/py/admin/crm/stage/"

#: Этапы, с которыми заводится воронка (миграция crm_stages)
ИСХОДНЫЕ = {
    ("leads", "new"): "Новый",
    ("leads", "working"): "В работе",
    ("leads", "qualified"): "Квалифицирован",
    ("leads", "converted"): "Стал сделкой",
    ("leads", "lost"): "Отказ",
    ("deals", "new"): "Новая",
    ("deals", "negotiation"): "Переговоры",
    ("deals", "proposal"): "Предложение отправлено",
    ("deals", "won"): "Выиграна",
    ("deals", "lost"): "Проиграна",
}


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    люди = {
        role: сотрудник(role) for role in ("superadmin", "admin", "sales", "moderator", "support")
    }
    [(other,)] = sql(
        "insert into users (name, email, password, is_admin, admin_role, status, "
        "created_at, updated_at) values ('Другой продавец', 'sales2@savdex.uz', 'x', true, "
        "'sales', 'active', now(), now()) returning id"
    )
    люди["sales2"] = int(other)

    return люди


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from crm_tasks")
    sql("delete from crm_deals")
    sql("delete from crm_leads")
    sql("delete from admin_actions")
    sql("delete from crm_stages where code like 's%%'")

    for (pipeline, code), name in ИСХОДНЫЕ.items():
        sql(
            "update crm_stages set name = %s where pipeline = %s and code = %s",
            [name, pipeline, code],
        )


def _лид(title: str, owner: int | None, status: str = "new", days: int = 0, **поля: Any) -> int:
    columns = ["title", "owner_id", "status", *поля]
    [(pk,)] = sql(
        f"insert into crm_leads ({', '.join(columns)}, created_at, updated_at, "
        f"stage_changed_at) values ({', '.join(['%s'] * len(columns))}, now(), now(), "
        "now() - make_interval(days => %s)) returning id",
        [title, owner, status, *поля.values(), days],
    )

    return int(pk)


def _сделка(title: str, owner: int, stage: str = "new", **поля: Any) -> int:
    columns = ["title", "owner_id", "stage", *поля]
    [(pk,)] = sql(
        f"insert into crm_deals ({', '.join(columns)}, created_at, updated_at, "
        f"stage_changed_at) values ({', '.join(['%s'] * len(columns))}, now(), now(), now()) "
        "returning id",
        [title, owner, stage, *поля.values()],
    )

    return int(pk)


def _перевести(uid: int, pk: int, stage: str, url: str = LEADS, **поля: Any) -> dict[str, Any]:
    _, ответ, доска = django(
        uid,
        ("post", f"{url}{pk}/move/", {"stage": stage, "next": url, **поля}),
        ("get", url, None),
    )
    ответ["доска"] = доска["body"]

    return ответ


def _этап_лида(pk: int) -> str:
    [(status,)] = sql("select status from crm_leads where id = %s", [pk])

    return str(status)


# ── Доска ───────────────────────────────────────────────────────────


def test_доска_вместо_списка(люди):
    _лид("Цемент М400", люди["sales"])
    _лид("Кирпич", None, "working")
    _лид("Свежий отказ", None, "lost", days=2, lost_reason="Дорого")
    _лид("Старый отказ", None, "lost", days=30, lost_reason="Дорого")

    _, доска, архив = django(
        люди["superadmin"], ("get", LEADS, None), ("get", LEADS + "archive/", None)
    )
    body = доска["body"]

    assert доска["status"] == 200
    колонки = ["Новый", "В работе", "Квалифицирован", "Стал сделкой", "Отказ"]
    места = [body.index(f"<h2>{name}</h2>") for name in колонки]
    assert места == sorted(места), "колонки — в порядке этапов"
    assert "Цемент М400" in body and "Кирпич" in body and "Свежий отказ" in body
    assert "Старый отказ" not in body, "закрытое старше недели — только в архиве"
    assert "ещё 1 —" in body
    assert "Старый отказ" in архив["body"] and "Архив лидов" in архив["body"]


def test_продавец_свои_и_ничьи_модератор_все_и_не_двигает(люди):
    _лид("Мой лид", люди["sales"])
    _лид("Ничей лид", None)
    _лид("Чужой лид", люди["sales2"])

    _, продавец = django(люди["sales"], ("get", LEADS, None))
    _, модератор = django(люди["moderator"], ("get", LEADS, None))
    _, поддержка = django(люди["support"], ("get", LEADS, None))

    assert "Мой лид" in продавец["body"] and "Ничей лид" in продавец["body"]
    assert "Чужой лид" not in продавец["body"]
    assert "data-movable" in продавец["body"]

    for title in ("Мой лид", "Ничей лид", "Чужой лид"):
        assert title in модератор["body"]
    assert "data-movable" not in модератор["body"]
    assert "data-droppable" not in модератор["body"]
    assert 'id="sx-move"' not in модератор["body"]

    assert поддержка["status"] == 403


def test_окно_спрашивает_поля_этапа(люди):
    _лид("Лид", люди["sales"])

    _, доска = django(люди["sales"], ("get", LEADS, None))
    body = доска["body"]

    # «В работе» по умолчанию спрашивает ответственного (обязательно)
    # и комментарий; «Стал сделкой» в окне нет — только кнопкой
    окно = body[
        body.index('id="sx-fields-working"') : body.index(
            "</template>", body.index('id="sx-fields-working"')
        )
    ]
    assert 'name="owner"' in окно and "required" in окно
    assert 'name="comment"' in окно
    assert 'id="sx-fields-converted"' not in body
    assert '<option value="converted">' not in body


# ── Перевод ─────────────────────────────────────────────────────────


def test_перевод_с_ответственным_и_комментарием(люди):
    pk = _лид("Арматура 12 мм", None, days=5)

    без_ответственного = _перевести(люди["sales"], pk, "working")
    assert _этап_лида(pk) == "new"
    assert "не переведена" in без_ответственного["доска"]

    ответ = _перевести(
        люди["sales"], pk, "working", owner=str(люди["sales"]), comment="Ждёт КП до пятницы"
    )

    assert ответ["status"] == 302
    [(status, owner, note, fresh)] = sql(
        "select status, owner_id, note, stage_changed_at > now() - interval '1 minute' "
        "from crm_leads where id = %s",
        [pk],
    )
    assert (status, owner, fresh) == ("working", люди["sales"], True)
    assert note.endswith("Сотрудник sales: Ждёт КП до пятницы")
    строка = журнал("updated")
    assert строка["section"] == "leads" and строка["subject_label"] == "Арматура 12 мм"
    [(note_,)] = sql("select note from admin_actions where action = 'updated'")
    assert note_ == "Этап: «Новый» → «В работе»"
    assert "stage_changed_at" not in json.dumps(строка["changes"])


def test_следующий_шаг_становится_задачей(люди):
    pk = _лид("Плитка", люди["sales"], "working")

    _перевести(
        люди["sales"],
        pk,
        "qualified",
        task_title="Отправить КП",
        task_due="2026-12-01T10:00",
    )

    assert _этап_лида(pk) == "qualified"
    [(title, assignee, subject_type, subject_id)] = sql(
        "select title, assignee_id, subject_type, subject_id from crm_tasks"
    )
    assert (title, assignee, subject_id) == ("Отправить КП", люди["sales"], pk)
    assert subject_type == "App\\Models\\Crm\\Lead"
    assert журнал("created")["section"] == "tasks"


def test_отказ_только_с_причиной_и_назад_можно(люди):
    pk = _лид("Песок", люди["sales"], "working")

    _перевести(люди["sales"], pk, "lost")
    assert _этап_лида(pk) == "working"

    _перевести(люди["sales"], pk, "lost", lost_reason="Купили у конкурента")
    assert sql("select status, lost_reason from crm_leads where id = %s", [pk]) == [
        ("lost", "Купили у конкурента")
    ]

    # Назад из отказа — тоже перевод
    _перевести(люди["sales"], pk, "new")
    assert _этап_лида(pk) == "new"


def test_в_стал_сделкой_только_кнопкой(люди):
    pk = _лид("Лид", люди["sales"], "working")

    ответ = _перевести(люди["sales"], pk, "converted")

    assert _этап_лида(pk) == "working"
    assert "кнопкой «В сделку»" in ответ["доска"]

    _, кнопка = django(люди["sales"], ("post", f"{LEADS}{pk}/convert/", {}))
    assert кнопка["status"] == 302
    assert _этап_лида(pk) == "converted"
    assert sql("select count(*) from crm_deals where lead_id = %s", [pk]) == [(1,)]


def test_чужое_и_без_права_не_двигается(люди):
    чужой = _лид("Чужой", люди["sales2"])
    ничей = _лид("Ничей", None)

    продавец = _перевести(люди["sales"], чужой, "working", owner=str(люди["sales"]))
    модератор = _перевести(люди["moderator"], ничей, "working", owner=str(люди["sales"]))
    _, get = django(люди["admin"], ("get", f"{LEADS}{ничей}/move/", None))

    assert продавец["status"] == 403 and модератор["status"] == 403
    assert get["status"] == 403
    assert _этап_лида(чужой) == "new" and _этап_лида(ничей) == "new"


def test_взять_себе_с_доски_возвращает_на_доску(люди):
    pk = _лид("Ничей", None)

    _, ответ = django(
        люди["sales"], ("post", f"{LEADS}{pk}/claim/", {"next": LEADS + "?owner=none"})
    )

    assert ответ["status"] == 302 and ответ["location"] == LEADS + "?owner=none"
    assert sql("select owner_id, status from crm_leads where id = %s", [pk]) == [
        (люди["sales"], "working")
    ]


def test_назначить_ответственного(люди):
    pk = _лид("Ничей", None)

    _, админ = django(
        люди["admin"], ("post", f"{LEADS}{pk}/assign/", {"owner": str(люди["sales2"])})
    )
    _, продавец = django(люди["sales"], ("post", f"{LEADS}{pk}/assign/", {"owner": ""}))
    _, модератор_в_список = django(
        люди["admin"], ("post", f"{LEADS}{pk}/assign/", {"owner": str(люди["moderator"])})
    )

    assert админ["status"] == 302
    assert продавец["status"] == 403, "продавец видит только своё — распределяет администратор"
    assert sql("select owner_id from crm_leads where id = %s", [pk]) == [(люди["sales2"],)]
    assert модератор_в_список["status"] == 302, "ошибка — сообщением, не 500"
    assert sql("select owner_id from crm_leads where id = %s", [pk]) == [(люди["sales2"],)]
    assert журнал("updated")["section"] == "leads"

    # Снять — лид снова ничей
    django(люди["admin"], ("post", f"{LEADS}{pk}/assign/", {"owner": ""}))
    assert sql("select owner_id from crm_leads where id = %s", [pk]) == [(None,)]


def test_сделка_выиграна_и_обратно(люди):
    pk = _сделка("Бетон М300", люди["sales"], "proposal", amount=1000)

    без_суммы = _перевести(люди["sales"], pk, "won", url=DEALS, amount="")
    assert sql("select stage from crm_deals where id = %s", [pk]) == [("proposal",)]
    assert "не переведена" in без_суммы["доска"]

    _перевести(люди["sales"], pk, "won", url=DEALS, amount="120000000", currency="UZS")
    assert sql(
        "select stage, amount, closed_at is not null from crm_deals where id = %s", [pk]
    ) == [("won", 120000000, True)]

    _перевести(люди["sales"], pk, "negotiation", url=DEALS)
    assert sql("select stage, closed_at from crm_deals where id = %s", [pk]) == [
        ("negotiation", None)
    ]


def test_долго_на_этапе_красная(люди):
    _лид("Залежался", люди["sales"], "working", days=10)
    _лид("Свежий", люди["sales"], "working", days=1)

    _, доска = django(люди["sales"], ("get", LEADS, None))
    body = доска["body"]

    залежался = body[: body.index("Залежался")].rsplit("<article", 1)[1]
    свежий = body[: body.index("Свежий")].rsplit("<article", 1)[1]
    assert "is-late" in залежался and "10 дней" in body
    assert "is-late" not in свежий


# ── Этапы воронки ───────────────────────────────────────────────────


def _форма_этапа(**поля: str) -> dict[str, str]:
    return {"name": "Встреча назначена", "limit_days": "3", **поля}


def test_этапы_правят_только_администраторы(люди):
    _, админ = django(люди["admin"], ("get", STAGES, None))
    _, продавец = django(люди["sales"], ("get", STAGES, None))
    _, модератор = django(люди["moderator"], ("get", STAGES, None))
    _, доска = django(люди["sales"], ("get", LEADS, None))

    assert админ["status"] == 200 and "Предложение отправлено" in админ["body"]
    assert продавец["status"] == 403 and модератор["status"] == 403
    assert "Этапы воронки</a>" not in доска["body"]


def test_новый_этап_в_журнале_и_на_доске(люди):
    _, ответ = django(
        люди["admin"],
        (
            "post",
            STAGES + "add/?pipeline=leads",
            {**_форма_этапа(f_owner="required", f_task="optional"), "pipeline": "leads"},
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:2000]
    [(code, kind, position, fields)] = sql(
        "select code, kind, position, fields from crm_stages where name = 'Встреча назначена'"
    )
    assert code.startswith("s") and kind == "open" and position == 4
    assert fields == {"owner": "required", "task": "optional"}
    строка = журнал("created")
    assert строка["section"] == "pipelines" and строка["subject_label"] == "Встреча назначена"

    _, доска = django(люди["sales"], ("get", LEADS, None))
    body = доска["body"]
    assert body.index("<h2>Квалифицирован</h2>") < body.index("<h2>Встреча назначена</h2>")
    assert body.index("<h2>Встреча назначена</h2>") < body.index("<h2>Стал сделкой</h2>")


def test_переименовать_и_сдвинуть(люди):
    [(pk,)] = sql("select id from crm_stages where pipeline = 'deals' and code = 'won'")
    [(proposal,)] = sql("select id from crm_stages where pipeline = 'deals' and code = 'proposal'")

    django(
        люди["superadmin"],
        (
            "post",
            f"{STAGES}{pk}/change/",
            {"name": "Оплачена", "limit_days": "", "f_amount": "required"},
        ),
        ("post", f"{STAGES}{proposal}/up/", {}),
    )

    assert sql("select name from crm_stages where id = %s", [pk]) == [("Оплачена",)]
    assert sql(
        "select code from crm_stages where pipeline = 'deals' and kind = 'open' order by position"
    ) == [("new",), ("proposal",), ("negotiation",)]
    строки = sql("select action, subject_label, changes::text from admin_actions order by id")
    assert строки[0][:2] == ("updated", "Оплачена")
    assert {label for _, label, _ in строки[1:]} == {"Предложение отправлено", "Переговоры"}


def test_удалить_только_пустой_несистемный(люди):
    django(
        люди["admin"],
        ("post", STAGES + "add/?pipeline=leads", {**_форма_этапа(), "pipeline": "leads"}),
    )
    [(pk, code)] = sql("select id, code from crm_stages where code like 's%%'")
    лид = _лид("На этапе", люди["sales"], code)
    [(system,)] = sql("select id from crm_stages where pipeline = 'leads' and code = 'new'")

    _, занятый, системный = django(
        люди["admin"],
        ("post", f"{STAGES}{pk}/delete/", {"post": "yes"}),
        ("post", f"{STAGES}{system}/delete/", {"post": "yes"}),
    )
    assert занятый["status"] == 403 and системный["status"] == 403

    _, перенос, удалить = django(
        люди["admin"],
        ("post", f"{STAGES}{pk}/move-all/", {"target": "working"}),
        ("post", f"{STAGES}{pk}/delete/", {"post": "yes"}),
    )

    assert перенос["status"] == 302 and удалить["status"] == 302
    assert _этап_лида(лид) == "working"
    assert sql("select count(*) from crm_stages where id = %s", [pk]) == [(0,)]
    assert журнал("deleted")["section"] == "pipelines"
    [(note,)] = sql("select note from admin_actions where section = 'leads'")
    assert note == "Этап: «Встреча назначена» → «В работе»"
