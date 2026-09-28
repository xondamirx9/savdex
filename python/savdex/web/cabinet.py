"""
Кабинет на Django (этап 5, шаг 2) — страницы, которые открываются
GET-запросом. Формы по-прежнему отправляются в Laravel.

Каждой странице кабинета предшествуют посредники маршрутов Laravel:

- auth (Authenticate): гость уходит на вход, а адрес страницы
  запоминается в сессии (url.intended) — после входа Laravel вернёт
  туда; XHR тоже (JSON с 401 у Laravel — только для api/*);
- RequirePasswordChange: пароль выдан вручную — на смену пароля, с
  предупреждением в сессии.

Счётчики у пунктов меню (counts) — HandleInertiaRequests::cabinetCounts:
только на адресах кабинета и только у человека с компанией.

Сверка с настоящим Laravel — tests/test_web_cabinet.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex.web import inertia, locales, session, ui
from savdex.web.home import _filled, completeness, php_round
from savdex.web.phpquery import laravel_input, php_int
from savdex.web.request import _expects_json, context
from savdex.web.seo import Seo
from savdex.web.shared import Context, ago

#: CabinetMetrics: окно показателей
DAYS = 30


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _count(query: str, params: list[Any]) -> int:
    return int(_rows(query, params)[0]["n"])


# ── Посредники маршрутов ────────────────────────────────────────────


def _redirect(ctx: Context, path: str) -> HttpResponse:
    """redirect()->route(…): адрес на хосте; с префиксом — LocalizeUrl его сохранит."""
    target = ctx.url(path)

    if ctx.url_locale is not None:
        target = locales.url(ctx.root, path, ctx.url_locale)

    return HttpResponseRedirect(target)


def page(request: HttpRequest) -> Context | HttpResponse:
    """
    Контекст страницы кабинета — или ответ посредника.

    Порядок, как после сортировки посредников у Laravel: auth стоит в
    списке приоритетов и встаёт раньше SetLocale, поэтому гость уходит
    на вход, не запомнив язык из адреса; RequirePasswordChange — после
    SetLocale и HandleInertiaRequests.
    """
    first = context(request, redirect=False)

    if isinstance(first, HttpResponse):
        return first

    refused = _authenticate(first)

    if refused is not None:
        return refused

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return _require_password_change(ctx) or ctx


def _store(ctx: Context) -> session.Store | None:
    started = session.start(ctx.request)

    return started[0] if started is not None else None


def _authenticate(ctx: Context) -> HttpResponse | None:
    """Authenticate: гость — на вход, адрес GET-страницы — в url.intended."""
    if ctx.user is not None:
        return None

    # JSON с 401 у Laravel — только для api/* (shouldRenderJsonWhen в
    # bootstrap/app.php): XHR страницы тоже уходит на вход
    store = _store(ctx)

    # Redirector::guest: страница — её адрес; XHR, ждущий JSON, — previous()
    if store is not None:
        if ctx.request.method == "GET" and not _expects_json(ctx.request):
            intended = store.full_url
        else:
            referer = ctx.request.headers.get("Referer")
            intended = referer or store.get("_previous.url") or ctx.url("/")

        store.put("url.intended", intended)

    return _redirect(ctx, "/login")


def _require_password_change(ctx: Context) -> HttpResponse | None:
    """RequirePasswordChange: выданный вручную пароль — сначала сменить."""
    if ctx.user is None or not ctx.user["must_change_password"]:
        return None

    store = _store(ctx)

    if store is not None:
        store.flash("warning", ctx.t("messages.auth.must_change_password"))

    return _redirect(ctx, "/password/change")


def company_of(ctx: Context) -> dict[str, Any] | None:
    """$request->user()->company: компания не в корзине."""
    user = ctx.user

    if user is None or user["company_id"] is None:
        return None

    rows = _rows(
        "select * from companies where id = %s and deleted_at is null", [user["company_id"]]
    )

    return rows[0] if rows else None


def counts(ctx: Context) -> dict[str, int] | None:
    """HandleInertiaRequests::cabinetCounts."""
    if ctx.path != "/cabinet" and not ctx.path.startswith("/cabinet/"):
        return None

    company = company_of(ctx)

    if company is None:
        return None

    cid = company["id"]

    return {
        "listings": _count(
            "select count(*) as n from listings where company_id = %s "
            "and status = 'active' and deleted_at is null",
            [cid],
        ),
        "contacts": _count(
            "select count(*) as n from contact_unlocks where company_id = %s", [cid]
        ),
        "incoming": _count(
            "select count(*) as n from contact_unlocks where target_company_id = %s", [cid]
        ),
        "reviews": _count(
            "select count(*) as n from reviews where company_id = %s and status = 'published'",
            [cid],
        ),
        "chats": unread_threads(cid),
    }


def unread_threads(company_id: int) -> int:
    """MessageThread::unreadThreadsFor: разговоры с непрочитанным от собеседника."""

    def unread(read_column: str) -> str:
        return (
            "exists (select 1 from messages where messages.thread_id = message_threads.id "
            "and messages.company_id != %s and messages.created_at > "
            f"coalesce(message_threads.{read_column}, '1970-01-01 00:00:00'))"
        )

    return _count(
        "select count(*) as n from message_threads where "
        f"((buyer_company_id = %s and {unread('buyer_read_at')}) "
        f"or (seller_company_id = %s and {unread('seller_read_at')}))",
        [company_id, company_id, company_id, company_id],
    )


# ── Сводка /cabinet (DashboardController) ───────────────────────────


def dashboard(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Dashboard", dashboard_props(ctx), _seo(ctx))


def _seo(ctx: Context) -> Seo:
    """Страница без своего SEO — только заголовок сайта по умолчанию."""
    return Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)


def dashboard_props(ctx: Context) -> dict[str, Any]:
    company = company_of(ctx)

    if company is None:
        return {
            "company": None,
            "metrics": None,
            "series": None,
            "events": [],
            "limits": None,
            "plan": None,
        }

    cid = company["id"]
    has_documents = bool(
        _rows(
            "select 1 from company_documents where company_id = %s "
            "and moderation_status = 'approved' limit 1",
            [cid],
        )
    )
    plan = company_plan(cid)
    wallets = _rows("select * from wallets where company_id = %s limit 1", [cid])
    wallet = wallets[0] if wallets else None
    subscription = active_subscription(cid)
    active = _count(
        "select count(*) as n from listings where company_id = %s "
        "and status = 'active' and deleted_at is null",
        [cid],
    )
    now = datetime.now(UTC).replace(tzinfo=None)

    return {
        "company": {
            "name": company["name"],
            "slug": company["slug"],
            "completeness": completeness(company, has_documents),
            "missing": _missing(ctx, company, has_documents),
        },
        "metrics": summary(cid),
        "series": series(cid),
        "events": [
            {
                "id": e["id"],
                "type": e["type"],
                "tone": e["tone"],
                "message": e["message"],
                "url": e["url"],
                "ago": ago(e["created_at"], ctx.locale),
            }
            for e in _rows(
                "select * from activity_events where company_id = %s "
                "order by created_at desc, id desc limit 5",
                [cid],
            )
        ],
        "limits": {
            "listings": {"used": active, "total": plan["listings_limit"]},
            "contacts": {
                "used": (wallet or {}).get("contacts_used_this_period") or 0,
                "total": plan["contacts_limit"],
            },
            "promo": {
                "used": max(
                    0, (plan["promo_units"] or 0) - ((wallet or {}).get("promo_units") or 0)
                ),
                "total": plan["promo_units"],
            },
            "resets_at": _date((wallet or {}).get("period_resets_at")),
        },
        "plan": {
            "name": plan["name"],
            "until": _date(subscription["ends_at"] if subscription else None),
        },
        "expiring": _count(
            "select count(*) as n from listings where company_id = %s and status = 'active' "
            "and deleted_at is null and expires_at is not null and expires_at <= %s",
            [cid, now + timedelta(days=7)],
        ),
        "drafts": _count(
            "select count(*) as n from listings where company_id = %s "
            "and status = 'draft' and deleted_at is null",
            [cid],
        ),
    }


def _date(value: datetime | None) -> str | None:
    """translatedFormat('d.m.Y') — цифры, от языка не зависят."""
    return value.strftime("%d.%m.%Y") if value is not None else None


def _missing(ctx: Context, company: dict[str, Any], has_documents: bool) -> list[str]:
    """Company::missingProfileFields: подписи из словаря company."""
    checks = (
        ("tin", not _filled(company["tin"])),
        ("address", not _filled(company["address"])),
        ("description", len(company["description"] or "") < 100),
        ("logo", not _filled(company["logo_path"])),
        ("documents", not has_documents),
    )

    return [ui.group_t(f"company.field.{key}", ctx.locale) for key, missing in checks if missing]


# ── Тариф ───────────────────────────────────────────────────────────


def active_subscription(company_id: int) -> dict[str, Any] | None:
    """Company::subscription: действующая, по сроку тоже; последняя по id."""
    rows = _rows(
        "select * from subscriptions where company_id = %s and status = 'active' "
        "and (ends_at is null or ends_at > %s) order by id desc limit 1",
        [company_id, datetime.now(UTC).replace(tzinfo=None)],
    )

    return rows[0] if rows else None


#: Company::plan — Free по умолчанию, если справочник тарифов пуст
_FREE_DEFAULT = {
    "code": "free",
    "name": "Free",
    "listings_limit": 4,
    "contacts_limit": 3,
    "promo_units": 0,
}


def company_plan(company_id: int) -> dict[str, Any]:
    """Company::plan: тариф действующей подписки, иначе Free."""
    subscription = active_subscription(company_id)

    if subscription is not None:
        rows = _rows("select * from plans where id = %s", [subscription["plan_id"]])

        if rows:
            return rows[0]

    rows = _rows("select * from plans where code = 'free' limit 1")

    return rows[0] if rows else dict(_FREE_DEFAULT)


# ── Показатели (CabinetMetrics) ─────────────────────────────────────


def _today() -> date:
    return datetime.now(UTC).date()


def _stats(company_id: int, start: date, end: date) -> list[dict[str, Any]]:
    """Суммы listing_stats по дням — объявления компании не в корзине."""
    return _rows(
        "select date, sum(impressions) as impressions, sum(views) as views, "
        "sum(favorites) as favorites, sum(unlocks) as unlocks from listing_stats "
        "where listing_id in (select id from listings where company_id = %s "
        "and deleted_at is null) and date between %s and %s group by date",
        [company_id, start, end],
    )


def _sum(company_id: int, start: date, end: date) -> dict[str, int]:
    rows = _stats(company_id, start, end)

    return {
        k: int(sum(r[k] or 0 for r in rows))
        for k in ("impressions", "views", "favorites", "unlocks")
    }


def _delta(now: int, prev: int) -> float | None:
    """Изменение в процентах; сравнивать не с чем — null."""
    return php_round((now - prev) / prev * 100, 1) if prev > 0 else None


def _from(days: int) -> date:
    return _today() - timedelta(days=days - 1)


def summary(company_id: int, days: int = DAYS) -> dict[str, Any]:
    """CabinetMetrics::summary: период и предыдущий такой же (граница — в обоих)."""
    start = _from(days)
    now = _sum(company_id, start, _today())
    prev = _sum(company_id, start - timedelta(days=days), start)

    def conversion(p: dict[str, int]) -> float:
        return php_round(p["unlocks"] / p["views"] * 100, 1) if p["views"] > 0 else 0.0

    return {
        **{
            key: {
                "value": now[key],
                "delta": _delta(now[key], prev[key]),
                "format": "int",
            }
            for key in ("impressions", "views", "unlocks")
        },
        "conversion": {
            "value": conversion(now),
            "delta": php_round(conversion(now) - conversion(prev), 1),
            "format": "percent",
        },
    }


def series(company_id: int, days: int = DAYS) -> dict[str, list[float]]:
    """CabinetMetrics::series: по дням, скользящее среднее за неделю."""
    today = _today()
    rows = {r["date"]: r for r in _stats(company_id, _from(days), today)}
    raw: dict[str, list[int]] = {"impressions": [], "views": [], "unlocks": []}

    for i in range(days - 1, -1, -1):
        row = rows.get(today - timedelta(days=i))

        for metric, values in raw.items():
            values.append(int((row or {}).get(metric) or 0))

    return {metric: _smooth(values) for metric, values in raw.items()}


def _smooth(values: list[int], window: int = 7) -> list[float]:
    out = []

    for i in range(len(values)):
        part = values[max(0, i - window + 1) : i + 1]
        out.append(php_round(sum(part) / len(part), 1))

    return out


#: CabinetMetrics::funnel — подписи в коде, по-русски на всех языках
_FUNNEL = (
    ("Показы в выдаче", "impressions", "primary"),
    ("Просмотры карточки", "views", "primary"),
    ("Добавили в избранное", "favorites", "primary"),
    ("Открыли контакт", "unlocks", "success"),
    ("Оставили отзыв", "reviews", "warning"),
)


def funnel(company_id: int, days: int) -> list[dict[str, Any]]:
    """CabinetMetrics::funnel: показы → просмотры → избранное → контакты → отзывы."""
    totals: dict[str, int] = dict(_sum(company_id, _from(days), _today()))
    totals["reviews"] = _count(
        "select count(*) as n from reviews where company_id = %s and status = 'published' "
        "and created_at >= %s",
        [company_id, _from(days)],
    )
    top = max(1, totals["impressions"])

    return [
        {
            "label": label,
            "value": totals[key],
            "share": php_round(totals[key] / top * 100, 1),
            "tone": tone,
        }
        for label, key, tone in _FUNNEL
    ]


def geography(company_id: int, locale: str) -> list[dict[str, Any]]:
    """
    CabinetMetrics::geography: города компаний, открывавших контакты, —
    группы в порядке первого появления, по убыванию, шесть первых.
    """
    from savdex.web.directory import _named

    cities = _named("cities", locale)
    groups: dict[str, int] = {}

    for row in _rows(
        "select c.city_id from contact_unlocks u left join companies c "
        "on c.id = u.company_id and c.deleted_at is null "
        "where u.target_company_id = %s order by u.id",
        [company_id],
    ):
        label = cities.get(row["city_id"]) if row["city_id"] is not None else None
        label = label if label is not None else "Не указан"
        groups[label] = groups.get(label, 0) + 1

    # sortDesc устойчив: равные остаются в порядке появления
    ranked = sorted(groups.items(), key=lambda kv: kv[1], reverse=True)[:6]

    return [{"label": label, "value": value} for label, value in ranked]


def queries(company_id: int, days: int, limit: int = 10) -> list[dict[str, Any]]:
    """CabinetMetrics::queries: поисковые запросы с CTR."""
    return [
        {
            "query": h["query"],
            "impressions": int(h["impressions"]),
            "clicks": int(h["clicks"]),
            "ctr": php_round(h["clicks"] / h["impressions"] * 100, 1)
            if h["impressions"] > 0
            else 0.0,
        }
        for h in _rows(
            "select query, sum(impressions) as impressions, sum(clicks) as clicks "
            "from search_hits where company_id = %s and date >= %s group by query "
            "order by impressions desc, query limit %s",
            [company_id, _from(days), limit],
        )
    ]


# ── Аналитика /cabinet/analytics (AnalyticsController) ──────────────

PERIODS = (7, 30, 90)


def analytics(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Analytics", analytics_props(ctx), _seo(ctx))


def analytics_props(ctx: Context) -> dict[str, Any]:
    periods = {str(d): ctx.t("cabinet.analytics.period_days", days=d) for d in PERIODS}
    company = company_of(ctx)

    if company is None:
        return {
            "metrics": None,
            "funnel": [],
            "geography": [],
            "queries": [],
            "benchmark": [],
            "periods": periods,
            "period": 30,
            "advanced": False,
            "plan": None,
        }

    # $request->integer('period', 30): intval ввода (пустое — null — это 0)
    value = laravel_input(ctx.query).get("period", 30)
    period = php_int(value, 0) if isinstance(value, str) else (30 if value == 30 else 0)
    period = period if period in PERIODS else 30

    cid = company["id"]
    plan = company_plan(cid)
    advanced = bool(plan.get("advanced_analytics"))
    metrics = summary(cid, period)

    return {
        "metrics": metrics,
        "series": series(cid, period),
        "funnel": funnel(cid, period),
        "geography": geography(cid, ctx.locale),
        "queries": queries(cid, period) if advanced else [],
        "benchmark": _benchmark(ctx, metrics) if advanced else [],
        "periods": periods,
        "period": period,
        "advanced": advanced,
        "plan": {"name": plan["name"]},
    }


def _benchmark(ctx: Context, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """AnalyticsController::benchmark: медианы категории пока постоянные."""
    views = float(metrics["views"]["value"])
    impressions = max(1.0, float(metrics["impressions"]["value"]))
    ctr = php_round(views / impressions * 100, 1)
    conversion = float(metrics["conversion"]["value"])

    return [
        _benchmark_row(ctx, ctx.t("cabinet.analytics.ctr"), ctr, 12.0),
        _benchmark_row(ctx, ctx.t("cabinet.analytics.to_contact"), conversion, 4.0),
    ]


def _benchmark_row(ctx: Context, label: str, you: float, median: float) -> dict[str, Any]:
    ratio = you / median if median > 0 else 1.0

    if ratio >= 1.4:
        verdict, tone = "top_quarter", "success"
    elif ratio >= 1.0:
        verdict, tone = "above_median", "success"
    elif ratio >= 0.7:
        verdict, tone = "near_median", "muted"
    else:
        verdict, tone = "below_median", "warning"

    return {
        "label": label,
        "you": you,
        "median": median,
        "position": min(96.0, max(4.0, ratio * 50)),
        "verdict": ctx.t(f"cabinet.analytics.{verdict}"),
        "tone": tone,
    }


# ── Кто мной интересуется /cabinet/incoming (IncomingController) ────


def incoming(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Incoming", incoming_props(ctx), _seo(ctx))


def _interested(
    ctx: Context, company: dict[str, Any] | None, cities: dict[int, str], sees_names: bool
) -> dict[str, Any]:
    """Общая часть строки: имя и рейтинг — только на тарифе, где их видно."""
    from savdex.web.shared import initials

    role = (company or {}).get("primary_role")
    city = cities.get(company["city_id"]) if company and company["city_id"] is not None else None

    return {
        "name": company["name"] if sees_names and company else None,
        "slug": company["slug"] if sees_names and company else None,
        "initials": initials(company["name"]) if sees_names and company else None,
        "verified": int(company["verification_level"] or 0) if sees_names and company else 0,
        "type": ctx.t("cabinet.incoming.buyer" if role == "buyer" else "cabinet.incoming.supplier"),
        "rating": float(company["rating"] or 0) if sees_names and company else 0.0,
        "city": city if city is not None else ctx.t("cabinet.incoming.city_unknown"),
    }


def incoming_props(ctx: Context) -> dict[str, Any]:
    from savdex.web.directory import _named

    company = company_of(ctx)

    if company is None:
        return {"rows": [], "viewers": [], "sees_names": False, "plan": None}

    cid = company["id"]
    plan = company_plan(cid)
    sees_names = bool(plan.get("sees_interested_names"))
    cities = _named("cities", ctx.locale)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    unlocks = _rows(
        "select u.id, u.created_at, l.title as listing_title, c.id as c_id "
        "from contact_unlocks u "
        "left join listings l on l.id = u.listing_id and l.deleted_at is null "
        "left join companies c on c.id = u.company_id and c.deleted_at is null "
        "where u.target_company_id = %s and u.created_at >= %s "
        "order by u.created_at desc, u.id desc",
        [cid, since],
    )
    companies = _companies([u["c_id"] for u in unlocks if u["c_id"] is not None])

    return {
        "rows": [
            {
                "id": u["id"],
                **_interested(ctx, companies.get(u["c_id"]), cities, sees_names),
                "listing": u["listing_title"],
                "when": ago(u["created_at"], ctx.locale),
            }
            for u in unlocks
        ],
        "viewers": _viewers(ctx, cid, sees_names, since, cities),
        "sees_names": sees_names,
        "plan": {"name": plan["name"]},
    }


def _companies(ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}

    return {
        c["id"]: c
        for c in _rows(
            "select id, name, slug, verification_level, primary_role, rating, city_id "
            "from companies where id = any(%s) and deleted_at is null",
            [list(set(ids))],
        )
    }


def _viewers(
    ctx: Context, company_id: int, sees_names: bool, since: datetime, cities: dict[int, str]
) -> list[dict[str, Any]]:
    """IncomingController::viewers: свёртка просмотров по зрителю, 50 последних."""
    aggregates = _rows(
        "select viewer_company_id, count(*) as views_total, max(created_at) as last_at "
        "from audience_views where target_company_id = %s and created_at >= %s "
        "group by viewer_company_id order by last_at desc, viewer_company_id desc limit 50",
        [company_id, since],
    )

    if not aggregates:
        return []

    ids = [a["viewer_company_id"] for a in aggregates]
    companies = _companies(ids)
    pages: dict[int, list[int | None]] = {}

    for p in _rows(
        "select distinct viewer_company_id, listing_id from audience_views "
        "where target_company_id = %s and created_at >= %s and viewer_company_id = any(%s) "
        "order by viewer_company_id, listing_id",
        [company_id, since, ids],
    ):
        pages.setdefault(p["viewer_company_id"], []).append(p["listing_id"])

    listing_ids = sorted({i for seen in pages.values() for i in seen if i is not None})
    # withTrashed: снятое объявление остаётся под своим названием
    titles = {
        r["id"]: r["title"]
        for r in _rows("select id, title from listings where id = any(%s)", [listing_ids])
    }
    result = []

    for i, row in enumerate(aggregates):
        viewed = pages.get(row["viewer_company_id"], [])
        found = [titles.get(x) for x in viewed if x]
        # ->filter()->unique(): пустые названия прочь, повторы — один раз
        listing_titles = list(dict.fromkeys(t for t in found if t))
        looked = listing_titles[:2]

        if len(listing_titles) > 2:
            looked.append(ctx.t("cabinet.incoming.and_more", count=len(listing_titles) - 2))

        if any(x is None for x in viewed):
            looked.append(ctx.t("cabinet.incoming.company_card"))

        result.append(
            {
                "id": i,
                **_interested(ctx, companies.get(row["viewer_company_id"]), cities, sees_names),
                "looked": " · ".join(looked),
                "views": int(row["views_total"]),
                "when": ago(row["last_at"], ctx.locale),
            }
        )

    return result


# ── Отзывы /cabinet/reviews (Cabinet\ReviewController::index) ───────

#: Review::CRITERIA — подписи в коде, по-русски на всех языках
CRITERIA = {
    "rating_description": "Соответствие описанию",
    "rating_response": "Скорость ответа",
    "rating_deadlines": "Соблюдение сроков",
    "rating_quality": "Качество товара",
}


def reviews(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Reviews", reviews_props(ctx), _seo(ctx))


def reviews_props(ctx: Context) -> dict[str, Any]:
    from savdex.web.shared import initials

    company = company_of(ctx)

    if company is None:
        return {"reviews": [], "summary": None, "criteria": CRITERIA}

    rows = _rows(
        "select r.*, a.name as a_name, a.verification_level as a_level, l.title as l_title "
        "from reviews r "
        "left join companies a on a.id = r.author_company_id and a.deleted_at is null "
        "left join listings l on l.id = r.listing_id and l.deleted_at is null "
        "where r.company_id = %s and r.status = 'published' "
        "order by r.created_at desc, r.id desc",
        [company["id"]],
    )

    return {
        "reviews": [
            {
                "id": r["id"],
                "author": r["a_name"],
                "initials": initials(r["a_name"]) if r["a_name"] is not None else None,
                "verified": int(r["a_level"] or 0),
                "rating": r["rating"],
                "body": r["body"],
                "deal_confirmed": bool(r["deal_confirmed"]),
                "listing": r["l_title"],
                "reply": r["reply"],
                "dispute_status": r["dispute_status"],
                "moderator_note": r["moderator_note"],
                "when": ago(r["created_at"], ctx.locale),
            }
            for r in rows
        ],
        "summary": _reviews_summary(rows),
        "criteria": CRITERIA,
    }


def _reviews_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Средние по критериям и распределение оценок, от пяти звёзд к одной."""
    if not rows:
        return None

    criteria = []

    for key, label in CRITERIA.items():
        # ->filter(): ни пустых, ни нулей
        values = [r[key] for r in rows if r[key]]
        criteria.append(
            {
                "label": label,
                "value": php_round(sum(values) / len(values), 1) if values else None,
            }
        )

    return {
        "average": php_round(sum(r["rating"] for r in rows) / len(rows), 1),
        "total": len(rows),
        "distribution": [
            {"star": star, "count": sum(1 for r in rows if r["rating"] == star)}
            for star in range(5, 0, -1)
        ],
        "criteria": criteria,
    }
