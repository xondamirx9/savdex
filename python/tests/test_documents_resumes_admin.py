"""
Модерация на Django, этап 6: «Документы на проверку» и «Резюме» вместо Filament.

Документы:
- в очереди только подтверждающие статус (не презентации), по умолчанию —
  ждущие проверки; просроченный срок — красным, ссылка на файл;
- принять — компании уведомление, отклонить — с причиной не короче 15
  знаков; в журнале «изменено» и строка о решении; решает модератор
  (documents.moderate), администратор только смотрит;
- ни создать, ни править, ни удалить.

Резюме:
- снять с причиной не короче 10 знаков, вернуть — заметка снимается,
  дата публикации остаётся; строки журнала о решении;
- поддержка смотрит, но не снимает; удаление — в корзину, суперадмином.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

DOCS = "/py/admin/moderation/companydocument/"
RESUMES = "/py/admin/moderation/resume/"
REASON = "Скан нечитаемый — загрузите документ целиком"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator", "support")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from user_notifications")
    sql("delete from activity_events")
    sql("delete from company_documents")
    sql("delete from resumes")
    sql("delete from users where email like 'staff-%%'")
    sql("delete from companies")
    sql("delete from admin_actions where section in ('documents', 'resumes')")


def _компания(name: str = "Стройбаза") -> int:
    [(pk,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values (%s, %s, 'active', now(), now()) returning id",
        [name, name.lower()],
    )
    sql(
        "insert into users (name, email, password, company_id, status, created_at, updated_at) "
        "values ('Владелец', %s, 'x', %s, 'active', now(), now())",
        [f"staff-{pk}@example.com", pk],
    )

    return int(pk)


def _документ(company: int, **поля: Any) -> int:
    строка = {
        "type": "license",
        "title": "Лицензия на строительство",
        "file_path": "documents/1.pdf",
        "file_size": 1572864,
        "moderation_status": "pending",
        "is_public": True,
        **поля,
    }
    columns = ["company_id", *строка]
    [(pk,)] = sql(
        f"insert into company_documents ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [company, *строка.values()],
    )

    return int(pk)


def _решить(uid: int, url: str, decision: str, note: str = "") -> dict[str, Any]:
    _, ответ = django(uid, ("post", f"{url}decide/", {"decision": decision, "note": note}))

    return ответ


# ── Документы ───────────────────────────────────────────────────────


def test_очередь_документов(люди):
    company = _компания()
    _документ(company, title="Свидетельство о регистрации", type="registration")
    _документ(company, title="Презентация компании", type="presentation")
    _документ(company, title="Старый сертификат", type="certificate", moderation_status="approved")
    _документ(company, title="Лицензия с истёкшим сроком", valid_until="2020-01-01")

    _, очередь, все = django(
        люди["moderator"], ("get", DOCS, None), ("get", DOCS + "?queue=1", None)
    )

    assert "Свидетельство о регистрации" in очередь["body"]
    assert "Презентация компании" not in все["body"], "материалы сюда не попадают"
    assert "Старый сертификат" not in очередь["body"] and "Старый сертификат" in все["body"]
    assert "1,5 МБ" in очередь["body"]
    # Просроченный документ помечен плашкой: цвет в ней от темы,
    # а не шестнадцатеричным кодом в разметке
    assert "01.01.2020" in очередь["body"] and "sx-pill--danger" in очередь["body"]


def test_принять_документ(люди):
    company = _компания()
    pk = _документ(company)

    _, страница = django(люди["moderator"], ("get", f"{DOCS}{pk}/change/", None))
    ответ = _решить(люди["moderator"], f"{DOCS}{pk}/", "approve")

    assert f'href="/files/{pk}"' in страница["body"]
    assert ответ["status"] == 302
    assert sql("select moderation_status, moderated_by from company_documents") == [
        ("approved", люди["moderator"])
    ]
    assert sql("select type, title, tone, url from user_notifications") == [
        ("moderation", "Документ «Лицензия на строительство» принят", "success", "/cabinet/company")
    ]
    assert журнал("approved")["section"] == "documents"
    [(changes,)] = sql(
        "select changes from admin_actions where section = 'documents' and action = 'updated'"
    )
    assert changes["after"]["moderation_status"] == "approved"
    assert sql("select verification_level from companies") == [(0,)], "уровень не меняется"


def test_отклонить_документ_с_причиной(люди):
    company = _компания()
    pk = _документ(company)

    _решить(люди["moderator"], f"{DOCS}{pk}/", "reject", "плохо")
    assert sql("select moderation_status from company_documents") == [("pending",)]

    _решить(люди["moderator"], f"{DOCS}{pk}/", "reject", REASON)

    assert sql("select moderation_status, moderation_note from company_documents") == [
        ("rejected", REASON)
    ]
    assert sql("select tone, body from user_notifications") == [("danger", REASON)]
    assert журнал("rejected")["changes"] is None


def test_документы_решает_модератор(люди):
    pk = _документ(_компания())

    _, список = django(люди["admin"], ("get", DOCS, None))
    ответ = _решить(люди["admin"], f"{DOCS}{pk}/", "approve")
    _, создать, удалить = django(
        люди["superadmin"],
        ("get", DOCS + "add/", None),
        ("post", f"{DOCS}{pk}/delete/", {"post": "yes"}),
    )

    assert список["status"] == 200, "администратор смотрит"
    assert ответ["status"] == 403
    assert (создать["status"], удалить["status"]) == (403, 403)
    assert sql("select count(*), max(moderation_status) from company_documents") == [(1, "pending")]


# ── Резюме ──────────────────────────────────────────────────────────


def _резюме(title: str = "Инженер-сметчик", **поля: Any) -> int:
    [(user,)] = sql(
        "insert into users (name, email, password, status, created_at, updated_at) "
        "values ('Соискатель', %s, 'x', 'active', now(), now()) returning id",
        [f"staff-{title.lower().replace(' ', '-')}@example.com"],
    )
    строка = {
        "user_id": user,
        "slug": title.lower().replace(" ", "-"),
        "title": title,
        "status": "published",
        "published_at": "2026-09-20 10:00:00",
        "experience_months": 40,
        "field": "construction",
        **поля,
    }
    columns = list(строка)
    [(pk,)] = sql(
        f"insert into resumes ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        list(строка.values()),
    )

    return int(pk)


def test_список_резюме(люди):
    _резюме()
    _резюме("Удалённое резюме", deleted_at="2026-09-21")

    _, список = django(люди["support"], ("get", RESUMES, None))

    assert список["status"] == 200
    assert "Инженер-сметчик" in список["body"] and "3 г. 4 мес." in список["body"]
    assert "Удалённое резюме" not in список["body"]


def test_снять_и_вернуть(люди):
    pk = _резюме()

    коротко = _решить(люди["moderator"], f"{RESUMES}{pk}/", "block", "спам")
    assert коротко["status"] == 302
    assert sql("select status from resumes") == [("published",)]

    _решить(люди["moderator"], f"{RESUMES}{pk}/", "block", "Контакты в тексте")
    assert sql("select status, moderation_note from resumes") == [("blocked", "Контакты в тексте")]
    assert журнал("hidden")["section"] == "resumes"

    _решить(люди["moderator"], f"{RESUMES}{pk}/", "restore")
    assert sql(
        "select status, moderation_note, to_char(published_at, 'YYYY-MM-DD') from resumes"
    ) == [("published", None, "2026-09-20")]
    assert журнал("restored")["section"] == "resumes"


def test_поддержка_не_снимает_удаление_суперадмином(люди):
    pk = _резюме()

    отказ = _решить(люди["support"], f"{RESUMES}{pk}/", "block", "Контакты в тексте")
    _, модератор = django(люди["moderator"], ("post", f"{RESUMES}{pk}/delete/", {"post": "yes"}))
    _, суперадмин = django(люди["superadmin"], ("post", f"{RESUMES}{pk}/delete/", {"post": "yes"}))

    assert отказ["status"] == 403
    assert модератор["status"] == 403
    assert суперадмин["status"] == 302
    assert sql("select status, deleted_at is not null from resumes") == [("published", True)]
