"""
Отзыв о компании на визитке на Django: проверка
ввода, право только у раскрывшего контакты и один раз (причины отказа —
как на витрине), автопроверка текста (контакты, брань, крик) и
премодерация, байесовский пересчёт рейтинга, уведомление компании об
опубликованном отзыве, журнал администратора.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex.web import review_screening

from .factories import компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="buyer", name="Покупатель")
    компания(slug="target", name="Цемент")

    for i in (1, 2, 3):
        компания(slug=f"author-{i}")

    учётка("target@savdex.uz", company_id=_id("target"))

    with адрес(MACHINE_TRANSLATION_ENABLED="false") as root:
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

КОНТАКТЫ = "В тексте есть контакты: телефон, почта или ссылка"
БРАНЬ = "В тексте есть брань"
КРИК = "Текст набран заглавными буквами"
ОПУБЛИКОВАН = "Отзыв опубликован. Компания получила уведомление и сможет ответить."


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return json.loads(итог["сессия"]["payload"])


def ошибки(итог: dict[str, Any]) -> set[str]:
    return set(сессия(итог).get("errors", {}).get("default", {}).get("messages", {}))


def на_проверку(причина: str) -> str:
    """Сообщение автору: причина автопроверки со строчной буквы."""
    return (
        f"Отзыв отправлен на проверку: {причина[0].lower() + причина[1:]}. "
        "Модератор посмотрит его вручную."
    )


#: Рейтинг «Цемента» — байесовский: (5 × средний по площадке + сумма) / (5 + число).
#: До отзыва у «Цемента» 5 и 4, у покупателя 2
@pytest.mark.parametrize(
    ("body", "ждём"),
    [
        # (оценки, текст, сделка, статус, флаги), (рейтинг, число отзывов)
        (
            {"rating": 5, "body": ТЕКСТ},
            ((5, None, None, None, None), ТЕКСТ, False, "published", None, ("4.25", 3)),
        ),
        # Текст обрезается по краям; оценка строкой — число
        (
            {"rating": "2", "body": "  " + ТЕКСТ + "  ", "deal_confirmed": True},
            ((2, None, None, None, None), ТЕКСТ, True, "published", None, ("3.41", 3)),
        ),
        (
            {
                "rating": 4,
                "rating_description": 5,
                "rating_response": "3",
                "rating_deadlines": None,
                "rating_quality": 1,
                "body": ТЕКСТ,
                "deal_confirmed": "1",
            },
            ((4, 5, 3, None, 1), ТЕКСТ, True, "published", None, ("3.97", 3)),
        ),
        # Автопроверка — на модерацию; в рейтинг не идёт, но пересчёт есть
        (
            {"rating": 5, "body": ТЕКСТ + " Звоните +998 90 123-45-67"},
            (
                (5, None, None, None, None),
                ТЕКСТ + " Звоните +998 90 123-45-67",
                False,
                "moderation",
                КОНТАКТЫ,
                ("3.90", 2),
            ),
        ),
        (
            {"rating": 5, "body": ТЕКСТ + " пишите sale@cement.uz"},
            (
                (5, None, None, None, None),
                ТЕКСТ + " пишите sale@cement.uz",
                False,
                "moderation",
                КОНТАКТЫ,
                ("3.90", 2),
            ),
        ),
        (
            {"rating": 1, "body": "Это какая-то с у к а, а не поставщик, ужас просто"},
            (
                (1, None, None, None, None),
                "Это какая-то с у к а, а не поставщик, ужас просто",
                False,
                "moderation",
                БРАНЬ,
                ("3.90", 2),
            ),
        ),
        (
            {"rating": 1, "body": "ОБМАНЩИКИ, ДЕНЬГИ ВЗЯЛИ И ПРОПАЛИ, НЕ СВЯЗЫВАЙТЕСЬ"},
            (
                (1, None, None, None, None),
                "ОБМАНЩИКИ, ДЕНЬГИ ВЗЯЛИ И ПРОПАЛИ, НЕ СВЯЗЫВАЙТЕСЬ",
                False,
                "moderation",
                КРИК,
                ("3.90", 2),
            ),
        ),
        # Номер ГОСТа и сумма — не телефон
        (
            {"rating": 5, "body": "ГОСТ 31108-2020, партия 12 000 000 сум, всё по договору"},
            (
                (5, None, None, None, None),
                "ГОСТ 31108-2020, партия 12 000 000 сум, всё по договору",
                False,
                "published",
                None,
                ("4.25", 3),
            ),
        ),
        ({}, {"rating", "body"}),
        ({"rating": 6, "body": "коротко"}, {"rating", "body"}),
        (
            {"rating": "x", "rating_quality": 0, "body": ТЕКСТ, "deal_confirmed": "yes"},
            {"rating", "rating_quality", "deal_confirmed"},
        ),
        ({"rating": 5, "body": ["массив"]}, {"body"}),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_отзыв(сайт, body, ждём, admin):
    uid = покупатель(admin=admin)
    итог = отправить(
        сайт,
        "/company/target/review",
        сброс(),
        снимок,
        uid=uid,
        body=body,
        headers=inertia(),
    )
    база = итог["база"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"

    if isinstance(ждём, set):
        assert ошибки(итог) == ждём
        assert len(база["reviews"]) == 3
        assert база["companies"][1][1:3] == ("4.50", 1)
        assert база["notifications"] == база["events"] == база["journal"] == []
        return

    оценки, текст, сделка, статус, флаги, рейтинг = ждём
    target, buyer = _id("target"), _id("buyer")

    assert база["reviews"][3] == (
        target, buyer, True, True, None, *оценки, текст, сделка, статус, флаги, "buyer"
    )  # fmt: skip
    assert база["companies"][1][0] == "target"
    assert (база["companies"][1][1], база["companies"][1][2]) == рейтинг
    assert база["companies"][1][4] is True

    if статус == "published":
        заголовок = f"Компания «Покупатель» оставила отзыв: {оценки[0]} из 5"
        тон = "success" if оценки[0] >= 4 else "warning"

        assert сессия(итог)["success"] == ОПУБЛИКОВАН
        assert база["notifications"] == [
            (учётка("target@savdex.uz"), "review", заголовок, текст, тон, "/cabinet/reviews")
        ]
        assert база["events"] == [(target, "review", тон, заголовок, "/cabinet/reviews")]
    else:
        assert сессия(итог)["success"] == на_проверку(флаги)
        assert база["notifications"] == база["events"] == []

    # Журнал — только действия администратора
    if admin:
        assert база["journal"][0][:4] == ("created", "reviews", "App\\Models\\Review", "Review #4")
    else:
        assert база["journal"] == []


@pytest.mark.parametrize(
    ("премодерация", "статус"),
    # Нет настройки — премодерация включена
    [(True, "moderation"), ("1", "moderation"), (0, "published"), ("", "published"),
     (None, "moderation")],
)  # fmt: skip
def test_премодерация(сайт, премодерация, статус):
    итог = отправить(
        сайт,
        "/en/company/target/review",
        сброс(премодерация=премодерация, чужие=()),
        снимок,
        uid=покупатель(admin=True),
        body={"rating": 3, "body": ТЕКСТ},
        headers=inertia(),
    )
    база = итог["база"]

    assert итог["ответ"]["headers"]["location"] == сайт + "/en/cabinet/settings"
    assert [r[12] for r in база["reviews"]] == [статус]

    if статус == "published":
        assert сессия(итог)["success"] == (
            "The review is published. The company has been notified and can reply."
        )
        # Единственный отзыв: (5 × 3 + 3) / 6
        assert база["companies"][1][1:3] == ("3.00", 1)
        assert len(база["notifications"]) == 1
    else:
        assert сессия(итог)["success"].startswith("The review has been sent for checking.")
        assert база["companies"][1][1:3] == ("0.00", 0)
        assert база["notifications"] == []


@pytest.mark.parametrize(
    ("случай", "ошибка"),
    [
        (
            "не раскрыт",
            "Отзыв можно оставить только после раскрытия контактов: так на площадке нет "
            "отзывов от тех, кто с компанией не работал.",
        ),
        (
            "на проверке",
            "Ваш отзыв на проверке — он появится здесь, когда модератор его посмотрит.",
        ),
        ("скрыт", "Ваш отзыв не прошёл проверку. Причина — в уведомлениях."),
        ("опубликован", "Вы уже оставляли отзыв этой компании."),
        ("своя", "Это ваша компания."),
        ("без компании", "Отзывы оставляют от имени компании — заполните её данные в кабинете."),
        ("компания заблокирована", "Ваша учётная запись заблокирована."),
        ("нет такой", None),
    ],
)
def test_отказ(сайт, случай, ошибка):
    uid = покупатель(company=случай != "без компании")
    свой = {"на проверке": "moderation", "скрыт": "hidden", "опубликован": "published"}.get(случай)
    подготовка = сброс(
        раскрыт=случай != "не раскрыт",
        свой=свой,
        блок=случай == "компания заблокирована",
    )
    slug = {"своя": "buyer", "нет такой": "missing"}.get(случай, "target")
    итог = отправить(
        сайт,
        f"/company/{slug}/review",
        подготовка,
        снимок,
        uid=uid,
        body={"rating": 5, "body": ТЕКСТ},
        headers=inertia(),
    )
    база = итог["база"]

    if ошибка is None:
        assert итог["ответ"]["status"] == 404
    else:
        assert итог["ответ"]["status"] == 302
        assert сессия(итог)["error"] == ошибка

    # Ничего не записано: только чужие отзывы и прежний свой
    assert len(база["reviews"]) == 3 + (свой is not None)
    assert база["companies"][1][1:3] == ("4.50", 1)
    assert база["notifications"] == база["events"] == []


def test_почта(сайт):
    uid = покупатель()
    sql("update users set email_verified_at = null where id = %s", [uid])

    try:
        итог = отправить(
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

    # Неподтверждённая почта — на подтверждение, отзыв не принят
    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
    assert len(итог["база"]["reviews"]) == 3


#: Текст → причины автопроверки
ТЕКСТЫ = [
    (ТЕКСТ, []),
    ("звоните 90 123 45 67", [КОНТАКТЫ]),
    # Номер стандарта и сумма — не телефон
    ("ГОСТ 34028-2016", []),
    ("цена 12 000 000 сум", []),
    ("998901234567", [КОНТАКТЫ]),
    ("+ 7 (495) 1234567", [КОНТАКТЫ]),
    ("пишите в t.me/cement", [КОНТАКТЫ]),
    ("мой ник @cement_uz", [КОНТАКТЫ]),
    ("почта Sale@Cement.UZ", [КОНТАКТЫ]),
    ("www.cement.uz", [КОНТАКТЫ]),
    ("ХОРОШИЙ ПОСТАВЩИК ВСЕМ СОВЕТУЮ ОЧЕНЬ", [КРИК]),
    # Заглавные лишь отчасти — не крик
    ("ХОРОШИЙ ПОСТАВЩИК всем советую очень", []),
    # Брань латиницей, через дефисы и с «ё»
    ("cyka", [БРАНЬ]),
    ("С-у-К-а", [БРАНЬ]),
    ("долбоёб", [БРАНЬ]),
    ("ПИЗДЕЦ ПОЛНЫЙ ПОСТАВЩИК ОБМАНУЛ СОВСЕМ", [БРАНЬ, КРИК]),
    # Цифры любой письменности — тоже номер
    ("١٢٣٤٥٦٧٨٩٠ арабские цифры", [КОНТАКТЫ]),
    ("", []),
]


@pytest.mark.parametrize(("текст", "причины"), ТЕКСТЫ)
def test_автопроверка(текст, причины):
    """review_screening.reasons: контакты, брань, крик."""
    assert review_screening.reasons(текст) == причины
