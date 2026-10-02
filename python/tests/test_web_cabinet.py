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
    отзыв,
    открытие_контакта,
)
from .factories import пользователь as сотрудник_компании
from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import (
    СЕССИЯ,
    адрес,
    вход,
    куки_ответа,
    открыть,
    пользователь,
    сессия_из,
    страница,
    строка,
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

    return куки_входа(email)


def куки_входа(email: str) -> dict[str, str]:
    """Куки вошедшего (сессия в базе, без формы входа)."""
    [(uid,)] = sql("select id from users where email = %s", [email])

    return вход(int(uid))


def без_компании(email: str) -> dict[str, str]:
    пользователь(email)

    return куки_входа(email)


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
        "update contact_unlocks set "
        "created_at = now() - make_interval(hours => id::int, mins => 30)"
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
        for j, номер in enumerate([None, *объявления][: 2 + 2 * i]):
            sql(
                "insert into audience_views (target_company_id, viewer_company_id, listing_id, "
                "created_at, updated_at) values (%s, %s, %s, "
                "now() - make_interval(hours => %s + 1, mins => 30), now())",
                [owner, зритель, номер, i + j],
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


СЧЁТЧИКИ = {"listings": 4, "contacts": 1, "incoming": 2, "reviews": 1, "chats": 1}


# ── Посредники ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "вход_", "запомнен"),
    [
        ("/cabinet", "/login", "/cabinet"),
        # Адрес запоминается без префикса языка, вход — на языке адреса
        ("/uz/cabinet", "/uz/login", "/cabinet"),
        ("/cabinet?tab=x&a=1", "/login", "/cabinet?a=1&tab=x"),
    ],
)
def test_гость_уходит_на_вход(сайт, path, вход_, запомнен):
    ответ, payload = с_сессией(сайт, path)

    assert ответ["status"] == 302 and ответ["headers"]["location"] == сайт + вход_
    intended = (сайт + запомнен).replace("/", "\\/")
    assert f'"url":{{"intended":"{intended}"}}' in payload and '"locale"' not in payload


def test_xhr_гостя_тоже_на_вход(сайт):
    """JSON с 401 у Laravel был только для api/*: XHR страницы уходит на вход."""
    ответ, payload = с_сессией(
        сайт, "/cabinet", headers={"X-Requested-With": "XMLHttpRequest", "Accept": "*/*"}
    )

    assert ответ["status"] == 302 and ответ["headers"]["location"] == сайт + "/login"
    assert "intended" in payload


def test_выданный_пароль_уводит_на_смену(сайт):
    пользователь("temp@savdex.uz", must_change_password=True)
    ответ, payload = с_сессией(сайт, "/cabinet", куки_входа("temp@savdex.uz"))

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == сайт + "/password/change"
    assert '"warning":' in payload and '"new":["warning"]' not in payload


# ── Сводка ──────────────────────────────────────────────────────────

НЕ_ХВАТАЕТ = {
    "ru": [
        "ИНН или СТИР",
        "юридический адрес",
        "описание компании (от 100 символов)",
        "логотип",
        "подтверждённые документы",
    ],
    "en": [
        "TIN",
        "legal address",
        "company description (100+ characters)",
        "logo",
        "verified documents",
    ],
    "uz": [
        "INN yoki STIR",
        "yuridik manzil",
        "kompaniya tavsifi (100 belgidan boshlab)",
        "logotip",
        "tasdiqlangan hujjatlar",
    ],
}


@pytest.mark.parametrize(
    ("path", "язык"),
    [("/cabinet", "ru"), ("/en/cabinet", "en"), ("/uz/cabinet", "uz")],
)
def test_сводка(сайт, path, язык):
    ответ, стр = зайти(сайт, path, владелец(сайт))
    props = стр["props"]

    assert ответ["status"] == 200 and стр["component"] == "cabinet/Dashboard"
    assert props["counts"] == СЧЁТЧИКИ
    # Профиль: нет ИНН, адреса (одни пробелы), описания короче 100, логотипа
    assert props["company"]["slug"] == "owner" and props["company"]["completeness"] == 30
    assert props["company"]["missing"] == НЕ_ХВАТАЕТ[язык]
    assert props["expiring"] == 3 and props["drafts"] == 1
    # Последние пять событий одной секунды — по убыванию номера
    assert [e["message"] for e in props["events"]] == [f"Событие {i}" for i in (7, 6, 5, 4, 3)]
    # 30 дней к предыдущим 30; удалённое объявление тоже в счёте
    assert props["metrics"]["impressions"] == {"value": 348, "delta": -8.7, "format": "int"}
    assert len(props["series"]["impressions"]) == 30
    assert props["limits"]["contacts"] == {"used": 2, "total": 10}
    assert props["plan"]["name"] == "Flash"


def test_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet", без_компании("nocompany@savdex.uz"))
    props = стр["props"]

    assert стр["component"] == "cabinet/Dashboard"
    assert props["company"] is None and props["counts"] is None
    assert props["metrics"] is None and props["events"] == []


def test_счётчики_только_в_кабинете(сайт):
    _, стр = зайти(сайт, "/about", владелец(сайт))

    assert стр["component"] == "About" and стр["props"]["counts"] is None


def test_переход_inertia(сайт):
    куки = владелец(сайт)
    полная = открыть(сайт, "/cabinet", куки)
    версия = страница(полная["body"])["version"]

    ответ = открыть(
        сайт,
        "/cabinet",
        куки,
        {
            "X-Inertia": "true",
            "X-Inertia-Version": версия,
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    # Переход Inertia — JSON страницы той же версии, без HTML
    assert ответ["status"] == 200 and ответ["headers"]["x-inertia"] == "true"
    assert ответ["body"].startswith("{")
    стр = страница(ответ["body"])
    assert стр["component"] == "cabinet/Dashboard" and стр["version"] == версия
    assert стр["props"]["counts"] == СЧЁТЧИКИ
    assert куки_ответа(полная)[СЕССИЯ]["value"]


# ── Аналитика ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("query", "period", "показы"),
    [
        ("", 30, 348),
        ("?period=7", 7, 67),
        ("?period=90", 90, 821),
        # Непонятный период — 30 дней; «7abc» — как (int) у PHP, 7
        ("?period=abc", 30, 348),
        ("?period=", 30, 348),
        ("?period[]=7", 30, 348),
        ("?period=7abc", 7, 67),
    ],
)
def test_аналитика(сайт, query, period, показы):
    _, стр = зайти(сайт, "/cabinet/analytics" + query, владелец(сайт))
    props = стр["props"]

    assert стр["component"] == "cabinet/Analytics"
    assert props["period"] == period and props["metrics"]["impressions"]["value"] == показы
    assert len(props["series"]["impressions"]) == period
    assert props["funnel"][0]["value"] == показы
    # Города компаний, открывавших контакты
    assert sorted(g["label"] for g in props["geography"]) == ["Самарканд", "Ташкент"]
    # Тариф без расширенной аналитики: ни запросов, ни сравнения
    assert props["advanced"] is False and props["queries"] == [] and props["benchmark"] == []


@pytest.mark.parametrize(
    ("path", "показы"),
    [("/uz/cabinet/analytics?period=90", [9, 9, 6, 6]), ("/en/cabinet/analytics", [6, 6, 4, 4])],
)
def test_аналитика_расширенная(сайт, path, показы):
    """Тариф с расширенной аналитикой: запросы и сравнение с категорией."""
    sql(
        "update subscriptions set plan_id = (select id from plans where advanced_analytics "
        "order by id limit 1) where company_id = (select id from companies where slug = 'owner')"
    )
    _, стр = зайти(сайт, path, владелец(сайт))
    props = стр["props"]

    assert props["advanced"] is True and props["benchmark"]
    # Шаги воронки — на языке страницы
    первый = "Impressions in search" if path.startswith("/en") else "Qidiruvdagi ko‘rsatuvlar"
    assert props["funnel"][0]["label"] == первый
    # Равные показы — порядок по запросу
    assert [(q["query"], q["impressions"]) for q in props["queries"]] == list(
        zip(["бетон", "цемент", "арматура", "кирпич"], показы, strict=True)
    )


def test_аналитика_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/analytics", без_компании("nocompany2@savdex.uz"))
    props = стр["props"]

    assert стр["component"] == "cabinet/Analytics" and props["period"] == 30
    assert props["metrics"] is None and props["funnel"] == [] and props["plan"] is None


# ── Кто мной интересуется ───────────────────────────────────────────


@pytest.mark.parametrize("names", [False, True])
@pytest.mark.parametrize("path", ["/cabinet/incoming", "/uz/cabinet/incoming"])
def test_кто_интересуется(сайт, path, names):
    _просмотры()
    sql(
        "update subscriptions set plan_id = (select id from plans where sees_interested_names = %s "
        "order by id limit 1) where company_id = (select id from companies where slug = 'owner')",
        [names],
    )
    _, стр = зайти(сайт, path, владелец(сайт))
    props = стр["props"]

    assert стр["component"] == "cabinet/Incoming" and props["sees_names"] is names
    # Две компании открыли контакты, две смотрели (просмотр старше месяца не в счёте)
    assert len(props["rows"]) == 2 and [v["views"] for v in props["viewers"]] == [2, 4]
    # Имена — только на тарифе, где их видно
    имена = [r["name"] for r in props["rows"] + props["viewers"]]
    assert all(имена) if names else not any(имена)


def test_кто_интересуется_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/incoming", без_компании("nocompany3@savdex.uz"))
    props = стр["props"]

    assert props["counts"] is None and props["rows"] == [] and props["viewers"] == []


# ── Отзывы ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet/reviews", "/zh/cabinet/reviews"])
def test_отзывы(сайт, path):
    _отзывы()
    _, стр = зайти(сайт, path, владелец(сайт))
    props = стр["props"]
    reviews = props["reviews"]

    # Скрытый отзыв не показывается
    assert стр["component"] == "cabinet/Reviews"
    assert props["summary"]["total"] == 5 and len(reviews) == 5
    assert props["summary"]["average"] == 4.2
    assert [d["count"] for d in props["summary"]["distribution"]] == [2, 2, 1, 0, 0]
    # Ответ, спор с решением модератора, автор в корзине — без имени
    assert [r["reply"] for r in reviews].count("Спасибо") == 1
    assert ("rejected", "Отзыв по делу") in [
        (r["dispute_status"], r["moderator_note"]) for r in reviews
    ]
    assert [r["author"] is None for r in reviews].count(True) == 1
    # Критерии — на языке страницы
    первый = "与描述相符" if path.startswith("/zh") else "Соответствие описанию"
    assert props["criteria"]["rating_description"] == первый
    assert props["summary"]["criteria"][0]["label"] == первый


def test_отзывы_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/reviews", без_компании("nocompany4@savdex.uz"))
    props = стр["props"]

    assert props["reviews"] == [] and props["summary"] is None and props["counts"] is None


# ── Мои контакты ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("query", "filters", "компании"),
    [
        ("", ("", ""), ["ООО «Компания 2»", "Поставщик 0", "Поставщик 1", "Поставщик 2", None]),
        ("?status=deal", ("", "deal"), ["Поставщик 1"]),
        (
            "?status=nonsense",
            ("", "nonsense"),
            ["ООО «Компания 2»", "Поставщик 0", "Поставщик 1", "Поставщик 2", None],
        ),
        (
            "?q=%D0%9F%D0%BE%D1%81%D1%82%D0%B0%D0%B2%D1%89%D0%B8%D0%BA",
            ("Поставщик", ""),
            ["Поставщик 0", "Поставщик 1", "Поставщик 2"],
        ),
        # Поиск и по заметке
        ("?q=%D0%9A%D0%9F", ("КП", ""), ["Поставщик 2"]),
        (
            "?q=%20%20&status=",
            ("", ""),
            ["ООО «Компания 2»", "Поставщик 0", "Поставщик 1", "Поставщик 2", None],
        ),
        # «%» не экранируется (как у Laravel): любое имя, удалённой компании — нет
        ("?q=%25", ("%", ""), ["ООО «Компания 2»", "Поставщик 0", "Поставщик 1", "Поставщик 2"]),
    ],
)
def test_мои_контакты(сайт, query, filters, компании):
    _раскрытия()
    _, стр = зайти(сайт, "/cabinet/contacts" + query, владелец(сайт))
    props = стр["props"]
    contacts = props["contacts"]

    assert стр["component"] == "cabinet/Contacts"
    assert (props["filters"]["q"], props["filters"]["status"]) == filters
    assert [c["company"]["name"] for c in contacts] == компании

    # Открытые контакты — все: публичные и нет, телефоны и почты
    for c in contacts:
        if c["company"]["name"] == "Поставщик 1":
            assert c["phones"] == ["+998900000001", "+998710000001"]
            assert c["emails"] == ["p1@x.uz"] and c["status_label"] == "Сделка"


def test_мои_контакты_статусы_на_языке_страницы(сайт):
    _раскрытия()
    _, стр = зайти(сайт, "/en/cabinet/contacts", владелец(сайт))
    props = стр["props"]

    assert props["statuses"] == {
        "new": "New",
        "contacted": "Contacted",
        "negotiating": "Negotiating",
        "deal": "Deal",
        "rejected": "Not a fit",
    }
    assert "Deal" in [c["status_label"] for c in props["contacts"]]


def test_мои_контакты_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/contacts", без_компании("nocompany5@savdex.uz"))

    assert стр["props"]["contacts"] == [] and стр["props"]["counts"] is None


# ── Настройки ───────────────────────────────────────────────────────


def test_настройки(сайт):
    куки = владелец(сайт)
    [(uid,)] = sql("select id from users where email = 'owner@savdex.uz'")
    sql(
        "update users set phone = '+998901112233', last_login_at = '2026-09-20 08:05:00', "
        "last_login_ip = '10.1.2.3', telegram_username = 'owner_tg', company_role = 'owner' "
        "where id = %s",
        [uid],
    )
    sql("delete from notification_preferences where user_id = %s", [uid])
    sql(
        "insert into notification_preferences (user_id, event, email, telegram, created_at, "
        "updated_at) values (%s, 'new_review', false, true, now(), now()), "
        "(%s, 'digest', true, false, now(), now()), (%s, 'unknown', false, false, now(), now())",
        [uid, uid, uid],
    )

    for path, locale in (("/cabinet/settings", "ru"), ("/tr/cabinet/settings", "tr")):
        _, стр = зайти(сайт, path, куки)
        props = стр["props"]

        assert стр["component"] == "cabinet/Settings" and props["locale"] == locale
        assert props["profile"]["phone"] == "+998901112233"
        assert props["security"]["last_login_ip"] == "10.1.2.3"
        assert props["is_owner"] is True
        # Свои настройки поверх «всё по почте»; неизвестное событие не показывается
        assert [(n["event"], n["email"], n["telegram"]) for n in props["notifications"]] == [
            ("contact_unlocked", True, False),
            ("new_review", False, True),
            ("moderation", True, False),
            ("listing_expiring", True, False),
            ("digest", True, False),
        ]


def test_настройки_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/settings", без_компании("nocompany6@savdex.uz"))
    props = стр["props"]

    assert props["counts"] is None and props["profile"]["email"] == "nocompany6@savdex.uz"


# ── Уведомления ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("query", "filter_", "заголовки"),
    [
        # Рассылка — в одну секунду: порядок решает номер
        ("", "all", [2, 1, 0, 3, 4, 5, 6]),
        ("?filter=unread", "unread", [1, 3, 5]),
        ("?filter=other", "all", [2, 1, 0, 3, 4, 5, 6]),
        ("?filter=", "all", [2, 1, 0, 3, 4, 5, 6]),
    ],
)
def test_уведомления(сайт, query, filter_, заголовки):
    куки = владелец(сайт)
    [(uid,)] = sql("select id from users where email = 'owner@savdex.uz'")

    if not sql("select 1 from user_notifications where user_id = %s", [uid]):
        for i in range(7):
            sql(
                "insert into user_notifications (user_id, type, tone, title, body, url, "
                "is_broadcast, read_at, created_at, updated_at) values (%s, %s, 'primary', %s, "
                "%s, %s, %s, %s, now() - make_interval(hours => %s, mins => 30), now())",
                [
                    uid,
                    "broadcast" if i < 3 else "review",
                    f"Уведомление {i}",
                    "Текст" if i % 2 else None,
                    "/cabinet/reviews" if i % 3 == 0 else None,
                    i < 3,
                    None if i % 2 else "2026-09-01 10:00:00",
                    1 if i < 3 else i + 1,
                ],
            )

    _, стр = зайти(сайт, "/notifications" + query, куки)
    props = стр["props"]

    assert стр["component"] == "Notifications"
    assert props["filter"] == filter_ and props["unread"] == 3
    assert [n["title"] for n in props["notifications"]] == [f"Уведомление {i}" for i in заголовки]


# ── Избранное ───────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/favorites", "/uz/favorites"])
def test_избранное(сайт, path):
    куки = владелец(сайт)
    [(uid,)] = sql("select id from users where email = 'owner@savdex.uz'")
    _избранное(uid)
    _, стр = зайти(сайт, path, куки)
    items = стр["props"]["items"]

    # Черновик, на модерации и удалённое — не показываются; истёкшее,
    # архивное и объявление удалённой компании (его страницы больше нет) —
    # неактивными; у удалённой компании — без имени
    assert стр["component"] == "Favorites"
    assert len(items) == 4 and [i["active"] for i in items].count(False) == 3
    assert [i["company"]["name"] is None for i in items].count(True) == 1


# ── Мои объявления ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("query", "вкладка", "статусы"),
    [
        ("", "active", ["active"] * 4),
        ("?status=draft", "draft", ["draft"]),
        ("?status=needs_changes", "needs_changes", ["needs_changes"]),
        ("?status=expired", "expired", ["expired"]),
        # Архива среди вкладок нет — активные
        ("?status=archived", "active", ["active"] * 4),
        ("?status=", "active", ["active"] * 4),
    ],
)
def test_мои_объявления(сайт, query, вкладка, статусы):
    _объявления()
    _, стр = зайти(сайт, "/cabinet/listings" + query, владелец(сайт))
    props = стр["props"]
    listings = props["listings"]

    assert стр["component"] == "cabinet/listings/Index" and props["status"] == вкладка
    assert [x["status"] for x in listings] == статусы
    assert list(props["tabs"]) == ["active", "draft", "needs_changes", "expired", "rejected"]

    if вкладка == "needs_changes":
        assert listings[0]["moderation_note"] == "Добавьте фото"

    if вкладка == "active":
        # Значок — у «Срочно»; у «Выделения» значка нет
        assert [x["badges"] for x in listings].count(["Срочно"]) == 1
        assert [x["expiring_soon"] for x in listings].count(True) == 3


def test_мои_объявления_по_узбекски(сайт):
    _объявления()
    _, стр = зайти(сайт, "/uz/cabinet/listings", владелец(сайт))
    props = стр["props"]

    assert props["locale"] == "uz" and props["status"] == "active" and len(props["listings"]) == 4
    assert props["tabs"]["active"] != "Активные"


def test_мои_объявления_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/listings", без_компании("nocompany7@savdex.uz"))

    assert стр["props"]["listings"] == []
    # Счётчики вкладок — нули
    assert set(стр["props"]["counts"].values()) == {0}


# ── Чаты ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet/chats", "/en/cabinet/chats"])
def test_чаты(сайт, path):
    _чаты()
    _, стр = зайти(сайт, path, владелец(сайт))
    threads = стр["props"]["threads"]

    assert стр["component"] == "cabinet/Chats" and len(threads) == 6
    # Пустой разговор — без последнего сообщения; последнее своё — отмечено
    assert threads[0]["last"] is None and threads[0]["unread"] == 0
    assert [t["last_mine"] for t in threads].count(True) == 1
    assert threads[-1]["last"] == "Здравствуйте"
    # Разговор об IT-задаче — с её названием
    [задача] = sql("select title from it_tasks where company_id != %s", [_owner()])
    assert задача[0] in [t["listing"] for t in threads]


def test_чаты_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/chats", без_компании("nocompany8@savdex.uz"))

    assert стр["props"]["threads"] == [] and стр["props"]["hasCompany"] is False


# ── Продвижение ─────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet/promo", "/uz/cabinet/promo"])
def test_продвижение(сайт, path):
    _объявления()
    # Эффект: прирост показов; у второго «до» — ноль (эффекта нет); одна секунда
    sql(
        "update promotions set impressions_before = case when mod(id, 2) = 0 then 40 else 0 end, "
        "impressions_after = 57, created_at = '2026-09-26 09:00:00'"
    )
    _, стр = зайти(сайт, path, владелец(сайт))
    props = стр["props"]

    assert стр["component"] == "cabinet/Promo"
    # (57 − 40) / 40 = 42,5 % → 43
    assert [(p["before"], p["after"], p["effect"]) for p in props["active"]] == [
        (40, 57, 43),
        (0, 57, None),
    ]
    assert {t["code"] for t in props["types"]} >= {"bump", "urgent", "highlight"}
    # Цена — на языке страницы; «/» перед сроком ждёт страница
    подписи = " ".join(t["cost_label"] for t in props["types"])
    assert ("ед." in подписи) == (path == "/cabinet/promo")
    assert ("birlik" in подписи) == (path != "/cabinet/promo")


def test_продвижение_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/promo", без_компании("nocompany9@savdex.uz"))
    props = стр["props"]

    assert props["active"] == [] and props["types"] == [] and props["units"] == 0


# ── Моё резюме ──────────────────────────────────────────────────────


def test_резюме_пустое(сайт):
    пользователь("seeker0@savdex.uz", phone="+998900000001")
    _, стр = зайти(сайт, "/cabinet/resume", куки_входа("seeker0@savdex.uz"))
    props = стр["props"]

    # Резюме нет — форма с контактами из профиля
    assert стр["component"] == "cabinet/Resume" and props["resume"] is None
    assert props["defaults"] == {
        "contact_name": "Покупатель seeker0@savdex.uz",
        "contact_email": "seeker0@savdex.uz",
        "contact_phone": "+998900000001",
    }


@pytest.mark.parametrize("path", ["/cabinet/resume", "/uz/cabinet/resume", "/zh/cabinet/resume"])
def test_резюме(сайт, path):
    email = "seeker@savdex.uz"

    if not sql("select 1 from users where email = %s", [email]):
        _резюме(пользователь(email))

    _, стр = зайти(сайт, path, куки_входа(email))
    resume = стр["props"]["resume"]

    assert стр["component"] == "cabinet/Resume"
    assert (resume["title"], resume["status"], resume["moderation_note"]) == (
        "Логист",
        "draft",
        "Уточните зарплату",
    )
    # 45 месяцев опыта — 3 года 9 месяцев
    assert resume["experience"] == {"years": 3, "months": 9}
    assert resume["employment"] == ["full", "project"] and resume["skills"] == ["1С", "Excel"]
    assert resume["photo"] == сайт + "/storage/resumes/p.webp"


# ── Профиль компании ────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet/company", "/uz/cabinet/company"])
def test_профиль_компании(сайт, path):
    _документы()
    sql(
        "update users set company_role = 'owner', phone_verified_at = '2026-09-01 10:00:00' "
        "where email = 'owner@savdex.uz'"
    )
    _, стр = зайти(сайт, path, владелец(сайт))
    props = стр["props"]

    assert стр["component"] == "cabinet/Company" and props["company"]["slug"] == "owner"
    # Подтверждённый документ засчитан в заполненность
    assert props["company"]["completeness"] == 40
    # Новые сверху; файла нет на диске — «missing»
    assert [(d["type"], d["status"], d["missing"]) for d in props["documents"]] == [
        ("price_list", "pending", True),
        ("license", "pending", True),
        ("registration", "approved", False),
    ]
    assert [c["value"] for c in props["contacts"]] == ["+998901234567", "sales@owner.uz"]
    assert len(props["employees"]) == 2


def test_профиль_без_компании(сайт):
    _, стр = зайти(сайт, "/cabinet/company", без_компании("nocompany10@savdex.uz"))
    props = стр["props"]

    assert props["company"] is None and props["contacts"] == [] and props["documents"] == []


# ── Мои IT-задачи ───────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet/it-tasks", "/uz/cabinet/it-tasks"])
def test_мои_задачи(сайт, path):
    _задачи()
    _, стр = зайти(сайт, path, владелец(сайт))
    tasks = стр["props"]["tasks"]

    assert стр["component"] == "cabinet/it-tasks/Index"
    assert [t["status"] for t in tasks] == ["closed", "completed", "active"]
    # Исполнитель, отклики (компания в корзине — без имени) и файлы — у своих задач
    assert tasks[1]["contractor"] == "Tashkent Soft"
    assert tasks[2]["files"] == 2 and len(tasks[2]["responders"]) == 2
    assert tasks[2]["responders"][0]["name"] == "Tashkent Soft"

    if path == "/cabinet/it-tasks":
        assert [t["budget"] for t in tasks] == ["Договорной", "500 – 900 USD", "1 500 000 сум"]
        assert [t["status_label"] for t in tasks] == ["Закрыта", "Выполнена", "Открыта"]
    else:
        # Статусы и виды услуг — на языке страницы
        assert [t["status_label"] for t in tasks] == ["Yopilgan", "Bajarilgan", "Ochiq"]
        assert all(t["service_type"] != "Сайты и веб-приложения" for t in tasks)


def test_задача_форма(сайт):
    task = _задачи()
    куки = владелец(сайт)

    _, новая = зайти(сайт, "/cabinet/it-tasks/create", куки)
    assert новая["component"] == "cabinet/it-tasks/Form" and новая["props"]["task"] is None
    assert новая["props"]["serviceTypes"]["web"] == "Сайты и веб-приложения"

    _, своя = зайти(сайт, f"/cabinet/it-tasks/{task}/edit", куки)
    assert своя["props"]["task"]["id"] == task
    assert своя["props"]["task"]["budget_type"] == "fixed"

    чужая = it_задача()
    ответ, _ = зайти(сайт, f"/cabinet/it-tasks/{чужая}/edit", куки)
    assert ответ["status"] == 404

    # Виды услуг — на языке страницы (последним: /en запоминает язык)
    _, английская = зайти(сайт, "/en/cabinet/it-tasks/create", куки)
    assert английская["props"]["serviceTypes"]["web"] == "Websites and web apps"


def test_задачи_без_компании(сайт):
    куки = без_компании("nocompany11@savdex.uz")
    _, стр = зайти(сайт, "/cabinet/it-tasks", куки)
    assert стр["props"]["tasks"] == [] and стр["props"]["hasCompany"] is False

    # Без компании форма уводит в профиль с предупреждением в сессии
    ответ, payload = с_сессией(сайт, "/cabinet/it-tasks/create", куки)

    assert ответ["headers"]["location"] == сайт + "/cabinet/company"
    assert '"warning":' in payload


# ── Мини-сайт ───────────────────────────────────────────────────────


def test_мини_сайт_без_сайта(сайт):
    sql("delete from company_sites where company_id = %s", [_owner()])
    _, стр = зайти(сайт, "/cabinet/site", владелец(сайт))

    assert стр["component"] == "cabinet/Site" and стр["props"]["site"] is None


def test_мини_сайт(сайт):
    _мини_сайт()
    sql(
        "update subscriptions set plan_id = (select id from plans where has_microsite "
        "order by id limit 1) where company_id = %s",
        [_owner()],
    )
    куки = владелец(сайт)

    for path in ("/cabinet/site", "/uz/cabinet/site"):
        _, стр = зайти(сайт, path, куки)
        props = стр["props"]

        assert стр["component"] == "cabinet/Site" and props["available"] is True
        assert props["site"]["subdomain"] == "owner-shop" and props["site"]["status"] == "published"
        # Черновик отличается от опубликованного
        assert props["site"]["unpublished_changes"] is True
        # Оформление нормализовано: цвет строчными, неизвестный режим — светлый
        assert props["theme"]["primary"] == "#aabbcc" and props["theme"]["mode"] == "light"
        assert "extra" not in props["theme"]
        # Товары — по порядку, затем по номеру
        assert [p["title"] for p in props["products"]] == ["Щебень", "Арматура", "Цемент"]
        assert props["products"][2]["image"] == сайт + "/storage/sites/1/hero.webp"


def test_мини_сайт_без_компании(сайт):
    ответ, _ = зайти(сайт, "/cabinet/site", без_компании("nocompany12@savdex.uz"))

    assert ответ["status"] == 302 and ответ["headers"]["location"] == сайт + "/cabinet/company"


# ── Разговор ────────────────────────────────────────────────────────


def test_разговор_отмечает_прочитанное(сайт):
    _чаты()
    owner = _owner()
    threads = sql(
        "select id, buyer_company_id = %s from message_threads where %s in "
        "(buyer_company_id, seller_company_id) and exists (select 1 from messages m "
        "where m.thread_id = message_threads.id) order by id",
        [owner, owner],
    )
    куки = владелец(сайт)

    for thread, is_buyer in threads[:3]:
        column, other = (
            ("buyer_read_at", "seller_read_at") if is_buyer else ("seller_read_at", "buyer_read_at")
        )
        [(before_other,)] = sql(f"select {other} from message_threads where id = %s", [thread])
        sql(f"update message_threads set {column} = null where id = %s", [thread])

        _, стр = зайти(сайт, f"/cabinet/chats/{thread}", куки)

        assert стр["component"] == "cabinet/Chat" and стр["props"]["thread"]["id"] == thread
        assert стр["props"]["messages"]
        # Отмечена своя сторона, чужая не тронута
        assert sql(
            f"select {column} > now() - interval '1 minute', {other} is not distinct from %s "
            "from message_threads where id = %s",
            [before_other, thread],
        ) == [(True, True)]


def test_чужой_разговор_404(сайт):
    _чаты()
    чужой = вставить("message_threads", buyer_company_id=компания(), seller_company_id=компания())
    куки = владелец(сайт)

    for path in (f"/cabinet/chats/{чужой}", "/cabinet/chats/999999"):
        ответ, _ = зайти(сайт, path, куки)
        assert ответ["status"] == 404


# ── Мастер объявления ───────────────────────────────────────────────


@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_мастер_объявления(сайт, prefix):
    listing = _черновик()
    _, стр = зайти(сайт, f"{prefix}/cabinet/listings/{listing}/edit", владелец(сайт))
    props = стр["props"]

    assert стр["component"] == "cabinet/listings/Wizard"
    assert (
        props["listing"]["title"] == "Цемент М400 навалом 50 кг" and props["listing"]["step"] == 3
    )
    assert props["listing"]["attributes"]["mark"] == "М400"
    # Фото — по порядку sort; превью, если есть
    assert [i["thumb"].removeprefix(сайт) for i in props["listing"]["images"]] == [
        "/storage/l/w1.webp",
        "/storage/l/wt0.webp",
    ]
    # Блок «Информация о товаре» (ProductSpecs): поля у каждого подраздела,
    # детали в теги не идут
    assert all("specs" in c for p in props["categories"] for c in p["children"])
    assert any(c["specs"] for p in props["categories"] for c in p["children"])
    assert "50 kg" not in props["tagOptions"] and "цемент" in props["tagOptions"]


def test_мастер_чужое_и_неподтверждённая_почта(сайт):
    listing = _черновик()
    чужое = объявление(draft=True)
    ответ, _ = зайти(сайт, f"/cabinet/listings/{чужое}/edit", владелец(сайт))
    assert ответ["status"] == 404

    пользователь("unverified@savdex.uz")
    sql(
        "update users set email_verified_at = null, company_id = (select id from companies "
        "where slug = 'owner') where email = 'unverified@savdex.uz'"
    )
    ответ, payload = с_сессией(
        сайт, f"/cabinet/listings/{listing}/edit", куки_входа("unverified@savdex.uz")
    )

    assert ответ["headers"]["location"] == сайт + "/verify-email"
    assert '"intended":' in payload
