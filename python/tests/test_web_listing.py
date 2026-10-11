"""
Этап 4, шаг 8: страница объявления /listing/<адрес> на Django.

Объявление с характеристиками (подписи из полей раздела), фото, тегами,
значками продвижения, продавцом и контактами (маской, пока не
заплачено), похожие; импортированное; черновик — только владельцу, как
предпросмотр. И просмотр, как StatsRecorder::view: счётчик, дневная
строка, «Кто мной интересуется», строка журнала администратору.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator

import pytest

from savdex import laravel_cache

from .factories import Выражение, компания, объявление, объявления
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база

#: Файловый кэш, как на боевом: курс ЦБ для цен в валюте языка — из него
ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

КУРСЫ = {"USD": 12650.5, "CNY": 1760.25, "TRY": 305.1, "EUR": 13710.0, "RUB": 140.2, "KZT": 25.3}

ЧЕРЕЗ_20_ДНЕЙ = Выражение("now() + interval '20 days'")


def справочники() -> None:
    """Страны, разделы, типы продвижения — manage.py seed --fresh (savdex/seeds.py)."""
    subprocess.run(
        [sys.executable, "manage.py", "seed", "--fresh"],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            # Справочники заводит владелец базы, как миграции
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        check=True,
    )


def контакт(company: int, type_: str, value: str, *, primary: bool = False) -> None:
    sql(
        "insert into company_contacts (company_id, type, value, is_public, is_primary, "
        "created_at, updated_at) values (%s, %s, %s, true, %s, now(), now())",
        [company, type_, value, primary],
    )


def данные() -> None:
    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(city,)] = sql("select id from cities where country_id = %s order by id limit 1", [uz])
    [(other_city,)] = sql("select id from cities where id <> %s order by id limit 1", [city])
    [(child,)] = sql("select id from categories where parent_id is not null order by id limit 1")
    sql("delete from category_fields where category_id = %s and key = 'mark'", [child])
    sql(
        "insert into category_fields (category_id, key, label, type, sort, created_at, "
        "updated_at) values (%s, 'mark', 'Марка', 'text', 1, now(), now())",
        [child],
    )

    c = компания(
        slug="stroy", city_id=city, country_id=uz, verification_level=2, website="stroy.uz"
    )
    контакт(c, "phone", "+998 90 123-45-67", primary=True)
    контакт(c, "website", "stroy.uz")
    cement = объявление(
        slug="cement",
        company_id=c,
        category_id=child,
        title="Цемент М400 оптом для стройки",
        title_i18n={"en": "Cement M400 wholesale"},
        price=102000,
        bundle_price=900000,
        delivery_terms="Самовывоз",
        payment_terms="Перечисление",
        tags=["нет такого", "цемент"],
        expires_at=ЧЕРЕЗ_20_ДНЕЙ,
    )

    # Детали товара (ProductSpecs) — раньше поля раздела: на карточке
    # они встают после него; пустая и чужая spec_* — как есть
    for key, value in [
        ("spec_weight", "25 kg"), ("spec_dimensions", "120xx75,5 cm"), ("spec_color", "black"),
        ("spec_material", "Сталь с медью"), ("spec_grade", " "), ("spec_unknown", "7 шт"),
        ("spec_warranty", "12 months"), ("spec_year", "2024"), ("spec_power", "3.5 zz"),
        ("spec_voltage", "220"), ("spec_origin", "Узбекистан"), ("mark", "М400"),
        ("weight", "50 кг"),
    ]:  # fmt: skip
        sql(
            "insert into listing_attributes (listing_id, key, value, created_at, updated_at) "
            "values (%s, %s, %s, now(), now())",
            [cement, key, value],
        )

    for i, sort in enumerate([1, 1, 0]):
        sql(
            "insert into listing_images (listing_id, path, thumb_path, sort, created_at, "
            "updated_at) values (%s, %s, %s, %s, now(), now())",
            [cement, f"l/{i}.webp", None if i == 2 else f"l/t{i}.webp", sort],
        )

    [(urgent,)] = sql("select id from promotion_types where code = 'urgent'")
    sql(
        "insert into promotions (listing_id, company_id, promotion_type_id, units_spent, status, "
        "starts_at, ends_at, created_at, updated_at) values (%s, %s, %s, 1, 'active', now(), "
        "now() + interval '3 days', now(), now())",
        [cement, c, urgent],
    )
    объявления(5, category_id=child)
    объявление(
        slug="imported", source="import", title_i18n={"uz": "Sement"}, price=None, description=None
    )
    объявление(draft=True, slug="draft", company_id=c)

    # Заявка площадки (PlatformListings): у служебной компании, из
    # Excel — подписана SavdEx, без её контактов; город — самой заявки
    anjir = компания(name="ООО Anjir Group", slug="anjir", city_id=city, country_id=uz)
    контакт(anjir, "phone", "+998 71 000-00-00", primary=True)
    объявление(
        slug="zayavka",
        source="import",
        company_id=anjir,
        category_id=child,
        type="demand",
        city_id=other_city,
        title="Куплю сепаратор САД-5 с циклоном",
        expires_at=ЧЕРЕЗ_20_ДНЕЙ,
    )
    объявление(
        slug="poddony", company_id=anjir, title="Поддоны деревянные", expires_at=ЧЕРЕЗ_20_ДНЕЙ
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники()
    данные()
    laravel_cache.put("cbu.rates", КУРСЫ, 86400)

    try:
        with адрес(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        laravel_cache.file_path("cbu.rates").unlink(missing_ok=True)


def обнулить() -> None:
    """
    Просмотры с нуля. Отсев повторов — по номеру сессии: у каждого
    запроса здесь своя сессия, так что повтором он не считается.
    """
    sql("update listings set views_count = 0")
    sql("delete from listing_stats")
    sql("delete from audience_views")


def показать(сайт: str, path: str, cookies: dict[str, str] | None = None) -> dict:
    обнулить()

    return открыть(сайт, path, cookies, env=ФАЙЛОВЫЙ)


@pytest.mark.parametrize(
    ("path", "заголовок"),
    [
        ("/listing/cement", "Цемент М400 оптом для стройки"),
        ("/en/listing/cement", "Cement M400 wholesale"),
        # Перевода на узбекский нет — заголовок как есть
        ("/uz/listing/cement", "Цемент М400 оптом для стройки"),
        ("/listing/imported", None),
        ("/uz/listing/imported", "Sement"),
        ("/en/listing/imported", None),
        ("/listing/zayavka", "Куплю сепаратор САД-5 с циклоном"),
        ("/listing/poddony", "Поддоны деревянные"),
    ],
)
def test_страница(сайт, path, заголовок):
    д = показать(сайт, path)
    стр = страница(д["body"])
    props = стр["props"]
    slug = path.rsplit("/", 1)[-1]
    [(pk, title)] = sql("select id, title from listings where slug = %s", [slug])

    assert д["status"] == 200
    assert стр["component"] == "catalog/Show"
    assert стр["url"] == path
    assert props["locale"] == (path.split("/")[1] if path.count("/") == 3 else "ru")
    assert props["listing"]["id"] == pk
    assert props["listing"]["title"] == (заголовок or title)
    assert props["preview"] is False and props["unlocked"] is False
    # Просмотр посчитан: счётчик и дневная строка
    assert props["listing"]["views"] == 1
    assert sql("select slug, views_count from listings where views_count > 0") == [(slug, 1)]
    assert sql("select listing_id, impressions, views from listing_stats") == [(pk, 0, 1)]


def test_карточка_объявления(сайт):
    """Фото по порядку, значок продвижения, известные теги, контакты маской."""
    props = страница(показать(сайт, "/listing/cement")["body"])["props"]
    listing = props["listing"]
    images = sql(
        "select id from listing_images where listing_id = %s order by sort, id", [listing["id"]]
    )

    assert [i["id"] for i in listing["images"]] == [r[0] for r in images]
    # Без уменьшенной копии — сама картинка
    assert listing["images"][0]["thumb"] == listing["images"][0]["url"]
    assert listing["badges"] == ["Срочно"] and listing["promoted"] is True
    assert listing["tags"] == ["цемент"]
    assert listing["bundle_price"] == 900000
    assert (listing["delivery_terms"], listing["payment_terms"]) == ("Самовывоз", "Перечисление")
    assert props["company"]["slug"] == "stroy" and props["company"]["website"] == "https://stroy.uz"
    # Телефон — маской, пока контакты не открыты; сайт виден сразу
    assert props["contacts"] == [
        {"type": "phone", "value": "+998 90 ••• •• ••", "href": None, "locked": True},
        {"type": "website", "value": "stroy.uz", "href": "https://stroy.uz", "locked": False},
    ]
    assert props["similar"] and all(s["id"] != listing["id"] for s in props["similar"])


def test_заявка_площадки_подписана_savdex(сайт):
    """Служебная компания не показана продавцом, контактов её нет."""
    д = показать(сайт, "/listing/zayavka")
    props = страница(д["body"])["props"]

    assert props["company"]["name"] == "SavdEx" and props["company"]["platform"] is True
    assert props["contacts"] == [] and props["company"]["slug"] is None
    assert props["company"]["city"] == props["listing"]["city"] == "Самарканд"


@pytest.mark.parametrize("slug", ["nothing", "draft"])
def test_нет_объявления(сайт, slug):
    д = показать(сайт, f"/listing/{slug}")

    assert д["status"] == 404
    assert sql("select count(*) from listings where views_count > 0") == [(0,)]


def статистика() -> tuple[object, ...]:
    return (
        sql("select slug, views_count from listings where views_count > 0 order by id"),
        sql("select listing_id, impressions, views from listing_stats order by 1"),
        sql("select target_company_id, viewer_company_id, listing_id from audience_views"),
    )


def test_просмотр(сайт):
    """Вошедший из другой компании: счётчик, дневная строка и «Кто мной интересуется»."""
    uid = пользователь("buyer@savdex.uz")
    своя = компания()
    sql("update users set company_id = %s where id = %s", [своя, uid])
    [(pk, stroy)] = sql("select id, company_id from listings where slug = 'cement'")

    показать(сайт, "/listing/cement", вход(uid))

    assert статистика() == ([("cement", 1)], [(pk, 0, 1)], [(stroy, своя, pk)])


def test_черновик_владельцу(сайт):
    uid = пользователь("owner@savdex.uz")
    sql(
        "update users set company_id = (select id from companies where slug = 'stroy') "
        "where id = %s",
        [uid],
    )

    д = показать(сайт, "/listing/draft", вход(uid))
    props = страница(д["body"])["props"]

    assert д["status"] == 200
    assert props["preview"] is True and props["unlocked"] is True
    # Предпросмотр не считается просмотром
    assert sql("select views_count from listings where slug = 'draft'")[0][0] == 0


def test_просмотр_администратора_в_журнале(сайт):
    uid = пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    sql("delete from admin_actions")
    [(pk,)] = sql("select id from listings where slug = 'cement'")

    показать(сайт, "/listing/cement", вход(uid))

    assert sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb from admin_actions order by id"
    ) == [
        (
            "Покупатель boss@savdex.uz",
            "updated",
            "listings",
            "App\\Models\\Listing",
            pk,
            "Цемент М400 оптом для стройки",
            {"before": {"views_count": 0}, "after": {"views_count": 1}},
        )
    ]


def test_цена_в_валюте_языка(сайт):
    """Курс ЦБ из файлового кэша: на английской странице — доллары."""
    listing = страница(показать(сайт, "/en/listing/cement")["body"])["props"]["listing"]

    # По курсу 12 650,5: три значащие цифры — 8,06 и 71,1 доллара
    assert listing["price"] == 102000
    assert listing["converted"] == {"price": 8.06, "currency": "USD"}
    assert listing["bundle_converted"] == {"price": 71.1, "currency": "USD"}


def test_цена_диапазоном(сайт):
    """Диапазон «от – до»: оба конца в валюте языка, для Google — AggregateOffer."""
    sql("update listings set price_to = 150000 where slug = 'cement'")

    try:
        ответ = показать(сайт, "/en/listing/cement")
    finally:
        sql("update listings set price_to = null where slug = 'cement'")

    listing = страница(ответ["body"])["props"]["listing"]

    assert (listing["price"], listing["price_to"], listing["price_from"]) == (102000, 150000, False)
    assert listing["converted_to"] == {"price": 11.9, "currency": "USD"}
    assert '"@type":"AggregateOffer"' in ответ["body"].replace(" ", "")
    assert '"lowPrice":102000' in ответ["body"].replace(" ", "")


def test_русский_перевод_объявления_не_по_русски(сайт):
    """Заголовок по-китайски — на русской странице русский перевод, на китайской — оригинал."""
    sql(
        "update listings set title = '水泥', title_i18n = '{\"ru\":\"Цемент\"}'::json "
        "where slug = 'cement'"
    )

    try:
        ru = страница(показать(сайт, "/listing/cement")["body"])["props"]["listing"]
        zh = страница(показать(сайт, "/zh/listing/cement")["body"])["props"]["listing"]
    finally:
        sql(
            "update listings set title = 'Цемент М400 оптом для стройки', "
            "title_i18n = '{\"en\":\"Cement M400 wholesale\"}'::json where slug = 'cement'"
        )

    assert (ru["title"], zh["title"]) == ("Цемент", "水泥")


def test_детали_товара(сайт):
    """ProductSpecs: детали после полей раздела, на языке посетителя, без пустых."""
    for path, вес, цвет in (
        ("/listing/cement", "25 кг", "Чёрный"),
        ("/en/listing/cement", "25 kg", "Black"),
    ):
        props = страница(показать(сайт, path)["body"])["props"]
        rows = {a["key"]: a["value"] for a in props["listing"]["attributes"]}
        ключи = [a["key"] for a in props["listing"]["attributes"]]

        # Чужой ключ spec_unknown — обычная характеристика, в начале списка
        assert set(ключи[:3]) == {"spec_unknown", "Марка", "weight"}
        assert вес in rows.values() and цвет in rows.values()
        assert "spec_unknown" in rows and "spec_grade" not in rows
        assert "25 kg" not in props["listing"]["tags"]


def test_метка_не_подтверждено(сайт):
    """Код пропущен при регистрации — метка на странице и в похожих карточках."""
    sql("update companies set email_unconfirmed = true where slug = 'stroy'")

    try:
        props = страница(показать(сайт, "/listing/cement")["body"])["props"]
    finally:
        sql("update companies set email_unconfirmed = false where slug = 'stroy'")

    assert props["company"]["unconfirmed"] is True
    stroy = sql(
        "select id from listings where company_id = (select id from companies where slug = 'stroy')"
    )
    своих = {r[0] for r in stroy}
    assert all(s["company"]["unconfirmed"] is (s["id"] in своих) for s in props["similar"])
