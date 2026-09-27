"""
Этап 4, шаг 8: страница объявления /listing/<адрес> на Django неотличима
от Laravel.

Объявление с характеристиками (подписи из полей раздела), фото, тегами,
значками продвижения, продавцом и контактами (маской, пока не
заплачено), похожие; импортированное — только на языках с переводом;
черновик — только владельцу, как предпросмотр. И просмотр, как
StatsRecorder::view: счётчик, дневная строка, «Кто мной интересуется»,
строка журнала администратору — у Django ровно то же, что у Laravel.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить, страница

pytestmark = нужна_база

#: Файловый кэш, общий с Laravel: курс ЦБ для цен в валюте языка Django
#: берёт из него (в CI у Laravel есть сеть, и курс он получает сам)
ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

#: Ключи курса ЦБ в кэше Laravel (CurrencyRate)
КУРС = ("cbu.rates", "cbu.rates.last", "cbu.rate.usd.last")


def очистить_кэш() -> None:
    """Кэш с нуля — заодно и счётчик ограничения частоты."""
    subprocess.run(
        ["php", "artisan", "cache:clear"],
        cwd=КОРЕНЬ,
        env={**ОКРУЖЕНИЕ, **ФАЙЛОВЫЙ},
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    for seeder in ("GeoSeeder", "CategorySeeder", "PromotionTypeSeeder"):
        subprocess.run(
            ["php", "artisan", "db:seed", f"--class={seeder}", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            check=True,
            capture_output=True,
        )

    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$city = App\\Models\\City::where('country_id', $uz)->value('id');"
        "$child = App\\Models\\Category::whereNotNull('parent_id')->orderBy('id')->first();"
        "$child->fields()->updateOrCreate(['key' => 'mark'], ['label' => 'Марка',"
        "'type' => 'text', 'sort' => 1]);"
        "$c = App\\Models\\Company::factory()->create(['slug' => 'stroy', 'city_id' => $city,"
        "'country_id' => $uz, 'verification_level' => 2, 'website' => 'stroy.uz']);"
        "$c->contacts()->create(['type' => 'phone', 'value' => '+998 90 123-45-67',"
        "'is_public' => true, 'is_primary' => true]);"
        "$c->contacts()->create(['type' => 'website', 'value' => 'stroy.uz', 'is_public' => true]);"
        "$l = App\\Models\\Listing::factory()->create(['slug' => 'cement', 'company_id' => $c->id,"
        "'category_id' => $child->id, 'title' => 'Цемент М400 оптом для стройки',"
        "'title_i18n' => ['en' => 'Cement M400 wholesale'], 'bundle_price' => 900000,"
        "'delivery_terms' => 'Самовывоз', 'payment_terms' => 'Перечисление',"
        "'tags' => ['нет такого', 'цемент'], 'expires_at' => now()->addDays(20)]);"
        "$l->attributes()->create(['key' => 'mark', 'value' => 'М400']);"
        "$l->attributes()->create(['key' => 'weight', 'value' => '50 кг']);"
        "foreach ([1, 1, 0] as $i => $sort) { $l->images()->create(['path' => 'l/'.$i.'.webp',"
        "'thumb_path' => $i === 2 ? null : 'l/t'.$i.'.webp', 'sort' => $sort]); }"
        "$type = App\\Models\\PromotionType::where('code', 'urgent')->value('id');"
        "App\\Models\\Promotion::create(['listing_id' => $l->id, 'company_id' => $c->id,"
        "'promotion_type_id' => $type, 'units_spent' => 1, 'status' => 'active',"
        "'starts_at' => now(), 'ends_at' => now()->addDays(3)]);"
        "App\\Models\\Listing::factory()->count(5)->create(['category_id' => $child->id]);"
        "App\\Models\\Listing::factory()->create(['slug' => 'imported', 'source' => 'import',"
        "'title_i18n' => ['uz' => 'Sement'], 'price' => null, 'description' => null]);"
        "App\\Models\\Listing::factory()->draft()->create(['slug' => 'draft',"
        "'company_id' => $c->id]);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    очистить_кэш()
    # Курс ЦБ — в кэш заранее: Laravel не пойдёт за ним в сеть (в CI она
    # есть, локально нет), и цены в валюте языка у обеих сторон одни
    php(
        "Illuminate\\Support\\Facades\\Cache::put('cbu.rates', ['USD' => 12650.5,"
        "'CNY' => 1760.25, 'TRY' => 305.1, 'EUR' => 13710.0, 'RUB' => 140.2, 'KZT' => 25.3],"
        "now()->addDay());"
        "echo 'ok';",
        ФАЙЛОВЫЙ,
    )

    try:
        with laravel(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        очистить_кэш()


def без_кэша() -> None:
    """
    Файлы кэша Laravel — прочь (отсев повторов и счётчик частоты с нуля),
    кроме курса ЦБ: его Django берёт из этого кэша, а в CI Laravel
    получает курс из сети.
    """
    import hashlib

    курс = {hashlib.sha1(k.encode()).hexdigest() for k in КУРС}

    for файл in (КОРЕНЬ / "storage/framework/cache/data").rglob("*"):
        if файл.is_file() and файл.name not in курс:
            файл.unlink(missing_ok=True)


def обнулить() -> None:
    """Просмотры с нуля перед каждой стороной — и ключи отсева в кэше тоже."""
    без_кэша()
    sql("update listings set views_count = 0")
    sql("delete from listing_stats")
    sql("delete from audience_views")


@pytest.mark.parametrize(
    "path",
    [
        "/listing/cement",
        "/en/listing/cement",
        "/uz/listing/cement",
        "/listing/imported",
        "/uz/listing/imported",
        "/en/listing/imported",
    ],
)
def test_страница(сайт, path):
    сверить(сайт, path, перед=обнулить, env=ФАЙЛОВЫЙ)


@pytest.mark.parametrize("slug", ["nothing", "draft"])
def test_нет_объявления(сайт, slug):
    д, _ = сверить(сайт, f"/listing/{slug}", env=ФАЙЛОВЫЙ)
    assert д["status"] == 404


def статистика() -> tuple[object, ...]:
    return (
        sql("select id, views_count from listings order by id"),
        sql("select listing_id, date, impressions, views from listing_stats order by 1"),
        sql("select target_company_id, viewer_company_id, listing_id from audience_views"),
    )


def test_просмотр_как_у_laravel(сайт):
    пользователь("buyer@savdex.uz")
    своя = int(php("echo App\\Models\\Company::factory()->create()->id;").splitlines()[-1])
    sql("update users set company_id = %s where email = 'buyer@savdex.uz'", [своя])
    куки = войти(сайт, "buyer@savdex.uz")

    обнулить()
    из_laravel(сайт, "/listing/cement", куки)
    laravel_side = статистика()

    обнулить()
    из_django(сайт, "/listing/cement", куки, env=ФАЙЛОВЫЙ)

    assert статистика() == laravel_side
    assert laravel_side[2], "«Кто мной интересуется» с объявлением"


def test_черновик_владельцу(сайт):
    пользователь("owner@savdex.uz")
    sql(
        "update users set company_id = (select id from companies where slug = 'stroy') "
        "where email = 'owner@savdex.uz'"
    )
    куки = войти(сайт, "owner@savdex.uz")

    д, _ = сверить(сайт, "/listing/draft", куки, перед=обнулить, env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]

    assert props["preview"] is True and props["unlocked"] is True
    # Предпросмотр не считается просмотром
    assert sql("select views_count from listings where slug = 'draft'")[0][0] == 0


def test_просмотр_администратора_в_журнале(сайт):
    пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    куки = войти(сайт, "boss@savdex.uz")
    sql("delete from admin_actions")

    обнулить()
    из_laravel(сайт, "/listing/cement", куки)
    обнулить()
    из_django(сайт, "/listing/cement", куки, env=ФАЙЛОВЫЙ)

    л, д = sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb from admin_actions order by id"
    )
    assert л == д and л[2] == "listings"


def test_цена_в_валюте_языка(сайт):
    """Курс ЦБ из общего кэша: на английской странице — доллары, у обеих сторон одни."""
    д, _ = сверить(сайт, "/en/listing/cement", перед=обнулить, env=ФАЙЛОВЫЙ)

    assert страница(д["body"])["props"]["listing"]["converted"]["currency"] == "USD"
