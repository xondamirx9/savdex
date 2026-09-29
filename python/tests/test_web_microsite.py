"""
Мини-сайт компании на Django неотличим от Laravel: страница /s/<адрес>
(оформление — переменные SiteTheme с подбором читаемых цветов, шрифты,
свой корневой шаблон с вывеской компании; контакты целиком, товары сайта
и объявления, файлы, отзывы), 404 для черновика, заблокированной
компании и тарифа без мини-сайта; предпросмотр в кабинете (оформление из
редактора или черновик); с MICROSITE_DOMAIN — сайт на поддомене,
301 с /s/<адрес>, сам домен — в каталог компаний, прочее там — 404.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import quote

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_forms import учётка
from .web_site import laravel, войти, сверить, страница

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}
ДОМЕН = {"MICROSITE_DOMAIN": "savdex.site"}
ТЕМА = {
    "template": "bold",
    "primary": "#FACC15",
    "accent": "#f5d020",
    "mode": "light",
    "heading_font": "lora",
    "body_font": "pt-sans",
    "radius": "round",
    "hero_image": "sites/1/hero.webp",
}


@pytest.fixture(scope="module")
def база() -> None:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'mine', 'name' => 'ООО «Цемент»',"
        " 'description' => \"  Цемент   М400\\n и арматура \" . str_repeat('оптом ', 40)]);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'buyer', 'name' => 'Покупатель']);"
        "foreach ([['phone', '+998 90 123-45-67', true], ['telegram', '@cement', true],"
        " ['email', 'hidden@cement.uz', false]] as $i => [$type, $value, $public]) {"
        " App\\Models\\CompanyContact::create(['company_id' => $c->id, 'type' => $type,"
        " 'value' => $value, 'is_public' => $public, 'sort_order' => 3 - $i]); }"
        "foreach (range(1, 3) as $i) { App\\Models\\Listing::factory()->create(["
        " 'company_id' => $c->id, 'status' => $i === 3 ? 'archived' : 'active',"
        " 'title' => 'Цемент '.$i, 'published_at' => now()->subDays($i)]); }"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        " 'author_company_id' => $o->id, 'status' => 'published', 'rating' => 5,"
        " 'body' => 'Отличный цемент']);"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        " 'author_company_id' => App\\Models\\Company::factory()->create()->id,"
        " 'status' => 'moderation', 'rating' => 1]);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    sql(
        "insert into company_site_products (company_id, title, description, price, currency, "
        "unit, sort, created_at, updated_at) select id, 'Свой товар', '  Мешок  50 кг ', "
        "120000, 'UZS', 'шт', 1, now(), now() from companies where slug = 'mine'"
    )
    sql(
        "insert into company_site_products (company_id, title, sort, created_at, updated_at) "
        "select id, 'Под заказ', 0, now(), now() from companies where slug = 'mine'"
    )
    фон = Path(КОРЕНЬ) / "storage/app/public/sites/1/hero.webp"
    фон.parent.mkdir(parents=True, exist_ok=True)
    фон.write_bytes(b"hero")


@pytest.fixture(scope="module")
def сайт(база) -> Iterator[str]:
    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def сброс(
    *,
    статус: str = "published",
    тариф: bool = True,
    блок: bool = False,
    тема: dict[str, object] | None = None,
    черновик: dict[str, object] | None = None,
) -> Callable[[], None]:
    def run() -> None:
        sql("update plans set has_microsite = %s where code = 'free'", [тариф])
        статус_компании = "blocked" if блок else "active"
        sql("update companies set status = %s where slug = 'mine'", [статус_компании])
        sql("delete from company_sites")
        sql(
            "insert into company_sites (company_id, subdomain, status, theme, published_theme, "
            "published_at, created_at, updated_at) select id, 'mine', %s, %s, %s, now(), now(), "
            "now() from companies where slug = 'mine'",
            [статус, json.dumps(черновик or {}), json.dumps(тема or ТЕМА)],
        )

    return run


@pytest.mark.parametrize(
    ("path", "настройка"),
    [
        ("/s/mine", {}),
        ("/en/s/mine", {}),
        ("/s/mine", {"тема": {"mode": "dark", "primary": "#0f172a", "accent": "#0f172a"}}),
        ("/s/mine", {"тема": {"primary": "#ffffff", "heading_font": "oswald", "radius": "x"}}),
        ("/s/mine", {"тема": {"primary": "#5b3cc4", "accent": "#e11d74", "template": "minimal"}}),
        ("/s/mine", {"статус": "draft"}),
        ("/s/mine", {"тариф": False}),
        ("/s/mine", {"блок": True}),
        ("/s/nothing", {}),
    ],
)
def test_страница(сайт, path, настройка):
    сверить(сайт, path, перед=сброс(**настройка))


def test_оформление_читаемо(сайт):
    д, _ = сверить(сайт, "/s/mine", перед=сброс())
    props = страница(д["body"])["props"]

    assert props["vars"]["--ms-primary-text"] != "#facc15"
    assert props["hero"] and props["contacts"] and len(props["products"]) == 4


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?theme=" + quote(json.dumps({"mode": "dark", "primary": "#112233"})),
        "?theme=" + quote("[1,2]"),
        "?theme=oops",
        "?theme=5",
    ],
)
def test_предпросмотр(сайт, query):
    учётка("owner@savdex.uz")
    sql(
        "update users set company_id = (select id from companies where slug = 'mine') "
        "where email = 'owner@savdex.uz'"
    )
    куки = войти(сайт, "owner@savdex.uz")
    сверить(
        сайт,
        "/cabinet/site/preview" + query,
        куки,
        перед=сброс(черновик={"template": "minimal", "primary": "#0f6e56"}),
    )


def test_предпросмотр_без_сайта_и_без_компании(сайт):
    учётка("nocompany@savdex.uz")
    куки = войти(сайт, "nocompany@savdex.uz")
    д, _ = сверить(сайт, "/cabinet/site/preview", куки)
    assert д["status"] == 302

    учётка("owner@savdex.uz")
    sql(
        "update users set company_id = (select id from companies where slug = 'mine') "
        "where email = 'owner@savdex.uz'"
    )
    куки = войти(сайт, "owner@savdex.uz")
    sql("delete from company_sites")
    сверить(сайт, "/cabinet/site/preview", куки)


@pytest.fixture(scope="module")
def поддомены(база) -> Iterator[str]:
    with laravel(**БЕЗ_ПЕРЕВОДА, **ДОМЕН) as root:
        yield root


@pytest.mark.parametrize(
    ("host", "path"),
    [
        ("mine.savdex.site", "/"),
        ("mine.savdex.site", "/uz"),
        ("nothing.savdex.site", "/"),
        ("savdex.site", "/"),
        ("mine.savdex.site", "/catalog"),
        (None, "/s/mine"),
    ],
)
def test_поддомены(поддомены, host, path):
    port = поддомены.rsplit(":", 1)[1]
    headers = {"Host": f"{host}:{port}"} if host else None
    сверить(поддомены, path, headers=headers, env=ДОМЕН, перед=сброс())
