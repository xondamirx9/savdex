"""
Отзыв о компании на визитке на Django неотличим от Laravel: проверка
ввода, право только у раскрывшего контакты и один раз (причины отказа —
как на витрине), автопроверка текста (контакты, брань, крик) и
премодерация, байесовский пересчёт рейтинга, уведомление компании об
опубликованном отзыве, журнал администратора.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex.web import review_screening

from .pg_admin import php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'buyer', 'name' => 'Покупатель']);"
        "App\\Models\\Company::factory()->create(['slug' => 'target', 'name' => 'Цемент']);"
        "foreach ([1, 2, 3] as $i) {"
        " App\\Models\\Company::factory()->create(['slug' => 'author-'.$i]); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    учётка("target@savdex.uz", company_id=_id("target"))

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def _id(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def покупатель(*, admin: bool = False, company: bool = True, status: str = "active") -> int:
    return учётка(
        "buyer@savdex.uz",
        company_id=_id("buyer") if company else None,
        is_admin=admin,
        status=status,
        email_verified_at="2026-09-01 10:00:00",
    )


def сброс(
    *,
    премодерация: Any = False,
    раскрыт: bool = True,
    свой: str | None = None,
    блок: bool = False,
    чужие: tuple[int, ...] = (5, 4, 2),
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from reviews")
        sql("delete from contact_unlocks")
        sql("delete from activity_events")
        sql("delete from user_notifications")
        sql("delete from admin_actions")
        sql("update users set locale = 'ru'")
        sql(
            "update companies set status = %s, rating = 4.5, reviews_count = 1, "
            "updated_at = now() - interval '1 day' where slug = 'buyer'",
            ["blocked" if блок else "active"],
        )
        sql(
            "update companies set status = 'active', rating = 4.5, reviews_count = 1, "
            "updated_at = now() - interval '1 day' where slug <> 'buyer'"
        )
        sql("select setval('reviews_id_seq', 1, false)")
        sql("select setval('contact_unlocks_id_seq', 1, false)")
        # Нет строки — умолчание Setting::get (премодерация включена)
        sql("delete from settings where key = 'reviews_premoderation'")

        if премодерация is not None:
            sql(
                "insert into settings (key, label, type, value, created_at, updated_at) "
                "values ('reviews_premoderation', 'Премодерация', 'boolean', %s, now(), now())",
                [json.dumps(премодерация)],
            )

        # Последний чужой отзыв — о покупателе: средний по площадке шире одной компании
        for i, rating in enumerate(чужие, start=1):
            sql(
                "insert into reviews (company_id, author_company_id, rating, body, status, "
                "created_at, updated_at) values (%s, %s, %s, 'Хороший поставщик', "
                "'published', now(), now())",
                [_id("buyer" if i == len(чужие) else "target"), _id(f"author-{i}"), rating],
            )

        if раскрыт:
            sql(
                "insert into contact_unlocks (company_id, target_company_id, credits_spent, "
                "status, created_at, updated_at) values (%s, %s, 1, 'new', now(), now())",
                [_id("buyer"), _id("target")],
            )

        if свой is not None:
            sql(
                "insert into reviews (company_id, author_company_id, rating, body, status, "
                "created_at, updated_at) values (%s, %s, 3, 'Прежний отзыв', %s, now(), now())",
                [_id("target"), _id("buyer"), свой],
            )

    return run


def снимок() -> Any:
    return {
        "reviews": sql(
            "select company_id, author_company_id, author_user_id is not null, "
            "contact_unlock_id is not null, listing_id, rating, rating_description, "
            "rating_response, rating_deadlines, rating_quality, body, deal_confirmed, status, "
            "screening_flags, origin from reviews order by id"
        ),
        "companies": sql(
            "select slug, rating::text, reviews_count, search_text, "
            "updated_at > now() - interval '1 hour' from companies order by id"
        ),
        "events": sql("select company_id, type, tone, message, url from activity_events"),
        "notifications": sql(
            "select user_id, type, title, body, tone, url from user_notifications order by id"
        ),
        "journal": sql(
            "select action, section, subject_type, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d \\d\\d:\\d\\d:\\d\\d', 'T', 'g') "
            "from admin_actions order by id"
        ),
    }


ТЕКСТ = "Поставка пришла вовремя, мешки целые, документы в порядке. Рекомендую."


@pytest.mark.parametrize(
    "body",
    [
        {"rating": 5, "body": ТЕКСТ},
        {"rating": "2", "body": "  " + ТЕКСТ + "  ", "deal_confirmed": True},
        {
            "rating": 4,
            "rating_description": 5,
            "rating_response": "3",
            "rating_deadlines": None,
            "rating_quality": 1,
            "body": ТЕКСТ,
            "deal_confirmed": "1",
        },
        {"rating": 5, "body": ТЕКСТ + " Звоните +998 90 123-45-67"},
        {"rating": 5, "body": ТЕКСТ + " пишите sale@cement.uz"},
        {"rating": 1, "body": "Это какая-то с у к а, а не поставщик, ужас просто"},
        {"rating": 1, "body": "ОБМАНЩИКИ, ДЕНЬГИ ВЗЯЛИ И ПРОПАЛИ, НЕ СВЯЗЫВАЙТЕСЬ"},
        {"rating": 5, "body": "ГОСТ 31108-2020, партия 12 000 000 сум, всё по договору"},
        {},
        {"rating": 6, "body": "коротко"},
        {"rating": "x", "rating_quality": 0, "body": ТЕКСТ, "deal_confirmed": "yes"},
        {"rating": 5, "body": ["массив"]},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_отзыв(сайт, body, admin):
    итог = отправить(
        сайт,
        "/company/target/review",
        сброс(),
        снимок,
        uid=покупатель(admin=admin),
        body=body,
        headers=inertia(),
    )

    if body.get("rating") == 5 and body.get("body") == ТЕКСТ:
        assert итог["база"]["notifications"]


@pytest.mark.parametrize("премодерация", [True, "1", 0, "", None])
def test_премодерация(сайт, премодерация):
    отправить(
        сайт,
        "/en/company/target/review",
        сброс(премодерация=премодерация, чужие=()),
        снимок,
        uid=покупатель(admin=True),
        body={"rating": 3, "body": ТЕКСТ},
        headers=inertia(),
    )


@pytest.mark.parametrize(
    "случай",
    [
        "не раскрыт",
        "на проверке",
        "скрыт",
        "опубликован",
        "своя",
        "без компании",
        "компания заблокирована",
        "нет такой",
    ],
)
def test_отказ(сайт, случай):
    uid = покупатель(company=случай != "без компании")
    подготовка = сброс(
        раскрыт=случай != "не раскрыт",
        свой={"на проверке": "moderation", "скрыт": "hidden", "опубликован": "published"}.get(
            случай
        ),
        блок=случай == "компания заблокирована",
    )
    slug = {"своя": "buyer", "нет такой": "missing"}.get(случай, "target")
    отправить(
        сайт,
        f"/company/{slug}/review",
        подготовка,
        снимок,
        uid=uid,
        body={"rating": 5, "body": ТЕКСТ},
        headers=inertia(),
    )


def test_почта(сайт):
    uid = покупатель()
    sql("update users set email_verified_at = null where id = %s", [uid])

    try:
        отправить(
            сайт,
            "/company/target/review",
            сброс(),
            снимок,
            uid=uid,
            body={"rating": 5, "body": ТЕКСТ},
            headers=inertia(),
        )
    finally:
        sql("update users set email_verified_at = now() where id = %s", [uid])


ТЕКСТЫ = [
    ТЕКСТ,
    "звоните 90 123 45 67",
    "ГОСТ 34028-2016",
    "цена 12 000 000 сум",
    "998901234567",
    "+ 7 (495) 1234567",
    "пишите в t.me/cement",
    "мой ник @cement_uz",
    "почта Sale@Cement.UZ",
    "www.cement.uz",
    "ХОРОШИЙ ПОСТАВЩИК ВСЕМ СОВЕТУЮ ОЧЕНЬ",
    "ХОРОШИЙ ПОСТАВЩИК всем советую очень",
    "cyka",
    "С-у-К-а",
    "долбоёб",
    "ПИЗДЕЦ ПОЛНЫЙ ПОСТАВЩИК ОБМАНУЛ СОВСЕМ",
    "١٢٣٤٥٦٧٨٩٠ арабские цифры",
    "",
]


def test_автопроверка_как_у_php():
    """ReviewScreening::reasons и review_screening.reasons на одних текстах."""
    php_reasons = json.loads(
        php(
            "echo json_encode(array_map(fn ($t) => App\\Support\\ReviewScreening::reasons($t),"
            f" json_decode({json.dumps(json.dumps(ТЕКСТЫ, ensure_ascii=False))}, true)),"
            " JSON_UNESCAPED_UNICODE);"
        )
    )

    assert [review_screening.reasons(t) for t in ТЕКСТЫ] == php_reasons
