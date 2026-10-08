"""
Стартовый экран админки на Django, этап 6: виджеты Filament на главной /py/admin/.

- кто что видит: без прав — только «Роль ещё не назначена»; поддержка —
  обращения, но не показатели площадки; модератор — очередь на проверку;
  менеджер поставщиков — новых поставщиков (и «both»); порядок — как
  у Filament;
- лиды — свои и ничьи, старые сверху, «Ждёт» краснеет с трёх дней;
- задачи — просроченные и сегодняшние по ташкентским суткам, своими;
- обращения — свои, ничьи, чужие; внутри — по важности и давности;
- очередь на проверку — число и возраст самого старого, красное с двух
  часов; контент в работе — черновики, запланированные, скрытые страницы;
- показатели площадки (PlatformMetrics) — на заданных данных, числа до
  знака; выручка — только с финансовыми отчётами;
- «Ждёт 3 дня» — как diffForHumans у Carbon.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

HOME = "/py/admin/"


def _время() -> datetime:
    """Сейчас по UTC без пояса — так Laravel пишет время в базу."""
    return datetime.now(UTC).replace(tzinfo=None)


def назад(**сдвиг: float) -> datetime:
    return _время() - timedelta(**сдвиг)


def _сотрудник(name: str, email: str, role: str | None, **поля: Any) -> int:
    columns = ["name", "email", "admin_role", *поля]
    [(uid,)] = sql(
        f"insert into users ({', '.join(columns)}, password, is_admin, status, created_at, "
        f"updated_at) values ({', '.join(['%s'] * len(columns))}, 'x', true, 'active', now(), "
        "now()) returning id",
        [name, email, role, *поля.values()],
    )

    return int(uid)


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    роли = (
        "superadmin",
        "admin",
        "sales",
        "support",
        "moderator",
        "supplier_manager",
        "buyer_manager",
        "content_manager",
        "finance",
    )
    люди = {role: сотрудник(role) for role in роли}
    люди["sales2"] = _сотрудник("Второй продавец", "sales2@savdex.uz", "sales")
    люди["support2"] = _сотрудник("Вторая поддержка", "support2@savdex.uz", "support")
    люди["nobody"] = _сотрудник("Новенький", "nobody@savdex.uz", None)
    # Роль есть, но все её права сняты лично — та же пустота
    люди["revoked"] = _сотрудник(
        "Без прав",
        "revoked@savdex.uz",
        "content_manager",
        admin_permissions=json.dumps(
            {
                "revoke": [
                    "content.view",
                    "content.create",
                    "content.edit",
                    "catalogs.view",
                    "catalogs.create",
                    "catalogs.edit",
                    "broadcasts.view",
                ]
            }
        ),
    )

    return люди


@pytest.fixture(autouse=True)
def чисто() -> None:
    for table in (
        "crm_tasks",
        "crm_communications",
        "crm_deals",
        "crm_leads",
        "crm_contacts",
        "support_messages",
        "support_tickets",
        "reviews",
        "company_documents",
        "contact_unlocks",
        "payments",
        "listings",
        "category_translations",
        "categories",
        "news_posts",
        "pages",
    ):
        sql(f"delete from {table}")

    sql("delete from users where not is_admin")
    sql("delete from companies")


def _вставить(table: str, **поля: Any) -> int:
    строка = {"created_at": _время(), "updated_at": _время(), **поля}
    [(pk,)] = sql(
        f"insert into {table} ({', '.join(строка)}) "
        f"values ({', '.join(['%s'] * len(строка))}) returning id",
        list(строка.values()),
    )

    return int(pk)


_номер = itertools.count(1)


def _компания(name: str, **поля: Any) -> int:
    return _вставить("companies", name=name, slug=f"company-{next(_номер)}", **поля)


def _главная(uid: int) -> str:
    _, главная = django(uid, ("get", HOME, None))
    assert главная["status"] == 200, главная["body"][:2000]

    return str(главная["body"])


def виджеты(body: str) -> list[str]:
    return re.findall(r'data-widget="([a-z_]+)"', body)


def блок(body: str, key: str) -> str:
    """Разметка одного виджета — до конца его раздела."""
    start = body.index(f'data-widget="{key}"')

    return body[start : body.index("</section>", start)]


def плитка(body: str, label: str) -> dict[str, str]:
    """Плитка с числом: значение, подпись и её цвет."""
    start = body.index(f'<div class="savdex-stat-label">{label}</div>')
    html = body[start : body.index("savdex-stat-description", start) + 300]
    value = re.search(r'savdex-stat-value">([^<]*)<', html)
    description = re.search(r'savdex-stat-description savdex-tone-(\w+)">(.*?)</div>', html, re.S)
    assert value and description, html

    return {
        "value": value.group(1),
        "tone": description.group(1),
        "description": re.sub(r"<[^>]+>", "", description.group(2)).strip(),
    }


def по_порядку(html: str, *тексты: str) -> bool:
    места = [html.index(t) for t in тексты]

    return места == sorted(места)


# ── Кто что видит ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("кто", "ожидается"),
    [
        (
            "superadmin",
            [
                "my_leads",
                "my_tasks",
                "intake_queue",
                "moderation_queue",
                "support_queue",
                "finance_today",
                "content_drafts",
                "platform_stats",
                "activation_funnel",
                "registrations_chart",
            ],
        ),
        (
            "admin",
            [
                "my_leads",
                "my_tasks",
                "support_queue",
                "content_drafts",
                "platform_stats",
                "activation_funnel",
                "registrations_chart",
            ],
        ),
        ("sales", ["my_leads", "my_tasks"]),
        ("supplier_manager", ["my_leads", "my_tasks", "intake_queue"]),
        ("moderator", ["moderation_queue"]),
        ("support", ["my_tasks", "support_queue"]),
        ("content_manager", ["content_drafts"]),
        ("finance", ["finance_today"]),
        ("nobody", ["awaiting_role"]),
        ("revoked", ["awaiting_role"]),
    ],
)
def test_кто_что_видит_и_в_каком_порядке(люди, кто, ожидается):
    body = _главная(люди[кто])

    assert виджеты(body) == ожидается
    # Перенос закончен: ни хода переноса, ни «разделов на Python»
    assert "Python" not in body


def test_без_прав_только_объяснение(люди):
    body = _главная(люди["nobody"])

    assert "Роль ещё не назначена" in body
    assert "это не сбой" in body
    assert "Лиды в работе" not in body and "За последние 30 дней" not in body


def test_выручка_только_с_финансовыми_отчётами(люди):
    суперадмин = _главная(люди["superadmin"])
    администратор = _главная(люди["admin"])

    assert "Выручка, сум" in блок(суперадмин, "platform_stats")
    assert "Раскрытий контактов" in блок(администратор, "platform_stats")
    assert "Выручка, сум" not in администратор


# ── Лиды ────────────────────────────────────────────────────────────


def test_лиды_свои_и_ничьи_старые_сверху(люди):
    мой = _вставить(
        "crm_leads", title="Мой старый лид", owner_id=люди["sales"], created_at=назад(days=4)
    )
    ничей = _вставить(
        "crm_leads", title="Ничей лид", source="call", contact_name="Пётр", created_at=назад(days=1)
    )
    _вставить("crm_leads", title="Чужой лид", owner_id=люди["sales2"], created_at=назад(days=2))
    _вставить("crm_leads", title="Закрытый лид", owner_id=люди["sales"], status="converted")
    _вставить("crm_leads", title="Удалённый лид", deleted_at=_время())

    продавец = блок(_главная(люди["sales"]), "my_leads")
    администратор = блок(_главная(люди["admin"]), "my_leads")

    assert по_порядку(продавец, "Мой старый лид", "Ничей лид")
    assert "Чужой лид" not in продавец
    assert "Закрытый лид" not in продавец and "Удалённый лид" not in продавец
    assert f'href="/py/admin/crm/lead/{мой}/change/"' in продавец
    assert f'href="/py/admin/crm/lead/{ничей}/change/"' in продавец
    # Три дня и больше — красным; «Кто» — имя из заявки; источник под заголовком
    assert '<span class="savdex-tone-danger">4 дня</span>' in продавец
    assert '<span class="savdex-tone-gray">1 день</span>' in продавец
    assert "Пётр" in продавец and "Звонок" in продавец
    assert "не распределён" in продавец
    # Руководитель видит всех
    assert по_порядку(администратор, "Мой старый лид", "Чужой лид", "Ничей лид")


def test_лиды_больше_пяти_ссылка_в_раздел(люди):
    for i in range(7):
        _вставить("crm_leads", title=f"Лид номер {i}", created_at=назад(hours=10 - i))

    лиды = блок(_главная(люди["admin"]), "my_leads")

    assert лиды.count("savdex-row-link") == 5
    assert "Лид номер 0" in лиды and "Лид номер 5" not in лиды
    assert "Все 7 в разделе" in лиды and 'href="/py/admin/crm/lead/"' in лиды


def test_пусто_лидов(люди):
    лиды = блок(_главная(люди["sales"]), "my_leads")

    assert "Лидов в работе нет" in лиды
    assert "<table" not in лиды


# ── Задачи ──────────────────────────────────────────────────────────


def test_задачи_на_сегодня_по_ташкенту(люди):
    ташкент = ZoneInfo("Asia/Tashkent")
    завтра = datetime.now(ташкент).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    завтра_utc = завтра.astimezone(UTC).replace(tzinfo=None)
    лид = _вставить("crm_leads", title="Поставка арматуры", owner_id=люди["sales"])

    просрочена = _вставить(
        "crm_tasks",
        title="Перезвонить вчера",
        assignee_id=люди["sales"],
        due_at=назад(days=1),
        subject_type="App\\Models\\Crm\\Lead",
        subject_id=лид,
    )
    _вставить(
        "crm_tasks",
        title="Вечером сегодня",
        assignee_id=люди["sales"],
        due_at=завтра_utc - timedelta(hours=1),
    )
    # 01:00 завтра по Ташкенту — ещё «сегодня» по UTC; Filament брал её в сегодняшние
    _вставить(
        "crm_tasks",
        title="Завтра утром",
        assignee_id=люди["sales"],
        due_at=завтра_utc + timedelta(hours=1),
    )
    _вставить("crm_tasks", title="Без срока", assignee_id=люди["sales"])
    _вставить(
        "crm_tasks",
        title="Уже сделана",
        assignee_id=люди["sales"],
        due_at=назад(days=2),
        done_at=назад(days=1),
    )
    _вставить("crm_tasks", title="Чужая задача", assignee_id=люди["sales2"], due_at=назад(hours=3))

    задачи = блок(_главная(люди["sales"]), "my_tasks")

    assert по_порядку(задачи, "Перезвонить вчера", "Вечером сегодня")
    for лишняя in ("Завтра утром", "Без срока", "Уже сделана", "Чужая задача"):
        assert лишняя not in задачи, лишняя
    assert f'href="/py/admin/crm/task/{просрочена}/change/"' in задачи
    # К чему относится — под заголовком; просроченная — красным
    assert "Поставка арматуры" in задачи
    assert "просрочена" in задачи
    срок = (назад(days=1).replace(tzinfo=UTC)).astimezone(ташкент).strftime("%d.%m.%Y")
    assert f'<span class="savdex-tone-danger">{срок}' in задачи


# ── Новые компании ──────────────────────────────────────────────────


def test_новые_компании_по_направлению(люди):
    sql("delete from cities where slug = 'dash-samarkand'")
    sql("delete from countries where code = 'zq'")
    страна = _вставить(
        "countries", code="zq", phone_code="+000", currency_code="XXX", sort=0, is_active=True
    )
    город = _вставить("cities", country_id=страна, slug="dash-samarkand", sort=0, is_active=True)
    _вставить("city_translations", city_id=город, locale="ru", name="Самарканд")
    поставщик = _компания(
        "Цемент Трейд",
        primary_role="supplier",
        city_id=город,
        phone="+998901112233",
        verification_level=2,
        created_at=назад(days=3),
    )
    _компания("Закупки Плюс", primary_role="buyer", created_at=назад(days=2))
    _компания("Всё Сразу", primary_role="both", created_at=назад(days=1))
    _компания("Старый Поставщик", primary_role="supplier", created_at=назад(days=20))
    _компания("Удалённый Поставщик", primary_role="supplier", deleted_at=_время())

    поставщики = блок(_главная(люди["supplier_manager"]), "intake_queue")
    покупатели = блок(_главная(люди["buyer_manager"]), "intake_queue")
    все = блок(_главная(люди["superadmin"]), "intake_queue")

    assert "Новые поставщики" in поставщики
    assert по_порядку(поставщики, "Всё Сразу", "Цемент Трейд")
    for лишняя in ("Закупки Плюс", "Старый Поставщик", "Удалённый Поставщик"):
        assert лишняя not in поставщики
    # Колонки «Направление» у менеджера направления нет
    assert "Направление" not in поставщики
    assert f'href="/py/admin/data/companyrecord/{поставщик}/change/"' in поставщики
    assert "Самарканд" in поставщики and "Проверена+" in поставщики
    assert "+998901112233" in поставщики and "не указан" in поставщики
    assert "3 дня" in поставщики

    assert "Новые покупатели" in покупатели
    assert "Закупки Плюс" in покупатели and "Всё Сразу" in покупатели
    assert "Цемент Трейд" not in покупатели

    assert "Новые компании" in все and "Направление" in все
    assert по_порядку(все, "Всё Сразу", "Закупки Плюс", "Цемент Трейд")
    assert "И то и другое" in все and "Поставщик" in все


# ── Обращения ───────────────────────────────────────────────────────


def test_обращения_свои_ничьи_чужие(люди):
    я = люди["support"]
    _вставить(
        "support_tickets",
        subject="Чужое срочное",
        priority="high",
        assignee_id=люди["support2"],
        created_at=назад(days=3),
    )
    _вставить("support_tickets", subject="Ничьё обычное", created_at=назад(days=2))
    _вставить(
        "support_tickets", subject="Ничьё срочное", priority="high", created_at=назад(hours=1)
    )
    _вставить(
        "support_tickets",
        subject="Моё неважное",
        priority="low",
        assignee_id=я,
        author_name="Пётр",
        # Давность — в часах: подпись округляется вниз, и с минутами
        # («30 минут») тест падал, если между вставкой и выдачей прошло
        # больше минуты — на загруженном раннере так и было
        created_at=назад(hours=5),
    )
    _вставить("support_tickets", subject="Моё закрытое", assignee_id=я, status="closed")
    _вставить("support_tickets", subject="Моё удалённое", assignee_id=я, deleted_at=_время())

    обращения = блок(_главная(я), "support_queue")

    assert по_порядку(обращения, "Моё неважное", "Ничьё срочное", "Ничьё обычное", "Чужое срочное")
    assert "Моё закрытое" not in обращения and "Моё удалённое" not in обращения
    assert "никто" in обращения and "Вторая поддержка" in обращения and "Пётр" in обращения
    # Сутки и дольше — красным
    assert '<span class="savdex-tone-danger">2 дня</span>' in обращения
    assert '<span class="savdex-tone-gray">5 часов</span>' in обращения
    assert '<span class="savdex-badge savdex-tone-danger">Срочный</span>' in обращения


# ── Очередь на проверку ─────────────────────────────────────────────


def test_очередь_на_проверку_и_два_часа(люди):
    продавец = _компания("Продавец")
    покупатель = _компания("Покупатель")
    _вставить(
        "listings",
        company_id=продавец,
        title="Цемент",
        status="moderation",
        updated_at=назад(hours=3, minutes=5),
    )
    _вставить(
        "listings",
        company_id=продавец,
        title="Песок",
        status="moderation",
        updated_at=назад(minutes=5),
    )
    _вставить(
        "listings",
        company_id=продавец,
        title="Удалённое",
        status="moderation",
        updated_at=назад(days=9),
        deleted_at=_время(),
    )
    _вставить(
        "company_documents",
        company_id=продавец,
        type="license",
        title="Лицензия",
        file_path="docs/x.pdf",
        # Полтора часа: подпись «1 час» держится полчаса, и до двух часов
        # (срок проверки) плитка остаётся жёлтой. С «30 минутами» запаса
        # было меньше минуты
        created_at=назад(hours=1, minutes=30),
    )
    _вставить(
        "contact_unlocks",
        company_id=покупатель,
        target_company_id=продавец,
        complaint_status="pending",
        complained_at=назад(days=1, minutes=1),
    )

    body = _главная(люди["moderator"])

    assert плитка(body, "Объявления") == {
        "value": "2",
        "tone": "danger",
        "description": "самое старое ждёт 3 часа",
    }
    assert плитка(body, "Документы") == {
        "value": "1",
        "tone": "warning",
        "description": "самое старое ждёт 1 час",
    }
    assert плитка(body, "Споры по отзывам") == {
        "value": "0",
        "tone": "success",
        "description": "очередь пуста",
    }
    assert плитка(body, "Жалобы на контакты") == {
        "value": "1",
        "tone": "danger",
        "description": "самое старое ждёт 1 день",
    }
    очередь = блок(body, "moderation_queue")
    assert 'href="/py/admin/data/listing/?status=moderation"' in очередь
    assert 'href="/py/admin/finance/complaint/"' in очередь


# ── Деньги за сегодня ───────────────────────────────────────────────


def test_деньги_за_сегодня_по_ташкенту(люди):
    sql("delete from refunds")
    sql("delete from payments")
    покупатель = _компания("Плательщик")
    зона = ZoneInfo("Asia/Tashkent")
    полночь = (
        datetime.now(зона)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )

    def счёт(status: str, amount: int, paid_at: datetime | None = None) -> int:
        return _вставить(
            "payments", company_id=покупатель, purpose="subscription", description="x",
            amount=amount, currency="UZS", status=status, paid_at=paid_at,
        )  # fmt: skip

    счёт("paid", 1000000, полночь + timedelta(seconds=1))
    возвращённый = счёт("refunded", 500000, полночь + timedelta(minutes=5))
    счёт("paid", 700000, полночь - timedelta(seconds=1))  # вчера по Ташкенту
    счёт("pending", 250000)
    счёт("pending", 499000)
    _вставить(
        "refunds", payment_id=возвращённый, company_id=покупатель, amount=200000,
        currency="UZS", reason="x", status="requested",
    )  # fmt: skip

    body = _главная(люди["finance"])

    assert плитка(body, "Оплачено сегодня") == {
        "value": "1 500 000 сум",
        "tone": "success",
        "description": "2 счёта",
    }
    assert плитка(body, "Ждут оплаты") == {
        "value": "2",
        "tone": "warning",
        "description": "на 749 000 сум",
    }
    assert плитка(body, "Возвраты на решении") == {
        "value": "1",
        "tone": "danger",
        "description": "на 200 000 сум",
    }
    деньги = блок(body, "finance_today")
    assert 'href="/py/admin/finance/payment/"' in деньги
    assert 'href="/py/admin/finance/refund/"' in деньги

    sql("delete from refunds")
    sql("delete from payments")
    пусто = _главная(люди["finance"])

    assert плитка(пусто, "Возвраты на решении")["description"] == "ничего не ждёт"
    assert плитка(пусто, "Ждут оплаты")["tone"] == "gray"


# ── Контент ─────────────────────────────────────────────────────────


def test_контент_в_работе(люди):
    def новость(slug: str, **поля: Any) -> None:
        _вставить(
            "news_posts", slug=slug, category="updates", title=slug, excerpt="…", body="…", **поля
        )

    новость("draft-1")
    новость("draft-2")
    новость("scheduled", is_published=True, published_at=_время() + timedelta(days=2))
    новость("published", is_published=True, published_at=назад(days=2))
    _вставить("pages", key="help", slug="help", title="Помощь", is_published=False)
    _вставить("pages", key="about", slug="about", title="О площадке")

    body = _главная(люди["content_manager"])

    assert плитка(body, "Черновики новостей") == {
        "value": "2",
        "tone": "warning",
        "description": "ждут публикации",
    }
    assert плитка(body, "Выйдут по расписанию") == {
        "value": "1",
        "tone": "info",
        "description": "уже назначены",
    }
    assert плитка(body, "Скрытые страницы") == {
        "value": "1",
        "tone": "gray",
        "description": "не видны посетителям",
    }
    контент = блок(body, "content_drafts")
    assert 'href="/py/admin/site/newspost/?status=draft"' in контент
    assert 'href="/py/admin/site/newspost/?status=scheduled"' in контент
    assert 'href="/py/admin/site/page/?is_published__exact=0"' in контент


# ── Показатели площадки ─────────────────────────────────────────────


def _площадка() -> None:
    """Данные для показателей — все даты далеко от краёв периодов."""
    категория = _вставить("categories", slug="cement", sort=0, is_active=True)
    _вставить("category_translations", category_id=категория, locale="ru", name="Цемент")
    без_перевода = _вставить("categories", slug="armatura", sort=1, is_active=True)

    а = _компания("Альфа", status="active", created_at=назад(days=2))
    б = _компания("Бета", status="active", created_at=назад(days=10))
    в = _компания("Вега", status="blocked", created_at=назад(days=40))
    г = _компания("Гамма", status="active", created_at=назад(days=40, hours=3))
    _компания("Дельта", status="pending", created_at=назад(days=20))
    _компания("Старая", status="active", created_at=назад(days=70))
    удалённая = _компания(
        "Удалённая", status="active", created_at=назад(days=2), deleted_at=_время()
    )

    def пользователь(email: str, **поля: Any) -> None:
        _вставить("users", name=email, email=email, password="x", **поля)

    пользователь(
        "a@example.com", company_id=а, email_verified_at=назад(days=1), created_at=назад(days=1)
    )
    пользователь("b@example.com", company_id=б, created_at=назад(days=5))
    пользователь("c@example.com", company_id=удалённая, created_at=назад(days=3))
    пользователь("d@example.com", created_at=назад(days=45))
    пользователь("e@example.com", created_at=назад(days=3), deleted_at=_время())

    def объявление(company: int, status: str, **поля: Any) -> None:
        _вставить(
            "listings", company_id=company, title=f"{status} {company}", status=status, **поля
        )

    объявление(а, "active", category_id=категория, views_count=100, expires_at=назад(days=-3))
    объявление(а, "active", category_id=категория, views_count=50, created_at=назад(days=35))
    объявление(а, "moderation", views_count=7)
    объявление(а, "draft")
    объявление(б, "active", category_id=без_перевода, views_count=30, expires_at=назад(days=-30))
    объявление(в, "draft", created_at=назад(days=36))
    объявление(удалённая, "active", category_id=категория, views_count=5)
    объявление(б, "active", category_id=без_перевода, views_count=1000, deleted_at=_время())

    for покупатель, продавец, когда in ((б, а, 1), (в, а, 1), (г, а, 2), (а, б, 35)):
        _вставить(
            "contact_unlocks",
            company_id=покупатель,
            target_company_id=продавец,
            created_at=назад(days=когда),
        )

    def платёж(amount: int, status: str, paid_at: datetime | None) -> None:
        _вставить(
            "payments",
            company_id=а,
            purpose="credits",
            description="Пакет",
            amount=amount,
            status=status,
            paid_at=paid_at,
        )

    платёж(500000, "paid", назад(days=2))
    платёж(300001, "refunded", назад(days=5))
    платёж(999, "pending", None)
    платёж(700000, "paid", назад(days=40))
    платёж(123, "paid", None)

    for автор, оценка, ответ in ((б, 2, None), (в, 3, "Спасибо"), (г, 5, None)):
        _вставить(
            "reviews",
            company_id=а,
            author_company_id=автор,
            rating=оценка,
            body="Отзыв",
            reply=ответ,
        )


ПОКАЗАТЕЛИ_PYTHON = """
import json
import django
django.setup()
from savdex.dashboard.metrics import PlatformMetrics

m = PlatformMetrics()
print(json.dumps({
    "summary": m.summary(),
    "funnel": m.activation_funnel(),
    "health": m.health(),
    "categories": m.top_categories(),
    "registrations": m.registrations_by_day(),
    "conversion": m.unlock_conversion(),
    "average": m.average_payment(),
}))
"""


def _python() -> dict[str, Any]:
    """Показатели глазами Django — под ролью savdex_django, как на боевом."""
    вывод = subprocess.run(
        [sys.executable, "-c", ПОКАЗАТЕЛИ_PYTHON],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return dict(json.loads(вывод.stdout))


def test_показатели_площадки(люди):
    """
    PlatformMetrics на данных _площадка(): последние 30 дней против
    предыдущих 30, удалённые не считаются.
    """
    _площадка()

    питон = _python()

    # Компании: Альфа, Бета, Дельта против Веги и Гаммы — +50 %; объявления
    # 5 против 2; раскрытия 3 против 1; выручка — оплаченные и возвращённые
    # с датой оплаты (500 000 + 300 001) против 700 000
    assert питон["summary"] == {
        "companies": {"value": 3, "delta": 50.0, "suffix": " компаний"},
        "listings": {"value": 5, "delta": 150.0, "suffix": " объявлений"},
        "unlocks": {"value": 3, "delta": 200.0, "suffix": " раскрытий"},
        "revenue": {"value": 800001, "delta": 14.3, "suffix": " сум"},
    }
    assert питон["average"] == 400000
    assert питон["categories"] == [
        {"label": "Цемент", "listings": 3, "companies": 2},
        # Без русского перевода — адрес раздела
        {"label": "armatura", "listings": 1, "companies": 1},
    ]
    # Активные компании с живыми объявлениями — Альфа и Бета из четырёх
    # активных; в очереди одно; истекает за неделю одно; плохой отзыв без
    # ответа — один (на тройку ответили)
    assert [(h["value"], h["tone"]) for h in питон["health"]] == [
        ("2 из 4 (50 %)", "success"),
        ("1", "success"),
        ("1", "success"),
        ("1", "warning"),
    ]
    # 13 сотрудников и 4 пользователя (удалённый — нет); почту подтвердил
    # один, с компанией — трое
    assert [(s["value"], s["share"]) for s in питон["funnel"]] == [
        (17, 100.0),
        (1, 5.9),
        (3, 17.6),
        (2, 11.8),
        (2, 11.8),
    ]
    регистрации = питон["registrations"]
    assert len(регистрации["labels"]) == len(регистрации["companies"]) == 30
    assert sum(регистрации["companies"]) == 3
    # Сегодня — 13 сотрудников; за месяц ещё три пользователя (45 дней — нет)
    assert регистрации["users"][-1] == 13 and sum(регистрации["users"]) == 16
    # 4 раскрытия на 192 просмотра живых объявлений
    assert питон["conversion"] == round(4 / 192 * 100, 2)


def test_показатели_на_главной(люди):
    _площадка()

    body = _главная(люди["superadmin"])

    assert плитка(body, "Новых компаний") == {
        "value": "3",
        "tone": "success",
        "description": "↗ +50 % к прошлым 30 дням",
    }
    assert плитка(body, "Раскрытий контактов")["description"] == "↗ Конверсия из просмотра: 2.08 %"
    assert плитка(body, "Выручка, сум") == {
        "value": "800 001",
        "tone": "success",
        "description": "↗ Средний чек: 400 000 сум",
    }
    воронка = body[body.index('data-widget="activation_funnel"') :]
    assert "Воронка активации" in воронка and "Здоровье площадки" in воронка
    # 17 зарегистрировались (с сотрудниками), 1 подтвердил почту, 3 с компанией, 2 и 2
    assert "−94 % к прошлому шагу" in воронка and "−33 % к прошлому шагу" in воронка
    assert "2 из 4 (50 %)" in воронка and "3 / 2 комп." in воронка
    график = блок(body, "registrations_chart")
    assert "<svg" in график and "Числа таблицей" in график
    # Координаты — с точкой: «194,0» из русской локализации SVG не поймёт
    assert re.search(r'd="M\d+\.\d,\d+\.\d L', график)
    assert not re.search(r'="\d+,\d', график)
    assert "пользователей" in график


# ── «Ждёт 3 дня» — как Carbon ───────────────────────────────────────


def test_возраст_как_у_carbon():
    """age() — как diffForHumans(syntax: true) у Carbon на тех же парах моментов."""
    from savdex.dashboard.widgets import age

    сейчас = datetime(2026, 9, 29, 12, 0, 0)
    пары = [
        (сейчас - timedelta(seconds=s), сейчас)
        for s in (
            0,
            1,
            59,
            60,
            119,
            120,
            3599,
            3600,
            7199,
            7200,
            86399,
            86400,
            3 * 86400,
            6 * 86400,
            7 * 86400,
            13 * 86400,
            14 * 86400,
            30 * 86400,
            31 * 86400,
            61 * 86400,
            365 * 86400,
            730 * 86400,
        )
    ] + [
        # Края месяцев: дни «занимаются» у месяца перед более поздней датой
        (datetime(2026, 1, 31, 10), datetime(2026, 3, 1, 9)),
        (datetime(2026, 2, 28, 23), datetime(2026, 3, 31, 1)),
        (datetime(2025, 12, 31, 12), datetime(2026, 1, 30, 12)),
        (datetime(2024, 2, 29, 12), datetime(2025, 2, 28, 12)),
    ]
    # Что выводил Carbon: одна старшая единица, вниз; неделя — от 7 дней;
    # месяц — календарный (DateTime::diff), дни занимаются у месяца перед
    # более поздней датой
    carbon = [
        "0 секунд",
        "1 секунда",
        "59 секунд",
        "1 минута",
        "1 минута",
        "2 минуты",
        "59 минут",
        "1 час",
        "1 час",
        "2 часа",
        "23 часа",
        "1 день",
        "3 дня",
        "6 дней",
        "1 неделя",
        "1 неделя",
        "2 недели",
        # 30 августа — 29 сентября: 30 дней, месяца ещё нет
        "4 недели",
        "1 месяц",
        "1 месяц",
        "1 год",
        "2 года",
        # 31.01 10:00 — 01.03 09:00: 28 дней 23 часа
        "4 недели",
        "1 месяц",
        # 31.12 — 30.01: 30 дней
        "4 недели",
        # 29.02.2024 — 28.02.2025: 11 месяцев 30 дней
        "11 месяцев",
    ]

    assert [age(a.replace(tzinfo=UTC), b.replace(tzinfo=UTC)) for a, b in пары] == carbon
