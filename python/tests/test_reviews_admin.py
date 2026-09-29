"""
Модерация отзывов на Django, этап 6: разделы «Отзывы» и «Отзывы о
площадке» вместо Filament.

- очередь «Ждут решения» по умолчанию: премодерация и споры;
- решения: опубликовать (рейтинг и уведомление компании), не пропускать
  (автору — формулировка), спор — скрыть (обеим сторонам) или оставить,
  вернуть на витрину; формулировка не короче 15 знаков; в журнале —
  «изменено» и строка о решении;
- решать может правка раздела, поддержка — только смотрит;
- заведение вручную (origin admin, кто завёл), пара «автор — компания»
  одна, компания не о себе; правка оценки двигает рейтинг, текста — нет;
- удаление — только суперадмин, рейтинг пересчитывается;
- загрузка файлом — право reviews.import, компании по названию;
- отзыв о площадке: опубликовать и отклонить — автору уведомление на
  его языке, заводить и править нельзя.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник, файл

pytestmark = нужна_база

LIST = "/py/admin/moderation/review/"
PLATFORM = "/py/admin/moderation/platformreview/"
NOTE = "В тексте указан телефон — контакты раскрываются платно"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator", "support")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from user_notifications")
    sql("delete from activity_events")
    sql("delete from reviews")
    sql("delete from platform_reviews")
    sql("delete from users where email like 'staff-%%'")
    sql("delete from companies")
    sql("delete from admin_actions where section in ('reviews', 'companies')")


def _компания(name: str, *, сотрудник_: bool = True) -> int:
    [(pk,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values (%s, %s, 'active', now(), now()) returning id",
        [name, name.lower().replace(" ", "-")],
    )

    if сотрудник_:
        sql(
            "insert into users (name, email, password, company_id, status, created_at, "
            "updated_at) values (%s, %s, 'x', %s, 'active', now(), now())",
            [f"Сотрудник {name}", f"staff-{pk}@example.com", pk],
        )

    return int(pk)


def _отзыв(about: int, author: int, **поля: Any) -> int:
    строка = {"rating": 5, "body": "Отгрузили вовремя, всё как в описании.", **поля}
    columns = ["company_id", "author_company_id", *строка]
    [(pk,)] = sql(
        f"insert into reviews ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [about, author, *строка.values()],
    )

    return int(pk)


def _рейтинг(company: int) -> tuple[Any, ...]:
    [row] = sql("select rating, reviews_count from companies where id = %s", [company])

    return row


def _уведомления(company: int) -> list[tuple[Any, ...]]:
    return sql(
        "select n.type, n.title, n.tone, n.body, n.url from user_notifications n "
        "join users u on u.id = n.user_id where u.company_id = %s order by n.id",
        [company],
    )


def _решить(uid: int, pk: int, decision: str, note: str = "") -> dict[str, Any]:
    _, ответ = django(uid, ("post", f"{LIST}{pk}/decide/", {"decision": decision, "note": note}))

    return ответ


# ── Очередь ─────────────────────────────────────────────────────────


def test_очередь_ждут_решения(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    _отзыв(about, author, status="moderation", body="Ждёт проверки модератора")
    other = _компания("Третья")
    _отзыв(about, other, dispute_status="pending", dispute_reason="Не работали с ними")
    _отзыв(author, about, body="Давно опубликованный отзыв")

    _, очередь, все = django(
        люди["moderator"], ("get", LIST, None), ("get", LIST + "?queue=1", None)
    )

    assert "Ждёт проверки модератора" in очередь["body"]
    assert "Не работали с ними" in очередь["body"]
    assert "Давно опубликованный" not in очередь["body"]
    assert "Давно опубликованный" in все["body"]


# ── Решения ─────────────────────────────────────────────────────────


def test_опубликовать(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author, status="moderation", rating=4)

    ответ = _решить(люди["moderator"], pk, "approve")

    assert ответ["status"] == 302
    assert sql("select status, moderated_by from reviews") == [("published", люди["moderator"])]
    assert _рейтинг(about)[1] == 1
    assert _уведомления(about) == [
        (
            "review",
            "Компания «Инвест» оставила отзыв: 4 из 5",
            "success",
            "Отгрузили вовремя, всё как в описании.",
            "/cabinet/reviews",
        )
    ]
    assert журнал("approved")["subject_label"] == f"Review #{pk}"
    [(changes,)] = sql(
        "select changes from admin_actions where section = 'reviews' and action = 'updated'"
    )
    assert changes["after"]["status"] == "published", "AuditObserver у Review"


def test_не_пропускать_с_формулировкой(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author, status="moderation")

    коротко = _решить(люди["moderator"], pk, "reject", "плохо")
    assert коротко["status"] == 302
    assert sql("select status from reviews") == [("moderation",)], "без формулировки — нет"

    _решить(люди["moderator"], pk, "reject", NOTE)

    assert sql("select status, moderator_note from reviews") == [("hidden", NOTE)]
    assert _уведомления(author) == [
        ("moderation", "Ваш отзыв не прошёл проверку", "warning", NOTE, None)
    ]
    assert _уведомления(about) == []
    assert журнал("rejected")["changes"] is None


def test_спор_удовлетворён_обе_стороны_узнают(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author, rating=1, dispute_status="pending", dispute_reason="Не работали")
    sql("update companies set rating = 1, reviews_count = 1 where id = %s", [about])

    _решить(люди["moderator"], pk, "accept", NOTE)

    assert sql("select status, dispute_status from reviews") == [("hidden", "accepted")]
    assert _рейтинг(about)[1] == 0, "рейтинг пересчитан"
    assert [row[1] for row in _уведомления(about)] == ["Спор по отзыву удовлетворён — отзыв скрыт"]
    assert [row[1] for row in _уведомления(author)] == ["Ваш отзыв скрыт по результатам проверки"]
    assert журнал("hidden")["changes"] is None


def test_спор_отклонён_и_вернуть_на_витрину(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author, dispute_status="pending")
    скрытый = _отзыв(author, about, status="hidden")

    _решить(люди["moderator"], pk, "decline", NOTE)
    _решить(люди["moderator"], скрытый, "restore")

    assert sql("select id, status, dispute_status from reviews order by id") == [
        (pk, "published", "declined"),
        (скрытый, "published", "declined"),
    ]
    assert [row[1] for row in _уведомления(about)] == ["Спор по отзыву отклонён — отзыв остаётся"]
    assert _рейтинг(author)[1] == 1


def test_решать_может_только_правка_раздела(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author, status="moderation")

    _, список, страница = django(
        люди["support"], ("get", LIST, None), ("get", f"{LIST}{pk}/change/", None)
    )
    отказ = _решить(люди["support"], pk, "approve")

    assert список["status"] == 200
    assert "Опубликовать" not in страница["body"]
    assert отказ["status"] == 403
    assert sql("select status from reviews") == [("moderation",)]


def test_недоступное_решение_не_проходит(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author)

    _решить(люди["moderator"], pk, "accept", NOTE)

    assert sql("select status, dispute_status from reviews") == [("published", None)]


# ── Форма ───────────────────────────────────────────────────────────


def _форма(about: int, author: int, **поля: str) -> dict[str, str]:
    return {
        "company": str(about),
        "author_company": str(author),
        "listing": "",
        "rating": "5",
        "rating_description": "",
        "rating_response": "",
        "rating_deadlines": "",
        "rating_quality": "",
        "body": "Отгрузили вовремя, качество соответствует.",
        "reply": "",
        "status": "published",
        **поля,
    }


def test_заведение_вручную(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")

    _, ответ = django(люди["admin"], ("post", LIST + "add/", _форма(about, author)))

    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql("select origin, created_by, reply, rating_quality, deal_confirmed from reviews") == [
        ("admin", люди["admin"], None, None, False)
    ]
    assert _рейтинг(about)[1] == 1, "заведённый отзыв двигает рейтинг"
    assert журнал("created")["section"] == "reviews"


def test_пара_одна_и_не_о_себе(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    _отзыв(about, author)

    _, повтор, о_себе = django(
        люди["admin"],
        ("post", LIST + "add/", _форма(about, author)),
        ("post", LIST + "add/", _форма(about, about)),
    )

    assert "Отзыв этой компании об этой уже есть" in повтор["body"]
    assert "Компания не может отозваться о себе" in о_себе["body"]
    assert sql("select count(*) from reviews") == [(1,)]


def test_правка_оценки_двигает_рейтинг_а_текста_нет(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author, origin="buyer")
    sql("update companies set rating = 0, reviews_count = 0 where id = %s", [about])

    django(
        люди["admin"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма(about, author, body="Исправлена опечатка в тексте."),
        ),
    )
    assert _рейтинг(about)[1] == 0, "правка текста рейтинг не трогает"

    django(люди["admin"], ("post", f"{LIST}{pk}/change/", _форма(about, author, rating="3")))

    assert _рейтинг(about)[1] == 1
    assert sql("select origin from reviews") == [("buyer",)], "происхождение не меняется"


def test_удаление_только_суперадмин(люди):
    about, author = _компания("Стройбаза"), _компания("Инвест")
    pk = _отзыв(about, author)
    sql("update companies set reviews_count = 1 where id = %s", [about])

    _, админ = django(люди["admin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    _, суперадмин = django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))

    assert админ["status"] == 403
    assert суперадмин["status"] == 302
    assert sql("select count(*) from reviews") == [(0,)]
    assert _рейтинг(about)[1] == 0
    assert журнал("deleted")["subject_label"] == f"Review #{pk}"


# ── Загрузка файлом ─────────────────────────────────────────────────


def test_загрузка_файлом(люди):
    about, author = _компания("Oltin Mebel"), _компания("Stroy Invest")
    csv = (
        "О какой компании;От какой компании;Оценка;Текст отзыва\n"
        "oltin mebel;STROY INVEST;4/5;Отгрузили вовремя, качество как в описании.\n"
        "Неизвестная;Stroy Invest;5;Такой компании нет на площадке совсем.\n"
    ).encode()

    _, модератор = django(люди["moderator"], ("get", LIST + "import/", None))
    _, ответ = django(люди["admin"], ("post", LIST + "import/", {"file": файл("reviews.csv", csv)}))

    assert модератор["status"] == 403, "загрузка — отдельное право"
    assert ответ["status"] == 200
    assert "Загружено отзывов: <b>1</b>" in ответ["body"]
    assert sql(
        "select company_id, author_company_id, rating, origin, status, created_by from reviews"
    ) == [(about, author, 4, "import", "published", люди["admin"])]
    assert _рейтинг(about)[1] == 1


# ── Отзывы о площадке ───────────────────────────────────────────────


def _о_площадке(**поля: Any) -> tuple[int, int]:
    [(user,)] = sql(
        "insert into users (name, email, password, status, locale, created_at, updated_at) "
        "values ('Автор', 'staff-author@example.com', 'x', 'active', 'uz', now(), now()) "
        "returning id"
    )
    строка = {"rating": 5, "body": "Удобная площадка, нашли поставщика за день.", **поля}
    columns = ["user_id", *строка]
    [(pk,)] = sql(
        f"insert into platform_reviews ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [user, *строка.values()],
    )

    return int(pk), int(user)


def test_о_площадке_опубликовать_и_отклонить(люди):
    pk, user = _о_площадке(status="moderation")

    _, страница, опубликован = django(
        люди["moderator"],
        ("get", f"{PLATFORM}{pk}/change/", None),
        ("post", f"{PLATFORM}{pk}/decide/", {"decision": "approve"}),
    )

    assert "Опубликовать" in страница["body"]
    assert опубликован["status"] == 302
    assert sql("select status, moderator_note from platform_reviews") == [("published", None)]

    django(
        люди["moderator"],
        ("post", f"{PLATFORM}{pk}/decide/", {"decision": "reject", "note": NOTE}),
    )

    assert sql("select status, moderator_note from platform_reviews") == [("hidden", NOTE)]
    уведомления = sql(
        "select type, tone, body, url from user_notifications where user_id = %s order by id",
        [user],
    )
    assert уведомления == [
        ("review", "success", None, "/reviews?type=platform"),
        ("moderation", "warning", NOTE, "/reviews/new"),
    ]
    [(title,)] = sql(
        "select title from user_notifications where user_id = %s and type = 'review'", [user]
    )
    assert "SavdEx" in title and "Ваш отзыв" not in title, "уведомление — на языке автора"
    assert журнал("rejected")["subject_type"] == "App\\Models\\PlatformReview"


def test_о_площадке_не_заводится_и_не_правится(люди):
    pk, _ = _о_площадке(status="moderation", body="Исходный текст отзыва о площадке.")

    _, добавить, править = django(
        люди["superadmin"],
        ("get", PLATFORM + "add/", None),
        ("post", f"{PLATFORM}{pk}/change/", {"body": "Подменённый текст"}),
    )

    assert добавить["status"] == 403
    assert править["status"] == 403
    assert sql("select body from platform_reviews") == [("Исходный текст отзыва о площадке.",)]
