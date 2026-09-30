"""
Виджеты стартового экрана — по одному на виджет Filament
(app/Filament/Widgets/*.php), в том же порядке ($sort и порядок
регистрации в AdminPanelProvider) и с теми же условиями показа (canView).

У каждого виджета две части: visible(admin) — кому виден, build(ctx) —
что показать; build возвращает простые словари, шаблон
(templates/admin/dashboard/) только выводит их. Шаблонов четыре на все
виджеты: таблица, плитки с числами, воронка и график.

Что отличается от Filament:

- «Роль ещё не назначена» — единственный виджет, когда показан: у
  Filament рядом с ним оставались бы новые компании менеджера
  направления, у которого сняли все права;
- «Задачи на сегодня» — по ташкентским суткам, как отбор «На сегодня»
  в разделе задач: Filament сравнивал дату срока по UTC, и задача на
  01:00 завтрашнего утра по Ташкенту попадала в сегодняшние;
- «Новые компании» показывают город (или страну): у Filament строка
  компании с городом падала — $record->city?->name у модели City не
  столбец, а метод;
- у таблиц вместо листания — число всех записей и ссылка в раздел.

Главная ничего не пишет: только чтение.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import connections
from django.db.models import Case, Count, IntegerField, Min, Q, QuerySet, Value, When
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from savdex import access
from savdex.accounts.models import User
from savdex.adminsite import _admin_of, site
from savdex.crm.admin import CrmAdmin, _today, when
from savdex.crm.models import LEAD_SOURCES, LEAD_STATUSES, SUBJECTS, Lead, SoftDeleting, Task
from savdex.dashboard.metrics import Metric, PlatformMetrics, php_number, php_round
from savdex.data.models import CompanyRecord, Listing
from savdex.geo.models import City, Country
from savdex.moderation.admin import _short
from savdex.moderation.models import CompanyDocument, Review
from savdex.site.models import NewsPost, Page
from savdex.support.models import PRIORITIES, STATUS_CLOSED, STATUSES, Ticket
from savdex.web.shared import _calendar_diff

#: Строк в таблице виджета — paginated([5]) у Filament
ROWS = 5


@dataclass(frozen=True)
class Context:
    """Кто смотрит и когда: одно «сейчас» на всю страницу."""

    request: HttpRequest
    admin: access.Admin
    now: datetime


@dataclass(frozen=True)
class Widget:
    key: str
    template: str
    visible: Callable[[access.Admin], bool]
    build: Callable[[Context], dict[str, Any]]


# ── Общее ───────────────────────────────────────────────────────────

#: Формы слов Carbon (ru) для diffForHumans(syntax: true): «3 дня»
_UNITS = {
    "year": ("год", "года", "лет"),
    "month": ("месяц", "месяца", "месяцев"),
    "week": ("неделя", "недели", "недель"),
    "day": ("день", "дня", "дней"),
    "hour": ("час", "часа", "часов"),
    "minute": ("минута", "минуты", "минут"),
    "second": ("секунда", "секунды", "секунд"),
}


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return forms[0]

    return forms[1] if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else forms[2]


def age(moment: datetime | None, now: datetime) -> str:
    """
    $date->diffForHumans(syntax: true): «3 дня», без «назад» — одна
    старшая единица, округление вниз, недели — из дней, месяцы и годы —
    по календарю (DateTime::diff).
    """
    if moment is None:
        return ""

    earlier, later = sorted((moment.astimezone(UTC), now.astimezone(UTC)))
    y, mo, d, h, mi, s = _calendar_diff(earlier, later)

    for unit, count in (
        ("year", y),
        ("month", mo),
        ("week", d // 7),
        ("day", d),
        ("hour", h),
        ("minute", mi),
        ("second", s),
    ):
        if count > 0:
            return f"{count} {_plural(count, _UNITS[unit])}"

    return "0 секунд"


def hours(moment: datetime | None, now: datetime) -> float:
    """$date->diffInHours(): сколько часов прошло, с дробной частью."""
    return 0.0 if moment is None else (now - moment).total_seconds() / 3600


def number(value: float) -> str:
    """number_format($value, 0, ',', ' '): «1 234 567»."""
    return f"{int(php_round(value)):,}".replace(",", " ")


def _aware(value: Any) -> datetime | None:  # noqa: ANN401
    """Время из столбца timestamp без пояса — в UTC, как пишет Laravel."""
    if value is None:
        return None

    return timezone.make_aware(value, UTC) if timezone.is_naive(value) else value


def _name(user: User | None) -> str | None:
    """Связь с пользователем у Eloquent: удалённый в корзину — как не найденный."""
    return user.name if user is not None and user.deleted_at is None else None


def cell(
    text: str | None,
    *,
    sub: str | None = None,
    tone: str | None = None,
    badge: bool = False,
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Ячейка таблицы: текст, строка под ним, цвет, значок, заглушка для пустого."""
    empty = text is None or text == ""

    return {
        "text": placeholder if empty and placeholder is not None else (text or ""),
        "sub": sub or None,
        "tone": "gray" if empty and placeholder is not None else tone,
        "badge": badge and not empty,
    }


def table(
    *,
    heading: str,
    description: str,
    columns: Sequence[str],
    rows: list[dict[str, Any]],
    total: int,
    more_url: str,
    empty: tuple[str, str],
) -> dict[str, Any]:
    return {
        "heading": heading,
        "description": description,
        "columns": list(columns),
        "rows": rows,
        "total": total,
        "more_url": more_url if total > len(rows) else None,
        "empty_heading": empty[0],
        "empty_description": empty[1],
    }


def _change(model: str, pk: int) -> str:
    return reverse(f"savdex_admin:{model}_change", args=[pk])


def _list(model: str, query: str = "") -> str:
    return reverse(f"savdex_admin:{model}_changelist") + query


# ── Роль ещё не назначена ───────────────────────────────────────────


def awaiting_role_visible(admin_: access.Admin) -> bool:
    """
    Права, а не пустая роль: роль может быть назначена, но все её права
    сняты личной настройкой — человек видит ту же пустоту.
    """
    return (
        admin_.is_admin
        and admin_.status == "active"
        and not admin_.is_superadmin
        and not admin_.abilities()
    )


def awaiting_role(ctx: Context) -> dict[str, Any]:
    return {}


# ── Лиды в работе ───────────────────────────────────────────────────


def my_leads(ctx: Context) -> dict[str, Any]:
    """
    Свои и ничьи открытые лиды — то же, что продавец видит в разделе
    лидов (его «только свои»), старые сверху: остывший лид дешевле.
    """
    queryset = (
        site._registry[Lead].get_queryset(ctx.request).exclude(status__in=("converted", "lost"))
    )
    leads = queryset.select_related("company", "contact", "owner").order_by("created_at", "id")

    return table(
        heading="Лиды в работе",
        description="Ваши и нераспределённые — те, что ждут звонка",
        columns=("Обращение", "Кто", "Статус", "Ответственный", "Ждёт"),
        rows=[
            {
                "url": _change("crm_lead", lead.pk),
                "cells": [
                    cell(_short(lead.title, 60), sub=LEAD_SOURCES.get(lead.source, lead.source)),
                    cell(
                        lead.contact_label() or "—",
                        sub=CrmAdmin.company_label(lead.company),
                    ),
                    cell(
                        LEAD_STATUSES.get(lead.status, lead.status),
                        badge=True,
                        tone="warning" if lead.status == "new" else "info",
                    ),
                    cell(_name(lead.owner), placeholder="не распределён"),
                    # «3 дня» читается быстрее даты: важно не когда пришёл,
                    # а сколько уже лежит
                    cell(
                        age(lead.created_at, ctx.now),
                        tone="danger" if hours(lead.created_at, ctx.now) >= 72 else "gray",
                    ),
                ],
            }
            for lead in leads[:ROWS]
        ],
        total=queryset.count(),
        more_url=_list("crm_lead"),
        empty=("Лидов в работе нет", "Новые обращения появятся здесь сами."),
    )


# ── Задачи на сегодня ───────────────────────────────────────────────


def _with_subjects(tasks: list[Task]) -> list[Task]:
    """Лиды и сделки задач — одним запросом на вид, а не по запросу на строку."""
    wanted: dict[str, set[int]] = {}

    for task in tasks:
        if task.subject_type in SUBJECTS and task.subject_id is not None:
            wanted.setdefault(task.subject_type, set()).add(int(task.subject_id))

    found: dict[tuple[str, int], SoftDeleting] = {
        (kind, int(obj.pk)): obj
        for kind, ids in wanted.items()
        for obj in SUBJECTS[kind][1].objects.filter(pk__in=ids)
    }

    for task in tasks:
        if task.subject_type in SUBJECTS and task.subject_id is not None:
            key = (str(task.subject_type), int(task.subject_id))
            # Тот же кэш, что у WithSubject.subject(): не найден — удалён
            task.__dict__.setdefault("_subject_cache", {})[key] = found.get(key)

    return tasks


def my_tasks(ctx: Context) -> dict[str, Any]:
    """
    Просроченные и сегодняшние вместе, просроченные первыми. Без срока
    сюда не попадают — они не про сегодня. «Сегодня» — по Ташкенту.
    """
    _, tomorrow = _today()
    queryset = (
        site._registry[Task]
        .get_queryset(ctx.request)
        .filter(done_at__isnull=True, due_at__isnull=False, due_at__lt=tomorrow)
    )
    tasks = _with_subjects(
        list(queryset.select_related("assignee").order_by("due_at", "id")[:ROWS])
    )

    return table(
        heading="Задачи на сегодня",
        description="Просроченные и сегодняшние",
        columns=("Что сделать", "Срок", "Исполнитель"),
        rows=[
            {
                "url": _change("crm_task", task.pk),
                "cells": [
                    cell(_short(task.title, 70), sub=task.subject_title()),
                    cell(
                        when(task.due_at),
                        tone="danger" if task.is_overdue else "gray",
                        sub="просрочена" if task.is_overdue else None,
                    ),
                    cell(_name(task.assignee), placeholder="—"),
                ],
            }
            for task in tasks
        ],
        total=queryset.count(),
        more_url=_list("crm_task"),
        empty=("На сегодня задач нет", "Сюда попадают задачи со сроком сегодня и раньше."),
    )


# ── Новые компании ──────────────────────────────────────────────────

#: Роль менеджера направления → его направление (primary_role)
DIRECTIONS = {"supplier_manager": "supplier", "buyer_manager": "buyer"}


def _direction(admin_: access.Admin) -> str | None:
    return DIRECTIONS.get(admin_.role or "")


def intake_visible(admin_: access.Admin) -> bool:
    return _direction(admin_) is not None or admin_.is_superadmin


def _places(companies: list[CompanyRecord]) -> dict[int, str]:
    """Город компании, иначе страна — названия по-русски (с откатом на адрес и код)."""
    cities = {
        c.pk: c.name("ru")
        for c in City.objects.filter(
            pk__in={x.city_id for x in companies if x.city_id}
        ).prefetch_related("translations")
    }
    countries = {
        c.pk: c.name("ru")
        for c in Country.objects.filter(
            pk__in={x.country_id for x in companies if x.country_id and x.city_id not in cities}
        ).prefetch_related("translations")
    }

    return {
        x.pk: cities.get(x.city_id or 0) or countries.get(x.country_id or 0) or ""
        for x in companies
    }


def intake_queue(ctx: Context) -> dict[str, Any]:
    """
    Зарегистрировавшиеся за две недели, свежие сверху: компания, пришедшая
    утром, вечером уже смотрит на конкурентов. «both» — и тем и другим
    менеджерам; у суперадмина направления нет — он видит всех.
    """
    direction = _direction(ctx.admin)
    queryset = CompanyRecord.objects.filter(
        deleted_at__isnull=True, created_at__gte=ctx.now - timedelta(weeks=2)
    )

    if direction is not None:
        queryset = queryset.filter(primary_role__in=(direction, "both"))

    companies = list(queryset.order_by("-created_at", "-id")[:ROWS])
    places = _places(companies)
    who = {"supplier": "поставщики", "buyer": "покупатели"}.get(direction or "", "компании")
    nobody = {"supplier": "поставщиков", "buyer": "покупателей"}.get(direction or "", "компаний")

    def row(company: CompanyRecord) -> dict[str, Any]:
        level = company.verification_level
        cells = [
            cell(_short(company.name, 50), sub=places[company.pk]),
            cell(
                "Проверена+" if level >= 2 else ("Проверена" if level == 1 else "Не проверена"),
                badge=True,
                tone="success" if level > 0 else "gray",
            ),
            cell(company.phone, placeholder="не указан"),
            cell(age(company.created_at, ctx.now)),
        ]

        # Менеджеру направления колонка не нужна: у него и так только свои
        if direction is None:
            label = {"supplier": "Поставщик", "buyer": "Покупатель"}.get(
                company.primary_role, "И то и другое"
            )
            cells.insert(1, cell(label, badge=True, tone="gray"))

        return {"url": _change("data_companyrecord", company.pk), "cells": cells}

    columns = ["Компания", "Проверка", "Телефон", "Появилась"]

    if direction is None:
        columns.insert(1, "Направление")

    return table(
        heading=f"Новые {who}",
        description="Зарегистрировались за последние две недели",
        columns=columns,
        rows=[row(company) for company in companies],
        total=queryset.count(),
        more_url=_list("data_companyrecord"),
        empty=(f"Новых {nobody} нет", "За две недели никто не зарегистрировался."),
    )


# ── Очередь на проверку ─────────────────────────────────────────────


def moderation_visible(admin_: access.Admin) -> bool:
    # Жалобы — только плиткой: у Filament canView их не спрашивал
    return any(
        admin_.can(f"{section}.moderate") for section in ("listings", "documents", "reviews")
    )


def _queue(
    label: str, count: int, oldest: datetime | None, url: str, now: datetime
) -> dict[str, Any]:
    """Число, возраст самого старого и ссылка в раздел."""
    stat: dict[str, Any] = {"label": label, "value": str(count), "url": url, "trend": None}

    if count == 0:
        return stat | {"description": "очередь пуста", "tone": "success"}

    if oldest is None:
        return stat | {"description": "ждут решения", "tone": "warning"}

    return stat | {
        "description": f"самое старое ждёт {age(oldest, now)}",
        # Два часа — обещанный площадкой срок проверки
        "tone": "danger" if hours(oldest, now) >= 2 else "warning",
    }


def _oldest(queryset: QuerySet[Any], column: str) -> tuple[int, datetime | None]:
    found = queryset.aggregate(n=Count("pk"), oldest=Min(column))

    return int(found["n"]), _aware(found["oldest"])


def moderation_queue(ctx: Context) -> dict[str, Any]:
    """
    Разбивка по типам, а не общий счётчик: «тридцать объявлений и один
    документ» говорит, с чего начинать. Под числом — сколько ждёт тот,
    кто ждёт дольше всех.
    """
    can = ctx.admin.can
    stats = []

    if can("listings.moderate"):
        stats.append(
            _queue(
                "Объявления",
                *_oldest(
                    Listing.objects.filter(deleted_at__isnull=True, status="moderation"),
                    "updated_at",
                ),
                _list("data_listing", "?status=moderation"),
                ctx.now,
            )
        )

    if can("documents.moderate"):
        stats.append(
            _queue(
                "Документы",
                *_oldest(CompanyDocument.objects.filter(moderation_status="pending"), "created_at"),
                _list("moderation_companydocument"),
                ctx.now,
            )
        )

    if can("reviews.moderate"):
        stats.append(
            _queue(
                "Споры по отзывам",
                *_oldest(Review.objects.filter(dispute_status="pending"), "updated_at"),
                _list("moderation_review"),
                ctx.now,
            )
        )

    if can("complaints.moderate"):
        with connections["default"].cursor() as cursor:
            cursor.execute(
                "select count(*), min(complained_at) from contact_unlocks "
                "where complaint_status = 'pending'"
            )
            count, oldest = cursor.fetchone()

        stats.append(
            _queue(
                "Жалобы на контакты",
                int(count),
                _aware(oldest),
                _list("finance_complaint"),
                ctx.now,
            )
        )

    return {"heading": "Очередь на проверку", "stats": stats}


# ── Открытые обращения ──────────────────────────────────────────────


def support_queue(ctx: Context) -> dict[str, Any]:
    """
    Свои сверху, потом ничьи, потом чужие; внутри — срочные вперёд,
    дальше по давности.
    """
    queryset = Ticket.objects.exclude(status=STATUS_CLOSED)
    tickets = (
        queryset.select_related("user", "company", "assignee")
        .annotate(
            whose=Case(
                When(assignee_id=ctx.admin.id, then=Value(0)),
                When(assignee__isnull=True, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            urgency=Case(
                When(priority="high", then=Value(0)),
                When(priority="normal", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
        )
        .order_by("whose", "urgency", "created_at", "id")
    )

    return table(
        heading="Открытые обращения",
        description="Ваши сверху, за ними ничьи",
        columns=("Тема", "Важность", "Статус", "Ведёт", "Ждёт"),
        rows=[
            {
                "url": _change("support_ticket", ticket.pk),
                "cells": [
                    cell(_short(ticket.subject, 60), sub=ticket.author()),
                    cell(
                        PRIORITIES.get(ticket.priority, ticket.priority),
                        badge=True,
                        tone={"high": "danger", "low": "gray"}.get(ticket.priority, "info"),
                    ),
                    cell(STATUSES.get(ticket.status, ticket.status), badge=True, tone="warning"),
                    cell(_name(ticket.assignee), placeholder="никто"),
                    cell(
                        age(ticket.created_at, ctx.now),
                        tone="danger" if hours(ticket.created_at, ctx.now) >= 24 else "gray",
                    ),
                ],
            }
            for ticket in tickets[:ROWS]
        ],
        total=queryset.count(),
        more_url=_list("support_ticket"),
        empty=("Открытых обращений нет", "Всё разобрано."),
    )


# ── Контент в работе ────────────────────────────────────────────────


def content_drafts(ctx: Context) -> dict[str, Any]:
    """Черновики и запланированное; опубликованное внимания не требует."""
    news = NewsPost.objects.aggregate(
        drafts=Count("pk", filter=Q(is_published=False)),
        # Опубликованная новость с будущей датой ещё не видна читателю:
        # это третье состояние, а не второе
        scheduled=Count(
            "pk", filter=Q(is_published=True, published_at__isnull=False, published_at__gt=ctx.now)
        ),
    )
    drafts, scheduled = int(news["drafts"]), int(news["scheduled"])
    hidden = Page.objects.filter(is_published=False).count()

    return {
        "heading": "Контент в работе",
        "stats": [
            {
                "label": "Черновики новостей",
                "value": str(drafts),
                "description": "ждут публикации" if drafts > 0 else "всё опубликовано",
                "tone": "warning" if drafts > 0 else "success",
                "url": _list("site_newspost", "?status=draft"),
                "trend": None,
            },
            {
                "label": "Выйдут по расписанию",
                "value": str(scheduled),
                "description": "уже назначены" if scheduled > 0 else "ничего не запланировано",
                "tone": "info",
                "url": _list("site_newspost", "?status=scheduled"),
                "trend": None,
            },
            {
                "label": "Скрытые страницы",
                "value": str(hidden),
                "description": "не видны посетителям" if hidden > 0 else "все страницы открыты",
                "tone": "gray" if hidden > 0 else "success",
                "url": _list("site_page", "?is_published__exact=0"),
                "trend": None,
            },
        ],
    }


# ── Показатели площадки ─────────────────────────────────────────────


def dashboard_visible(admin_: access.Admin) -> bool:
    """
    Общая картина площадки — не всем: продавцу, модератору и контенту
    она в границах роли не положена, у них свой стартовый экран.
    """
    return admin_.can("dashboard.view")


def _trend(label: str, metric: Metric) -> dict[str, Any]:
    stat: dict[str, Any] = {"label": label, "value": number(metric["value"]), "url": None}
    delta = metric["delta"]

    # Без прошлого периода сравнивать не с чем — говорим прямо, вместо
    # «+100 %», которое читается как рост
    if delta is None:
        return stat | {"description": "нет данных за прошлый период", "tone": "gray", "trend": None}

    return stat | {
        "description": f"{'+' if delta > 0 else ''}{php_number(delta)} % к прошлым 30 дням",
        "trend": "up" if delta >= 0 else "down",
        "tone": "success" if delta > 0 else ("danger" if delta < 0 else "gray"),
    }


def platform_stats(ctx: Context) -> dict[str, Any]:
    """Прирост за 30 дней против прошлых 30 — а не «всего», которое растёт всегда."""
    metrics = PlatformMetrics(now=ctx.now)
    summary = metrics.summary()
    stats = [
        _trend("Новых компаний", summary["companies"]),
        _trend("Новых объявлений", summary["listings"]),
        _trend("Раскрытий контактов", summary["unlocks"])
        | {"description": f"Конверсия из просмотра: {php_number(metrics.unlock_conversion())} %"},
    ]

    # Выручка — только тем, кому положены финансы: раздел закрыт, а цифра
    # из него на первом экране — утечка, оформленная как удобство
    if ctx.admin.can("finreports.view"):
        stats.append(
            _trend("Выручка, сум", summary["revenue"])
            | {"description": f"Средний чек: {number(metrics.average_payment())} сум"}
        )

    return {"heading": "За последние 30 дней", "stats": stats}


def activation_funnel(ctx: Context) -> dict[str, Any]:
    """Воронка активации, здоровье площадки и категории — рядом."""
    metrics = PlatformMetrics(now=ctx.now)
    steps = metrics.activation_funnel()
    rows = []

    for i, step in enumerate(steps):
        # Потери — к предыдущему шагу: доля от всех не показывает, где провал
        prev = steps[i - 1]["value"] if i > 0 else 0
        drop = int(php_round((prev - step["value"]) / prev * 100)) if prev > 0 else 0
        rows.append(
            {
                "label": step["label"],
                "value": number(step["value"]),
                "share": php_number(step["share"]),
                "width": php_number(max(step["share"], 1)),
                "hint": step["hint"],
                "drop": drop if drop > 0 else None,
                # Провал больше половины — почти всегда сломанный шаг
                "drop_tone": "danger" if drop >= 50 else ("warning" if drop >= 25 else "gray"),
            }
        )

    categories = metrics.top_categories()
    top = max((c["listings"] for c in categories), default=0) or 1

    return {
        "steps": rows,
        "health": metrics.health(),
        "categories": [
            {**c, "width": php_number(php_round(c["listings"] / top * 100))} for c in categories
        ],
    }


# ── Регистрации по дням ─────────────────────────────────────────────

#: Размеры графика в точках viewBox
_W, _H = 720, 220
_LEFT, _RIGHT, _TOP, _BOTTOM = 36, 12, 12, 26


def _step(top: int) -> int:
    """Шаг делений оси: целые (регистраций не бывает 2,5), не больше пяти делений."""
    for base in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if top / base <= 5:
            return base

    return int(10 ** len(str(top)))


def registrations_chart(ctx: Context) -> dict[str, Any]:
    """
    Две линии: разрыв между пользователями и компаниями — люди,
    застрявшие на втором шаге регистрации. График — SVG без скриптов,
    подсказка по дню — при наведении, числа — ещё и таблицей.
    """
    data = PlatformMetrics(now=ctx.now).registrations_by_day()
    labels, users, companies = data["labels"], data["users"], data["companies"]
    step = _step(max([*users, *companies, 1]))
    top = max(step, -(-max([*users, *companies, 1]) // step) * step)
    width, height = _W - _LEFT - _RIGHT, _H - _TOP - _BOTTOM
    count = len(labels)
    gap = width / max(count - 1, 1)

    def x(i: int) -> float:
        return round(_LEFT + i * gap, 1)

    def y(value: int) -> float:
        return round(_TOP + height - value / top * height, 1)

    def line(values: list[int]) -> str:
        return " ".join(f"{'M' if i == 0 else 'L'}{x(i)},{y(v)}" for i, v in enumerate(values))

    def area(values: list[int]) -> str:
        return f"{line(values)} L{x(count - 1)},{y(0)} L{x(0)},{y(0)} Z"

    return {
        "width": _W,
        "height": _H,
        "left": _LEFT,
        "right": _W - _RIGHT,
        "baseline": y(0),
        "ticks": [{"y": y(v), "label": number(v)} for v in range(0, top + 1, step)],
        "days": [
            {
                "x": x(i),
                "label": label,
                # Подпись у каждого пятого дня и у последнего — иначе сливаются
                "show": i % 5 == (count - 1) % 5,
                "band_x": round(x(i) - gap / 2, 1),
                "users": users[i],
                "companies": companies[i],
            }
            for i, label in enumerate(labels)
        ],
        "band": round(gap, 1),
        "series": [
            {
                "key": key,
                "label": label,
                "line": line(values),
                "area": area(values),
                # Точка на сегодняшнем дне — где линия кончается
                "end_x": x(count - 1),
                "end_y": y(values[-1]),
            }
            for key, label, values in (
                ("users", "Пользователи", users),
                ("companies", "Компании", companies),
            )
        ],
        "total_users": sum(users),
        "total_companies": sum(companies),
    }


# ── Деньги за сегодня ───────────────────────────────────────────────


def _sum(money: int) -> str:
    return f"{int(money):,}".replace(",", " ") + " сум"


def finance_today(ctx: Context) -> dict[str, Any]:
    """
    FinanceToday: сколько пришло сегодня, сколько ждёт оплаты и сколько
    заявлено к возврату. Первое — выручка, два других — долг перед
    клиентом. «Сегодня» — ташкентское (Business::today).
    """
    from savdex.finance import reports

    today = timezone.localtime(ctx.now).date()

    with connections["default"].cursor() as cursor:
        cursor.execute(
            f"select count(*), coalesce(sum(amount), 0) from payments where {reports.RECEIVED} "
            "and paid_at between %s and %s",
            [reports.start_of_day(today), reports.end_of_day(today)],
        )
        paid, paid_sum = cursor.fetchone()
        cursor.execute(
            "select count(*), coalesce(sum(amount), 0) from payments where status = 'pending'"
        )
        pending, pending_sum = cursor.fetchone()
        cursor.execute(
            "select count(*), coalesce(sum(amount), 0) from refunds where status = 'requested'"
        )
        refunds, refunds_sum = cursor.fetchone()

    payments_url = _list("finance_payment")

    return {
        "heading": "Деньги за сегодня",
        "stats": [
            {
                "label": "Оплачено сегодня",
                "value": _sum(paid_sum),
                "description": f"{paid} {_plural(paid, ('счёт', 'счёта', 'счетов'))}",
                "tone": "success",
                "url": payments_url,
                "trend": None,
            },
            {
                "label": "Ждут оплаты",
                "value": str(pending),
                # Выставленные, но неоплаченные — ещё не выручка
                "description": f"на {_sum(pending_sum)}",
                "tone": "warning" if pending > 0 else "gray",
                "url": payments_url,
                "trend": None,
            },
            {
                "label": "Возвраты на решении",
                "value": str(refunds),
                "description": f"на {_sum(refunds_sum)}" if refunds > 0 else "ничего не ждёт",
                "tone": "danger" if refunds > 0 else "gray",
                "url": _list("finance_refund"),
                "trend": None,
            },
        ],
    }


# ── Порядок ─────────────────────────────────────────────────────────

AWAITING_ROLE = Widget(
    "awaiting_role", "admin/dashboard/awaiting_role.html", awaiting_role_visible, awaiting_role
)

#: Порядок Filament: $sort, при равном — порядок в AdminPanelProvider
WIDGETS: tuple[Widget, ...] = (
    Widget("my_leads", "admin/dashboard/table.html", lambda a: a.can("leads.view"), my_leads),
    Widget("my_tasks", "admin/dashboard/table.html", lambda a: a.can("tasks.view"), my_tasks),
    Widget("intake_queue", "admin/dashboard/table.html", intake_visible, intake_queue),
    Widget("moderation_queue", "admin/dashboard/stats.html", moderation_visible, moderation_queue),
    Widget(
        "support_queue",
        "admin/dashboard/table.html",
        lambda a: a.can("support.view"),
        support_queue,
    ),
    Widget(
        "finance_today",
        "admin/dashboard/stats.html",
        lambda a: a.can("payments.view"),
        finance_today,
    ),
    Widget(
        "content_drafts",
        "admin/dashboard/stats.html",
        lambda a: a.can("content.edit"),
        content_drafts,
    ),
    Widget("platform_stats", "admin/dashboard/stats.html", dashboard_visible, platform_stats),
    Widget(
        "activation_funnel", "admin/dashboard/funnel.html", dashboard_visible, activation_funnel
    ),
    Widget(
        "registrations_chart", "admin/dashboard/chart.html", dashboard_visible, registrations_chart
    ),
)


def visible(admin_: access.Admin) -> list[Widget]:
    """Виджеты, которые видит сотрудник, по порядку."""
    if awaiting_role_visible(admin_):
        # Если он показан, других всё равно нет: у человека нет прав
        return [AWAITING_ROLE]

    return [widget for widget in WIDGETS if widget.visible(admin_)]


def for_request(request: HttpRequest) -> list[dict[str, Any]]:
    """Стартовый экран сотрудника: по словарю на виджет, с именем шаблона."""
    ctx = Context(request=request, admin=_admin_of(request), now=timezone.now())

    return [
        {"key": widget.key, "template": widget.template, **widget.build(ctx)}
        for widget in visible(ctx.admin)
    ]
