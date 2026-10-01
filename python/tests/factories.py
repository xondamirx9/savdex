"""
Данные для проверок — фабрики на Python вместо фабрик Laravel
(database/factories): тесты больше не зовут PHP, чтобы завести
компанию или объявление.

Поля — те же, что у фабрик Laravel, и то же, что делали события моделей
при создании: адрес (slug) из названия, поисковый текст (search_text),
пересчёт рейтинга после отзыва. Случайные значения Faker заменены
предсказуемыми: n-я компания — «ООО «Компания n»», ИНН из номера; так
повторный прогон даёт те же данные, а проверки не зависят от удачи.

Каждая функция пишет в базу проверок (SAVDEX_PARITY_PG_URL, через
pg_admin.sql) и возвращает номер записи; поля переопределяются
именованными аргументами: компания(status="blocked").
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import bcrypt

from savdex.tenders.slug import slugify
from savdex.web.search_text import index

from .pg_admin import sql

_номер = itertools.count(1)


class Выражение(str):
    """Значение-выражение SQL (now(), now() - interval …), а не строка."""


def _следующий() -> int:
    return next(_номер)


def _вставить(table: str, поля: dict[str, Any], *, время: bool = True) -> int:
    """insert … returning id; списки и словари — в JSON, как касты Eloquent."""
    значения = {
        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
        for k, v in поля.items()
    }
    колонки = list(значения)
    выражения = [v if isinstance(v, Выражение) else "%s" for v in значения.values()]

    if время:
        for колонка in ("created_at", "updated_at"):
            if колонка not in значения:
                колонки.append(колонка)
                выражения.append("now()")

    [(pk,)] = sql(
        f"insert into {table} ({', '.join(колонки)}) values ({', '.join(выражения)}) returning id",
        [v for v in значения.values() if not isinstance(v, Выражение)],
    )

    return int(pk)


# ── География и категории ───────────────────────────────────────────


def узбекистан() -> int:
    """Country::firstOrCreate(['code' => 'uz'], …) из CompanyFactory."""
    rows = sql("select id from countries where code = 'uz'")

    if rows:
        return int(rows[0][0])

    return _вставить(
        "countries", {"code": "uz", "phone_code": "998", "currency_code": "UZS", "is_active": True}
    )


def ташкент(country_id: int | None = None) -> int:
    """City::firstOrCreate(['country_id' => …, 'slug' => 'tashkent'], …)."""
    country_id = country_id or узбекистан()
    rows = sql("select id from cities where country_id = %s and slug = 'tashkent'", [country_id])

    if rows:
        return int(rows[0][0])

    return _вставить("cities", {"country_id": country_id, "slug": "tashkent", "is_active": True})


def категория(name: str | None = None, **поля: Any) -> int:
    """
    CategoryFactory; name — состояние named(): русское название в
    category_translations.
    """
    n = _следующий()
    pk = _вставить(
        "categories",
        {"parent_id": None, "slug": f"category-{n}", "sort": 0, "is_active": True, **поля},
    )

    if name is not None:
        _вставить("category_translations", {"category_id": pk, "locale": "ru", "name": name})

    return pk


def _активная_категория() -> int:
    """Первая активная категория, иначе новая «Стройматериалы» — как в ListingFactory."""
    rows = sql("select id from categories where is_active order by id limit 1")

    return int(rows[0][0]) if rows else категория("Стройматериалы")


# ── Пользователи и компании ─────────────────────────────────────────

#: Hash::make('password') из UserFactory — bcrypt в виде Laravel ($2y$)
ПАРОЛЬ_ФАБРИКИ = "$2y$" + bcrypt.hashpw(b"password", bcrypt.gensalt(rounds=4)).decode()[4:]


def пользователь(**поля: Any) -> int:
    """UserFactory: подтверждённая почта, владелец своей компании."""
    n = _следующий()

    return _вставить(
        "users",
        {
            "name": f"Пользователь {n}",
            "email": f"user{n}@example.com",
            "email_verified_at": Выражение("now()"),
            "password": ПАРОЛЬ_ФАБРИКИ,
            "remember_token": f"remember{n:02d}",
            "status": "active",
            "must_change_password": False,
            "company_role": "owner",
            **поля,
        },
    )


def _уникальный_адрес(name: str) -> str:
    """Company::makeSlug: свободный адрес, в том числе среди удалённых."""
    base = slugify(name) or "company"
    slug, i = base, 2

    while sql("select 1 from companies where slug = %s limit 1", [slug]):
        slug = f"{base}-{i}"
        i += 1

    return slug


def компания(**поля: Any) -> int:
    """CompanyFactory; события Company: slug при создании, search_text при сохранении."""
    n = _следующий()
    country_id = поля.pop("country_id", None) or узбекистан()
    данные: dict[str, Any] = {
        "name": f"ООО «Компания {n}»",
        "tin": str(100_000_000 + n),
        "type": ("manufacturer", "importer", "distributor", "trading", "services")[n % 5],
        "primary_role": "both",
        "verification_level": 0,
        "rating": 4.5,
        "reviews_count": n % 60,
        "completed_deals_count": n % 120,
        "response_time_hours": 1 + n % 24,
        "status": "active",
        "country_id": country_id,
        **поля,
    }

    if "city_id" not in данные:
        данные["city_id"] = ташкент(country_id)

    данные.setdefault("slug", _уникальный_адрес(данные["name"]))
    данные["search_text"] = index(f"{данные['name']} {данные.get('legal_name') or ''}".strip())

    return _вставить("companies", данные)


def компании(count: int, **поля: Any) -> list[int]:
    return [компания(**поля) for _ in range(count)]


# ── Объявления, задачи, закупки ─────────────────────────────────────

_ЗАГОЛОВКИ = (
    "Цемент М400 навалом",
    "Щебень фракция 5-20",
    "Арматура А500С",
    "Кирпич керамический М150",
    "Песок карьерный мытый",
)


def объявление(*, draft: bool = False, **поля: Any) -> int:
    """
    ListingFactory (draft — состояние draft()); события Listing:
    search_text из заголовка, описания и переводов, slug после создания.
    """
    n = _следующий()
    данные: dict[str, Any] = {
        "type": "supply",
        "title": f"{_ЗАГОЛОВКИ[n % 5]} {100 + n % 900}",
        "description": f"Описание объявления {n}: поставка партиями, доставка по городу.",
        "price": 100_000 + n * 1000,
        "currency": "UZS",
        "unit": "т",
        "status": "active",
        "impressions_count": n % 2000,
        "views_count": n % 300,
        "unlocks_count": n % 20,
        **поля,
    }

    if "company_id" not in данные:
        данные["company_id"] = компания()

    if "category_id" not in данные:
        данные["category_id"] = _активная_категория()

    i18n = данные.get("title_i18n") or {}
    данные["search_text"] = index(
        " ".join(
            x for x in [данные["title"], str(данные.get("description") or ""), *i18n.values()] if x
        )
    )
    if draft:
        данные["status"] = "draft"
        данные.setdefault("published_at", None)
        данные.setdefault("expires_at", None)
    else:
        данные.setdefault("published_at", Выражение(f"now() - interval '{1 + n % 60} days'"))
        данные.setdefault("expires_at", Выражение(f"now() + interval '{10 + n % 80} days'"))

    pk = _вставить("listings", данные)

    if not данные.get("slug"):
        sql(
            "update listings set slug = %s where id = %s",
            [slugify(данные["title"])[:60].rstrip() + f"-{pk}", pk],
        )

    return pk


def объявления(count: int, **поля: Any) -> list[int]:
    return [объявление(**поля) for _ in range(count)]


_ЗАДАЧИ = (
    "Разработать интернет-магазин стройматериалов",
    "Интеграция сайта с 1С и складом",
    "Мобильное приложение для дилеров",
    "Telegram-бот для приёма заявок",
)


def it_задача(*, closed: bool = False, **поля: Any) -> int:
    """ItTaskFactory (closed — состояние closed()); slug и search_text — как события ItTask."""
    n = _следующий()
    данные: dict[str, Any] = {
        "title": f"{_ЗАДАЧИ[n % 4]} {100 + n % 900}",
        "description": f"Описание задачи {n}: нужен подрядчик с опытом похожих проектов.",
        "service_type": "web",
        "stack": ["Laravel", "React"],
        "budget_type": "range",
        "budget_from": 20_000_000,
        "budget_to": 50_000_000,
        "currency": "UZS",
        "status": "closed" if closed else "active",
        **поля,
    }

    if "company_id" not in данные:
        данные["company_id"] = компания()

    данные["search_text"] = index(
        " ".join(
            x
            for x in [
                данные["title"],
                str(данные.get("description") or ""),
                " ".join(данные.get("stack") or []),
            ]
            if x
        )
    )
    данные.setdefault("deadline_at", Выражение("now() + interval '30 days'"))
    данные.setdefault("published_at", Выражение("now()"))

    if closed:
        данные.setdefault("closed_at", Выражение("now()"))

    pk = _вставить("it_tasks", данные)

    if not данные.get("slug"):
        sql(
            "update it_tasks set slug = %s where id = %s",
            [(slugify(данные["title"]) or "task")[:60].rstrip() + f"-{pk}", pk],
        )

    return pk


_ЗАКУПКИ = (
    "Поставка цемента М400 для строительства школы",
    "Закупка хлопчатобумажной пряжи 30/1",
    "Поставка металлопроката для моста",
    "Закупка упаковочной плёнки",
    "Поставка офисной мебели",
)


def тендер(*, draft: bool = False, closed: bool = False, **поля: Any) -> int:
    """TenderFactory (draft(), closed()); slug и search_text — как события Tender."""
    n = _следующий()
    данные: dict[str, Any] = {
        "title": f"{_ЗАКУПКИ[n % 5]} {100 + n % 900}",
        "description": f"Описание закупки {n}: условия поставки и оплаты в документации.",
        "customer": ("ГУП «Тошкент шахар курилиш»", "АО «Узбекнефтегаз»", "ООО «Андижан текстиль»")[
            n % 3
        ],
        "location": "Ташкент",
        "budget": 10_000_000 + n * 100_000,
        "currency": "UZS",
        "status": "draft" if draft else "published",
        **поля,
    }

    if "category_id" not in данные:
        данные["category_id"] = _активная_категория()

    i18n = данные.get("title_i18n") or {}
    данные["search_text"] = index(
        " ".join(
            x
            for x in [
                данные["title"],
                str(данные.get("description") or ""),
                str(данные.get("customer") or ""),
                *i18n.values(),
            ]
            if x
        )
    )
    данные.setdefault(
        "deadline_at",
        Выражение(
            "now() - interval '3 days'" if closed else f"now() + interval '{5 + n % 40} days'"
        ),
    )

    if not draft:
        данные.setdefault("published_at", Выражение(f"now() - interval '{n % 10} days'"))

    pk = _вставить("tenders", данные)

    if not данные.get("slug"):
        sql(
            "update tenders set slug = %s where id = %s",
            [(slugify(данные["title"]) or "tender")[:60].rstrip() + f"-{pk}", pk],
        )

    return pk


# ── Отзывы и контакты ───────────────────────────────────────────────


def пересчитать_рейтинг(company_id: int) -> None:
    """ReviewService::recalculate — как событие Review::saved."""
    from savdex.web.review_actions import WEIGHT, _php_round

    [(среднее,)] = sql("select avg(rating) from reviews where status = 'published'")
    общее = float(среднее or 0) or 4.0
    [(count, total)] = sql(
        "select count(*), coalesce(sum(rating), 0) from reviews "
        "where company_id = %s and status = 'published'",
        [company_id],
    )
    рейтинг = _php_round((WEIGHT * общее + float(total)) / (WEIGHT + count)) if count else 0.0
    sql(
        "update companies set rating = %s, reviews_count = %s where id = %s",
        [рейтинг, count, company_id],
    )


def отзыв(**поля: Any) -> int:
    """ReviewFactory; после создания — пересчёт рейтинга компании (Review::saved)."""
    n = _следующий()
    оценка = поля.pop("rating", 3 + n % 3)
    данные: dict[str, Any] = {
        "rating": оценка,
        "rating_description": оценка,
        "rating_response": оценка,
        "rating_deadlines": оценка,
        "rating_quality": оценка,
        "body": f"Отзыв {n}: поставка в срок, документы в порядке, рекомендуем.",
        "deal_confirmed": True,
        "status": "published",
        **поля,
    }

    if "company_id" not in данные:
        данные["company_id"] = компания()

    if "author_company_id" not in данные:
        данные["author_company_id"] = компания()

    pk = _вставить("reviews", данные)
    пересчитать_рейтинг(int(данные["company_id"]))

    return pk


def открытие_контакта(**поля: Any) -> int:
    """ContactUnlockFactory."""
    данные: dict[str, Any] = {"credits_spent": 1, "status": "new", **поля}

    if "company_id" not in данные:
        данные["company_id"] = компания()

    if "target_company_id" not in данные:
        данные["target_company_id"] = компания()

    return _вставить("contact_unlocks", данные)
