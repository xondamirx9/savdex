"""
Главная на Django неотличима от Laravel (этап 3).

Данные — справочники (DatabaseSeeder), задачи услуг (ItTasksDemoSeeder)
и компании с объявлениями из фабрик: витрина VIP с платным продвижением
и истёкшей подпиской, импортированное объявление без перевода, цены в
долларах, евро и «договорная», фотографии с уменьшенной копией и без,
ИП без типа компании, баннер с картинкой под язык, свой фон первого
экрана, скрытая секция и отзывы. Курс — из файлового кэша,
как на боевом.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, пользователь, сверить, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

#: Без машинного перевода при создании объявлений: он ходит в сеть
БЕЗ_ПЕРЕВОДА = {**ФАЙЛОВЫЙ, "MACHINE_TRANSLATION_ENABLED": "false"}

#: PNG 3 × 2 — пропорция фона 1.5
КАДР = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAIAAAASFvFNAAAAEUlEQVR4nGP4z8DwHwoYSGYCAKq9Jfr"
    "B8PoKAAAAAElFTkSuQmCC"
)


def artisan(*args: str) -> None:
    subprocess.run(
        ["php", "artisan", *args, "--force"],
        cwd=КОРЕНЬ,
        env={**ОКРУЖЕНИЕ, **БЕЗ_ПЕРЕВОДА},
        check=True,
        capture_output=True,
    )


def очистить_кэш() -> None:
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
    artisan("db:seed")
    artisan("db:seed", "--class=ItTasksDemoSeeder")
    фон = КОРЕНЬ / "storage/app/public/appearance/test-hero.png"
    фон.parent.mkdir(parents=True, exist_ok=True)
    фон.write_bytes(КАДР)
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$kz = App\\Models\\Country::where('code', 'kz')->value('id');"
        "$cities = App\\Models\\City::where('country_id', $uz)->orderBy('id')"
        "->take(3)->pluck('id');"
        "$companies = collect(range(0, 5))->map(fn ($i) => "
        "App\\Models\\Company::factory()->create(["
        "'country_id' => $i === 5 ? $kz : $uz, 'city_id' => $i === 5 ? null : $cities[$i % 3], "
        "'verification_level' => $i % 3, 'rating' => 3 + $i * 0.3, "
        "'legal_form' => $i === 4 ? 'individual' : 'legal', "
        "'type' => $i === 4 ? null : 'importer', "
        "'phone' => '+998 90 000 00 0'.$i, 'email' => $i % 2 ? 'c'.$i.'@example.com' : null]));"
        "foreach ($companies as $i => $c) {"
        " App\\Models\\Listing::factory()->count(3)->create(['company_id' => $c->id]);"
        " App\\Models\\Listing::factory()->create(['company_id' => $c->id, 'type' => 'demand']); }"
        "foreach (App\\Models\\Listing::orderBy('id')->take(5)->get() as $n => $l) {"
        " App\\Models\\ListingImage::create(['listing_id' => $l->id, "
        "'path' => 'listings/'.$n.'.jpg', "
        "'thumb_path' => $n % 2 ? null : 'listings/thumb-'.$n.'.jpg', 'sort' => 1]);"
        " App\\Models\\ListingImage::create(['listing_id' => $l->id, "
        "'path' => 'listings/b'.$n.'.jpg', "
        "'sort' => 0]); }"
        "$vip = App\\Models\\Plan::where('code', 'vip')->first();"
        "foreach ($companies->take(2) as $c) { App\\Models\\Subscription::create(["
        "'company_id' => $c->id, 'plan_id' => $vip->id, 'status' => 'active', "
        "'started_at' => now()->subDay(), 'ends_at' => now()->addMonth()]); }"
        "App\\Models\\Subscription::create(['company_id' => $companies[2]->id, "
        "'plan_id' => $vip->id, 'status' => 'active', 'started_at' => now()->subMonths(2), "
        "'ends_at' => now()->subDay()]);"
        "$type = App\\Models\\PromotionType::query()->whereNotNull('badge')->first();"
        "$listing = App\\Models\\Listing::where('company_id', $companies[1]->id)"
        "->where('type', 'supply')->orderBy('id')->first();"
        "App\\Models\\Promotion::create(['listing_id' => $listing->id, "
        "'company_id' => $listing->company_id, 'promotion_type_id' => $type->id, "
        "'units_spent' => 1, 'status' => 'active', 'starts_at' => now()->subDay(), "
        "'ends_at' => now()->addWeek()]);"
        "App\\Models\\Listing::factory()->create(['company_id' => $companies[0]->id, "
        "'price' => 1234.5, 'currency' => 'USD', 'published_at' => now()->subHours(3), "
        "'description' => str_repeat('供应优质水泥，', 40)]);"
        "App\\Models\\Listing::factory()->create(['company_id' => $companies[0]->id, "
        "'price_negotiable' => true, 'published_at' => now()->subMinutes(20)]);"
        "App\\Models\\Listing::factory()->create(['company_id' => $companies[0]->id, "
        "'source' => 'import', 'title_i18n' => ['en' => 'Imported cement'], "
        "'published_at' => now()->subMinutes(5)]);"
        "App\\Models\\Listing::factory()->create(['company_id' => $companies[1]->id, "
        "'type' => 'demand', 'price' => 99, 'currency' => 'EUR', "
        "'published_at' => now()->subDays(2)]);"
        "foreach (range(0, 3) as $i) { App\\Models\\Review::factory()->create(["
        "'company_id' => $companies[$i]->id, 'author_company_id' => $companies[$i + 1]->id, "
        "'created_at' => now()->subDays($i)]); }"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    sql(
        "insert into banners (name, placement, url, alt, image_path, focal_x, focal_y, is_active, "
        "is_dismissible, sort, created_at, updated_at) values ('Акция', 'home', '/pricing', "
        "'Скидка', 'banners/a.png', 30, 70, true, true, 0, now(), now())"
    )
    sql(
        "insert into banner_images (banner_id, locale, image_path, image_mobile_path, "
        "created_at, updated_at) select id, 'en', 'banners/en.png', null, now(), now() "
        "from banners"
    )
    sql("update landing_blocks set is_visible = false where key = 'reviews'")
    sql(
        "update settings set value = %s where key = 'hero_image'",
        ['"appearance/test-hero.png"'],
    )
    очистить_кэш()
    php(
        "Cache::put('cbu.rates', ['USD' => 12650.0, 'EUR' => 13790.25, 'CNY' => 1755.4, "
        "'TRY' => 380.12], now()->addDay());",
        ФАЙЛОВЫЙ,
    )

    try:
        with laravel(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        очистить_кэш()
        фон.unlink(missing_ok=True)


@pytest.mark.parametrize("path", ["/", "/uz", "/en", "/zh/", "/tr"])
def test_главная(сайт, path):
    д, _ = сверить(сайт, path, env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]

    assert props["latest"] and props["requests"] and props["suppliers"]
    assert props["heroRatio"] == 1.5


def test_витрина_vip_и_цены(сайт):
    д, _ = сверить(сайт, "/en", env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]

    assert props["latest"][0]["promoted"]
    assert any(card["converted"] for card in props["latest"])
    assert props["banner"]["image"].endswith("/storage/banners/en.png")


def test_вошедший(сайт):
    пользователь("home@savdex.uz")
    куки = войти(сайт, "home@savdex.uz")

    сверить(сайт, "/", куки, env=ФАЙЛОВЫЙ)
    # Без версии сборки — 409: адрес перезагрузки у корня без «/»,
    # а с параметрами — «/?…», как Request::fullUrl у Laravel
    сверить(сайт, "/uz", куки, {"X-Inertia": "true"}, env=ФАЙЛОВЫЙ)
    сверить(сайт, "/?utm_source=tg", куки, {"X-Inertia": "true"}, env=ФАЙЛОВЫЙ)
