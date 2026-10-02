"""
Чат на Django: сообщение в разговор (маскировка
контактов, уведомление собеседнику только о первом непрочитанном,
проверка ввода, чужой разговор — 404, неподтверждённая почта — на
подтверждение), отклик на объявление (новый разговор тратит отклик
тарифа, повторный — нет; лимит, нулевой лимит, безлимит; своё, снятое,
удалённое объявление; без компании) и на IT-задачу (роль исполнителя,
закрытая задача, счётчик откликов и журнал администратора).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import Выражение, it_задача, компания, объявление
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .test_web_forms import xsrf, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (PlanSeeder).
    """
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"seeds.seed(data={{k: v if k in {list(таблицы)!r} else [] for k, v in data.items()}})"
    )
    subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            # Справочники заводит владелец базы, как миграции
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        check=True,
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники("plans")
    s = компания(slug="seller", name="Цемент Трейд")
    b = компания(slug="buyer", name="Стройка Плюс", is_it_provider=True)
    gone = компания(slug="gone")
    компания(slug="third")

    for status, slug in (("active", "cement"), ("archived", "old")):
        объявление(
            company_id=s, status=status, slug=slug, title="Цемент", description="Мешки по 50 кг"
        )

    объявление(company_id=b, status="active", slug="own", title="Свой", description="Своё")
    объявление(company_id=gone, status="active", slug="orphan", title="Ничей", description="Ничей")
    # Удалённые (SoftDeletes): объявление и компания, чьё объявление осталось
    объявление(
        company_id=s,
        status="active",
        slug="deleted",
        title="Удалён",
        description="Удалён",
        deleted_at=Выражение("now()"),
    )
    sql("update companies set deleted_at = now() where id = %s", [gone])

    for status, slug in (("active", "site"), ("closed", "closed-site")):
        it_задача(company_id=s, status=status, slug=slug, title="Сайт магазина")

    with адрес() as root:
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


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    """Ошибки проверки из сессии после ответа (пусто — ошибок нет)."""
    payload = json.loads(итог["сессия"]["payload"])

    return dict(payload.get("errors", {}).get("default", {}).get("messages", {}))


ТЕКСТ = "Пишите на sale@cement.uz или @cement_trade, звоните +998 (90) 111-22-33, цена 1 200 000"


# ── Сообщение в разговор ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("body", "записано", "ошибка"),
    [
        # Контакты в тексте скрыты, цифры цены — нет
        ({"body": ТЕКСТ}, "Пишите на [•••] или [•••], звоните [•••], цена 1 200 000", None),
        ({"body": "  Есть ли доставка?  "}, "Есть ли доставка?", None),
        ({"body": "价格" * 70}, "价格" * 70, None),
        ({"body": "https://savdex.uz/catalog www.site.uz t.me/savdex"}, "[•••] [•••] [•••]", None),
        ({}, None, ("Введите сообщение", "Enter a message")),
        ({"body": "   "}, None, ("Введите сообщение", "Enter a message")),
        ({"body": "x" * 2001}, None, ("Сообщение слишком длинное", "The message is too long")),
        ({"body": ["массив"]}, None, ("Укажите текст.", "The body field must be a string.")),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_сообщение(сайт, body, записано, ошибка, prefix):
    итог = отправить(
        сайт, f"{prefix}/cabinet/chats/1", сброс(), снимок, uid=покупатель(), body=body
    )
    база = итог["база"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"].endswith(f"{prefix}/cabinet/settings")

    if ошибка is None:
        assert ошибки(итог) == {}
        assert база["messages"][-1] == (1, _компания("buyer"), покупатель(), записано)
        # Разговор: последнее сообщение, прочитан покупателем, тронут
        assert база["threads"][0][5:] == (True, True, False, True)
        # Продавцу — уведомление и событие ленты о первом непрочитанном
        assert len(база["notifications"]) == 1 and len(база["events"]) == 1
    else:
        assert ошибки(итог) == {"body": [ошибка[1 if prefix else 0]]}
        assert [m[3] for m in база["messages"]] == ["Здравствуйте"]
        assert not база["notifications"] and not база["events"]


def test_сообщение_при_непрочитанном(сайт):
    итог = отправить(
        сайт,
        "/cabinet/chats/1",
        сброс(непрочитано=True),
        снимок,
        uid=покупатель(),
        body={"body": "Ещё вопрос"},
    )

    assert [m[3] for m in итог["база"]["messages"]] == ["Здравствуйте", "Ещё вопрос"]
    # Продавец ещё не прочёл прошлое — второй раз не уведомляют
    assert not итог["база"]["notifications"] and not итог["база"]["events"]


def test_сообщение_продавца(сайт):
    итог = отправить(
        сайт, "/cabinet/chats/1", сброс(), снимок, uid=продавец(), body={"body": "Доставляем"}
    )

    assert итог["база"]["messages"][-1] == (1, _компания("seller"), продавец(), "Доставляем")
    # Прочёл продавец, уведомлён покупатель
    assert итог["база"]["threads"][0][5:] == (True, None, True, True)
    [уведомление] = итог["база"]["notifications"]
    assert уведомление[0] == покупатель() and уведомление[1] == _компания("buyer")


@pytest.mark.parametrize("path", ["/cabinet/chats/1", "/cabinet/chats/999"])
def test_чужой_разговор_404(сайт, path):
    чужой = учётка(
        "stranger@savdex.uz",
        company_id=_компания("third"),
        email_verified_at="2026-09-01 10:00:00",
    )
    итог = отправить(сайт, path, сброс(), снимок, uid=чужой, body={"body": "Привет"})

    assert итог["ответ"]["status"] == 404
    assert [m[3] for m in итог["база"]["messages"]] == ["Здравствуйте"]


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

    if headers is None:
        assert итог["ответ"]["status"] == 302
        assert итог["ответ"]["headers"]["location"].endswith("/verify-email")
    else:
        # Запрос JSON — отказ, а не переход
        assert итог["ответ"]["status"] == 403

    assert [m[3] for m in итог["база"]["messages"]] == ["Здравствуйте"]
    assert not итог["база"]["wallets"]


# ── Отклик на объявление ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("slug", "подготовка", "ошибка"),
    [
        ("cement", {"разговор": False}, None),
        ("cement", {"разговор": False, "потрачено": 2}, None),
        ("cement", {"разговор": False, "потрачено": 5}, "Лимит откликов на этот месяц исчерпан"),
        ("cement", {"разговор": False, "лимит": 0}, "Ваш тариф не включает отклики"),
        ("cement", {"разговор": False, "лимит": None}, None),
        # Разговор уже есть — отклик не тратится и при исчерпанном лимите
        ("cement", {"разговор": True, "потрачено": 5}, None),
        ("old", {"разговор": False}, "Объявление снято с публикации"),
        ("own", {"разговор": False}, "Это ваше объявление"),
        ("orphan", {"разговор": False}, "Объявление больше не доступно"),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_отклик(сайт, slug, подготовка, ошибка, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/listing/{_объявление(slug)}/respond",
        сброс(**подготовка),
        снимок,
        uid=покупатель(),
        body={"body": ТЕКСТ},
    )
    база = итог["база"]
    потрачено = подготовка.get("потрачено")

    assert итог["ответ"]["status"] == 302

    if ошибка is None:
        assert итог["ответ"]["headers"]["location"].endswith(f"{prefix}/cabinet/chats/1")
        assert ошибки(итог) == {}
        assert база["messages"][-1][3] == (
            "Пишите на [•••] или [•••], звоните [•••], цена 1 200 000"
        )
        assert [t[1:5] for t in база["threads"]] == [
            (_объявление("cement"), None, _компания("buyer"), _компания("seller"))
        ]
        assert len(база["notifications"]) == 1

        if подготовка["разговор"] or подготовка.get("лимит", 5) is None:
            # Повторный отклик и безлимит отклик не тратят
            assert [w[1] for w in база["wallets"]] == ([потрачено] if потрачено else [])
        else:
            assert [w[1] for w in база["wallets"]] == [(потрачено or 0) + 1]
    else:
        assert итог["ответ"]["headers"]["location"].endswith(f"{prefix}/cabinet/settings")
        [текст] = ошибки(итог)["body"]

        if not prefix:
            assert текст.startswith(ошибка), текст

        assert not база["messages"] and not база["threads"]
        assert [w[1] for w in база["wallets"]] == ([потрачено] if потрачено else [])


@pytest.mark.parametrize(
    ("body", "ошибка"),
    [({}, "Напишите, что вас интересует"), ({"body": "x" * 2001}, "Сообщение слишком длинное")],
)
def test_отклик_ошибки(сайт, body, ошибка):
    итог = отправить(
        сайт,
        f"/listing/{_объявление('cement')}/respond",
        сброс(разговор=False),
        снимок,
        uid=покупатель(),
        body=body,
    )

    assert итог["ответ"]["status"] == 302
    assert ошибки(итог) == {"body": [ошибка]}
    assert not итог["база"]["threads"] and not итог["база"]["wallets"]


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
    assert not итог["база"]["threads"]


def test_отклик_без_компании(сайт):
    uid = учётка("nocompany@savdex.uz", company_id=None, email_verified_at="2026-09-01 10:00:00")
    итог = отправить(
        сайт,
        f"/listing/{_объявление('cement')}/respond",
        сброс(разговор=False),
        снимок,
        uid=uid,
        body={"body": ТЕКСТ},
    )

    assert итог["ответ"]["status"] == 302
    assert ошибки(итог) == {
        "body": ["Сначала заполните данные компании — отклик отправляется от её имени"]
    }
    assert not итог["база"]["threads"] and not итог["база"]["messages"]


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

    база = итог["база"]
    принят = исполнитель and slug == "site" and not подготовка.get("потрачено")

    assert bool(база["journal"]) is (новый and admin)
    assert итог["ответ"]["status"] == 302

    if принят:
        assert итог["ответ"]["headers"]["location"].endswith("/cabinet/chats/1")
        assert база["messages"][-1][3] == "Сделаю за неделю"
        assert [t[1:3] for t in база["threads"]] == [(None, _задача("site"))]
        # Новый отклик: счётчик задачи и потраченный отклик тарифа
        assert база["tasks"][0] == ((1, True) if новый else (0, False))
        assert [w[1] for w in база["wallets"]] == ([1] if новый else [])
    else:
        assert ошибки(итог)["body"], ошибки(итог)
        assert not база["messages"] and база["tasks"][0] == (0, False)
