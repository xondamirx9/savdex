"""
Этап 5, шаг 2: кабинет на Django — сводка /cabinet и разделы.

Перед страницей — посредники маршрута: гость уходит на вход (адрес
запоминается в сессии, url.intended), пароль, выданный вручную, — на
смену пароля с предупреждением в сессии; XHR гостя — тоже на вход.

Сама сводка: компания и заполненность профиля (чего не хватает — на
языке страницы), показатели за 30 дней к предыдущим 30, ряды со
сглаживанием, последние события, лимиты тарифа, истекающие и черновики;
у пунктов меню — счётчики кабинета. Без компании — пустая сводка.
Разделы кабинета (аналитика, отзывы, контакты, чаты, объявления,
продвижение, резюме, профиль, IT-задачи, мини-сайт, мастер объявления)
проверяются по ключевым данным страницы.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from .factories import (
    Выражение,
    _вставить,
    it_задача,
    компания,
    объявление,
    открытие_контакта,
    отзыв,
)
from .factories import пользователь as сотрудник_компании
from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import (
    СЕССИЯ,
    куки_ответа,
    открыть,
    пользователь,
    сессия_из,
    страница,
    строка,
    адрес,
    вход,
)

pytestmark = нужна_база

СЕГОДНЯ = "(now() at time zone 'utc')::date"


def вставить(table: str, **поля: Any) -> int:
    """Строка таблицы (created_at и updated_at — сейчас, если не заданы)."""
    return _вставить(table, поля)


def удалить(table: str, pk: int) -> None:
    """Мягкое удаление (SoftDeletes): deleted_at — сейчас."""
    sql(f"update {table} set deleted_at = now() where id = %s", [pk])


def _owner() -> int:
    return int(sql("select id from companies where slug = 'owner'")[0][0])


def _первое_объявление(company: int) -> int:
    return int(sql("select min(id) from listings where company_id = %s", [company])[0][0])


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    # Справочники, как db:seed (тарифы, география, категории, типы
    # продвижения) — manage.py seed --fresh под владельцем базы
    subprocess.run(
        [sys.executable, "manage.py", "seed", "--fresh"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        check=True,
        capture_output=True,
    )

    # Компания владельца: объявления, статистика за 70 дней, кошелёк,
    # подписка, события одной секунды, чаты, отзывы, раскрытия
    c = компания(slug="owner", tin=None, address="  ", description="а" * 99, logo_path=None)
    other = компания()
    ls = [
        объявление(company_id=c, expires_at=Выражение("now() + interval '3 days'"))
        for _ in range(3)
    ]
    объявление(company_id=c, expires_at=Выражение("now() + interval '20 days'"))
    объявление(company_id=c, draft=True)
    gone = объявление(company_id=c)

    for d in range(70):
        for k, listing in enumerate([ls[0], ls[1], gone]):
            вставить(
                "listing_stats",
                listing_id=listing,
                date=Выражение(f"{СЕГОДНЯ} - {d}"),
                impressions=(d * 7 + k) % 13,
                views=(d * 3 + k) % 5,
                favorites=d % 2,
                unlocks=(d + k) % 3,
            )

    удалить("listings", gone)
    [(plan,)] = sql("select id from plans where code != 'free' order by id limit 1")
    вставить(
        "subscriptions",
        company_id=c,
        plan_id=plan,
        status="active",
        started_at=Выражение("now() - interval '3 days'"),
        ends_at=Выражение("now() + interval '27 days'"),
    )
    вставить(
        "wallets",
        company_id=c,
        credits=4,
        promo_units=1,
        contacts_used_this_period=2,
        period_resets_at=Выражение("now() + interval '10 days'"),
    )

    for i in range(1, 8):
        вставить(
            "activity_events",
            company_id=c,
            type="view",
            tone="primary",
            message=f"Событие {i}",
            url="/cabinet",
            created_at=Выражение("now() - interval '3 hours'"),
        )

    открытие_контакта(company_id=c, target_company_id=other)

    for from_ in (other, компания()):
        открытие_контакта(company_id=from_, target_company_id=c)

    [_, city] = [r[0] for r in sql("select id from cities order by id limit 2")]
    sql("update companies set city_id = %s where id = %s", [city, other])
    отзыв(company_id=c, author_company_id=other, status="published")
    t = вставить(
        "message_threads",
        buyer_company_id=other,
        seller_company_id=c,
        seller_read_at=Выражение("now() - interval '1 day'"),
    )
    вставить("messages", thread_id=t, company_id=other, body="Здравствуйте")

    # Аналитика: поисковые запросы (равные показы — порядок по запросу),
    # города компаний, открывавших контакты
    for i, q in enumerate(["цемент", "арматура", "бетон", "кирпич"]):
        for d in (0, 5, 40):
            вставить(
                "search_hits",
                company_id=c,
                query=q,
                date=Выражение(f"{СЕГОДНЯ} - {d}"),
                impressions=3 - (i % 2),
                clicks=i,
            )

    with адрес() as root:
        yield root


def владелец(сайт: str) -> dict[str, str]:
    """Куки вошедшего владельца компании owner."""
    email = "owner@savdex.uz"

    if not sql("select 1 from users where email = %s", [email]):
        пользователь(email)
        sql(
            "update users set company_id = (select id from companies where slug = 'owner') "
            "where email = %s",
            [email],
        )

    # Язык из адреса прошлой страницы (/uz/cabinet) уводил бы на /uz/…
    sql("update users set locale = 'ru' where email = %s", [email])

    return войти(email)


def войти(email: str) -> dict[str, str]:
    """Куки вошедшего (сессия в базе, без формы входа)."""
    [(uid,)] = sql("select id from users where email = %s", [email])

    return вход(int(uid))


def без_компании(email: str) -> dict[str, str]:
    пользователь(email)

    return войти(email)


def зайти(
    сайт: str, path: str, куки: dict[str, str] | None = None, **kwargs: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ответ Django и объект страницы Inertia (у перехода — пустой)."""
    ответ = открыть(сайт, path, куки, **kwargs)

    return ответ, (страница(ответ["body"]) if ответ["status"] == 200 else {})


def с_сессией(
    сайт: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str]:
    """Ответ и payload строки sessions, на которую указывает кука ответа."""
    ответ = открыть(сайт, path, cookies, headers)
    итог = строка(сессия_из(ответ))
    assert итог is not None

    return ответ, итог["payload"]


def _отзывы() -> None:
    """Отзывы разных оценок: критерии с нулями и пустыми, автор в корзине, спор."""
    if sql("select count(*) from reviews")[0][0] > 1:
        return

    c = _owner()
    first = _первое_объявление(c)
    оценки = [(5, 5, 0, None, 4), (3, 2, 3, 3, 3), (4, 4, 5, None, None), (5, 5, 5, 5, 5)]

    for i, (r, d, s, t, q) in enumerate(оценки):
        автор = компания()
        отзыв(
            company_id=c,
            author_company_id=автор,
            rating=r,
            rating_description=d,
            rating_response=s,
            rating_deadlines=t,
            rating_quality=q,
            status="published",
            listing_id=first if i == 0 else None,
            reply="Спасибо" if i == 1 else None,
            dispute_status="rejected" if i == 2 else None,
            moderator_note="Отзыв по делу" if i == 2 else None,
            deal_confirmed=i % 2 == 0,
        )

        if i == 3:
            удалить("companies", автор)

    отзыв(company_id=c, author_company_id=компания(), status="hidden")
    # Часами раньше, одна пара — в одну секунду: «N секунд назад» и
    # порядок равных не плавают
    sql("update reviews set created_at = now() - make_interval(hours => id::int, mins => 30)")
    sql(
        "update reviews set created_at = (select min(created_at) from reviews) where id in "
        "(select id from reviews order by id desc limit 2)"
    )


def _раскрытия() -> None:
    """Раскрытия владельца: статусы, заметки, телефоны и почты, компания в корзине."""
    if sql("select count(*) from contact_unlocks where note is not null")[0][0]:
        return

    c = _owner()
    first = _первое_объявление(c)

    for i, status in enumerate(["negotiating", "deal", "rejected", "contacted"]):
        t = компания(name=f"Поставщик {i}")
        вставить(
            "company_contacts",
            company_id=t,
            type="phone",
            value=f"+99890000000{i}",
            is_public=True,
            is_primary=i == 1,
        )
        вставить(
            "company_contacts", company_id=t, type="email", value=f"p{i}@x.uz", is_public=False
        )
        вставить(
            "company_contacts", company_id=t, type="phone", value=f"+99871000000{i}", is_public=True
        )
        открытие_контакта(
            company_id=c,
            target_company_id=t,
            status=status,
            note="ждём КП" if i == 2 else None,
            listing_id=first if i == 0 else None,
            complaint_status="pending" if i == 3 else None,
        )

        if i == 3:
            удалить("companies", t)

    sql(
        "update contact_unlocks set created_at = now() - make_interval(hours => id::int, mins => 30)"
    )


def _избранное(uid: int) -> None:
    """Избранное: объявления всех статусов, удалённое, у удалённой компании."""
    if sql("select 1 from favorites where user_id = %s", [uid]):
        return

    seller, gone = компания(), компания()
    ids = [
        объявление(company_id=seller, status=s, published_at="2026-09-20 10:00:00")
        for s in ("active", "expired", "archived", "draft", "moderation")
    ]
    trashed = объявление(company_id=seller)
    удалить("listings", trashed)
    ids += [trashed, объявление(company_id=gone, published_at="2026-09-21 10:00:00")]
    удалить("companies", gone)

    for listing in ids:
        вставить("favorites", user_id=uid, listing_id=listing)


def _объявления() -> None:
    """Объявления всех вкладок, два значка продвижения, замечание модератора."""
    if sql("select 1 from listings where status = 'needs_changes'"):
        return

    c = _owner()

    for status in ("needs_changes", "expired", "rejected", "archived"):
        объявление(
            company_id=c,
            status=status,
            moderation_note="Добавьте фото" if status == "needs_changes" else None,
        )

    [(active,)] = sql(
        "select min(id) from listings where company_id = %s and status = 'active' "
        "and deleted_at is null",
        [c],
    )

    for code in ("urgent", "highlight"):
        [(type_,)] = sql("select id from promotion_types where code = %s", [code])
        вставить(
            "promotions",
            listing_id=active,
            company_id=c,
            units_spent=1,
            promotion_type_id=type_,
            status="active",
            starts_at=Выражение("now()"),
            ends_at=Выражение("now() + interval '3 days'"),
            # Promotion::saving: ключ «одно продвижение на объявление»
            active_key=f"{active}:{type_}",
        )

    # Массовое действие — одна секунда у всех: порядок решает id
    sql("update listings set updated_at = '2026-09-25 12:00:00'")


def _чаты() -> None:
    """Разговоры: обе стороны, собеседник в корзине, IT-задача, пустой, прочитанное."""
    if sql("select count(*) from message_threads")[0][0] > 1:
        return

    c = _owner()
    first = _первое_объявление(c)
    task = it_задача()

    for i in range(5):
        o = компания()
        t = вставить(
            "message_threads",
            buyer_company_id=c if i % 2 else o,
            seller_company_id=o if i % 2 else c,
            listing_id=first if i == 0 else None,
            it_task_id=task if i == 1 else None,
        )

        if i < 4:
            for k in (1, 2, 3):
                вставить(
                    "messages",
                    thread_id=t,
                    company_id=c if k == 3 and i == 2 else o,
                    body=f"Сообщение {k} " * (k * 5),
                )

        if i == 3:
            удалить("companies", o)

    sql("update messages set created_at = now() - make_interval(hours => 50 - id::int, mins => 30)")
    sql(
        "update message_threads t set last_message_at = (select max(created_at) from messages m "
        "where m.thread_id = t.id)"
    )
    # Прочитано до второго сообщения — у одной стороны
    sql(
        "update message_threads t set seller_read_at = (select min(created_at) from messages m "
        "where m.thread_id = t.id) + interval '1 minute' where t.id = (select min(id) from "
        "message_threads where seller_company_id = (select id from companies where slug = 'owner'))"
    )


def _резюме(uid: int) -> None:
    вставить(
        "resumes",
        user_id=uid,
        slug="logist",
        title="Логист",
        field="logistics",
        salary=1200,
        currency="USD",
        employment=["full", "project"],
        skills=["1С", "Excel"],
        jobs=[{"company": "Стройбаза", "position": "Логист", "from": "2020-01", "to": None}],
        experience_months=45,
        photo_path="resumes/p.webp",
        moderation_note="Уточните зарплату",
        status="draft",
    )


def _документы() -> None:
    """Документы разных видов, файл на диске у одного; сотрудник; контакты."""
    if sql("select 1 from company_documents limit 1"):
        return

    файл = КОРЕНЬ / "storage/app/private/docs/reg.pdf"
    файл.parent.mkdir(parents=True, exist_ok=True)
    файл.write_bytes(b"%PDF-1.4 test")
    c = _owner()

    for type_, status, path, size in (
        ("registration", "approved", "docs/reg.pdf", 2500000),
        ("license", "pending", "docs/lic.pdf", 20480),
        ("price_list", "pending", "docs/p.xlsx", None),
    ):
        вставить(
            "company_documents",
            company_id=c,
            type=type_,
            title=f"Док {type_}",
            file_path=path,
            file_size=size,
            is_public=type_ != "license",
            moderation_status=status,
            valid_until="2027-01-31" if type_ == "license" else None,
            created_at="2026-09-20 10:00:00",
        )

    вставить(
        "company_contacts",
        company_id=c,
        type="phone",
        value="+998901234567",
        label="Отдел продаж",
        contact_person="Азиз",
        is_public=True,
        is_primary=True,
    )
    вставить(
        "company_contacts", company_id=c, type="email", value="sales@owner.uz", is_public=False
    )
    сотрудник_компании(company_id=c, company_role="staff", email_verified_at=None)


def _задачи() -> int:
    """IT-задачи владельца: бюджеты трёх видов, исполнитель, отклики, файлы."""
    c = _owner()

    if not sql("select 1 from it_tasks where company_id = %s", [c]):
        dev = компания(name="Tashkent Soft")
        бюджеты = [
            ("fixed", 1500000, None, "UZS"),
            ("range", 500, 900, "USD"),
            ("negotiable", None, None, "UZS"),
        ]

        for i, (type_, from_, to, cur) in enumerate(бюджеты):
            t = it_задача(
                company_id=c,
                budget_type=type_,
                budget_from=from_,
                budget_to=to,
                currency=cur,
                status=["active", "completed", "closed"][i],
                contractor_company_id=dev if i == 1 else None,
                deadline_at="2026-12-01" if i == 0 else None,
                stack=["Laravel", "React"],
                created_at="2026-09-20 10:00:00",
            )

            if i == 0:
                for k, b in enumerate([dev, компания()]):
                    вставить(
                        "message_threads", buyer_company_id=b, seller_company_id=c, it_task_id=t
                    )

                    if k == 1:
                        удалить("companies", b)

                for size in (2048, 3500000):
                    вставить(
                        "it_task_files",
                        it_task_id=t,
                        title=f"ТЗ {size}",
                        file_path=f"it/{size}",
                        file_size=size,
                        mime="application/pdf",
                    )

    [(first,)] = sql(
        "select min(id) from it_tasks where company_id = %s and budget_type = 'fixed'", [c]
    )

    return int(first)


def _мини_сайт() -> None:
    """Опубликованный сайт с фоном на диске и тремя товарами."""
    фон = КОРЕНЬ / "storage/app/public/sites/1/hero.webp"
    фон.parent.mkdir(parents=True, exist_ok=True)
    фон.write_bytes(b"RIFF")
    c = _owner()
    sql("delete from company_sites where company_id = %s", [c])
    вставить(
        "company_sites",
        company_id=c,
        subdomain="owner-shop",
        status="published",
        published_at="2026-09-21 14:30:00",
        theme={
            "template": "bold",
            "primary": "#AABBCC",
            "mode": "neon",
            "hero_image": "sites/1/hero.webp",
            "extra": "x",
        },
        published_theme={"template": "classic"},
    )
    sql("delete from company_site_products where company_id = %s", [c])

    for sort, title, price in ((2, "Цемент", 45000), (1, "Арматура", None), (1, "Щебень", 120)):
        вставить(
            "company_site_products",
            company_id=c,
            title=title,
            price=price,
            currency="UZS",
            sort=sort,
            image_path="sites/1/hero.webp" if title == "Цемент" else None,
        )


def _черновик() -> int:
    """Черновик владельца в подразделе с полями, характеристиками и фото."""
    found = sql("select id from listings where slug = 'wizard-draft'")

    if found:
        return int(found[0][0])

    [(child,)] = sql("select min(id) from categories where parent_id is not null")
    # updateOrCreate(['key' => 'mark'], …) у полей подраздела
    поле = {"label": "Марка", "type": "select", "options": '["М400", "М500"]', "sort": 1}

    if sql("select 1 from category_fields where category_id = %s and key = 'mark'", [child]):
        sql(
            "update category_fields set label = %s, type = %s, options = %s, sort = %s, "
            "updated_at = now() where category_id = %s and key = 'mark'",
            [*поле.values(), child],
        )
    else:
        вставить("category_fields", category_id=child, key="mark", **поле)

    listing = объявление(
        draft=True,
        company_id=_owner(),
        slug="wizard-draft",
        category_id=child,
        title="Цемент М400 навалом 50 кг",
        tags=["цемент"],
        wizard_step=3,
    )

    for key, value in (
        ("weight", "50 кг"),
        ("mark", "М400"),
        ("spec_weight", "50 kg"),
        ("spec_color", "grey"),
    ):
        вставить("listing_attributes", listing_id=listing, key=key, value=value)

    for i, sort in enumerate((1, 0)):
        вставить(
            "listing_images",
            listing_id=listing,
            path=f"l/w{i}.webp",
            thumb_path=None if i else f"l/wt{i}.webp",
            sort=sort,
        )

    return listing


def _просмотры() -> None:
    """Просмотры визитки и объявлений: зрители, удалённое объявление, «и ещё»."""
    if sql("select 1 from audience_views limit 1"):
        return

    [(owner,)] = sql("select id from companies where slug = 'owner'")
    зрители = [r[0] for r in sql("select id from companies where id != %s order by id", [owner])]
    объявления = [
        r[0] for r in sql("select id from listings where company_id = %s order by id", [owner])
    ]

    for i, зритель in enumerate(зрители[:3]):
        for j, объявление in enumerate([None, *объявления][: 2 + 2 * i]):
            sql(
                "insert into audience_views (target_company_id, viewer_company_id, listing_id, "
                "created_at, updated_at) values (%s, %s, %s, "
                "now() - make_interval(hours => %s + 1, mins => 30), now())",
                [owner, зритель, объявление, i + j],
            )

    # Раскрытия — часами раньше: «N секунд назад» разошлось бы между сторонами
    sql(
        "update contact_unlocks set "
        "created_at = now() - make_interval(hours => id::int, mins => 30)"
    )

    # Старше месяца — не считается
    sql(
        "insert into audience_views (target_company_id, viewer_company_id, listing_id, "
        "created_at, updated_at) values (%s, %s, null, now() - interval '40 days', now())",
        [owner, зрители[0]],
    )
