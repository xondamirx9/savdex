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

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex.web import inertia, locales, session, specs, ui
from savdex.web.home import _filled, completeness, php_round
from savdex.web.phpquery import laravel_input, php_int, text
from savdex.web.request import _expects_json, context
from savdex.web.seo import Seo
from savdex.web.shared import Context, ago, local_time

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
    """
    RequirePasswordChange: выданный вручную пароль — сначала сменить.
    Кроме самой смены пароля и подтверждения почты (ALLOWED посредника).
    """
    if ctx.user is None or not ctx.user["must_change_password"]:
        return None

    match = ctx.request.resolver_match
    name = (match.url_name if match is not None else None) or ""

    # RequirePasswordChange::ALLOWED
    if name in ("password.forced", "logout", "locale.update") or name.startswith("verification."):
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
    """
    Кабинет, вход, регистрация: заголовок сайта по умолчанию и noindex —
    в поиске этим страницам делать нечего.
    """
    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.noindex = True

    return seo


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
    "listing_days": 30,
    "listings_limit": 4,
    "contacts_limit": 3,
    "promo_units": 0,
}


#: Пока почта не подтверждена (код пропущен при регистрации) — не больше
#: стольких активных объявлений, какой бы ни был тариф
UNCONFIRMED_LISTINGS = 3


def company_plan(company_id: int) -> dict[str, Any]:
    """
    Company::plan: тариф действующей подписки, иначе Free. Компания
    с меткой «Не подтверждено» — не больше UNCONFIRMED_LISTINGS объявлений.
    """
    plan = _plan_of(company_id)
    unconfirmed = _rows("select 1 from companies where id = %s and email_unconfirmed", [company_id])
    limit = plan.get("listings_limit")

    if unconfirmed and (limit is None or limit > UNCONFIRMED_LISTINGS):
        plan = {**plan, "listings_limit": UNCONFIRMED_LISTINGS, "unconfirmed_cap": True}

    return plan


def _plan_of(company_id: int) -> dict[str, Any]:
    subscription = active_subscription(company_id)

    if subscription is not None:
        rows = _rows("select * from plans where id = %s", [subscription["plan_id"]])

        if rows:
            return rows[0]

    rows = _rows("select * from plans where code = 'free' limit 1")

    return rows[0] if rows else dict(_FREE_DEFAULT)


def listing_limit_message(ctx: Context, plan: dict[str, Any], hint: bool = True) -> str:
    """«Достигнут лимит тарифа…» — или лимит до подтверждения почты."""
    if plan.get("unconfirmed_cap"):
        return ctx.t("messages.listing.limit_unconfirmed", limit=plan["listings_limit"])

    message = ctx.t("messages.listing.limit", plan=plan["name"], limit=plan["listings_limit"])

    return message + " " + ctx.t("messages.listing.limit_hint") if hint else message


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


#: CabinetMetrics::funnel — шаги и тон; подписи — cabinet.analytics.funnel_steps
_FUNNEL = (
    ("impressions", "primary"),
    ("views", "primary"),
    ("favorites", "primary"),
    ("unlocks", "success"),
    ("reviews", "warning"),
)


def funnel(company_id: int, days: int, locale: str) -> list[dict[str, Any]]:
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
            "label": ui.t(f"cabinet.analytics.funnel_steps.{key}", locale),
            "value": totals[key],
            "share": php_round(totals[key] / top * 100, 1),
            "tone": tone,
        }
        for key, tone in _FUNNEL
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
        label = label if label is not None else ui.t("cabinet.incoming.city_unknown", locale)
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
        "funnel": funnel(cid, period, ctx.locale),
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

#: Review::CRITERIA — поля оценок по критериям
CRITERIA = ("rating_description", "rating_response", "rating_deadlines", "rating_quality")


def review_criteria(locale: str) -> dict[str, str]:
    """Подписи критериев отзыва на языке страницы (reviews.criteria)."""
    return {field: ui.t(f"reviews.criteria.{field}", locale) for field in CRITERIA}


def reviews(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Reviews", reviews_props(ctx), _seo(ctx))


def reviews_props(ctx: Context) -> dict[str, Any]:
    from savdex.web.shared import initials

    company = company_of(ctx)

    if company is None:
        return {"reviews": [], "summary": None, "criteria": review_criteria(ctx.locale)}

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
        "summary": _reviews_summary(rows, ctx.locale),
        "criteria": review_criteria(ctx.locale),
    }


def _reviews_summary(rows: list[dict[str, Any]], locale: str) -> dict[str, Any] | None:
    """Средние по критериям и распределение оценок, от пяти звёзд к одной."""
    if not rows:
        return None

    criteria = []

    for key, label in review_criteria(locale).items():
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


# ── Мои контакты /cabinet/contacts (ContactController::index) ───────

#: ContactUnlock::STATUSES — коды статусов контакта по порядку
UNLOCK_STATUSES = ("new", "contacted", "negotiating", "deal", "rejected")


def unlock_statuses(locale: str) -> dict[str, str]:
    """Подписи статусов контакта на языке страницы (cabinet.contacts.statuses)."""
    return {code: ui.t(f"cabinet.contacts.statuses.{code}", locale) for code in UNLOCK_STATUSES}


def contacts(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Contacts", contacts_props(ctx), _seo(ctx))


def contacts_props(ctx: Context) -> dict[str, Any]:
    from savdex.web.directory import _named
    from savdex.web.shared import initials

    company = company_of(ctx)
    statuses = unlock_statuses(ctx.locale)

    if company is None:
        return {
            "contacts": [],
            "statuses": statuses,
            "filters": {"q": "", "status": ""},
        }

    query = laravel_input(ctx.query)
    # $request->string(): нет ключа или пусто (null) — ''
    raw_q, raw_status = query.get("q"), query.get("status")
    q = text(raw_q) if isinstance(raw_q, str) else ""
    status = text(raw_status) if isinstance(raw_status, str) else ""
    where = ["u.company_id = %s"]
    params: list[Any] = [company["id"]]

    if status != "" and status in UNLOCK_STATUSES:
        where.append("u.status = %s")
        params.append(status)

    if q != "":
        # Поиск и по заметке: человек ищет «ждём КП», а не только название
        where.append(
            "(exists (select 1 from companies s where s.id = u.target_company_id "
            "and s.name like %s and s.deleted_at is null) or u.note like %s)"
        )
        params += [f"%{q}%", f"%{q}%"]

    unlocks = _rows(
        "select u.*, l.title as l_title from contact_unlocks u "
        "left join listings l on l.id = u.listing_id and l.deleted_at is null "
        f"where {' and '.join(where)} order by u.created_at desc, u.id desc",
        params,
    )
    targets = {
        c["id"]: c
        for c in _rows(
            "select * from companies where id = any(%s) and deleted_at is null",
            [list({u["target_company_id"] for u in unlocks})],
        )
    }
    reachable: dict[int, list[dict[str, Any]]] = {}

    for c in _rows(
        "select company_id, type, value from company_contacts where company_id = any(%s) "
        "order by is_primary desc, sort_order, id",
        [list(targets)],
    ):
        reachable.setdefault(c["company_id"], []).append(c)

    cities = _named("cities", ctx.locale)
    result = []

    for u in unlocks:
        target = targets.get(u["target_company_id"])
        own = reachable.get(target["id"], []) if target else []
        city = target["city_id"] if target else None

        result.append(
            {
                "id": u["id"],
                "company": {
                    "name": target["name"] if target else None,
                    "slug": target["slug"] if target else None,
                    "initials": initials(target["name"]) if target else None,
                    "verified": int(target["verification_level"] or 0) if target else 0,
                    "city": cities.get(city) if city is not None else None,
                },
                # Контакты целиком — они оплачены
                "phones": [c["value"] for c in own if c["type"] == "phone"],
                "emails": [c["value"] for c in own if c["type"] == "email"],
                "listing": u["l_title"],
                "opened_at": _date(u["created_at"]),
                "status": u["status"],
                "status_label": statuses.get(u["status"], u["status"]),
                "note": u["note"],
                "can_review": u["status"] in ("deal", "negotiating"),
                "complaint_status": u["complaint_status"],
                "moderator_note": u["moderator_note"],
                "refunded": bool(u["refunded"]),
            }
        )

    return {
        "contacts": result,
        "statuses": statuses,
        "filters": {"q": q, "status": status},
    }


# ── Настройки /cabinet/settings (SettingsController::index) ─────────

#: События настроек уведомлений — на странице подписи из словаря
#: (ui.notification_events). Какие виды уведомлений входят в событие и
#: уходят по его галочкам на почту и в Telegram — savdex/deliveries.py.
#: «Дайджест по подпискам» был обещанием без рассылки — убран
NOTIFICATION_EVENTS = {
    "contact_unlocked": "Открыли мой контакт",
    "new_review": "Новый отзыв",
    "chat": "Новое сообщение в чате",
    "moderation": "Решения модерации",
    "listing_expiring": "Объявление истекает",
    "tender_expiring": "Тендер истекает",
    "billing": "Оплаты, тариф и продвижение",
}


def settings_page(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Settings", settings_props(ctx), _seo(ctx))


def _telegram_configured() -> bool:
    """TelegramGateway::configured: токен и имя бота заданы."""
    import os

    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    username = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")

    return token != "" and username != ""


def settings_props(ctx: Context) -> dict[str, Any]:
    assert ctx.user is not None
    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    saved = {
        p["event"]: p
        for p in _rows(
            "select event, email, telegram from notification_preferences where user_id = %s "
            "order by id",
            [user["id"]],
        )
    }
    last_login = user["last_login_at"]

    return {
        "profile": {
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "locale": user["locale"],
            "email_verified": user["email_verified_at"] is not None,
            "phone_verified": user["phone_verified_at"] is not None,
        },
        # Умолчания — здесь, а не строками в базе: список событий растёт
        "notifications": [
            {
                "event": event,
                "label": ctx.t(f"notification_events.{event}"),
                "email": _pref(saved.get(event), "email", True),
                "telegram": _pref(saved.get(event), "telegram", False),
            }
            for event in NOTIFICATION_EVENTS
        ],
        "telegram": {
            "available": _telegram_configured(),
            "linked": user["telegram_chat_id"] is not None,
            "username": user["telegram_username"],
        },
        "security": {
            "two_factor": user["two_factor_confirmed_at"] is not None,
            "last_login_at": local_time(last_login).strftime("%d.%m.%Y, %H:%M")
            if last_login
            else None,
            "last_login_ip": user["last_login_ip"],
        },
        "is_owner": user["company_role"] == "owner",
        "categories": _company_categories(user, ctx.locale),
        "feed": _feed_on(user["id"]),
    }


def _company_categories(user: dict[str, Any], locale: str) -> dict[str, Any] | None:
    """
    Категории компании: по ним бот присылает новые объявления и тендеры.
    Выбор — разделы верхнего уровня; уже выбранные подразделы (услуги со
    второго шага регистрации) — тоже в списке, чтобы не потерялись.
    """
    from savdex.web.directory import _named
    from savdex.web.settings_actions import CATEGORIES_MAX

    if user["company_id"] is None:
        return None

    names = _named("categories", locale)
    selected = [
        r["category_id"]
        for r in _rows(
            "select category_id from company_category where company_id = %s order by id",
            [user["company_id"]],
        )
    ]
    options = [
        r["id"]
        for r in _rows(
            "select id from categories where parent_id is null and is_active order by sort, id",
            [],
        )
    ]
    options += [c for c in selected if c not in options]

    return {
        "options": [{"id": c, "name": names.get(c, str(c))} for c in options],
        "selected": selected,
        "max": CATEGORIES_MAX,
        "editable": user["company_role"] == "owner",
    }


def _feed_on(user_id: object) -> bool:
    from savdex.telegram_bot import feed_on

    return feed_on(user_id)


def _pref(row: dict[str, Any] | None, key: str, default: bool) -> bool:
    """$saved->get($event)?->email ?? true: нет строки или null — умолчание."""
    if row is None or row[key] is None:
        return default

    return bool(row[key])


# ── Уведомления /notifications (NotificationController::index) ──────


def notifications(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "Notifications", notifications_props(ctx), _seo(ctx))


def notifications_props(ctx: Context) -> dict[str, Any]:
    assert ctx.user is not None
    raw = laravel_input(ctx.query).get("filter")
    only_unread = isinstance(raw, str) and text(raw) == "unread"
    rows = _rows(
        "select * from user_notifications where user_id = %s"
        + (" and read_at is null" if only_unread else "")
        + " order by created_at desc, id desc limit 100",
        [ctx.user["id"]],
    )

    return {
        "notifications": [
            {
                "id": n["id"],
                "type": n["type"],
                "tone": n["tone"],
                "title": n["title"],
                "body": n["body"],
                "url": n["url"],
                "is_broadcast": bool(n["is_broadcast"]),
                "read": n["read_at"] is not None,
                "ago": ago(n["created_at"], ctx.locale),
                "date": local_time(n["created_at"]).strftime("%d.%m.%Y, %H:%M"),
            }
            for n in rows
        ],
        "filter": "unread" if only_unread else "all",
        "unread": _count(
            "select count(*) as n from user_notifications where user_id = %s and read_at is null",
            [ctx.user["id"]],
        ),
    }


# ── Избранное /favorites (FavoriteController::index) ────────────────


def favorites(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "Favorites", favorites_props(ctx), _seo(ctx))


def favorites_props(ctx: Context) -> dict[str, Any]:
    """
    Живые, истёкшие и архивные — с пометкой «не активно»; черновики,
    модерация и отклонённые скрыты целиком. Компания в корзине — карточка
    без продавца, как у ListingCard с пустой связью.
    """
    from savdex.web import content
    from savdex.web.home import _LISTING_COMPANY, Cards
    from savdex.web.shared import settings_values

    assert ctx.user is not None
    rows = _rows(
        f"select l.*, {_LISTING_COMPANY}, c.status as c_status from listings l "
        "left join companies c on c.id = l.company_id and c.deleted_at is null "
        "where l.status in ('active', 'expired', 'archived') and l.deleted_at is null "
        "and l.id in (select listing_id from favorites where user_id = %s) "
        "order by l.published_at desc nulls first, l.id desc",
        [ctx.user["id"]],
    )
    cards = Cards(ctx, settings_values(), content.Translations(ctx.locale))

    return {
        "items": [
            # Объявление заблокированной или удалённой компании открыть нельзя
            {**card, "active": row["status"] == "active" and row["c_status"] == "active"}
            for card, row in zip(cards.present(rows), rows, strict=True)
        ]
    }


# ── Мои объявления /cabinet/listings (Cabinet\ListingController::index)

#: Вкладки — порядок как в интерфейсе; «На модерации» нет (постмодерация)
LISTING_TABS = ("active", "draft", "needs_changes", "expired", "rejected")


def listings(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/listings/Index", listings_props(ctx), _seo(ctx))


def listings_props(ctx: Context) -> dict[str, Any]:
    from savdex.web import content
    from savdex.web.directory import _named

    tabs = {key: ctx.t(f"cabinet.listings.tab_{key}") for key in LISTING_TABS}
    company = company_of(ctx)

    if company is None:
        return {
            "listings": [],
            "counts": dict.fromkeys(LISTING_TABS, 0),
            "tabs": tabs,
            "status": "active",
            "limit": None,
        }

    raw = laravel_input(ctx.query).get("status")
    status = text(raw) if isinstance(raw, str) else ""
    status = status if status in LISTING_TABS else "active"
    cid = company["id"]
    counts = {
        key: _count(
            "select count(*) as n from listings where company_id = %s and status = %s "
            "and deleted_at is null",
            [cid, key],
        )
        for key in LISTING_TABS
    }
    rows = _rows(
        "select * from listings where company_id = %s and status = %s and deleted_at is null "
        "order by updated_at desc, id desc",
        [cid, status],
    )
    categories = _named("categories", ctx.locale)
    translations = content.Translations(ctx.locale)
    badges: dict[int, list[str | None]] = {}

    if rows:
        promotions = _rows(
            "select p.listing_id, t.badge from promotions p left join promotion_types t "
            "on t.id = p.promotion_type_id where p.listing_id = any(%s) and p.status = 'active' "
            "order by p.id",
            [[r["id"] for r in rows]],
        )
        translations.prefetch(p["badge"] for p in promotions)

        for p in promotions:
            badges.setdefault(p["listing_id"], []).append(translations.text(p["badge"]))

    soon = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)

    return {
        "listings": [
            {
                "id": r["id"],
                # Слаг пуст у свежего черновика — кабинет ведёт в редактор
                "slug": r["slug"],
                "title": r["title"],
                "type": r["type"],
                "category": categories.get(r["category_id"]) if r["category_id"] else None,
                "price": float(r["price"]) if r["price"] is not None else None,
                "price_from": bool(r["price_from"]),
                "price_to": float(r["price_to"]) if r["price_to"] is not None else None,
                "currency": r["currency"],
                "unit": r["unit"],
                "negotiable": bool(r["price_negotiable"]),
                "status": r["status"],
                "moderation_note": r["moderation_note"],
                "impressions": r["impressions_count"],
                "views": r["views_count"],
                "unlocks": r["unlocks_count"],
                "expires_at": _date(r["expires_at"]),
                "expiring_soon": r["status"] == "active"
                and r["expires_at"] is not None
                and r["expires_at"] < soon,
                "badges": [b for b in badges.get(r["id"], []) if b],
            }
            for r in rows
        ],
        "counts": counts,
        "tabs": tabs,
        "status": status,
        "limit": {"used": counts["active"], "total": company_plan(cid)["listings_limit"]},
    }


# ── Чаты /cabinet/chats (ChatController::index) ─────────────────────


def chats(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Chats", chats_props(ctx), _seo(ctx))


def chats_props(ctx: Context) -> dict[str, Any]:
    from savdex.web.seo import _limit
    from savdex.web.shared import initials

    company = company_of(ctx)

    if company is None:
        return {"threads": [], "hasCompany": False}

    cid = company["id"]
    threads = _rows(
        "select t.*, l.title as l_title, k.title as k_title from message_threads t "
        "left join listings l on l.id = t.listing_id and l.deleted_at is null "
        "left join it_tasks k on k.id = t.it_task_id "
        "where t.buyer_company_id = %s or t.seller_company_id = %s "
        "order by t.last_message_at desc, t.id desc limit 100",
        [cid, cid],
    )
    ids = [t["id"] for t in threads]
    last = {
        m["thread_id"]: m
        for m in _rows(
            "select * from messages where id in (select max(id) from messages "
            "where thread_id = any(%s) group by thread_id)",
            [ids],
        )
    }
    others = _companies(
        [
            t["seller_company_id"] if t["buyer_company_id"] == cid else t["buyer_company_id"]
            for t in threads
        ]
    )
    result = []

    for t in threads:
        mine_buyer = t["buyer_company_id"] == cid
        other = others.get(t["seller_company_id"] if mine_buyer else t["buyer_company_id"])
        read_at = t["buyer_read_at"] if mine_buyer else t["seller_read_at"]
        message = last.get(t["id"])
        unread = _count(
            "select count(*) as n from messages where thread_id = %s and company_id != %s"
            + (" and created_at > %s" if read_at is not None else ""),
            [t["id"], cid, *([read_at] if read_at is not None else [])],
        )
        result.append(
            {
                "id": t["id"],
                "company": other["name"] if other else ctx.t("cabinet.incoming.deleted"),
                "initials": initials(other["name"]) if other else "—",
                "listing": t["l_title"] if t["l_title"] is not None else t["k_title"],
                "last": _limit(message["body"], 80, "...") if message else None,
                "last_mine": message is not None and message["company_id"] == cid,
                "at": ago(t["last_message_at"], ctx.locale) if t["last_message_at"] else None,
                "unread": unread,
            }
        )

    return {"hasCompany": True, "threads": result}


# ── Продвижение /cabinet/promo (PromotionController::index) ─────────


def promo(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Promo", promo_props(ctx), _seo(ctx))


def _cost_label(ctx: Context, t: dict[str, Any]) -> str:
    """PromotionType::costLabel на языке страницы; «/» перед сроком ждёт Promo.tsx."""
    units = ctx.t("cabinet.promo.cost_units", count=t["cost_units"])

    return (
        f"{units} / {ctx.t('cabinet.promo.cost_days', days=t['duration_days'])}"
        if (t["duration_days"] or 0) > 0
        else f"{units} {ctx.t('cabinet.promo.once')}"
    )


def promo_props(ctx: Context) -> dict[str, Any]:
    from savdex.web import content

    company = company_of(ctx)

    if company is None:
        return {"active": [], "types": [], "listings": [], "units": 0, "resets_at": None}

    cid = company["id"]
    translations = content.Translations(ctx.locale)
    active = _rows(
        "select p.*, l.title as l_title, t.name as t_name, t.badge as t_badge "
        "from promotions p "
        "left join listings l on l.id = p.listing_id and l.deleted_at is null "
        "left join promotion_types t on t.id = p.promotion_type_id "
        "where p.company_id = %s and p.status = 'active' order by p.created_at desc, p.id desc",
        [cid],
    )
    types = _rows("select * from promotion_types where is_active order by sort, id")
    translations.prefetch(
        [a["t_badge"] for a in active]
        + [t[k] for t in types for k in ("name", "description", "effect_hint")]
    )
    taken = {
        r["promotion_type_id"]: r["n"]
        for r in _rows(
            "select promotion_type_id, count(*) as n from promotions where status = 'active' "
            "group by promotion_type_id"
        )
    }
    wallets = _rows("select * from wallets where company_id = %s limit 1", [cid])
    wallet = wallets[0] if wallets else None

    def effect(p: dict[str, Any]) -> int | None:
        """Promotion::effect: прирост показов в процентах."""
        before, after = p["impressions_before"], p["impressions_after"]

        if after is None or (before or 0) < 1:
            return None

        return int(php_round((after - before) / before * 100))

    return {
        "active": [
            {
                "id": p["id"],
                "listing": p["l_title"],
                "type": translations.text(p["t_name"]) or p["t_name"],
                "badge": translations.text(p["t_badge"]),
                "ends_at": _date(p["ends_at"]),
                "before": p["impressions_before"],
                "after": p["impressions_after"],
                "effect": effect(p),
            }
            for p in active
        ],
        "types": [
            {
                "id": t["id"],
                "code": t["code"],
                "name": translations.text(t["name"]),
                "description": translations.text(t["description"]),
                "effect_hint": translations.text(t["effect_hint"]),
                "cost": t["cost_units"],
                "cost_label": _cost_label(ctx, t),
                "icon": t["icon"],
                "slots": t["slots"],
                "taken": taken.get(t["id"], 0) if t["slots"] is not None else None,
                "available": t["slots"] is None or taken.get(t["id"], 0) < t["slots"],
            }
            for t in types
        ],
        "listings": [
            {"id": r["id"], "title": r["title"]}
            for r in _rows(
                "select id, title from listings where company_id = %s and status = 'active' "
                "and deleted_at is null order by id",
                [cid],
            )
        ],
        "units": (wallet or {}).get("promo_units") or 0,
        "resets_at": _date((wallet or {}).get("period_resets_at")),
    }


# ── Моё резюме /cabinet/resume (Cabinet\ResumeController::edit) ─────

#: Currencies::ALL — подписи в коде, по-русски на всех языках
CURRENCY_LABELS = {
    "UZS": "сум",
    "USD": "доллар США",
    "EUR": "евро",
    "CNY": "юань",
    "TRY": "турецкая лира",
    "RUB": "рубль",
    "KZT": "тенге",
}


def resume(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Resume", resume_props(ctx), _seo(ctx))


def resume_props(ctx: Context) -> dict[str, Any]:
    from savdex.web import resumes as options
    from savdex.web.directory import _named, listed_countries
    from savdex.web.shared import public_url

    assert ctx.user is not None
    user = _rows("select name, email, phone from users where id = %s", [ctx.user["id"]])[0]
    found = _rows(
        "select * from resumes where user_id = %s and deleted_at is null order by id limit 1",
        [ctx.user["id"]],
    )
    city_names = _named("cities", ctx.locale)

    return {
        "resume": _present_resume(found[0], public_url) if found else None,
        # Заготовка для первого захода — из профиля
        "defaults": {
            "contact_name": user["name"],
            "contact_email": user["email"],
            "contact_phone": user["phone"],
        },
        "options": {
            "fields": options.labels(ctx, "field", options.FIELDS),
            "employment": options.labels(ctx, "employment", options.EMPLOYMENT),
            "schedule": options.labels(ctx, "schedule", options.SCHEDULE),
            "language_levels": options.labels(ctx, "language_level", options.LANGUAGE_LEVELS),
            "education_levels": options.labels(ctx, "education_level", options.EDUCATION_LEVELS),
            "currencies": CURRENCY_LABELS,
        },
        "countries": [
            {"id": c["id"], "name": c["name"], "code": c["code"]}
            for c in listed_countries(ctx.locale)
        ],
        "cities": [
            {"id": c["id"], "name": city_names[c["id"]], "country_id": c["country_id"]}
            for c in _rows("select id, country_id from cities where is_active order by sort, id")
        ],
    }


def _present_resume(r: dict[str, Any], public_url: Any) -> dict[str, Any]:  # noqa: ANN401
    months = r["experience_months"] or 0

    return {
        "id": r["id"],
        "slug": r["slug"],
        "title": r["title"],
        "field": r["field"],
        "country_id": r["country_id"],
        "city_id": r["city_id"],
        "salary": r["salary"],
        "currency": r["currency"],
        "employment": r["employment"] or [],
        "schedule": r["schedule"] or [],
        "about": r["about"],
        "skills": r["skills"] or [],
        "jobs": r["jobs"] or [],
        "education": r["education"] or [],
        "languages": r["languages"] or [],
        "contact_name": r["contact_name"],
        "contact_phone": r["contact_phone"],
        "contact_email": r["contact_email"],
        "show_phone": bool(r["show_phone"]),
        "show_email": bool(r["show_email"]),
        "photo": public_url(r["photo_path"]) if r["photo_path"] is not None else None,
        "status": r["status"],
        "moderation_note": r["moderation_note"],
        "views": r["views_count"],
        "experience": {"years": months // 12, "months": months % 12},
    }


# ── Профиль компании /cabinet/company (CompanyProfileController::edit)

#: ItTask::SERVICE_TYPES; подписи — it_tasks.types на языке страницы
SERVICE_TYPES = (
    "web", "mobile", "erp", "integration", "design", "automation", "support",
    "logistics", "hr", "customs", "accounting", "other",
)  # fmt: skip


def service_types(ctx: Context) -> dict[str, str]:
    return {code: ctx.t(f"it_tasks.types.{code}") for code in SERVICE_TYPES}


#: CompanyDocument::MATERIAL_TYPES
_MATERIALS = ("presentation", "price_list", "catalog", "other")


def company_page(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/Company", company_props(ctx), _seo(ctx))


def company_props(ctx: Context) -> dict[str, Any]:
    from savdex import laravel_storage
    from savdex.web.company import _file_size
    from savdex.web.company_profile_actions import locked_fields
    from savdex.web.directory import _named, listed_countries, logo_url
    from savdex.web.shared import initials

    assert ctx.user is not None
    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    company = company_of(ctx)
    cid = company["id"] if company else None
    documents = (
        _rows(
            "select * from company_documents where company_id = %s "
            "order by created_at desc, id desc",
            [cid],
        )
        if cid
        else []
    )
    approved = {d["type"] for d in documents if d["moderation_status"] == "approved"}
    city_names = _named("cities", ctx.locale)
    private = laravel_storage.private_root()
    plan = company_plan(cid) if cid else None

    def document(d: dict[str, Any]) -> dict[str, Any]:
        label = ctx.t(f"cabinet.files.types.{d['type']}")

        return {
            "id": d["id"],
            "type": d["type"],
            "type_label": label if label != f"ui.cabinet.files.types.{d['type']}" else d["type"],
            "title": d["title"],
            "status": d["moderation_status"],
            "size": _file_size(d["file_size"], ctx.locale),
            "is_material": d["type"] in _MATERIALS,
            "is_public": bool(d["is_public"]),
            "valid_until": _date(d["valid_until"]),
            "missing": not (private / str(d["file_path"] or "")).is_file(),
        }

    def check(key: str, done: bool, hint: bool = False) -> dict[str, Any]:
        return {
            "label": ctx.t(f"cabinet.company.{key}"),
            "done": done,
            "hint": ctx.t("cabinet.company.verify_hint_plus") if hint else None,
        }

    return {
        "company": None
        if company is None
        else {
            "id": company["id"],
            "name": company["name"],
            "slug": company["slug"],
            "legal_name": company["legal_name"],
            "tin": company["tin"],
            "country_id": company["country_id"],
            "city_id": company["city_id"],
            "address": company["address"],
            "description": company["description"],
            "custom_category": company["custom_category"],
            "website": company["website"],
            "founded_year": company["founded_year"],
            "employees_range": company["employees_range"],
            "type": company["type"],
            "primary_role": company["primary_role"],
            "is_it_provider": bool(company["is_it_provider"]),
            "it_specializations": company["it_specializations"] or [],
            "initials": initials(company["name"]),
            "logo": logo_url(ctx, company["logo_path"]),
            "cover": logo_url(ctx, company["cover_path"]),
            "completeness": completeness(company, bool(approved)),
            "missing": _missing(ctx, company, bool(approved)),
            "verification_level": company["verification_level"],
            "locked_fields": list(locked_fields(company)),
        },
        "serviceTypes": service_types(ctx),
        "contacts": [
            {
                "id": c["id"],
                "type": c["type"],
                "value": c["value"],
                "label": c["label"],
                "contact_person": c["contact_person"],
                "is_public": bool(c["is_public"]),
            }
            for c in _rows(
                "select * from company_contacts where company_id = %s "
                "order by is_primary desc, sort_order, id",
                [cid],
            )
        ]
        if cid
        else [],
        "documents": [document(d) for d in documents],
        "employees": [
            {
                "id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "role": ctx.t(
                    "cabinet.company.role_owner"
                    if u["company_role"] == "owner"
                    else "cabinet.company.role_staff"
                ),
                "verified": u["email_verified_at"] is not None,
            }
            for u in _rows(
                "select * from users where company_id = %s and deleted_at is null order by id",
                [cid],
            )
        ]
        if cid
        else [],
        "countries": [
            {"id": c["id"], "name": c["name"], "code": c["code"]}
            for c in listed_countries(ctx.locale)
        ],
        "cities": [
            {"id": c["id"], "name": city_names[c["id"]], "country_id": c["country_id"]}
            # Свой «другой город» (скрытый, city_choice.py) — тоже в списке
            for c in _rows(
                "select id, country_id from cities where is_active or id = %s order by sort, id",
                [company["city_id"] if company else None],
            )
        ],
        "verification": [
            check("verify_email", user["email_verified_at"] is not None),
            check("verify_phone", user["phone_verified_at"] is not None),
            check("verify_registration", "registration" in approved),
            check("verify_tin", company is not None and _filled(company["tin"])),
            check("verify_licenses", "license" in approved, hint=True),
            check("verify_address", company is not None and _filled(company["address"]), hint=True),
        ],
        "plan": None
        if plan is None
        else {
            "name": plan["name"],
            "verification_days": plan.get("verification_days"),
            "has_microsite": bool(plan.get("has_microsite")),
        },
    }


# ── Мои IT-задачи /cabinet/it-tasks (Cabinet\ItTaskController) ──────

#: ItTask::STATUSES и ::CURRENCIES; подписи статусов — cabinet.it_tasks.statuses
IT_TASK_STATUSES = ("active", "closed", "completed", "archived")
IT_TASK_CURRENCIES = ["UZS", "USD"]


def _budget_label(ctx: Context, t: dict[str, Any]) -> str:
    """ItTaskController::budgetLabel."""
    from savdex.web.it_tasks import number_format

    currency = ctx.t("catalog.currency_uzs") if t["currency"] == "UZS" else t["currency"]
    negotiable = ctx.t("cabinet.it_task_form.budget_negotiable")
    low, high = t["budget_from"], t["budget_to"]

    if t["budget_type"] == "fixed":
        return f"{number_format(float(low), 0)} {currency}" if low is not None else negotiable

    if t["budget_type"] == "range":
        if low is None or high is None:
            return negotiable

        return f"{number_format(float(low), 0)} – {number_format(float(high), 0)} {currency}"

    return negotiable


def it_tasks(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(ctx, "cabinet/it-tasks/Index", it_tasks_props(ctx), _seo(ctx))


def it_tasks_props(ctx: Context) -> dict[str, Any]:
    from savdex.web.it_tasks import _date as day_month_year

    company = company_of(ctx)

    if company is None:
        return {"hasCompany": False, "tasks": []}

    tasks = _rows(
        "select t.*, c.name as contractor_name, (select count(*) from it_task_files f "
        "where f.it_task_id = t.id) as files_count from it_tasks t "
        "left join companies c on c.id = t.contractor_company_id and c.deleted_at is null "
        "where t.company_id = %s order by t.created_at desc, t.id desc",
        [company["id"]],
    )
    responders: dict[int, list[dict[str, Any]]] = {}

    for r in _rows(
        "select m.it_task_id, m.buyer_company_id, b.name from message_threads m "
        "left join companies b on b.id = m.buyer_company_id and b.deleted_at is null "
        "where m.it_task_id = any(%s) order by m.id",
        [[t["id"] for t in tasks]],
    ):
        responders.setdefault(r["it_task_id"], []).append(
            {
                "id": r["buyer_company_id"],
                "name": r["name"] if r["name"] is not None else ctx.t("cabinet.incoming.deleted"),
            }
        )

    return {
        "hasCompany": True,
        "tasks": [
            {
                "id": t["id"],
                "slug": t["slug"],
                "title": t["title"],
                "service_type": (
                    ctx.t(f"it_tasks.types.{t['service_type']}")
                    if t["service_type"] in SERVICE_TYPES
                    else t["service_type"]
                ),
                "budget": _budget_label(ctx, t),
                "deadline": day_month_year(t["deadline_at"], ctx.locale),
                "status": t["status"],
                "status_label": (
                    ctx.t(f"cabinet.it_tasks.statuses.{t['status']}")
                    if t["status"] in IT_TASK_STATUSES
                    else t["status"]
                ),
                "responses": t["responses_count"],
                "views": t["views_count"],
                "files": t["files_count"],
                "published": day_month_year(t["published_at"], ctx.locale),
                "result_url": t["result_url"],
                "result_summary": t["result_summary"],
                "contractor": t["contractor_name"],
                "responders": responders.get(t["id"], []),
            }
            for t in tasks
        ],
    }


def it_task_create(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    if company_of(ctx) is None:
        # Задачу без компании не поставить — сначала профиль
        store = _store(ctx)

        if store is not None:
            store.flash("warning", ctx.t("messages.it_task.no_company"))

        return _redirect(ctx, "/cabinet/company")

    return inertia.render(
        ctx,
        "cabinet/it-tasks/Form",
        {
            "task": None,
            "files": [],
            "serviceTypes": service_types(ctx),
            "currencies": IT_TASK_CURRENCIES,
        },
        _seo(ctx),
    )


def it_task_edit(request: HttpRequest, task_id: str) -> HttpResponse:
    from savdex.web.it_tasks import size_label
    from savdex.web.views import not_found

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    company = company_of(ctx)
    found = (
        _rows(
            "select * from it_tasks where id = %s and company_id = %s",
            [int(task_id), company["id"]],
        )
        if company is not None
        else []
    )

    # 404, а не 403: чужая задача не подтверждает своё существование
    if not found:
        return not_found(ctx)

    t = found[0]

    return inertia.render(
        ctx,
        "cabinet/it-tasks/Form",
        {
            "task": {
                "id": t["id"],
                "slug": t["slug"],
                "title": t["title"],
                "description": t["description"],
                "service_type": t["service_type"],
                "stack": t["stack"] or [],
                "budget_type": t["budget_type"],
                "budget_from": float(t["budget_from"]) if t["budget_from"] is not None else None,
                "budget_to": float(t["budget_to"]) if t["budget_to"] is not None else None,
                "currency": t["currency"],
                "deadline_at": t["deadline_at"].strftime("%Y-%m-%d") if t["deadline_at"] else None,
                "status": t["status"],
            },
            "files": [
                {"id": f["id"], "title": f["title"], "size": size_label(f["file_size"], ctx.locale)}
                for f in _rows(
                    "select id, title, file_size from it_task_files where it_task_id = %s "
                    "order by id",
                    [t["id"]],
                )
            ],
            "serviceTypes": service_types(ctx),
            "currencies": IT_TASK_CURRENCIES,
        },
        _seo(ctx),
    )


# ── Мини-сайт: редактор /cabinet/site (Cabinet\SiteController::edit) ─

#: SiteTheme — шаблоны, режимы, скругления, шрифты, умолчания, пресеты
SITE_TEMPLATES = ["classic", "bold", "minimal"]
SITE_MODES = ["light", "dark"]
SITE_RADII = ["sharp", "soft", "round"]
SITE_FONTS = {
    "manrope": "Manrope",
    "inter": "Inter",
    "montserrat": "Montserrat",
    "rubik": "Rubik",
    "nunito": "Nunito",
    "pt-sans": "PT Sans",
    "ibm-plex-sans": "IBM Plex Sans",
    "oswald": "Oswald",
    "playfair-display": "Playfair Display",
    "lora": "Lora",
    "pt-serif": "PT Serif",
    "roboto": "Roboto",
    "open-sans": "Open Sans",
    "raleway": "Raleway",
    "ubuntu": "Ubuntu",
    "exo-2": "Exo 2",
    "comfortaa": "Comfortaa",
    "roboto-slab": "Roboto Slab",
    "merriweather": "Merriweather",
}
SITE_DEFAULTS: dict[str, str | None] = {
    "template": "classic",
    "primary": "#1a56db",
    "accent": "#f59e0b",
    "mode": "light",
    "heading_font": "manrope",
    "body_font": "manrope",
    "radius": "soft",
    "hero_image": None,
}
#: Готовые сочетания. Подписи — cabinet.site.preset_names.<ключ>;
#: редактор ставит светлые перед тёмными
SITE_PRESETS = {
    "savdex": {
        "primary": "#1a56db",
        "accent": "#f59e0b",
        "mode": "light",
        "heading_font": "manrope",
        "body_font": "manrope",
        "radius": "soft",
    },
    "forest": {
        "primary": "#0f6e56",
        "accent": "#d4a017",
        "mode": "light",
        "heading_font": "lora",
        "body_font": "pt-sans",
        "radius": "soft",
    },
    "graphite": {
        "primary": "#f97316",
        "accent": "#38bdf8",
        "mode": "dark",
        "heading_font": "oswald",
        "body_font": "inter",
        "radius": "sharp",
    },
    "terracotta": {
        "primary": "#b4532a",
        "accent": "#2f6f73",
        "mode": "light",
        "heading_font": "playfair-display",
        "body_font": "nunito",
        "radius": "round",
    },
    "royal": {
        "primary": "#5b3cc4",
        "accent": "#e11d74",
        "mode": "light",
        "heading_font": "montserrat",
        "body_font": "rubik",
        "radius": "round",
    },
    "ocean": {
        "primary": "#0369a1",
        "accent": "#f97316",
        "mode": "light",
        "heading_font": "raleway",
        "body_font": "open-sans",
        "radius": "soft",
    },
    "mint": {
        "primary": "#0d9488",
        "accent": "#f43f5e",
        "mode": "light",
        "heading_font": "nunito",
        "body_font": "nunito",
        "radius": "round",
    },
    "sunset": {
        "primary": "#c2410c",
        "accent": "#facc15",
        "mode": "light",
        "heading_font": "montserrat",
        "body_font": "inter",
        "radius": "soft",
    },
    "berry": {
        "primary": "#9d174d",
        "accent": "#0ea5e9",
        "mode": "light",
        "heading_font": "rubik",
        "body_font": "rubik",
        "radius": "round",
    },
    "coffee": {
        "primary": "#6f4e37",
        "accent": "#d4a373",
        "mode": "light",
        "heading_font": "merriweather",
        "body_font": "pt-sans",
        "radius": "soft",
    },
    "sakura": {
        "primary": "#db2777",
        "accent": "#7c3aed",
        "mode": "light",
        "heading_font": "comfortaa",
        "body_font": "nunito",
        "radius": "round",
    },
    "cobalt": {
        "primary": "#1e3a8a",
        "accent": "#10b981",
        "mode": "light",
        "heading_font": "ibm-plex-sans",
        "body_font": "ibm-plex-sans",
        "radius": "sharp",
    },
    "olive": {
        "primary": "#4d7c0f",
        "accent": "#ea580c",
        "mode": "light",
        "heading_font": "roboto-slab",
        "body_font": "roboto",
        "radius": "soft",
    },
    "steel": {
        "primary": "#334155",
        "accent": "#0ea5e9",
        "mode": "light",
        "heading_font": "inter",
        "body_font": "inter",
        "radius": "sharp",
    },
    "midnight": {
        "primary": "#6366f1",
        "accent": "#22d3ee",
        "mode": "dark",
        "heading_font": "exo-2",
        "body_font": "inter",
        "radius": "soft",
    },
    "emerald": {
        "primary": "#10b981",
        "accent": "#fbbf24",
        "mode": "dark",
        "heading_font": "montserrat",
        "body_font": "roboto",
        "radius": "soft",
    },
    "neon": {
        "primary": "#a855f7",
        "accent": "#f472b6",
        "mode": "dark",
        "heading_font": "ubuntu",
        "body_font": "ubuntu",
        "radius": "round",
    },
    "gold": {
        "primary": "#d4a017",
        "accent": "#e11d48",
        "mode": "dark",
        "heading_font": "playfair-display",
        "body_font": "lora",
        "radius": "sharp",
    },
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_HERO = re.compile(r"^sites/\d+/[A-Za-z0-9._-]+$")

#: CompanySiteProduct::LIMIT
SITE_PRODUCTS_LIMIT = 60


def site_theme(value: Any) -> dict[str, str | None]:  # noqa: ANN401
    """SiteTheme::normalize: неизвестное — отброшено, недопустимое — умолчание."""
    source = value if isinstance(value, dict) else {}
    theme = dict(SITE_DEFAULTS)

    if source.get("template") in SITE_TEMPLATES:
        theme["template"] = source["template"]

    for key in ("primary", "accent"):
        if isinstance(source.get(key), str) and _HEX.match(source[key]):
            theme[key] = source[key].lower()

    if source.get("mode") in SITE_MODES:
        theme["mode"] = source["mode"]

    for key in ("heading_font", "body_font"):
        if isinstance(source.get(key), str) and source[key] in SITE_FONTS:
            theme[key] = source[key]

    if isinstance(source.get("radius"), str) and source["radius"] in SITE_RADII:
        theme["radius"] = source["radius"]

    if isinstance(source.get("hero_image"), str) and _HERO.match(source["hero_image"]):
        theme["hero_image"] = source["hero_image"]

    return theme


def _site_options() -> dict[str, Any]:
    """SiteTheme::options."""
    return {
        "templates": SITE_TEMPLATES,
        "modes": SITE_MODES,
        "radii": SITE_RADII,
        "fonts": [{"key": k, "name": v} for k, v in SITE_FONTS.items()],
        "presets": SITE_PRESETS,
        "fonts_url": "https://fonts.bunny.net/css?family="
        + "|".join(f"{k}:600" for k in SITE_FONTS)
        + "&display=swap",
    }


def _microsite_domain() -> str:
    """SiteHost::domain: MICROSITE_DOMAIN; пусто — сайты по пути /s/…."""
    import os

    return (os.environ.get("MICROSITE_DOMAIN") or "").strip().lower()


def _app_url() -> str:
    import os

    return os.environ.get("APP_URL", "http://localhost")


def site_url(subdomain: str) -> str:
    """SiteHost::url."""
    from urllib.parse import urlsplit

    domain = _microsite_domain()

    if domain == "":
        return _app_url().rstrip("/") + "/s/" + subdomain

    app = urlsplit(_app_url())
    port = f":{app.port}" if app.port else ""

    return f"{app.scheme or 'https'}://{subdomain}.{domain}{port}"


def _address_parts() -> dict[str, str]:
    """SiteHost::addressParts."""
    from urllib.parse import urlsplit

    domain = _microsite_domain()

    if domain != "":
        return {"prefix": "", "suffix": "." + domain}

    return {"prefix": (urlsplit(_app_url()).hostname or "") + "/s/", "suffix": ""}


def suggest_subdomain(slug: str) -> str:
    """SiteHost::suggest."""
    sub = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    sub = re.sub(r"-{2,}", "-", sub)[:40].strip("-")

    return sub if len(sub) >= 3 else sub + "-site"


def site_page(request: HttpRequest) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    company = company_of(ctx)

    if company is None:
        return _redirect(ctx, "/cabinet/company")

    return inertia.render(ctx, "cabinet/Site", site_props(ctx, company), _seo(ctx))


def site_props(ctx: Context, company: dict[str, Any]) -> dict[str, Any]:
    from savdex.web.directory import logo_url

    cid = company["id"]
    found = _rows("select * from company_sites where company_id = %s order by id limit 1", [cid])
    site = found[0] if found else None
    plan = company_plan(cid)
    draft = site_theme(site["theme"]) if site else None
    hero = (draft or {}).get("hero_image")

    return {
        "available": company["status"] != "blocked" and bool(plan.get("has_microsite")),
        "address": _address_parts(),
        "site": None
        if site is None
        else {
            "subdomain": site["subdomain"],
            "url": site_url(site["subdomain"]),
            "status": site["status"],
            "published_at": local_time(site["published_at"]).strftime("%d.%m.%Y %H:%M")
            if site["published_at"]
            else None,
            # Черновик отличается от того, что видят посетители
            "unpublished_changes": site["status"] != "published"
            or draft != site_theme(site["published_theme"]),
        },
        "subdomain": site["subdomain"] if site else suggest_subdomain(company["slug"]),
        "theme": draft if draft is not None else site_theme(None),
        "hero_url": (logo_url(ctx, hero) if isinstance(hero, str) else None) if site else None,
        "options": _site_options(),
        "products": [
            {
                "id": p["id"],
                "title": p["title"],
                "description": p["description"],
                "price": float(p["price"]) if p["price"] is not None else None,
                "currency": p["currency"],
                "unit": p["unit"],
                "image": logo_url(ctx, p["thumb_path"] or p["image_path"]),
            }
            for p in _rows(
                "select * from company_site_products where company_id = %s order by sort, id desc",
                [cid],
            )
        ],
        "products_limit": SITE_PRODUCTS_LIMIT,
        "listings_count": _count(
            "select count(*) as n from listings where company_id = %s and status = 'active' "
            "and deleted_at is null",
            [cid],
        ),
        "currencies": list(CURRENCY_LABELS),
    }


# ── Разговор /cabinet/chats/<id> (ChatController::show) ─────────────


def chat(request: HttpRequest, thread_id: str) -> HttpResponse:
    from savdex.guards import allowed_writes
    from savdex.web.shared import initials
    from savdex.web.views import not_found

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    company = company_of(ctx)
    found = _rows("select * from message_threads where id = %s", [int(thread_id)])

    # 404, а не 403: чужой разговор не подтверждает своё существование
    if company is None or not found:
        return not_found(ctx)

    t = found[0]
    cid = company["id"]

    if cid not in (t["buyer_company_id"], t["seller_company_id"]):
        return not_found(ctx)

    # markReadFor: прочитано — своей стороной; save() двигает и updated_at
    column = "buyer_read_at" if t["buyer_company_id"] == cid else "seller_read_at"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    with allowed_writes("message_threads"), connection.cursor() as cursor:
        cursor.execute(
            f"update message_threads set {column} = %s, updated_at = %s where id = %s",
            [stamp, stamp, t["id"]],
        )

    other_id = t["seller_company_id"] if t["buyer_company_id"] == cid else t["buyer_company_id"]
    others = _companies([other_id])
    other = others.get(other_id)
    listing = (
        _rows(
            "select title, slug, status from listings where id = %s and deleted_at is null",
            [t["listing_id"]],
        )
        if t["listing_id"]
        else []
    )
    task = (
        _rows("select title, slug, status from it_tasks where id = %s", [t["it_task_id"]])
        if t["it_task_id"]
        else []
    )

    return inertia.render(
        ctx,
        "cabinet/Chat",
        {
            "thread": {
                "id": t["id"],
                "company": other["name"] if other else ctx.t("cabinet.incoming.deleted"),
                "initials": initials(other["name"]) if other else "—",
                "company_slug": other["slug"] if other else None,
                "listing": {
                    "title": listing[0]["title"],
                    "slug": listing[0]["slug"],
                    "active": listing[0]["status"] == "active",
                }
                if listing
                else None,
                "task": {
                    "title": task[0]["title"],
                    "slug": task[0]["slug"],
                    "active": task[0]["status"] == "active",
                }
                if task
                else None,
            },
            "messages": [
                {
                    "id": m["id"],
                    "mine": m["company_id"] == cid,
                    "body": m["body"],
                    "at": local_time(m["created_at"]).strftime("%d.%m.%Y %H:%M"),
                }
                # Последние 500, а не первые: в долгом разговоре новые иначе пропадали
                for m in _rows(
                    "select * from (select id, company_id, body, created_at from messages "
                    "where thread_id = %s order by id desc limit 500) last order by id",
                    [t["id"]],
                )
            ],
        },
        _seo(ctx),
    )


# ── Мастер объявления: шаги /cabinet/listings/<id>/edit ─────────────


def _require_verified(ctx: Context) -> HttpResponse | None:
    """
    verified (EnsureEmailIsVerified): почта не подтверждена — на экран
    подтверждения, адрес страницы — в url.intended; XHR, ждущий JSON, — 403.
    """
    from savdex.web.shared import email_ok
    from savdex.web.views import error

    # Код пропущен при регистрации — мастер открыт (объявление с меткой)
    if ctx.user is None or email_ok(ctx.user):
        return None

    if _expects_json(ctx.request):
        return error(ctx, 403)

    store = _store(ctx)

    if store is not None:
        store.put("url.intended", store.full_url if ctx.request.method == "GET" else ctx.url("/"))

    return _redirect(ctx, "/verify-email")


def _category_tree(locale: str) -> list[dict[str, Any]]:
    """ListingWizardController::categoryTree: активные разделы, подразделы с полями."""
    from savdex.web.directory import _named

    names = _named("categories", locale)
    roots = _rows(
        "select id, slug from categories where parent_id is null and is_active order by sort, id"
    )
    children = _rows(
        "select id, parent_id, slug from categories where parent_id = any(%s) order by sort, id",
        [[r["id"] for r in roots]],
    )
    fields: dict[int, list[dict[str, Any]]] = {}
    with_specs = specs.enabled()
    # Подписи полей раздела заводятся по-русски — на языке мастера;
    # варианты — как есть: они же сохраняются значением
    from savdex.web import content

    translations = content.Translations(locale)

    for f in _rows(
        "select category_id, key, label, type, options, unit from category_fields "
        "where category_id = any(%s) order by sort, id",
        [[c["id"] for c in children]],
    ):
        fields.setdefault(f["category_id"], []).append(
            {
                "key": f["key"],
                "label": translations.text(f["label"]) or f["label"],
                "type": f["type"],
                "options": f["options"] or [],
                "unit": f["unit"],
            }
        )

    return [
        {
            "id": r["id"],
            "slug": r["slug"],
            "name": names[r["id"]],
            "children": [
                {
                    "id": c["id"],
                    "name": names[c["id"]],
                    # Блок «Информация о товаре»: поля под категорию
                    **({"specs": specs.form(r["slug"], c["slug"], locale)} if with_specs else {}),
                    "fields": fields.get(c["id"], []),
                }
                for c in children
                if c["parent_id"] == r["id"]
            ],
        }
        for r in roots
    ]


def wizard_tag_options(
    locale: str, row: dict[str, Any], company: dict[str, Any] | None
) -> list[str]:
    """ListingTags::suggestions для мастера: разделы, заголовок, характеристики, город."""
    from savdex.web.directory import _named
    from savdex.web.listing import suggestions

    categories = _named("categories", locale)
    category = parent = None

    if row["category_id"]:
        category = categories.get(row["category_id"])
        found_parent = _rows("select parent_id from categories where id = %s", [row["category_id"]])
        parent_id = found_parent[0]["parent_id"] if found_parent else None
        parent = categories.get(parent_id) if parent_id is not None else None

    attributes = _rows(
        "select key, value from listing_attributes where listing_id = %s order by id", [row["id"]]
    )
    city_id = company["city_id"] if company else None
    city = _named("cities", locale).get(city_id) if city_id else None

    return suggestions(
        row,
        category,
        parent,
        [str(a["value"] or "") for a in attributes if not specs.owns(str(a["key"]))],
        city,
    )


def listing_wizard(request: HttpRequest, listing_id: str) -> HttpResponse:
    from savdex.web.views import not_found

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    refused = _require_verified(ctx)

    if refused is not None:
        return refused

    company = company_of(ctx)
    found = (
        _rows(
            "select * from listings where id = %s and company_id = %s and deleted_at is null",
            [int(listing_id), company["id"]],
        )
        if company is not None
        else []
    )

    if not found:
        return not_found(ctx)

    row = found[0]
    parent_id = None

    if row["category_id"]:
        found_parent = _rows("select parent_id from categories where id = %s", [row["category_id"]])
        parent_id = found_parent[0]["parent_id"] if found_parent else None

    attributes = _rows(
        "select key, value from listing_attributes where listing_id = %s order by id", [row["id"]]
    )
    plan = company_plan(company["id"]) if company else None

    return inertia.render(
        ctx,
        "cabinet/listings/Wizard",
        {
            "listing": {
                "id": row["id"],
                "type": row["type"],
                "category_id": row["category_id"],
                "parent_id": parent_id,
                "title": row["title"],
                "description": row["description"],
                "price": float(row["price"]) if row["price"] is not None else None,
                "price_from": bool(row["price_from"]),
                "price_to": float(row["price_to"]) if row["price_to"] is not None else None,
                "bundle_price": float(row["bundle_price"])
                if row["bundle_price"] is not None
                else None,
                "currency": row["currency"],
                "unit": row["unit"],
                "price_negotiable": bool(row["price_negotiable"]),
                "min_order": row["min_order"],
                "delivery_terms": row["delivery_terms"],
                "payment_terms": row["payment_terms"],
                "status": row["status"],
                "step": row["wizard_step"],
                "tags": list(row["tags"] or []),
                # pluck('value', 'key'): повтор ключа — побеждает последняя
                "attributes": {a["key"]: a["value"] for a in attributes},
                "images": [
                    # ListingImage::thumbUrl — без проверки, что файл на месте
                    {"id": i["id"], "thumb": ctx.url("storage/" + (i["thumb_path"] or i["path"]))}
                    for i in _rows(
                        "select id, path, thumb_path from listing_images where listing_id = %s "
                        "order by sort, id",
                        [row["id"]],
                    )
                ],
            },
            "categories": _category_tree(ctx.locale),
            "slots": {
                "used": _count(
                    "select count(*) as n from listings where company_id = %s "
                    "and status = 'active' and deleted_at is null",
                    [company["id"]],
                )
                if company
                else 0,
                "total": plan["listings_limit"] if plan else None,
            },
            "tagOptions": wizard_tag_options(ctx.locale, row, company),
        },
        _seo(ctx),
    )
