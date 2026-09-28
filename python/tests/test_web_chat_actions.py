"""
Чат на Django неотличим от Laravel: сообщение в разговор (маскировка
контактов, уведомление собеседнику только о первом непрочитанном,
проверка ввода, чужой разговор — 404, неподтверждённая почта — на
подтверждение), отклик на объявление (новый разговор тратит отклик
тарифа, повторный — нет; лимит, нулевой лимит, безлимит; своё, снятое,
удалённое объявление; без компании) и на IT-задачу (роль исполнителя,
закрытая задача, счётчик откликов и журнал администратора).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_forms import xsrf, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "$s = App\\Models\\Company::factory()->create(['slug' => 'seller',"
        " 'name' => 'Цемент Трейд']);"
        "$b = App\\Models\\Company::factory()->create(['slug' => 'buyer', 'name' => 'Стройка Плюс',"
        " 'is_it_provider' => true]);"
        "$gone = App\\Models\\Company::factory()->create(['slug' => 'gone']);"
        "App\\Models\\Company::factory()->create(['slug' => 'third']);"
        "foreach (['active' => 'cement', 'archived' => 'old'] as $st => $slug) {"
        " App\\Models\\Listing::factory()->create(['company_id' => $s->id, 'status' => $st,"
        " 'slug' => $slug, 'title' => 'Цемент', 'description' => 'Мешки по 50 кг']); }"
        "App\\Models\\Listing::factory()->create(['company_id' => $b->id, 'status' => 'active',"
        " 'slug' => 'own', 'title' => 'Свой', 'description' => 'Своё']);"
        "App\\Models\\Listing::factory()->create(['company_id' => $gone->id, 'status' => 'active',"
        " 'slug' => 'orphan', 'title' => 'Ничей', 'description' => 'Ничей']);"
        "App\\Models\\Listing::factory()->create(['company_id' => $s->id, 'status' => 'active',"
        " 'slug' => 'deleted', 'title' => 'Удалён', 'description' => 'Удалён'])->delete();"
        "$gone->delete();"
        "foreach (['active' => 'site', 'closed' => 'closed-site'] as $st => $slug) {"
        " App\\Models\\ItTask::factory()->create(['company_id' => $s->id, 'status' => $st,"
        " 'slug' => $slug, 'title' => 'Сайт магазина']); }"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def _объявление(slug: str) -> int:
    return int(sql("select id from listings where slug = %s", [slug])[0][0])


def _задача(slug: str) -> int:
    return int(sql("select id from it_tasks where slug = %s", [slug])[0][0])


def покупатель(**поля: Any) -> int:
    return учётка(
        "buyer@savdex.uz",
        **{
            "company_id": _компания("buyer"),
            "email_verified_at": "2026-09-01 10:00:00",
            **поля,
        },
    )


def продавец() -> int:
    return учётка(
        "seller@savdex.uz", company_id=_компания("seller"), email_verified_at="2026-09-01 10:00:00"
    )


def сброс(
    *,
    разговор: bool = True,
    непрочитано: bool = False,
    лимит: int | None = 5,
    потрачено: int | None = None,
    задача: bool = False,
) -> Callable[[], None]:
    """Подготовка: разговор покупателя с продавцом, квота тарифа Free, кошелёк."""

    def run() -> None:
        продавец()
        for table in (
            "messages",
            "message_threads",
            "wallets",
            "activity_events",
            "user_notifications",
        ):
            sql(f"delete from {table}")
            sql(f"select setval('{table}_id_seq', 1, false)")

        sql("delete from admin_actions where section = 'ittasks'")
        sql("update it_tasks set responses_count = 0, updated_at = now() - interval '1 day'")
        sql("update plans set responses_limit = %s where code = 'free'", [лимит])

        if потрачено is not None:
            sql(
                "insert into wallets (company_id, responses_used_this_period, created_at, "
                "updated_at) values (%s, %s, now() - interval '1 day', now() - interval '1 day')",
                [_компания("buyer"), потрачено],
            )

        if разговор:
            column, subject = (
                ("it_task_id", _задача("site")) if задача else ("listing_id", _объявление("cement"))
            )
            sql(
                f"insert into message_threads ({column}, buyer_company_id, seller_company_id, "
                "seller_read_at, created_at, updated_at) values (%s, %s, %s, "
                "now() - interval '2 hour', now() - interval '1 day', now() - interval '1 day')",
                [subject, _компания("buyer"), _компания("seller")],
            )
            sql(
                "insert into messages (thread_id, company_id, user_id, body, created_at, "
                "updated_at) values (1, %s, %s, 'Здравствуйте', %s, %s)",
                [
                    _компания("buyer"),
                    int(sql("select id from users where email = 'buyer@savdex.uz'")[0][0]),
                    *(
                        ["2026-09-28 00:00:00", "2026-09-28 00:00:00"]
                        if непрочитано
                        else ["2026-01-01 00:00:00", "2026-01-01 00:00:00"]
                    ),
                ],
            )
            # Непрочитанное у продавца — сообщение позже его отметки прочтения
            if непрочитано:
                sql("update message_threads set seller_read_at = '2026-01-01 00:00:00'")

    return run


def снимок() -> Any:
    журнал = [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions "
            "where section = 'ittasks' order by id"
        )
    ]

    return {
        "messages": sql("select thread_id, company_id, user_id, body from messages order by id"),
        "threads": sql(
            "select id, listing_id, it_task_id, buyer_company_id, seller_company_id, "
            "last_message_at is not null, buyer_read_at > now() - interval '1 hour', "
            "seller_read_at > now() - interval '1 hour', updated_at > now() - interval '1 hour' "
            "from message_threads order by id"
        ),
        "wallets": sql(
            "select company_id, responses_used_this_period, credits, "
            "updated_at > now() - interval '1 hour' from wallets order by id"
        ),
        "tasks": sql(
            "select responses_count, updated_at > now() - interval '1 hour' from it_tasks "
            "order by id"
        ),
        "events": sql(
            "select company_id, type, tone, message, url from activity_events order by id"
        ),
        "notifications": sql(
            "select user_id, company_id, type, title, body, tone, url from user_notifications "
            "order by id"
        ),
        "journal": журнал,
    }


ТЕКСТ = "Пишите на sale@cement.uz или @cement_trade, звоните +998 (90) 111-22-33, цена 1 200 000"


# ── Сообщение в разговор ────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"body": ТЕКСТ},
        {"body": "  Есть ли доставка?  "},
        {"body": "价格" * 70},
        {"body": "https://savdex.uz/catalog www.site.uz t.me/savdex"},
        {},
        {"body": "   "},
        {"body": "x" * 2001},
        {"body": ["массив"]},
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_сообщение(сайт, body, prefix):
    итог = отправить(
        сайт, f"{prefix}/cabinet/chats/1", сброс(), снимок, uid=покупатель(), body=body
    )

    if body.get("body") == ТЕКСТ:
        assert итог["база"]["messages"][-1][3] == (
            "Пишите на [•••] или [•••], звоните [•••], цена 1 200 000"
        )
        assert итог["база"]["notifications"]


def test_сообщение_при_непрочитанном(сайт):
    итог = отправить(
        сайт,
        "/cabinet/chats/1",
        сброс(непрочитано=True),
        снимок,
        uid=покупатель(),
        body={"body": "Ещё вопрос"},
    )

    assert not итог["база"]["notifications"]


def test_сообщение_продавца(сайт):
    итог = отправить(
        сайт, "/cabinet/chats/1", сброс(), снимок, uid=продавец(), body={"body": "Доставляем"}
    )

    assert итог["база"]["notifications"]


@pytest.mark.parametrize("path", ["/cabinet/chats/1", "/cabinet/chats/999"])
def test_чужой_разговор_404(сайт, path):
    чужой = учётка(
        "stranger@savdex.uz",
        company_id=_компания("third"),
        email_verified_at="2026-09-01 10:00:00",
    )
    итог = отправить(сайт, path, сброс(), снимок, uid=чужой, body={"body": "Привет"})

    assert итог["ответ"]["status"] == 404


@pytest.mark.parametrize(
    "path", ["/cabinet/chats/1", "/listing/1/respond", "/it-services/1/respond"]
)
@pytest.mark.parametrize("headers", [None, {"Accept": "application/json", "X-XSRF-TOKEN": xsrf()}])
def test_почта_не_подтверждена(сайт, path, headers):
    итог = отправить(
        сайт,
        path,
        сброс(),
        снимок,
        uid=покупатель(email_verified_at=None),
        body={"body": "Привет"},
        headers=headers,
    )

    assert итог["ответ"]["status"] in (302, 403)


# ── Отклик на объявление ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("slug", "подготовка"),
    [
        ("cement", {"разговор": False}),
        ("cement", {"разговор": False, "потрачено": 2}),
        ("cement", {"разговор": False, "потрачено": 5}),
        ("cement", {"разговор": False, "лимит": 0}),
        ("cement", {"разговор": False, "лимит": None}),
        ("cement", {"разговор": True, "потрачено": 5}),
        ("old", {"разговор": False}),
        ("own", {"разговор": False}),
        ("orphan", {"разговор": False}),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_отклик(сайт, slug, подготовка, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/listing/{_объявление(slug)}/respond",
        сброс(**подготовка),
        снимок,
        uid=покупатель(),
        body={"body": ТЕКСТ},
    )
    новый = slug == "cement" and not подготовка["разговор"] and подготовка.get("лимит", 5)

    if новый and подготовка.get("потрачено", 0) < 5:
        assert итог["база"]["wallets"][0][1] == подготовка.get("потрачено", 0) + 1
        assert итог["ответ"]["headers"]["location"].endswith("/cabinet/chats/1")


@pytest.mark.parametrize("body", [{}, {"body": "x" * 2001}])
def test_отклик_ошибки(сайт, body):
    отправить(
        сайт,
        f"/listing/{_объявление('cement')}/respond",
        сброс(разговор=False),
        снимок,
        uid=покупатель(),
        body=body,
    )


def test_отклик_на_удалённое_404(сайт):
    итог = отправить(
        сайт,
        f"/listing/{_объявление('deleted')}/respond",
        сброс(разговор=False),
        снимок,
        uid=покупатель(),
        body={"body": ТЕКСТ},
    )

    assert итог["ответ"]["status"] == 404


def test_отклик_без_компании(сайт):
    uid = учётка("nocompany@savdex.uz", company_id=None, email_verified_at="2026-09-01 10:00:00")
    отправить(
        сайт,
        f"/listing/{_объявление('cement')}/respond",
        сброс(разговор=False),
        снимок,
        uid=uid,
        body={"body": ТЕКСТ},
    )


# ── Отклик на IT-задачу ─────────────────────────────────────────────


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize(
    ("slug", "подготовка", "исполнитель"),
    [
        ("site", {"разговор": False}, True),
        ("site", {"разговор": True, "задача": True}, True),
        ("site", {"разговор": False, "потрачено": 5}, True),
        ("site", {"разговор": False}, False),
        ("closed-site", {"разговор": False}, True),
    ],
)
def test_отклик_на_задачу(сайт, slug, подготовка, исполнитель, admin):
    sql("update companies set is_it_provider = %s where slug = 'buyer'", [исполнитель])
    итог = отправить(
        сайт,
        f"/it-services/{_задача(slug)}/respond",
        сброс(**подготовка),
        снимок,
        uid=покупатель(is_admin=admin),
        body={"body": "Сделаю за неделю"},
    )
    новый = (
        исполнитель
        and slug == "site"
        and not подготовка.get("разговор")
        and not подготовка.get("потрачено")
    )

    assert bool(итог["база"]["journal"]) is (новый and admin)
