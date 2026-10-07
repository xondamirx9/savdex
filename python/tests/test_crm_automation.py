"""
CRM сама (savdex/crm/automation.py).

- Оплата → сделка: «Деньги пришли» в админке — открытая сделка
  компании выиграна (сумма пустой — из счёта, строка в заметке, журнал
  от имени сотрудника); из нескольких — на ту же сумму; закрытые,
  удалённые и чужие сделки не трогаются; без сделки — ничего.
- Заявка с сайта → лид: форма на /contact — лид «Форма на сайте» на
  первом этапе; вошедшему — с его компанией; проверка ввода; бот
  (скрытое поле) лида не создаёт; не больше 5 заявок за 10 минут.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from .factories import компания
from .pg_admin import КОРЕНЬ, django, sql, нужна_база, свежая_база, сотрудник
from .test_web_forms import отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

PAYMENTS = "/py/admin/finance/payment/"
#: Счётчик частоты — в файловом кэше, как на сервере (CACHE_STORE=file)
КЭШ = Path(КОРЕНЬ) / "storage/framework/cache/data"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )

    было = os.environ.get("CACHE_STORE")
    os.environ["CACHE_STORE"] = "file"

    with адрес() as root:
        yield root

    if было is None:
        os.environ.pop("CACHE_STORE", None)
    else:
        os.environ["CACHE_STORE"] = было


@pytest.fixture(scope="module")
def finance(сайт: str) -> int:
    return сотрудник("finance")


@pytest.fixture(autouse=True)
def чисто(сайт: str) -> None:
    sql("delete from crm_deals")
    sql("delete from crm_leads")
    sql("delete from admin_actions")
    shutil.rmtree(КЭШ, ignore_errors=True)
    sql(
        "truncate payment_transactions, payments, wallets, wallet_transactions, "
        "user_notifications, activity_events restart identity cascade"
    )


# ── Оплата → сделка ─────────────────────────────────────────────────


def _счёт(company: int, amount: int = 350000, currency: str = "UZS") -> int:
    [(pk,)] = sql(
        "insert into payments (company_id, purpose, credit_pack_id, number, description, "
        "amount, currency, provider, status, created_at, updated_at) values (%s, 'credits', "
        "(select id from credit_packs where code = 'm'), 'SVD-000077', 'Пакет «Средний»', "
        "%s, %s, 'invoice', 'pending', now(), now()) returning id",
        [company, amount, currency],
    )

    return int(pk)


def _сделка(company: int | None, title: str, stage: str = "negotiation", **поля: Any) -> int:
    columns = ["title", "company_id", "stage", *поля]
    [(pk,)] = sql(
        f"insert into crm_deals ({', '.join(columns)}, created_at, updated_at, "
        f"stage_changed_at) values ({', '.join(['%s'] * len(columns))}, "
        "now() - interval '2 days', now() - interval '2 days', now() - interval '2 days') "
        "returning id",
        [title, company, stage, *поля.values()],
    )

    return int(pk)


def _сделки() -> dict[str, tuple[Any, ...]]:
    return {
        row[0]: row[1:]
        for row in sql(
            "select title, stage, amount, currency, closed_at is not null, "
            "stage_changed_at > now() - interval '1 hour', note from crm_deals order by id"
        )
    }


def _оплатить(staff: int, payment: int) -> dict[str, Any]:
    *_, ответ = django(staff, ("post", f"{PAYMENTS}{payment}/confirm/", {"note": "п/п 1"}))
    assert ответ["status"] == 302

    return ответ


def _журнал_сделок() -> list[tuple[Any, ...]]:
    return sql(
        "select user_id, action, section, subject_label, changes::text, note from admin_actions "
        "where subject_type = 'App\\Models\\Crm\\Deal' order by id"
    )


def test_оплата_закрывает_сделку(finance):
    c = компания()
    pk = _сделка(c, "Пакет для склада", note="Звонили 01.10")
    _оплатить(finance, _счёт(c))

    [(title, (stage, amount, currency, closed, свежий, note))] = _сделки().items()
    assert title == "Пакет для склада"
    assert (stage, amount, currency, closed, свежий) == ("won", 350000, "UZS", True, True)
    # Строка в заметке — с датой, после прежних
    assert note.startswith("Звонили 01.10\n")
    assert note.endswith(", автоматически: оплачен счёт SVD-000077 (350 000 сум)")

    [(user_id, action, section, label, changes, текст)] = _журнал_сделок()
    assert (user_id, action, section, label) == (finance, "updated", "deals", "Пакет для склада")
    assert json.loads(changes) == {
        "before": {"stage": "negotiation", "amount": 0},
        "after": {"stage": "won", "amount": 350000},
    }
    assert текст == (
        "Этап: «Переговоры» → «Выиграна» — автоматически, оплачен счёт SVD-000077 (350 000 сум)"
    )
    assert sql("select id from crm_deals where stage = 'won'") == [(pk,)]


def test_сумма_сделки_не_меняется_и_выбирается_та_же(finance):
    c = компания()
    _сделка(c, "Другая сумма", amount=900000)
    _сделка(c, "Та же сумма", stage="proposal", amount=350000)
    _оплатить(finance, _счёт(c))

    сделки = _сделки()
    assert сделки["Та же сумма"][:4] == ("won", 350000, "UZS", True)
    assert сделки["Другая сумма"][:4] == ("negotiation", 900000, "UZS", False)


def test_что_оплата_не_трогает(finance):
    c = компания()
    _сделка(c, "Уже выиграна", stage="won", closed_at="2026-09-01 00:00:00")
    _сделка(c, "Проиграна", stage="lost", closed_at="2026-09-01 00:00:00")
    _сделка(c, "В корзине", deleted_at="2026-09-01 00:00:00")
    _сделка(компания(), "Чужая")
    _сделка(None, "Без компании")
    _оплатить(finance, _счёт(c))

    assert {k: v[0] for k, v in _сделки().items()} == {
        "Уже выиграна": "won",
        "Проиграна": "lost",
        "В корзине": "negotiation",
        "Чужая": "negotiation",
        "Без компании": "negotiation",
    }
    assert _журнал_сделок() == []
    # Сама оплата прошла как обычно
    assert sql("select status from payments") == [("paid",)]


# ── Заявка с сайта → лид ────────────────────────────────────────────


def _заявка(
    сайт: str, uid: int | None = None, path: str = "/contact", **поля: Any
) -> dict[str, Any]:
    body = {
        "name": "  Алишер  Каримов ",
        "phone": "+998 90 123-45-67",
        "email": "",
        "company": "ООО «Стройбаза»",
        "message": "Хотим тариф для 5 сотрудников.\nЕсть ли скидка?",
        "website": "",
        **поля,
    }

    return отправить(сайт, path, lambda: None, uid=uid, body=body, env={"CACHE_STORE": "file"})


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"])) if итог["сессия"] else {}


def _ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    return dict(_сессия(итог).get("errors", {}).get("default", {}).get("messages", {}))


def _лиды() -> list[tuple[Any, ...]]:
    return sql(
        "select title, source, status, company_id, contact_name, contact_phone, contact_email, "
        "owner_id, note, stage_changed_at is not null from crm_leads order by id"
    )


def test_заявка_гостя_становится_лидом(сайт):
    итог = _заявка(сайт)

    assert итог["ответ"]["status"] == 302
    assert _сессия(итог)["success"] == (
        "Заявка отправлена. Мы свяжемся с вами в течение рабочего дня."
    )
    assert _лиды() == [
        (
            "Хотим тариф для 5 сотрудников. Есть ли скидка?",
            "site",
            "new",
            None,
            "Алишер Каримов",
            "+998 90 123-45-67",
            None,
            None,
            "Хотим тариф для 5 сотрудников.\nЕсть ли скидка?\n"
            "Компания (со слов): ООО «Стройбаза»\nЯзык сайта: ru",
            True,
        )
    ]
    [(user_id, action, section, note)] = sql(
        "select user_id, action, section, note from admin_actions "
        "where subject_type = 'App\\Models\\Crm\\Lead'"
    )
    assert (user_id, action, section, note) == (
        None,
        "created",
        "leads",
        "Заявка с сайта (страница «Контакты»)",
    )


def test_заявка_вошедшего_с_его_компанией(сайт):
    c = компания()
    uid = учётка("lead-user@savdex.uz", company_id=c)
    _заявка(сайт, uid, path="/en/contact", phone="", email="Lead-User@Savdex.uz")

    [лид] = _лиды()
    assert (лид[3], лид[5], лид[6]) == (c, None, "lead-user@savdex.uz")
    assert лид[8].endswith("Язык сайта: en")


@pytest.mark.parametrize(
    ("поля", "ошибки"),
    [
        (
            {"name": " ", "message": "Да"},
            {
                "name": ["Укажите, как к вам обращаться"],
                "message": ["Опишите вопрос хотя бы в нескольких словах"],
            },
        ),
        (
            {"phone": "", "email": ""},
            {"phone": ["Укажите телефон или почту, чтобы мы могли ответить"]},
        ),
        (
            {"phone": "12"},
            {"phone": ["Номер должен содержать от 9 до 15 цифр. Например: +998 90 123-45-67"]},
        ),
        ({"email": "не почта"}, {"email": ["Проверьте адрес почты"]}),
    ],
)
def test_проверка_заявки(сайт, поля, ошибки):
    итог = _заявка(сайт, **поля)

    assert _ошибки(итог) == ошибки
    assert _лиды() == []


def test_бот_лида_не_создаёт(сайт):
    итог = _заявка(сайт, website="http://spam.example")

    # Ответ как у человека — бот не узнает, что его отсеяли
    assert итог["ответ"]["status"] == 302 and "success" in _сессия(итог)
    assert _лиды() == []


def test_не_чаще_5_заявок_за_10_минут(сайт):
    итоги = [_заявка(сайт) for _ in range(6)]

    # Шестая — назад с «слишком часто», лида нет
    assert [и["ответ"]["status"] for и in итоги] == [302] * 6
    assert "body" in _ошибки(итоги[-1]) and "body" not in _ошибки(итоги[-2])
    assert len(_лиды()) == 5


def test_страница_контактов_открывается(сайт):
    итог = отправить(сайт, "/contact", lambda: None, method="GET", headers={})

    assert итог["ответ"]["status"] == 200
    assert '"component":"Contacts"' in итог["ответ"]["body"].replace("&quot;", '"')
