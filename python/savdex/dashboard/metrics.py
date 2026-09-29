"""
Продуктовые показатели площадки — копия App\\Support\\PlatformMetrics.

Считает то, по чему принимают решения о продукте, а не то, что проще
достать: «всего компаний» растёт всегда и ни о чём не говорит, «доля
дошедших до первого объявления» показывает, где люди отваливаются.

Числа обязаны совпадать с PHP до знака — это проверяет
tests/test_dashboard.py, считая одно и то же обеими сторонами. Отсюда
правила, взятые у Eloquent как есть:

- удалённые в корзину (SoftDeletes) не считаются: у пользователей,
  компаний и объявлений — deleted_at; у раскрытий, платежей и отзывов
  корзины нет;
- «сегодня» и «день» — по UTC (Carbon::today() при app.timezone = UTC),
  а не по Ташкенту, как у раздела задач: иначе инфопанель Laravel и эта
  расходились бы на пять часов каждые сутки;
- округление — как round() PHP (половина — от нуля).

Запросов немного и все агрегатные: по одному на таблицу, счётчики
текущего и прошлого периода — одним проходом (FILTER).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypedDict

from django.db import connections
from django.utils import timezone

from savdex.catalogs.models import Category

#: Payment::scopeReceived — оплачено, в том числе потом возвращено:
#: иначе инфопанель и раздел отчётов показывали бы разную выручку
RECEIVED = "status in ('paid', 'refunded') and paid_at is not null"


class Metric(TypedDict):
    value: int
    delta: float | None
    suffix: str


class Step(TypedDict):
    label: str
    value: int
    share: float
    hint: str


class Health(TypedDict):
    label: str
    value: str
    tone: str
    hint: str


class CategoryRow(TypedDict):
    label: str
    listings: int
    companies: int


class Registrations(TypedDict):
    labels: list[str]
    companies: list[int]
    users: list[int]


def _rows(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connections["default"].cursor() as cursor:
        cursor.execute(query, params or [])

        return list(cursor.fetchall())


def _row(query: str, params: list[Any] | None = None) -> tuple[Any, ...]:
    return _rows(query, params)[0]


def _int(value: Any) -> int:  # noqa: ANN401
    """(int) PHP: NULL — ноль, дробное — отбрасывается к нулю."""
    return int(Decimal(value)) if value is not None else 0


def php_round(value: float, places: int = 0) -> float:
    """round() PHP: половина — от нуля, а не к чётному, как у round() Python."""
    return float(Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP))


def php_number(value: float) -> str:
    """Число в строке, как у PHP: 12.0 — «12», 1.5 — «1.5»."""
    return f"{value:.14G}"


class PlatformMetrics:
    """PlatformMetrics: период — последние days дней, включая сегодняшний."""

    def __init__(self, days: int = 30, now: datetime | None = None) -> None:
        self.days = days
        # Время в запросах — наивное UTC: столбцы timestamp без пояса,
        # Laravel пишет в них UTC
        moment = now or timezone.now()
        self.now = moment.astimezone(UTC).replace(tzinfo=None)

    @property
    def today(self) -> date:
        return self.now.date()

    def start(self) -> datetime:
        """from(): полночь (UTC) days − 1 дней назад."""
        return datetime.combine(self.today - timedelta(days=self.days - 1), time())

    # ── Воронка ──

    def activation_funnel(self) -> list[Step]:
        """Воронка регистрации: где именно теряются люди."""
        # whereHas('company.listings'): компания и объявление — не в корзине
        with_listing = (
            "exists (select 1 from companies c where c.id = u.company_id "
            "and c.deleted_at is null and exists (select 1 from listings l "
            "where l.company_id = c.id and l.deleted_at is null{}))"
        )
        any_listing = with_listing.format("")
        active_listing = with_listing.format(" and l.status = 'active'")
        registered, verified, with_company, listing, active = _row(
            "select count(*), "
            "count(*) filter (where u.email_verified_at is not null), "
            "count(*) filter (where u.company_id is not null), "
            f"count(*) filter (where {any_listing}), "
            f"count(*) filter (where {active_listing}) "
            "from users u where u.deleted_at is null"
        )
        top = max(1, registered)

        steps = [
            ("Зарегистрировались", registered, "все аккаунты за всё время"),
            ("Подтвердили почту", verified, "без подтверждения публикация закрыта"),
            ("Завели компанию", with_company, "второй шаг регистрации, он пропускаемый"),
            ("Создали объявление", listing, "включая черновики и отклонённые"),
            ("Дошли до публикации", active, "объявление реально видно покупателям"),
        ]

        return [
            {
                "label": label,
                "value": int(value),
                "share": php_round(value / top * 100, 1),
                "hint": hint,
            }
            for label, value, hint in steps
        ]

    # ── Прирост за период ──

    def summary(self) -> dict[str, Metric]:
        """Ключевые показатели с изменением к прошлому периоду."""
        now = self.start()
        prev = now - timedelta(days=self.days)
        period = "count(*) filter (where {0} >= %s), count(*) filter (where {0} >= %s and {0} < %s)"

        def count(table: str, alive: str = "") -> tuple[int, int]:
            current, previous = _row(
                f"select {period.format('created_at')} from {table}{alive}",
                [now, prev, now],
            )

            return int(current), int(previous)

        revenue_now, revenue_prev = _row(
            "select coalesce(sum(amount) filter (where paid_at >= %s), 0), "
            "coalesce(sum(amount) filter (where paid_at >= %s and paid_at < %s), 0) "
            f"from payments where {RECEIVED}",
            [now, prev, now],
        )

        return {
            "companies": self._metric(
                *count("companies", " where deleted_at is null"), " компаний"
            ),
            "listings": self._metric(
                *count("listings", " where deleted_at is null"), " объявлений"
            ),
            "unlocks": self._metric(*count("contact_unlocks"), " раскрытий"),
            "revenue": self._metric(_int(revenue_now), _int(revenue_prev), " сум"),
        }

    @staticmethod
    def _metric(now: int, prev: int, suffix: str) -> Metric:
        return {
            "value": now,
            # None, когда сравнивать не с чем: «+100 %» от нуля — неправда
            "delta": php_round((now - prev) / prev * 100, 1) if prev > 0 else None,
            "suffix": suffix,
        }

    # ── Здоровье ──

    def health(self) -> list[Health]:
        """Показатели, по которым проблему видно раньше, чем по выручке."""
        active_companies, with_active_listings = _row(
            "select count(*) filter (where c.status = 'active'), "
            "count(*) filter (where exists (select 1 from listings l where l.company_id = c.id "
            "and l.deleted_at is null and l.status = 'active')) "
            "from companies c where c.deleted_at is null"
        )
        moderation_queue, expiring_soon = _row(
            "select count(*) filter (where status = 'moderation'), "
            "count(*) filter (where status = 'active' and expires_at is not null "
            "and expires_at <= %s) "
            "from listings where deleted_at is null",
            [self.now + timedelta(days=7)],
        )
        (unanswered,) = _row("select count(*) from reviews where reply is null and rating <= 3")

        share = (
            int(php_round(with_active_listings / active_companies * 100))
            if active_companies > 0
            else 0
        )

        return [
            {
                "label": "Компаний с активными объявлениями",
                "value": f"{with_active_listings} из {active_companies} ({share} %)",
                # Пустая витрина — главный риск маркетплейса: покупателю
                # нечего смотреть, и он не возвращается
                "tone": "success" if share >= 50 else ("warning" if share >= 25 else "danger"),
                "hint": "Ниже четверти — витрина выглядит пустой",
            },
            {
                "label": "В очереди модерации",
                "value": str(moderation_queue),
                "tone": "danger"
                if moderation_queue > 20
                else ("warning" if moderation_queue > 5 else "success"),
                "hint": "Обещанный срок проверки — до 2 часов",
            },
            {
                "label": "Объявлений истекает за неделю",
                "value": str(expiring_soon),
                "tone": "warning" if expiring_soon > 10 else "success",
                "hint": "После истечения показы прекращаются",
            },
            {
                "label": "Отзывов 3★ и ниже без ответа",
                "value": str(unanswered),
                "tone": "warning" if unanswered > 0 else "success",
                "hint": "Молчание на плохой отзыв читается как согласие",
            },
        ]

    # ── Категории ──

    def top_categories(self, limit: int = 8) -> list[CategoryRow]:
        """
        Категории по числу активных объявлений — где идёт торговля, а где
        справочник заполнен зря. При равенстве — по номеру категории
        (у PHP порядок равных не задан).
        """
        rows = _rows(
            "select category_id, count(*) as listings_count, "
            "count(distinct company_id) as companies_count "
            "from listings where deleted_at is null and category_id is not null "
            "and status = 'active' "
            "group by category_id order by listings_count desc, category_id limit %s",
            [limit],
        )
        categories = {
            c.pk: c
            for c in Category.objects.filter(pk__in=[r[0] for r in rows]).prefetch_related(
                "translations"
            )
        }

        return [
            {
                # Category::name() на языке админки (ru) — с откатом на адрес
                "label": categories[pk].name("ru") if pk in categories else "Без категории",
                "listings": int(listings),
                "companies": int(companies),
            }
            for pk, listings, companies in rows
        ]

    # ── По дням ──

    def registrations_by_day(self) -> Registrations:
        """Регистрации по дням — для графика: компании и пользователи."""
        companies = self._by_day("companies")
        users = self._by_day("users")
        days = [self.today - timedelta(days=i) for i in range(self.days - 1, -1, -1)]

        return {
            "labels": [day.strftime("%d.%m") for day in days],
            "companies": [companies.get(day, 0) for day in days],
            "users": [users.get(day, 0) for day in days],
        }

    def _by_day(self, table: str) -> dict[date, int]:
        """Число записей по дням UTC; удалённые в корзину не считаются."""
        return {
            day: int(n)
            for day, n in _rows(
                f"select created_at::date, count(*) from {table} "
                "where deleted_at is null and created_at >= %s group by 1",
                [self.start()],
            )
        }

    # ── Деньги ──

    def unlock_conversion(self) -> float:
        """
        Конверсия просмотра карточки в раскрытие контакта — главный
        показатель монетизации: именно здесь площадка зарабатывает.
        """
        (views,) = _row(
            "select coalesce(sum(views_count), 0) from listings where deleted_at is null"
        )
        (unlocks,) = _row("select count(*) from contact_unlocks")
        views = _int(views)

        return php_round(unlocks / views * 100, 2) if views > 0 else 0.0

    def average_payment(self) -> int:
        """Средний чек полученных платежей за период."""
        (average,) = _row(
            f"select avg(amount) from payments where {RECEIVED} and paid_at >= %s",
            [self.start()],
        )

        return _int(average)
