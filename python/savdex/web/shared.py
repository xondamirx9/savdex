"""
Запрос к странице сайта и общие данные страницы — как у Laravel.

Context — то, что Laravel знает о запросе к моменту, когда контроллер
собирает страницу: адрес сайта (схема и хост из заголовков прокси, как
при trustProxies('*')), путь без языкового префикса (LocalizeUrl), язык
(SetLocale), посетитель и его сессия (savdex/laravel_session.py).

shared() — общие пропсы страницы, копия HandleInertiaRequests::share и
Inertia\\Middleware::share: тот же набор, тот же порядок, те же значения.
Сверка — tests/test_web_parity.py.
"""

from __future__ import annotations

import calendar
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from typing import Any

from django.db import connection
from django.http import HttpRequest

from savdex import laravel_session, laravel_storage
from savdex.web import locales, ui


@dataclass
class Context:
    request: HttpRequest
    #: url('/') — схема и хост, как их видит Laravel за прокси
    root: str
    #: Путь без языкового префикса — как после LocalizeUrl
    path: str
    #: Строка запроса без «?»
    query: str
    locale: str
    visitor: laravel_session.Visitor
    session: dict[str, Any] = field(default_factory=dict)
    #: Язык из префикса адреса; None — адрес без префикса
    url_locale: str | None = None

    @property
    def inertia(self) -> bool:
        """Переход Inertia (XHR), а не полная загрузка страницы."""
        return bool(self.request.headers.get("X-Inertia"))

    @property
    def request_uri(self) -> str:
        """
        $request->getRequestUri() после LocalizeUrl: путь без префикса и
        запрос. С префиксом языка LocalizeUrl собирает адрес заново из
        getQueryString() — параметры уже упорядочены (normalizeQueryString);
        без префикса адрес остаётся как пришёл.
        """
        if self.url_locale is None:
            return self.path + (f"?{self.query}" if self.query else "")

        from savdex.web.phpquery import normalize

        query = normalize(self.query)

        return self.path + (f"?{query}" if query else "")

    def url(self, path: str) -> str:
        """url('/…') на текущем хосте."""
        return self.root + ("/" + path.lstrip("/") if path.strip("/") else "")

    def t(self, key: str, **replace: object) -> str:
        return ui.t(key, self.locale, **replace)

    @cached_property
    def user(self) -> dict[str, Any] | None:
        if self.visitor.user_id is None:
            return None

        rows = _rows(
            "select id, name, email, locale, email_verified_at, must_change_password, "
            "is_admin, company_id from users where id = %s and deleted_at is null",
            [self.visitor.user_id],
        )

        return rows[0] if rows else None


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description or []]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


# ── Настройки ───────────────────────────────────────────────────────


def settings_values() -> dict[str, Any]:
    """Setting::values(): ключ → значение из json-столбца."""
    values: dict[str, Any] = {}

    for row in _rows("select key, value::text as value from settings"):
        try:
            values[row["key"]] = json.loads(row["value"]) if row["value"] is not None else None
        except ValueError:
            values[row["key"]] = None

    return values


def setting(values: dict[str, Any], key: str, default: str = "") -> str:
    """(string) Setting::get($key, $default)."""
    value = values.get(key)

    if value is None:
        return default

    if value is True:
        return "1"

    if value is False:
        return ""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def public_url(path: str) -> str:
    """Storage::disk('public')->url(): APP_URL/storage/…, как в config/filesystems.php."""
    import os

    return os.environ.get("APP_URL", "http://localhost").rstrip("/") + "/storage/" + path


#: Знак из коробки: шапка, подвал, админка
DEFAULT_LOGO = "/images/logo-mark.svg"
#: Тот же знак с полями — значок вкладки и выдачи Google
DEFAULT_ICON = "/images/favicon.svg"


def appearance_logo(values: dict[str, Any]) -> str:
    """Appearance::logo()."""
    path = setting(values, "logo_image").strip()

    if path == "":
        return DEFAULT_LOGO

    if path.startswith(("http://", "https://", "/")):
        return path

    return public_url(path)


def appearance_icon(logo: str) -> str:
    """
    Значок сайта для <link rel="icon">.

    Свой логотип из админки — как есть: подсказка «Оформления» обещает его
    и на вкладке браузера. Знак из коробки — в варианте с полями: Google
    и соцсети обрезают значок кругом, а знак занимает квадрат до краёв,
    и у него срезались самолёт и росчерк.
    """
    return DEFAULT_ICON if logo == DEFAULT_LOGO else logo


# ── «N минут назад» ─────────────────────────────────────────────────


def local_time(moment: datetime) -> datetime:
    """
    Время для показа — по часам площадки (TIME_ZONE, Ташкент). В базе оно
    в UTC без пояса: «20:30» на экране было бы на пять часов раньше, а
    дата у позднего вечера — вчерашней.
    """
    from zoneinfo import ZoneInfo

    from django.conf import settings

    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)

    return aware.astimezone(ZoneInfo(settings.TIME_ZONE))


def _calendar_diff(earlier: datetime, later: datetime) -> tuple[int, int, int, int, int, int]:
    """DateTime::diff: годы, месяцы, дни, часы, минуты, секунды по календарю."""
    y, mo, d = later.year - earlier.year, later.month - earlier.month, later.day - earlier.day
    h, mi, s = (
        later.hour - earlier.hour,
        later.minute - earlier.minute,
        later.second - earlier.second,
    )

    if s < 0:
        s, mi = s + 60, mi - 1
    if mi < 0:
        mi, h = mi + 60, h - 1
    if h < 0:
        h, d = h + 24, d - 1

    # Дни занимаются у месяцев перед «позже», по одному, пока не хватит —
    # как timelib (do_range_limit_days_relative). Одного месяца мало:
    # с 31 января до 1 марта февраль короче, и выходило «1 месяц» с
    # минусом дней вместо «4 недели» у PHP
    year, month = later.year, later.month

    while d < 0:
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        d, mo = d + calendar.monthrange(year, month)[1], mo - 1

    # Месяцы в минусе — занять у лет (у timelib — do_range_limit)
    y, mo = y + mo // 12, mo % 12

    return y, mo, d, h, mi, s


def ago(moment: datetime, locale: str, now: datetime | None = None) -> str:
    """
    $date->diffForHumans(): одна старшая единица, округление вниз,
    недели — из дней. Сами слова — из выгрузки Carbon (savdex/web/ui.py).
    """
    now = now or datetime.now(UTC)
    moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
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
            return ui.ago_phrase(locale, unit, min(count, 100))

    # Carbon не пишет «0 секунд»: разница меньше секунды — «1 секунду»
    return ui.ago_phrase(locale, "second", 1)


# ── Общие пропсы ────────────────────────────────────────────────────


def _errors(ctx: Context) -> dict[str, Any]:
    """Inertia\\Middleware::resolveValidationErrors из сессии в JSON."""
    bags = ctx.session.get("errors")

    if not isinstance(bags, dict) or not bags:
        return {}

    resolved = {
        name: {field: messages[0] for field, messages in (bag.get("messages") or {}).items()}
        for name, bag in bags.items()
        if isinstance(bag, dict)
    }
    header = ctx.request.headers.get("X-Inertia-Error-Bag")

    if "default" in resolved and header:
        return {header: resolved["default"]}

    if "default" in resolved:
        return resolved["default"]

    return resolved


def _company(ctx: Context, company_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    rows = _rows(
        "select id, name, slug, logo_path, verification_level, status, blocked_reason, type, "
        "legal_form, city_id, phone, email, tin, address, description from companies "
        "where id = %s and deleted_at is null",
        [company_id],
    )

    if not rows:
        return None, None

    company = rows[0]
    logo = None

    if company["logo_path"] and (laravel_storage.public_root() / company["logo_path"]).is_file():
        logo = ctx.url("storage/" + company["logo_path"])

    documents = _rows(
        "select 1 as x from company_documents where company_id = %s "
        "and moderation_status = 'approved' limit 1",
        [company_id],
    )
    checks = [
        bool(company["name"]),
        bool(company["type"]) or company["legal_form"] in ("individual", "freelancer"),
        company["city_id"] is not None,
        _filled(company["phone"]),
        _filled(company["email"]),
        _filled(company["tin"]),
        _filled(company["address"]),
        len(company["description"] or "") >= 100,
        _filled(company["logo_path"]),
        bool(documents),
    ]

    card = {
        "id": company["id"],
        "name": company["name"],
        "slug": company["slug"],
        "logo": logo,
        "initials": initials(company["name"]),
        "verification_level": company["verification_level"],
        "profile_completeness": int(_php_round(sum(checks) / len(checks) * 100)),
        "blocked": company["status"] == "blocked",
        "blocked_reason": company["blocked_reason"],
        # Company::isPerson: в меню «Мой профиль», а не «Моя компания»
        "person": company["legal_form"] in ("individual", "freelancer"),
    }

    return card, company


def _filled(value: object) -> bool:
    """filled(): не null и не пустая строка из пробелов."""
    return value is not None and str(value).strip() != ""


def _php_round(value: float) -> float:
    """round() PHP: половина — от нуля, а не к чётному."""
    return math.floor(value + 0.5) if value >= 0 else -math.floor(-value + 0.5)


_SKIP = {"ООО", "ЧП", "АО", "ЗАО", "ИП", "МЧЖ", "ЖЧЖ", "LLC", "JSC"}


def initials(name: str | None) -> str:
    """Company::initials: «ООО «Стройбаза»» → «СБ»."""
    words = [w for w in re.split(r"[\s«»\"']+", name or "") if w]
    words = [w for w in words if w.upper() not in _SKIP]

    if not words:
        return "?"

    if len(words) == 1:
        return words[0][:2].upper()

    return "".join(w[:1].upper() for w in words[:2])


def _cabinet_counts(ctx: Context) -> dict[str, int] | None:
    from savdex.web.cabinet import counts

    return counts(ctx)


def _wallet_summary(company_id: int) -> dict[str, Any]:
    """HandleInertiaRequests::walletSummary."""
    plans = _rows(
        "select p.contacts_limit from subscriptions s join plans p on p.id = s.plan_id "
        "where s.id = (select max(id) from subscriptions where company_id = %s "
        "and status = 'active' and (ends_at is null or ends_at > now()))",
        [company_id],
    ) or _rows("select contacts_limit from plans where code = 'free' limit 1")
    limit = plans[0]["contacts_limit"] if plans else 3
    wallets = _rows(
        "select credits, contacts_used_this_period, period_resets_at from wallets "
        "where company_id = %s limit 1",
        [company_id],
    )
    wallet = wallets[0] if wallets else None
    credits = (wallet or {}).get("credits") or 0
    plan_left = (
        None
        if limit is None
        else max(0, limit - ((wallet or {}).get("contacts_used_this_period") or 0))
    )
    resets = (wallet or {}).get("period_resets_at")

    return {
        "plan_left": plan_left,
        "credits": credits,
        "total": None if plan_left is None else plan_left + credits,
        "resets_at": resets.strftime("%d.%m.%Y") if resets else None,
    }


def _bell(ctx: Context, user_id: int) -> dict[str, Any]:
    unread = _rows(
        "select count(*) as n from user_notifications where user_id = %s and read_at is null",
        [user_id],
    )[0]["n"]
    latest = _rows(
        "select id, type, tone, title, read_at, created_at from user_notifications "
        "where user_id = %s order by created_at desc, id desc limit 5",
        [user_id],
    )

    return {
        "unread": unread,
        "latest": [
            {
                "id": n["id"],
                "type": n["type"],
                "tone": n["tone"],
                "title": n["title"],
                "read": n["read_at"] is not None,
                "ago": ago(n["created_at"], ctx.locale),
            }
            for n in latest
        ],
    }


def _nav_categories(locale: str) -> list[dict[str, Any]]:
    rows = _rows(
        "select c.id, c.slug, (select name from category_translations t "
        "where t.category_id = c.id and t.locale = %s) as own, (select name from "
        "category_translations t where t.category_id = c.id and t.locale = 'ru') as ru "
        "from categories c where c.parent_id is null and c.is_active order by c.sort",
        [locale],
    )

    return [{"id": r["id"], "name": r["own"] or r["ru"] or r["slug"]} for r in rows]


def locale_links(ctx: Context) -> list[dict[str, str]]:
    return [
        {
            "code": code,
            "label": meta["label"],
            "short": meta["short"],
            "url": locales.switch_url(ctx.root, ctx.request_uri, code),
        }
        for code, meta in locales.ALL.items()
    ]


_LANG = re.compile(
    r"^([a-zA-Z]{2,3}|i-[a-zA-Z]{5,})(?:-([a-zA-Z]{4}))?(?:-([a-zA-Z]{2}))?(?:-(.+))?$"
)


def _components(locale: str) -> tuple[str, str | None, str | None]:
    """Request::getLanguageComponents (Symfony)."""
    locale = locale.lower().replace("_", "-")
    match = _LANG.match(locale)

    if not match:
        return locale, None, None

    language = match.group(1)[2:] if match.group(1).startswith("i-") else match.group(1)
    script = match.group(2).lower().capitalize() if match.group(2) else None
    region = match.group(3).upper() if match.group(3) else None

    return language, script, region


def _format(locale: str) -> str:
    return "_".join(p for p in _components(locale) if p)


def preferred_language(header: str, available: tuple[str, ...]) -> str | None:
    """
    Request::getPreferredLanguage (Symfony 7): языки Accept-Language по
    весу (при равном — по порядку), к каждому — его сочетания («zh_Hans_CN»
    → «zh_Hans», «zh_CN», «zh»); первое, с которого начинается доступный
    язык. Ни одного — первый из доступных.
    """
    items: list[tuple[float, int, str]] = []

    for index, part in enumerate(p for p in header.split(",") if p.strip()):
        value, *params = (x.strip() for x in part.split(";"))
        quality = 1.0

        for param in params:
            key, _, raw = param.partition("=")

            if key.strip().lower() == "q":
                try:
                    quality = float(raw.strip().strip('"'))
                except ValueError:
                    quality = 0.0

        items.append((quality, index, value))

    preferred = list(
        dict.fromkeys(_format(v) for _, _, v in sorted(items, key=lambda i: (-i[0], i[1])))
    )
    targets = [_format(code) for code in available]

    if not preferred:
        return targets[0] if targets else None

    for lang in preferred:
        language, script, region = _components(lang)
        combinations = dict.fromkeys(
            [
                "_".join(p for p in (language, script, region) if p),
                "_".join(p for p in (language, script) if p),
                "_".join(p for p in (language, region) if p),
                language,
            ]
        )

        for combination in combinations:
            for target in targets:
                if target.startswith(combination):
                    return target

    return targets[0]


def shared(ctx: Context) -> dict[str, Any]:
    """Общие пропсы — ключи и порядок HandleInertiaRequests::share."""
    user = ctx.user
    values = settings_values()
    company_card, company = (
        _company(ctx, user["company_id"]) if user and user["company_id"] else (None, None)
    )

    # Язык из префикса Laravel в этом же запросе запоминает в сессии
    # (SetLocale) — значит, выбор уже сделан, хоть Django его и не пишет
    chosen = (
        ctx.url_locale is not None
        or "locale" in ctx.session
        or locales.supports((user or {}).get("locale"))
    )
    browser = preferred_language(ctx.request.headers.get("Accept-Language", ""), locales.CODES)
    suggest = None if chosen or browser == ctx.locale or not locales.supports(browser) else browser

    return {
        "errors": _errors(ctx),
        "auth": {
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "locale": user["locale"],
                "email_verified": user["email_verified_at"] is not None,
                "must_change_password": bool(user["must_change_password"]),
                "is_admin": bool(user["is_admin"]),
            }
            if user
            else None,
            "company": company_card,
        },
        "contactsLeft": _wallet_summary(company["id"]) if company else None,
        "favorites": [
            r["listing_id"]
            for r in _rows("select listing_id from favorites where user_id = %s", [user["id"]])
        ]
        if user
        else [],
        "flash": {
            # «status» — так сообщают о себе резюме и отвязка Telegram
            "success": ctx.session.get("success") or ctx.session.get("status"),
            "error": ctx.session.get("error"),
            "warning": ctx.session.get("warning"),
        },
        # Счётчики кабинета — только на его адресах (savdex/web/cabinet.py)
        "counts": _cabinet_counts(ctx),
        "bell": _bell(ctx, user["id"]) if user else None,
        "navCategories": _nav_categories(ctx.locale),
        "support": {
            "email": setting(values, "support_email"),
            "phone": setting(values, "support_phone"),
            "telegram": setting(values, "telegram"),
            "legal_name": setting(values, "legal_name"),
            "legal_tin": setting(values, "legal_tin"),
        },
        "brandLogo": appearance_logo(values),
        "locale": ctx.locale,
        "translations": None if ctx.inertia else ui.translations(ctx.locale),
        "localeLinks": locale_links(ctx),
        "localeSuggest": suggest,
        "analytics": _analytics(ctx, company),
    }


def _analytics(ctx: Context, company: dict[str, Any] | None) -> dict[str, Any]:
    """
    GA4 (ТЗ-03): номер потока (пусто — тега нет), тариф для user_properties
    и события, подтверждённые сервером (savdex/web/analytics.py).
    """
    from savdex.web import analytics

    ga = analytics.measurement_id()

    if not ga:
        return {"id": "", "plan": None, "events": []}

    plan = None

    if company is not None:
        from savdex.web.cabinet import company_plan

        plan = company_plan(company["id"]).get("code")

    return {"id": ga, "plan": plan, "events": analytics.events(ctx)}
