"""
Этап 4, шаг 4: вкладка «Тендеры» каталога (/catalog?type=tender) на
Django неотличима от Laravel.

Открытые (ближайший срок сверху, без срока — в конце) и завершённые,
поиск, раздел каталога с подразделами, переводы заголовка, будущая
публикация и черновик не видны; баннер каталога; дни до конца приёма.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    for seeder in ("GeoSeeder", "CategorySeeder"):
        subprocess.run(
            ["php", "artisan", "db:seed", f"--class={seeder}", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            check=True,
            capture_output=True,
        )

    # 24 открытых (две страницы), 4 без срока, 5 завершённых, будущая
    # публикация, черновик; часть — в подразделе, часть — с переводом
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$root = App\\Models\\Category::whereNull('parent_id')->orderBy('sort')->first();"
        "$child = App\\Models\\Category::where('parent_id', $root->id)->orderBy('sort')->first();"
        "$other = App\\Models\\Category::whereNull('parent_id')->orderBy('sort')->skip(1)->first();"
        "foreach (range(1, 24) as $i) { App\\Models\\Tender::factory()->create(["
        "'title' => ($i % 5 ? 'Поставка цемента ' : 'Sement yetkazib berish ').$i,"
        "'category_id' => [$root->id, $child->id, $other->id][$i % 3],"
        "'country_id' => $i % 2 ? $uz : null, 'budget' => $i % 4 ? 1000000 * $i : null,"
        "'deadline_at' => now()->addHours(20 * $i), 'published_at' => now()->subDays($i % 5),"
        "'title_i18n' => $i % 6 ? null : ['en' => 'Cement supply '.$i, 'uz' => ' '],"
        "'description_i18n' => $i % 6 ? null : ['en' => 'Cement.']]); }"
        "foreach (range(1, 4) as $i) { App\\Models\\Tender::factory()->create(["
        "'deadline_at' => null, 'published_at' => now()->subDays($i)]); }"
        "foreach (range(1, 5) as $i) { App\\Models\\Tender::factory()->create(["
        "'deadline_at' => now()->subDays($i)->subHours(3)]); }"
        "App\\Models\\Tender::factory()->create(['published_at' => now()->addDay()]);"
        "App\\Models\\Tender::factory()->create(['status' => 'draft']);"
        "App\\Models\\Listing::factory()->count(3)->create();"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "/catalog?type=tender",
        "/catalog?type=tender&page=2",
        "/catalog?page=3&type=tender",
        "/en/catalog?type=tender",
        "/uz/catalog?type=tender&page=2",
        "/zh/catalog?type=tender&closed=1",
        "/tr/catalog?type=%20tender%20&closed=yes",
        "/catalog?type=tender&closed=0",
        "/catalog?type=tender&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82",
        "/catalog?type=tender&q=sement",
        "/catalog?type=tender&q=%20",
        "/catalog?type=tender&category=abc",
        "/catalog?type=tender&sort=cheap&city=5&verified=1",
    ],
)
def test_вкладка_тендеров(сайт, path):
    сверить(сайт, path)


def test_раздел_с_подразделами(сайт):
    д, _ = сверить(сайт, "/catalog?type=tender")
    раздел = страница(д["body"])["props"]["categories"][0]["id"]
    д, _ = сверить(сайт, f"/catalog?type=tender&category={раздел}")

    # Раздел включает свой подраздел: 16 из 24 — корень и подраздел, и
    # ещё 4 открытых без срока — фабрика кладёт их в первый раздел
    assert страница(д["body"])["props"]["total"] == 20


def test_баннер_каталога(сайт):
    php(
        "App\\Models\\Banner::create(['name' => 'Тарифы', 'placement' => 'catalog',"
        "'is_active' => true,"
        "'image_path' => 'banners/c.jpg', 'url' => 'https://savdex.uz/pricing',"
        "'alt' => 'Тарифы', 'sort' => 1]);"
        "echo 'ok';"
    )
    д, _ = сверить(сайт, "/catalog?type=tender")

    assert страница(д["body"])["props"]["banner"]["alt"] == "Тарифы"


def адреса() -> list[str]:
    return [r[0] for r in sql("select slug from tenders where status = 'published' order by id")]


def test_страница_закупки(сайт):
    slugs = адреса()

    # открытая с переводом, без срока, завершённая
    for slug, prefix in ((slugs[5], ""), (slugs[5], "/en"), (slugs[25], "/uz"), (slugs[30], "/zh")):
        сверить(сайт, f"{prefix}/tenders/{slug}")


def test_нет_закупки(сайт):
    черновик = sql("select slug from tenders where status = 'draft'")[0][0]
    будущая = sql("select slug from tenders where published_at > now()")[0][0]

    for slug in ("nothing-here", черновик, будущая):
        д, _ = сверить(сайт, f"/tenders/{slug}")
        assert д["status"] == 404


def test_просмотры_считают_обе_стороны(сайт):
    slug = адреса()[2]
    было = sql("select views_count from tenders where slug = %s", [slug])[0][0]

    из_django(сайт, f"/tenders/{slug}")
    из_laravel(сайт, f"/tenders/{slug}")

    assert sql("select views_count from tenders where slug = %s", [slug])[0][0] == было + 2


def test_просмотр_администратора_в_журнале(сайт):
    пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    куки = войти(сайт, "boss@savdex.uz")
    slug = адреса()[3]
    sql("delete from admin_actions")

    из_laravel(сайт, f"/tenders/{slug}", куки)
    из_django(сайт, f"/tenders/{slug}", куки)

    строки = sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb, ip from admin_actions order by id"
    )
    assert len(строки) == 2
    л, д = строки
    # До и после — на единицу больше у второй строки; остальное одинаково
    assert л[:6] == д[:6] and л[7] == д[7]
    assert д[6]["after"]["views_count"] == л[6]["after"]["views_count"] + 1
    assert д[6]["before"]["views_count"] == л[6]["after"]["views_count"]
