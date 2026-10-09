"""
Этап 4, шаг 6: визитка компании /company/<адрес> на Django.

Шапка (businessCard), контакты: гостю и не заплатившему — маской,
кроме сайта; заплатившему и своей компании — открыты. Файлы: материалы
сразу, документы после одобрения, пропавшие с диска не видны. Отзывы,
право оставить свой, кошелёк смотрящего. И запись «Кто мной
интересуется»: вошедший с компанией — одна строка на полчаса (по
таблице и по ключу сессии в файловом кэше).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from typing import Any

import pytest

from .factories import компания as новая
from .factories import объявление, отзыв
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_catalog import ГЕО, справочники
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база

ФАЙЛЫ = КОРЕНЬ / "storage/app/private/parity-docs"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники(*ГЕО)
    ФАЙЛЫ.mkdir(parents=True, exist_ok=True)

    for name in ("license.pdf", "price.xlsx", "photo.JPG", "old.png"):
        (ФАЙЛЫ / name).write_bytes(b"x" * 10)

    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(city,)] = sql("select id from cities where country_id = %s order by id limit 1", [uz])
    c = новая(
        slug="stroybaza",
        name="ООО «Стройбаза»",
        legal_name="ООО «Стройбаза Групп»",
        country_id=uz,
        city_id=city,
        address="Ташкент, Чиланзар 5",
        lat=41.3,
        lng=69.2,
        tin="301234567",
        founded_year=2012,
        employees_range="11-50",
        verification_level=2,
        is_it_provider=True,
        it_specializations=["web", "erp", "unknown"],
        custom_category="Сухие смеси",
        website="stroybaza.uz",
        rating=4.35,
        reviews_count=2,
        description="Поставки цемента. " * 10,
    )
    контакты = [
        ("phone", "+998 90 123-45-67", True),
        ("email", "sales@stroybaza.uz", False),
        ("telegram", "@stroybaza", False),
        ("whatsapp", "+998901234567", False),
        ("website", "https://stroybaza.uz", False),
        ("phone", "123", False),
    ]

    for i, (вид, значение, главный) in enumerate(контакты):
        sql(
            "insert into company_contacts (company_id, type, value, label, contact_person, "
            "is_primary, is_public, sort_order, created_at, updated_at) "
            "values (%s, %s, %s, %s, %s, %s, true, %s, now(), now())",
            [
                c,
                вид,
                значение,
                "Отдел продаж" if i == 1 else None,
                "Азиз" if i == 0 else None,
                главный,
                i,
            ],
        )

    sql(
        "insert into company_contacts (company_id, type, value, is_public, created_at, "
        "updated_at) values (%s, 'phone', '+998 71 000-00-00', false, now(), now())",
        [c],
    )
    документы = [
        ("license", "Лицензия", "license.pdf", "approved", 2516582, "2020-01-01"),
        ("price_list", "Прайс", "price.xlsx", "pending", 800, None),
        ("certificate", "Сертификат", "photo.JPG", "pending", 5000, None),
        ("quality", "Качество", "old.png", "approved", None, "2099-05-01"),
        ("license", "Пропавшая", "missing.pdf", "approved", 100, None),
    ]

    for вид, title, файл, статус, размер, срок in документы:
        sql(
            "insert into company_documents (company_id, type, title, file_path, "
            "moderation_status, file_size, valid_until, is_public, created_at, updated_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, true, now(), now())",
            [c, вид, title, f"parity-docs/{файл}", статус, размер, срок],
        )

    автор = новая(name="Андижан Текстиль")
    ушедшая = новая(name="Ушедшая компания")
    отзыв(
        company_id=c,
        author_company_id=автор,
        status="published",
        rating=5,
        reply="Спасибо!",
        deal_confirmed=True,
    )
    отзыв(company_id=c, author_company_id=ушедшая, status="published", rating=3)
    отзыв(company_id=c, author_company_id=новая(), status="moderation")
    sql("update companies set deleted_at = now() where id = %s", [ушедшая])

    for _ in range(3):
        объявление(company_id=c)

    объявление(company_id=c, source="import")
    новая(
        slug="bare",
        name="ИП Каримов",
        legal_form="individual",
        type=None,
        city_id=None,
        tin=None,
        description=None,
        lat=None,
    )

    try:
        with адрес() as root:
            yield root
    finally:
        shutil.rmtree(ФАЙЛЫ, ignore_errors=True)


def визитка(сайт: str, path: str, cookies: dict[str, str] | None = None) -> dict[str, Any]:
    д = открыть(сайт, path, cookies)
    стр = страница(д["body"])

    assert д["status"] == 200
    assert стр["component"] == "companies/Show"

    return dict(стр["props"])


@pytest.mark.parametrize(
    ("path", "locale"),
    [
        ("/company/stroybaza", "ru"),
        ("/en/company/stroybaza", "en"),
        ("/uz/company/stroybaza", "uz"),
    ],
)
def test_визитка_гостю(сайт, path, locale):
    props = визитка(сайт, path)

    assert props["locale"] == locale
    assert props["company"]["name"] == "ООО «Стройбаза»"
    assert props["company"]["website"] == "https://stroybaza.uz"
    assert props["company"]["coords"] == {"lat": 41.3, "lng": 69.2}
    # Скрытый телефон не показан; сайт открыт всегда, остальные контакты — маской
    assert [c["locked"] for c in props["contacts"]] == [True, True, True, True, False, True]
    assert props["contacts"][0]["value"] == "+998 90 ••• •• ••"
    assert props["contacts"][1]["value"] == "s••••@stroybaza.uz"
    assert props["locked_count"] == 5 and props["unlocked"] is False
    # Материал (прайс) — сразу; документы — после одобрения; пропавший с диска не виден
    assert [f["title"] for f in props["files"]] == ["Лицензия", "Прайс", "Качество"]
    assert [f["expired"] for f in props["files"]] == [True, False, False]
    # Отзывы — опубликованные; автор удалён — без имени
    assert [r["rating"] for r in props["reviews"]] == [5, 3]
    assert props["reviews"][0]["author"] == "Андижан Текстиль"
    assert props["reviews"][0]["reply"] == "Спасибо!"
    assert props["reviews"][1]["initials"] == "?"
    # Три объявления и загруженное из книги
    assert props["listings_count"] == 4
    assert props["wallet"] is None and props["is_own"] is False
    # Специализации и критерии отзыва — на языке страницы; неизвестной нет
    assert props["company"]["it_specializations"] == СПЕЦИАЛИЗАЦИИ[locale]
    assert props["criteria"]["rating_quality"] == КАЧЕСТВО[locale]


СПЕЦИАЛИЗАЦИИ = {
    "ru": ["Сайты и веб-приложения", "1С, учёт и ERP"],
    "en": ["Websites and web apps", "1C, accounting and ERP"],
    "uz": ["Saytlar va veb-ilovalar", "1C, hisob va ERP"],
}
КАЧЕСТВО = {"ru": "Качество товара", "en": "Product quality", "uz": "Mahsulot sifati"}


def test_визитка_без_данных(сайт):
    props = визитка(сайт, "/company/bare")

    assert props["company"]["name"] == "ИП Каримов"
    # Типа нет — вместо него правовая форма
    assert props["company"]["type"] is None
    assert props["company"]["type_label"] == props["company"]["legal_form_label"]
    assert props["company"]["coords"] is None and props["company"]["city"] is None
    assert props["contacts"] == [] and props["files"] == [] and props["reviews"] == []
    assert props["listings_count"] == 0 and props["locked_count"] == 0


def test_нет_компании(сайт):
    д = открыть(сайт, "/company/nothing")
    assert д["status"] == 404


def компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def новая_компания() -> int:
    return новая()


def вошедший(сайт: str, email: str, company_id: int | None, **поля: object) -> dict[str, str]:
    del сайт

    return вход(пользователь(email, company_id=company_id, **поля))


def просмотры(target: int) -> int:
    return int(
        sql("select count(*) from audience_views where target_company_id = %s", [target])[0][0]
    )


def test_чужая_компания_без_раскрытия(сайт):
    цель = компания("stroybaza")
    своя = новая_компания()
    sql(
        "insert into wallets (company_id, credits, contacts_used_this_period, created_at, "
        "updated_at) values (%s, 7, 2, now(), now())",
        [своя],
    )
    куки = вошедший(сайт, "viewer@savdex.uz", своя)
    sql("delete from audience_views")

    props = визитка(сайт, "/company/stroybaza", куки)

    assert props["wallet"] == {"contacts_left": 1, "credits": 7}
    assert props["unlocked"] is False and props["locked_count"] == 5
    # Контакты не раскрыты — отзыв оставить нельзя
    assert props["review_blocked"] is not None
    assert просмотры(цель) == 1

    # Повтор за полчаса — та же одна строка «Кто мной интересуется»
    визитка(сайт, "/company/stroybaza", куки)
    assert просмотры(цель) == 1


def test_раскрытые_контакты(сайт):
    цель = компания("stroybaza")
    своя = новая_компания()
    sql(
        "insert into contact_unlocks (company_id, target_company_id, credits_spent, status, "
        "created_at, updated_at) values (%s, %s, 1, 'new', now(), now())",
        [своя, цель],
    )
    куки = вошедший(сайт, "buyer@savdex.uz", своя)

    for path in ("/company/stroybaza", "/company/stroybaza?utm=1"):
        props = визитка(сайт, path, куки)

        assert props["unlocked"] is True and props["locked_count"] == 0
        assert not any(c["locked"] for c in props["contacts"])
        assert props["contacts"][0]["value"] == "+998 90 123-45-67"
        # Раскрыл — можно оставить отзыв
        assert props["review_blocked"] is None


def test_своя_компания(сайт):
    цель = компания("stroybaza")
    куки = вошедший(сайт, "owner@savdex.uz", цель)
    было = просмотры(цель)

    props = визитка(сайт, "/company/stroybaza", куки)

    assert props["is_own"] is True and props["wallet"] is None
    assert not any(c["locked"] for c in props["contacts"])
    # Свою визитку в «Кто мной интересуется» не пишет
    assert просмотры(цель) == было


@pytest.mark.parametrize(
    ("email", "поля", "причина"),
    [
        (
            "nocompany@savdex.uz",
            {},
            "Отзывы оставляют от имени компании — заполните её данные в кабинете.",
        ),
        (
            "unverified@savdex.uz",
            {"email_verified_at": None},
            "Подтвердите почту, чтобы оставлять отзывы.",
        ),
        # Заблокированный выведен из сессии: визитку видит гостем
        (
            "blocked@savdex.uz",
            {"status": "blocked"},
            "Отзывы оставляют от имени компании — заполните её данные в кабинете.",
        ),
    ],
)
def test_почему_нельзя_оставить_отзыв(сайт, email, поля, причина):
    company_id = None if email.startswith("nocompany") else новая_компания()
    куки = вошедший(сайт, email, company_id)

    if "email_verified_at" in поля:
        sql("update users set email_verified_at = null where email = %s", [email])

    if "status" in поля:
        sql("update users set status = %s where email = %s", [поля["status"], email])

    props = визитка(сайт, "/company/stroybaza", куки)

    assert props["review_blocked"] == причина


def test_повтор_отсеивает_кэш(сайт):
    """Ключ повтора — в файловом кэше: строку убрали, повтор отсеивает ключ сессии."""
    цель = компания("bare")
    своя = новая_компания()
    файловый = {"CACHE_STORE": "file"}
    куки = вошедший(сайт, "cache@savdex.uz", своя)
    sql("delete from audience_views")

    открыть(сайт, "/company/bare", куки, env=файловый)
    assert просмотры(цель) == 1

    sql("delete from audience_views")
    открыть(сайт, "/company/bare", куки, env=файловый)
    assert просмотры(цель) == 0


@pytest.mark.parametrize(
    ("статус", "тариф", "ждём"),
    [
        # Опубликован и входит в тариф — кнопка ведёт на мини-сайт
        ("published", True, "/s/stroybaza"),
        # Черновик или тариф без мини-сайта — кнопки нет: страница была бы 404
        ("draft", True, None),
        ("published", False, None),
    ],
)
def test_кнопка_мини_сайта(сайт, статус, тариф, ждём):
    if not sql("select 1 from plans where code = 'free'"):
        справочники("plans")

    было = sql("select has_microsite from plans where code = 'free'")[0][0]
    sql("delete from company_sites")
    sql("update plans set has_microsite = %s where code = 'free'", [тариф])
    sql(
        "insert into company_sites (company_id, subdomain, status, created_at, updated_at) "
        "select id, 'stroybaza', %s, now(), now() from companies where slug = 'stroybaza'",
        [статус],
    )

    try:
        адрес_сайта = визитка(сайт, "/company/stroybaza")["company"]["microsite"]
    finally:
        sql("delete from company_sites")
        sql("update plans set has_microsite = %s where code = 'free'", [было])

    if ждём is None:
        assert адрес_сайта is None
    else:
        assert адрес_сайта == сайт + ждём


def test_без_мини_сайта_кнопки_нет(сайт):
    # Свой сайт компании в профиле есть, а мини-сайта нет — кнопки нет
    props = визитка(сайт, "/company/stroybaza")

    assert props["company"]["website"] == "https://stroybaza.uz"
    assert props["company"]["microsite"] is None


@pytest.mark.parametrize(
    ("значение", "ждём"),
    [
        ("stroybaza.uz", "https://stroybaza.uz"),
        ("http://сайт.рф/о-нас", "http://сайт.рф/о-нас"),
        (None, None),
        ("", None),
        # Мусор из старых анкет — кнопки «Сайт компании» нет
        ("fwfwfef", None),
        ("https://fwfwfef", None),
    ],
)
def test_кнопка_своего_сайта(сайт, значение, ждём):
    sql("update companies set website = %s where slug = 'stroybaza'", [значение])

    try:
        assert визитка(сайт, "/company/stroybaza")["company"]["website"] == ждём
    finally:
        sql("update companies set website = 'stroybaza.uz' where slug = 'stroybaza'")
