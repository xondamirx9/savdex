"""
Этап 4, шаг 6: визитка компании /company/<адрес> на Django неотличима
от Laravel.

Шапка (businessCard), контакты: гостю и не заплатившему — маской,
кроме сайта; заплатившему и своей компании — открыты. Файлы: материалы
сразу, документы после одобрения, пропавшие с диска не видны. Отзывы,
право оставить свой, кошелёк смотрящего. И запись «Кто мной
интересуется»: вошедший с компанией — одна строка на полчаса, у обеих
сторон одна и та же.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить, страница

pytestmark = нужна_база

ФАЙЛЫ = КОРЕНЬ / "storage/app/private/parity-docs"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=GeoSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    ФАЙЛЫ.mkdir(parents=True, exist_ok=True)

    for name in ("license.pdf", "price.xlsx", "photo.JPG", "old.png"):
        (ФАЙЛЫ / name).write_bytes(b"x" * 10)

    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$city = App\\Models\\City::where('country_id', $uz)->value('id');"
        "$c = App\\Models\\Company::factory()->create(['slug' => 'stroybaza',"
        " 'name' => 'ООО «Стройбаза»',"
        "'legal_name' => 'ООО «Стройбаза Групп»', 'country_id' => $uz, 'city_id' => $city,"
        "'address' => 'Ташкент, Чиланзар 5', 'lat' => 41.3, 'lng' => 69.2, 'tin' => '301234567',"
        "'founded_year' => 2012, 'employees_range' => '11-50', 'verification_level' => 2,"
        "'is_it_provider' => true, 'it_specializations' => ['web', 'erp', 'unknown'],"
        "'custom_category' => 'Сухие смеси', 'website' => 'stroybaza.uz', 'rating' => 4.35,"
        "'reviews_count' => 2, 'description' => str_repeat('Поставки цемента. ', 10)]);"
        "foreach ([['phone', '+998 90 123-45-67', true], ['email', 'sales@stroybaza.uz', false],"
        "['telegram', '@stroybaza', false], ['whatsapp', '+998901234567', false],"
        "['website', 'https://stroybaza.uz', false], ['phone', '123', false]] as $i => [$t, $v,"
        " $p]) {"
        " $c->contacts()->create(['type' => $t, 'value' => $v,"
        " 'label' => $i === 1 ? 'Отдел продаж' : null,"
        " 'contact_person' => $i === 0 ? 'Азиз' : null, 'is_primary' => $p, 'is_public' => true,"
        " 'sort_order' => $i]); }"
        "$c->contacts()->create(['type' => 'phone', 'value' => '+998 71 000-00-00',"
        " 'is_public' => false]);"
        "foreach ([['license', 'Лицензия', 'license.pdf', 'approved', 2516582, '2020-01-01'],"
        "['price_list', 'Прайс', 'price.xlsx', 'pending', 800, null],"
        "['certificate', 'Сертификат', 'photo.JPG', 'pending', 5000, null],"
        "['quality', 'Качество', 'old.png', 'approved', null, '2099-05-01'],"
        "['license', 'Пропавшая', 'missing.pdf', 'approved', 100, null]] as [$t, $title, $f, $s,"
        " $size, $valid]) {"
        " $c->documents()->forceCreate(['type' => $t, 'title' => $title,"
        " 'file_path' => 'parity-docs/'.$f, 'moderation_status' => $s, 'file_size' => $size,"
        " 'valid_until' => $valid, 'is_public' => true]); }"
        "$author = App\\Models\\Company::factory()->create(['name' => 'Андижан Текстиль']);"
        "$gone = App\\Models\\Company::factory()->create(['name' => 'Ушедшая компания']);"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        " 'author_company_id' => $author->id,"
        "'status' => 'published', 'rating' => 5, 'reply' => 'Спасибо!', 'deal_confirmed' => true]);"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        " 'author_company_id' => $gone->id,"
        "'status' => 'published', 'rating' => 3]);"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        "'author_company_id' => App\\Models\\Company::factory()->create()->id,"
        "'status' => 'moderation']);"
        "$gone->delete();"
        "App\\Models\\Listing::factory()->count(3)->create(['company_id' => $c->id]);"
        "App\\Models\\Listing::factory()->create(['company_id' => $c->id, 'source' => 'import']);"
        "App\\Models\\Company::factory()->create(['slug' => 'bare', 'name' => 'ИП Каримов',"
        "'legal_form' => 'individual', 'type' => null, 'city_id' => null, 'tin' => null,"
        "'description' => null, 'lat' => null]);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    try:
        with laravel() as root:
            yield root
    finally:
        shutil.rmtree(ФАЙЛЫ, ignore_errors=True)


@pytest.mark.parametrize(
    "path",
    ["/company/stroybaza", "/en/company/stroybaza", "/uz/company/stroybaza", "/company/bare"],
)
def test_визитка_гостю(сайт, path):
    д, _ = сверить(сайт, path)
    props = страница(д["body"])["props"]

    if path.endswith("stroybaza"):
        # Сайт открыт всегда, остальные контакты — маской
        assert [c["locked"] for c in props["contacts"]] == [True, True, True, True, False, True]
        assert props["wallet"] is None


def test_нет_компании(сайт):
    д, _ = сверить(сайт, "/company/nothing")
    assert д["status"] == 404


def компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def новая_компания() -> int:
    return int(php("echo App\\Models\\Company::factory()->create()->id;").splitlines()[-1])


def вошедший(сайт: str, email: str, company_id: int | None, **поля: object) -> dict[str, str]:
    пользователь(email, company_id=company_id, **поля)

    return войти(сайт, email)


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

    д, _ = сверить(сайт, "/company/stroybaza", куки)
    props = страница(д["body"])["props"]

    assert props["wallet"] == {"contacts_left": 1, "credits": 7}
    assert props["unlocked"] is False and props["locked_count"] == 5
    assert props["review_blocked"] is not None
    # Две стороны за полчаса — одна строка «Кто мной интересуется»
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

    # Без префикса языка: с ним Laravel пишет язык в профиль, а Django
    # профиль до этапа 5 не трогает (раздел «Этап 3» документа)
    for path in ("/company/stroybaza", "/company/stroybaza?utm=1"):
        д, _ = сверить(сайт, path, куки)
        props = страница(д["body"])["props"]

        assert props["unlocked"] is True and props["locked_count"] == 0
        # Раскрыл — можно оставить отзыв
        assert props["review_blocked"] is None


def test_своя_компания(сайт):
    цель = компания("stroybaza")
    куки = вошедший(сайт, "owner@savdex.uz", цель)
    было = просмотры(цель)

    д, _ = сверить(сайт, "/company/stroybaza", куки)
    props = страница(д["body"])["props"]

    assert props["is_own"] is True and props["wallet"] is None
    assert просмотры(цель) == было


@pytest.mark.parametrize(
    ("email", "поля"),
    [
        ("nocompany@savdex.uz", {}),
        ("unverified@savdex.uz", {"email_verified_at": None}),
        ("blocked@savdex.uz", {"status": "blocked"}),
    ],
)
def test_почему_нельзя_оставить_отзыв(сайт, email, поля):
    company_id = None if email.startswith("nocompany") else новая_компания()
    куки = вошедший(сайт, email, company_id)

    if "email_verified_at" in поля:
        sql("update users set email_verified_at = null where email = %s", [email])

    if "status" in поля:
        sql("update users set status = %s where email = %s", [поля["status"], email])

    сверить(сайт, "/company/stroybaza", куки)


def test_повтор_отсеивает_общий_кэш(сайт):
    """Ключ повтора — в файловом кэше Laravel: Django поставил, Laravel видит."""
    цель = компания("bare")
    своя = новая_компания()
    файловый = {"CACHE_STORE": "file"}

    with laravel(**файловый) as root:
        куки = вошедший(root, "cache@savdex.uz", своя)
        sql("delete from audience_views")

        из_django(root, "/company/bare", куки, env=файловый)
        assert просмотры(цель) == 1

        # Строку убрали — повтор отсеивает уже только ключ сессии в кэше
        sql("delete from audience_views")
        из_laravel(root, "/company/bare", куки)
        assert просмотры(цель) == 0
