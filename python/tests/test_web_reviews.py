"""
«Все отзывы» на Django неотличимы от Laravel.

Лента — отзывы компаний о компаниях и отзывы о самой площадке одним
запросом UNION: свежие сверху, при равной дате — по виду и номеру.
Сводка по площадке — средняя, звёзды и стороны работы. Проверяются
вкладки, страницы (в том числе странные номера страниц — как (int)
у PHP), подпись автора (компания, имя с буквой фамилии, удалённый
пользователь) и что в ленту не попадает неопубликованное.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база
from .web_site import laravel, сверить, страница

pytestmark = нужна_база

#: Без машинного перевода при создании данных: он ходит в сеть
БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


def отзыв_о_площадке(
    user: int | None,
    rating: int,
    status: str = "published",
    минут_назад: int = 0,
    company: int | None = None,
    **оценки: int,
) -> None:
    columns = {"rating_usability": None, "rating_search": None, "rating_support": None, **оценки}
    sql(
        "insert into platform_reviews (user_id, company_id, rating, rating_usability, "
        "rating_search, rating_support, body, status, created_at, updated_at) values "
        "(%s, %s, %s, %s, %s, %s, %s, %s, "
        "'2026-09-01 12:00:00'::timestamp - make_interval(mins => %s), now())",
        [
            user,
            company,
            rating,
            columns["rating_usability"],
            columns["rating_search"],
            columns["rating_support"],
            f"Пользуемся площадкой полгода, оценка {rating}: поиск поставщиков удобный.",
            status,
            минут_назад,
        ],
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    вывод = php(
        "$c = collect(range(1, 6))->map(fn ($i) => App\\Models\\Company::factory()->create());"
        "foreach (range(0, 3) as $i) { App\\Models\\Review::factory()->create(["
        "'company_id' => $c[$i]->id, 'author_company_id' => $c[$i + 1]->id, "
        "'status' => 'published', 'rating' => 5 - $i])->forceFill(["
        "'created_at' => Carbon\\Carbon::parse('2026-09-01 12:00:00')"
        "->subMinutes($i * 7)])->save(); }"
        "App\\Models\\Review::factory()->create(['company_id' => $c[4]->id, "
        "'author_company_id' => $c[5]->id, 'status' => 'moderation']);"
        "$c[5]->forceFill(['status' => 'blocked'])->save();"
        "App\\Models\\Review::factory()->create(['company_id' => $c[5]->id, "
        "'author_company_id' => $c[0]->id, 'status' => 'published']);"
        "$u = App\\Models\\User::factory()->create(['name' => 'Азиз Каримов']);"
        "$gone = App\\Models\\User::factory()->create(['name' => 'Удалённый Пользователь']);"
        "$gone->delete();"
        "echo $c[0]->id, ',', $u->id, ',', $gone->id;",
        БЕЗ_ПЕРЕВОДА,
    )
    company, user, gone = (int(x) for x in вывод.splitlines()[-1].split(","))

    отзыв_о_площадке(user, 4, rating_usability=5, rating_support=3)
    отзыв_о_площадке(gone, 2, минут_назад=7, rating_usability=2)
    отзыв_о_площадке(None, 5, минут_назад=14, company=company)
    отзыв_о_площадке(None, 1, status="moderation")
    отзыв_о_площадке(None, 3, status="hidden")

    # Ещё 22 — на вторую страницу; у части дата та же, что у отзывов о компаниях
    for i in range(22):
        uid = sql(
            "insert into users (name, email, password, status, created_at, updated_at) "
            "values (%s, %s, 'x', 'active', now(), now()) returning id",
            [f"Покупатель {i}", f"buyer{i}@savdex.uz"],
        )[0][0]
        отзыв_о_площадке(uid, 3 + i % 3, минут_назад=7 * (i % 4) + 30 * (i // 4))

    with laravel() as root:
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "/reviews",
        "/en/reviews",
        "/uz/reviews?type=platform",
        "/zh/reviews?type=company",
        "/tr/reviews?page=2",
        "/reviews?type=platform&page=2",
        "/reviews?page=3",
        "/reviews?page=abc",
        "/reviews?page=2abc",
        "/reviews?page=+2",
        "/reviews?page=0.9e1",
        "/reviews?type=nonsense&page=-4",
        "/reviews?type[]=platform&page[]=2",
        "/reviews?page=99999999",
    ],
)
def test_отзывы(сайт, path):
    сверить(сайт, path)


def test_сводка_и_подписи(сайт):
    д, _ = сверить(сайт, "/reviews?type=platform")
    props = страница(д["body"])["props"]
    authors = {r["author"] for r in props["reviews"]}

    assert props["summary"]["count"] == 25
    assert {"Азиз К.", "Пользователь SavdEx"} <= authors
    assert props["counts"]["company"] == 4


def test_главная_с_отзывами_о_площадке(сайт):
    д, _ = сверить(сайт, "/")
    kinds = [r["kind"] for r in страница(д["body"])["props"]["reviews"]]

    assert len(kinds) == 3 and "platform" in kinds and "company" in kinds
