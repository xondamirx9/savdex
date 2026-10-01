"""
«Все отзывы» — проверки Django.

Лента — отзывы компаний о компаниях и отзывы о самой площадке одним
запросом UNION: свежие сверху, при равной дате — по виду и номеру.
Сводка по площадке — средняя, звёзды и стороны работы. Проверяются
вкладки, страницы (в том числе странные номера страниц — как (int)
у PHP), подпись автора (компания, имя с буквой фамилии, удалённый
пользователь) и что в ленту не попадает неопубликованное.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .factories import Выражение, компании, отзыв, пользователь
from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть, страница

pytestmark = нужна_база


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
    c = компании(6)

    for i in range(4):
        отзыв(
            company_id=c[i],
            author_company_id=c[i + 1],
            status="published",
            rating=5 - i,
            created_at=Выражение(
                f"'2026-09-01 12:00:00'::timestamp - make_interval(mins => {i * 7})"
            ),
        )

    отзыв(company_id=c[4], author_company_id=c[5], status="moderation")
    sql("update companies set status = 'blocked' where id = %s", [c[5]])
    отзыв(company_id=c[5], author_company_id=c[0], status="published")
    company = c[0]
    user = пользователь(name="Азиз Каримов")
    gone = пользователь(name="Удалённый Пользователь", deleted_at=Выражение("now()"))

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

    with адрес() as root:
        yield root


@pytest.mark.parametrize(
    ("path", "type_", "page", "на_странице"),
    [
        ("/reviews", "all", 1, 20),
        ("/en/reviews", "all", 1, 20),
        ("/uz/reviews?type=platform", "platform", 1, 20),
        # Отзыв о заблокированной компании в ленту не попадает
        ("/zh/reviews?type=company", "company", 1, 4),
        ("/tr/reviews?page=2", "all", 2, 9),
        ("/reviews?type=platform&page=2", "platform", 2, 5),
        ("/reviews?page=3", "all", 3, 0),
        # Номер страницы — как (int) у PHP: «abc» → 1, «2abc» и «+2» → 2,
        # «0.9e1» → 9; отрицательный — первая, огромный — не дальше 10000
        ("/reviews?page=abc", "all", 1, 20),
        ("/reviews?page=2abc", "all", 2, 9),
        ("/reviews?page=+2", "all", 2, 9),
        ("/reviews?page=0.9e1", "all", 9, 0),
        ("/reviews?type=nonsense&page=-4", "all", 1, 20),
        ("/reviews?type[]=platform&page[]=2", "all", 1, 20),
        ("/reviews?page=99999999", "all", 10000, 0),
    ],
)
def test_отзывы(сайт, path, type_, page, на_странице):
    д = открыть(сайт, path)
    стр = страница(д["body"])
    props = стр["props"]

    assert д["status"] == 200 and стр["component"] == "Reviews"
    assert (props["type"], props["page"], len(props["reviews"])) == (type_, page, на_странице)
    # Неопубликованное (на проверке, скрытое) не считается
    assert props["counts"] == {"all": 29, "platform": 25, "company": 4}
    assert props["pages"] == {"all": 2, "platform": 2, "company": 1}[type_]

    if type_ != "all":
        assert {r["kind"] for r in props["reviews"]} <= {type_}


def test_порядок_ленты(сайт):
    props = страница(открыть(сайт, "/reviews")["body"])["props"]

    # Свежие сверху; при равной дате — отзыв о компании, затем о площадке
    # по убыванию номера
    assert [(r["kind"], r["author"], r["rating"]) for r in props["reviews"][:6]] == [
        ("company", "ООО «Компания 2»", 5),
        ("platform", "Покупатель 0.", 3),
        ("platform", "Азиз К.", 4),
        ("company", "ООО «Компания 3»", 4),
        ("platform", "Покупатель 1.", 4),
        ("platform", "Пользователь SavdEx", 2),
    ]


def test_сводка_и_подписи(сайт):
    д = открыть(сайт, "/reviews?type=platform")
    props = страница(д["body"])["props"]
    authors = {r["author"] for r in props["reviews"]}

    assert props["summary"]["count"] == 25
    assert props["summary"]["average"] == 3.9
    assert [s["count"] for s in props["summary"]["stars"]] == [8, 8, 8, 1, 0]
    assert [c["average"] for c in props["summary"]["criteria"]] == [3.5, None, 3]
    # Компания, имя с буквой фамилии, удалённый пользователь
    assert {"ООО «Компания 1»", "Азиз К.", "Пользователь SavdEx"} <= authors
    assert props["counts"]["company"] == 4


def test_главная_с_отзывами_о_площадке(сайт):
    д = открыть(сайт, "/")
    kinds = [r["kind"] for r in страница(д["body"])["props"]["reviews"]]

    assert len(kinds) == 3 and "platform" in kinds and "company" in kinds
