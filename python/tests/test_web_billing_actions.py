"""
Этап 7, шаг 53: формы кассы на Django — отмена и включение
автопродления, отвязка карты, отказ от счёта.

Нет подписки — 404; включить можно только оплаченную; основную карту
при автопродлении не отвязать; чужая карта и чужой или уже оплаченный
счёт — 404; отменённый счёт возвращает скидочный промокод, если по нему
нет живой карточной транзакции. У администратора — строка журнала.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import компания
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    # Тарифы, как при деплое (вместо PlanSeeder) — под владельцем базы
    subprocess.run(
        [sys.executable, "manage.py", "seed"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        check=True,
        capture_output=True,
    )
    компания(slug="mine")
    компания(slug="other")

    with адрес() as root:
        yield root


def _id(table: str, where: str) -> int:
    return int(sql(f"select id from {table} where {where}")[0][0])


def владелец(admin: bool = False) -> int:
    return учётка("owner@savdex.uz", company_id=_id("companies", "slug = 'mine'"), is_admin=admin)


def сброс(
    *,
    подписка: str | None = "payment",
    автопродление: bool = True,
    конец: str | None = "now() + interval '20 days'",
    промокод: bool = False,
    транзакция: str | None = None,
) -> Callable[[], None]:
    def run() -> None:
        # Номера с единицы: карта и счёт в адресе — предсказуемые
        sql(
            "truncate payment_transactions, payments, promo_codes, payment_methods, "
            "subscriptions, admin_actions restart identity cascade"
        )
        # Язык из адреса (/en/…) правит учётку — каждый раз заново
        sql("update users set locale = 'ru'")

        mine = _id("companies", "slug = 'mine'")
        other = _id("companies", "slug = 'other'")
        plan = _id("plans", "code = 'business'")

        if подписка is not None:
            sql(
                "insert into subscriptions (company_id, plan_id, status, source, auto_renew, "
                "started_at, ends_at, created_at, updated_at) values (%s, %s, 'active', %s, %s, "
                f"now() - interval '10 days', {конец or 'null'}, now() - interval '10 days', "
                "now() - interval '10 days')",
                [mine, plan, подписка, автопродление],
            )

        for company, token, default in ((mine, "a", True), (mine, "b", False), (other, "c", True)):
            sql(
                "insert into payment_methods (company_id, provider, token, brand, last4, "
                "is_default, created_at, updated_at) values (%s, 'uzum', %s, 'Humo', '1234', "
                "%s, now(), now())",
                [company, token, default],
            )

        code = None

        if промокод:
            sql(
                "insert into promo_codes (code, plan_id, days, discount_percent, used_at, "
                "used_by_company_id, created_at, updated_at) values ('SALE20', %s, 30, 20, "
                "now(), %s, now() - interval '1 day', now() - interval '1 day')",
                [plan, mine],
            )
            code = _id("promo_codes", "code = 'SALE20'")

        for company, number, status in (
            (mine, "SVX-1", "pending"),
            (mine, "SVX-2", "paid"),
            (other, "SVX-3", "pending"),
        ):
            sql(
                "insert into payments (company_id, purpose, description, amount, currency, "
                "status, number, promo_code_id, admin_note, created_at, updated_at) values "
                "(%s, 'plan', 'Тариф', 1000000, 'UZS', %s, %s, %s, 'заметка', "
                "now() - interval '2 days', now() - interval '2 days')",
                [company, status, number, code if number == "SVX-1" else None],
            )

        if транзакция is not None:
            sql(
                "insert into payment_transactions (payment_id, provider, provider_transaction_id, "
                "state, amount_minor, created_at, updated_at) values (%s, 'uzum', 'T1', "
                "'created', 100000000, "
                f"{транзакция}, {транзакция})",
                [_id("payments", "number = 'SVX-1'")],
            )

    return run


def снимок() -> Any:
    return {
        "subscriptions": sql(
            "select auto_renew, cancelled_at is not null, "
            "cancelled_at > now() - interval '1 minute', updated_at > now() - interval '1 minute' "
            "from subscriptions order by id"
        ),
        "cards": sql("select token from payment_methods order by id"),
        "payments": sql(
            "select number, status, confirmed_by, admin_note, "
            "updated_at > now() - interval '1 minute' from payments order by id"
        ),
        "promo": sql(
            "select used_at is null, used_by_company_id, used_by_user_id, "
            "updated_at > now() - interval '1 minute' from promo_codes order by id"
        ),
        "journal": sql(
            "select action, section, subject_type, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g') "
            "from admin_actions order by id"
        ),
    }


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


def _журнал(итог: dict[str, Any]) -> list[tuple[str, str]]:
    """Журнал администратора: (раздел, правка) без смены языка учётки."""
    return [(section, changes) for _, section, _, _, changes in итог["база"]["journal"]]


ЯЗЫК = {
    "en": '{"before":{"locale":"ru"},"after":{"locale":"en"}}',
    "uz": '{"before":{"locale":"ru"},"after":{"locale":"uz"}}',
}


@pytest.mark.parametrize(
    ("подготовка", "ждём"),
    [
        # ждём: правка в журнале — или None, когда подписки нет / она истекла (404)
        ({}, '{"before":{"auto_renew":true,"cancelled_at":null},"after":{"auto_renew":false,'
             '"cancelled_at":"T"}}'),
        # Автопродление уже выключено — отмечается только отмена
        ({"автопродление": False}, '{"before":{"cancelled_at":null},"after":{"cancelled_at":"T"}}'),
        ({"конец": None}, '{"before":{"auto_renew":true,"cancelled_at":null},"after":{'
                          '"auto_renew":false,"cancelled_at":"T"}}'),
        ({"подписка": None}, None),
        ({"конец": "now() - interval '1 day'"}, None),
    ],
)  # fmt: skip
@pytest.mark.parametrize("admin", [False, True])
def test_отмена_автопродления(сайт, подготовка, ждём, admin):
    итог = отправить(
        сайт, "/cabinet/billing/cancel", сброс(**подготовка), снимок, uid=владелец(admin)
    )
    подписки = итог["база"]["subscriptions"]

    if ждём is None:
        assert итог["ответ"]["status"] == 404
        assert подписки in ([], [(True, False, None, False)])
        assert итог["база"]["journal"] == []

        return

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
    # Выключено и отменено сейчас
    assert подписки == [(False, True, True, True)]

    if подготовка.get("конец", "") is None:
        assert _сессия(итог)["success"] == "Автопродление отключено."
    else:
        [(до,)] = sql(
            "select to_char(ends_at at time zone 'Asia/Tashkent', 'DD.MM.YYYY') from subscriptions"
        )
        assert _сессия(итог)["success"] == f"Автопродление отключено. Тариф действует до {до}."

    assert _журнал(итог) == ([("subscriptions", ждём)] if admin else [])


@pytest.mark.parametrize(
    ("подготовка", "ждём"),
    [
        # ждём: (сообщение, правилась ли подписка) — или None (404)
        ({"автопродление": False}, ("success", True)),
        # Уже включено — строка не трогается
        ({}, ("success", False)),
        # Тариф без оплаты продлевать нечем
        ({"подписка": "promo"}, ("warning", False)),
        ({"подписка": "manual"}, ("warning", False)),
        ({"подписка": None}, None),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_включение_автопродления(сайт, подготовка, ждём, admin):
    итог = отправить(
        сайт, "/en/cabinet/billing/resume", сброс(**подготовка), снимок, uid=владелец(admin)
    )
    # Язык из адреса сотрудник тоже записывает в журнал
    журнал = [("users", ЯЗЫК["en"])] if admin else []

    if ждём is None:
        assert итог["ответ"]["status"] == 404
        assert итог["база"]["subscriptions"] == []
        assert _журнал(итог) == журнал

        return

    вид, правка = ждём
    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/en/cabinet/settings"
    assert _сессия(итог)[вид] == (
        "Auto-renewal is on"
        if вид == "success"
        else "This plan was granted without payment — there is nothing to renew. "
        "Issue an invoice when the period ends."
    )
    assert итог["база"]["subscriptions"] == [(True, False, None, правка)]

    if admin and правка:
        журнал.append(("subscriptions", '{"before":{"auto_renew":false},"after":{"auto_renew":true}}'))

    assert _журнал(итог) == журнал


def _карта(token: str) -> int:
    return _id("payment_methods", f"token = '{token}'")


@pytest.mark.parametrize(
    ("карта", "подготовка", "ждём"),
    [
        # ждём: карты после — или None (404: чужая или нет такой)
        ("a", {}, ["a", "b", "c"]),
        ("a", {"автопродление": False}, ["b", "c"]),
        ("a", {"подписка": None}, ["b", "c"]),
        ("b", {}, ["a", "c"]),
        ("c", {}, None),
        (None, {}, None),
    ],
)
def test_отвязка_карты(сайт, карта, подготовка, ждём):
    сброс(**подготовка)()
    номер = _карта(карта) if карта else 999999
    итог = отправить(
        сайт,
        f"/cabinet/billing/card/{номер}",
        сброс(**подготовка),
        снимок,
        uid=владелец(),
        method="DELETE",
    )
    карты = [token for (token,) in итог["база"]["cards"]]

    if ждём is None:
        assert итог["ответ"]["status"] == 404
        assert карты == ["a", "b", "c"]

        return

    # Inertia: DELETE, ответивший переходом, — 303
    assert итог["ответ"]["status"] == 303
    assert карты == ждём

    if карты == ["a", "b", "c"]:
        # Основная карта при автопродлении остаётся
        assert _сессия(итог)["error"] == (
            "Это основная карта, по ней идёт автопродление. Сначала привяжите другую "
            "или отключите автопродление."
        )
    else:
        assert _сессия(итог)["success"] == "Карта отвязана"


def _счёт(number: str) -> int:
    return _id("payments", f"number = '{number}'")


ОТМЕНЁН = [
    ("SVX-1", "failed", None, None, True),
    ("SVX-2", "paid", None, "заметка", False),
    ("SVX-3", "pending", None, "заметка", False),
]
НЕ_ТРОНУТЫ = [
    ("SVX-1", "pending", None, "заметка", False),
    ("SVX-2", "paid", None, "заметка", False),
    ("SVX-3", "pending", None, "заметка", False),
]


@pytest.mark.parametrize(
    ("счёт", "подготовка", "промокод"),
    [
        # промокод после отмены: (свободен, кем занят, правился) — или [] без него
        ("SVX-1", {}, []),
        ("SVX-1", {"промокод": True}, [(True, None, None, True)]),
        # Живая карточная транзакция (свежее часа) держит промокод занятым
        (
            "SVX-1",
            {"промокод": True, "транзакция": "now() - interval '5 minutes'"},
            [(False, 1, None, False)],
        ),
        (
            "SVX-1",
            {"промокод": True, "транзакция": "now() - interval '2 hours'"},
            [(True, None, None, True)],
        ),
        # Оплаченный, чужой и несуществующий — 404
        ("SVX-2", {}, None),
        ("SVX-3", {}, None),
        (None, {}, None),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_отказ_от_счёта(сайт, счёт, подготовка, промокод, admin):
    сброс(**подготовка)()
    номер = _счёт(счёт) if счёт else 999999
    итог = отправить(
        сайт,
        f"/uz/cabinet/billing/invoice/{номер}/cancel",
        сброс(**подготовка),
        снимок,
        uid=владелец(admin),
        headers=inertia(),
    )
    журнал = [("users", ЯЗЫК["uz"])] if admin else []

    if промокод is None:
        assert итог["ответ"]["status"] == 404
        assert итог["база"]["payments"] == НЕ_ТРОНУТЫ
        assert _журнал(итог) == журнал

        return

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/uz/cabinet/settings"
    assert _сессия(итог)["success"] == "SVX-1 hisob-fakturasi bekor qilindi"
    # Счёт — «не оплачен», заметка администратора снята
    assert итог["база"]["payments"] == ОТМЕНЁН
    assert итог["база"]["promo"] == промокод

    if admin:
        журнал.append(
            (
                "payments",
                '{"before":{"status":"pending","admin_note":"\\u0437\\u0430\\u043c\\u0435'
                '\\u0442\\u043a\\u0430"},"after":{"status":"failed","admin_note":null}}',
            )
        )

    assert _журнал(итог) == журнал


def test_без_компании(сайт):
    uid = учётка("nocompany@savdex.uz")

    for path, method in (
        ("/cabinet/billing/cancel", "POST"),
        ("/cabinet/billing/resume", "POST"),
        ("/cabinet/billing/card/1", "DELETE"),
        ("/cabinet/billing/invoice/1/cancel", "POST"),
    ):
        итог = отправить(сайт, path, сброс(), снимок, uid=uid, method=method)
        база = итог["база"]

        # Без компании нет ни подписки, ни карт, ни счетов — 404, ничего не тронуто
        assert итог["ответ"]["status"] == 404, path
        assert база["subscriptions"] == [(True, False, None, False)]
        assert len(база["cards"]) == 3 and база["payments"] == НЕ_ТРОНУТЫ


def test_гость(сайт):
    итог = отправить(сайт, "/cabinet/billing/cancel", сброс(), снимок)

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/login"
    assert итог["база"]["subscriptions"] == [(True, False, None, False)]
