"""
Страницы входа, регистрации и пароля на Django (этап 5) — только то,
что открывается GET-запросом. Формы по-прежнему отправляются в Laravel.

Гостевые страницы (/login, /register, /forgot-password,
/reset-password/<токен>) стоят за посредником guest: вошедший уходит
на главную. guest не в списке приоритетов посредников Laravel, поэтому
работает после SetLocale — язык из адреса успевает запомниться.

Остальные (/verify-email, /password/change, /onboarding/company,
/reviews/new) — за auth и RequirePasswordChange, как кабинет
(savdex/web/cabinet.py: page).

Сверка с настоящим Laravel — tests/test_web_auth.py.
"""

from __future__ import annotations

import os
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex.web import inertia, locales
from savdex.web.cabinet import _redirect, _rows, _seo, _store, company_of, page
from savdex.web.phpquery import laravel_input, text
from savdex.web.request import context
from savdex.web.shared import Context

#: Company::LEGAL_FORMS
LEGAL_FORMS = ("legal", "individual", "freelancer")

#: PlatformReview::CRITERIA
CRITERIA = {
    "rating_usability": "usability",
    "rating_search": "search",
    "rating_support": "support",
}

#: PlatformReviewService::MIN_BODY
MIN_BODY = 30


def guest(request: HttpRequest) -> Context | HttpResponse:
    """
    Контекст гостевой страницы — или ответ посредника.

    RedirectIfAuthenticated: вошедший — на route('home'); LocalizeUrl
    добавит к адресу префикс языка, если он был в запросе.
    """
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    if ctx.user is not None:
        return _redirect(ctx, "/")

    return ctx


def _flash(ctx: Context, key: str) -> Any:  # noqa: ANN401
    store = _store(ctx)

    return store.get(key) if store is not None else None


def _query(ctx: Context, key: str) -> str:
    """
    $request->string(key)->toString(): нет — пусто. Массив (?key[]=…) —
    тоже пусто: у Laravel это была страница 500 «Array to string
    conversion», посетителю она ни к чему.
    """
    raw = laravel_input(ctx.query).get(key)

    return (text(raw) or "") if isinstance(raw, str) else ""


# ── Гостевые ─────────────────────────────────────────────────────────


def login(request: HttpRequest) -> HttpResponse:
    """AuthenticatedSessionController::create."""
    ctx = guest(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    # ?back=/listing/… — гость нажал «В избранное» или «Откликнуться»:
    # после входа он вернётся туда же. Только свой адрес: «//чужой.сайт»
    # и прочее, что браузер поймёт как другой хост, не принимается
    back_to = _query(ctx, "back")
    store = _store(ctx)

    if (
        store is not None
        and back_to.startswith("/")
        and not back_to.startswith(("//", "/\\"))
        and not any(ch in back_to for ch in "\\\r\n")
        and len(back_to) <= 2000
    ):
        store.put("url.intended", ctx.root + back_to)

    return inertia.render(
        ctx,
        "auth/Login",
        {"status": _flash(ctx, "status")},
        _seo(ctx).title(ctx.t("auth.login_title")),
    )


def register(request: HttpRequest) -> HttpResponse:
    """
    RegisteredUserController::create — первый шаг регистрации, почта.
    Пришёл с тарифов кнопкой «Выбрать» (?plan=код) — после регистрации
    его ждёт оплата этого тарифа. Код и анкета — savdex/web/register_code.py.
    """
    ctx = guest(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    plan = _query(ctx, "plan")

    if plan not in ("", "free") and _rows(
        "select 1 from plans where code = %s and is_active limit 1", [plan]
    ):
        store = _store(ctx)

        if store is not None:
            store.put(
                "url.intended",
                locales.url(ctx.root, "/cabinet/billing?plan=" + plan, ctx.locale),
            )

    # «Изменить почту» со второго шага — адрес уже в поле
    store = _store(ctx)
    email = store.get("register.email") if store is not None else None

    return inertia.render(
        ctx, "auth/RegisterEmail", {"email": email}, _seo(ctx).title(ctx.t("auth.register_title"))
    )


def _whatsapp_configured() -> bool:
    """WhatsAppGateway::configured: токен и номер отправителя заданы."""
    token = (os.environ.get("WHATSAPP_TOKEN") or "").strip()
    phone = (os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip()

    return token != "" and phone != ""


def reset_channels() -> list[str]:
    """PasswordResetDelivery::channels: почта и настроенные мессенджеры."""
    from savdex.web.cabinet import _telegram_configured

    return [
        channel
        for channel, on in (
            ("mail", True),
            ("telegram", _telegram_configured()),
            ("whatsapp", _whatsapp_configured()),
        )
        if on
    ]


def forgot_password(request: HttpRequest) -> HttpResponse:
    """PasswordResetController::request."""
    ctx = guest(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return inertia.render(
        ctx,
        "auth/ForgotPassword",
        {"status": _flash(ctx, "status"), "channels": reset_channels()},
        _seo(ctx),
    )


def reset_password(request: HttpRequest, token: str) -> HttpResponse:
    """PasswordResetController::reset: токен из адреса, почта из ?email=."""
    ctx = guest(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    email = _query(ctx, "email")

    return inertia.render(ctx, "auth/ResetPassword", {"token": token, "email": email}, _seo(ctx))


# ── После входа ──────────────────────────────────────────────────────


def verify_email(request: HttpRequest) -> HttpResponse:
    """
    EmailVerificationController::notice: почта подтверждена — туда, куда
    человек шёл (url.intended), иначе в кабинет.
    """
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    assert ctx.user is not None

    if ctx.user["email_verified_at"] is not None:
        return _intended(ctx, "/cabinet")

    return inertia.render(
        ctx,
        "auth/VerifyEmail",
        {"email": ctx.user["email"], "status": _flash(ctx, "status")},
        _seo(ctx),
    )


def _intended(ctx: Context, default: str) -> HttpResponse:
    """
    redirect()->intended(route(default)): адрес из сессии (и прочь из
    неё) или default; LocalizeUrl переводит адрес на хосте на язык запроса.
    """
    store = _store(ctx)
    target = ctx.url(default)

    if store is not None:
        saved = store.get("url.intended")
        store.forget("url.intended")

        if isinstance(saved, str):
            target = saved

    if ctx.url_locale is not None and target.startswith(ctx.root):
        target = locales.url(ctx.root, target[len(ctx.root) :] or "/", ctx.url_locale)

    return HttpResponseRedirect(target)


def force_password(request: HttpRequest) -> HttpResponse:
    """ForcePasswordController::edit: без флага смены пароля — в кабинет."""
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    assert ctx.user is not None

    if not ctx.user["must_change_password"]:
        return _redirect(ctx, "/cabinet")

    return inertia.render(ctx, "auth/ForcePassword", {}, _seo(ctx))


def onboarding_company_of(company_id: int | None) -> dict[str, Any] | None:
    """$user->company: не удалённая."""
    if company_id is None:
        return None

    rows = _rows("select * from companies where id = %s and deleted_at is null", [company_id])

    return rows[0] if rows else None


def onboarding_open(company_id: int | None) -> bool:
    """
    OnboardingController::stepOpen: компании ещё нет (старые аккаунты) или
    юрлицо не дополнило заведённую при регистрации — у неё нет города.
    """
    company = onboarding_company_of(company_id)

    return company is None or (company["legal_form"] == "legal" and company["city_id"] is None)


def onboarding_company(request: HttpRequest) -> HttpResponse:
    """OnboardingController::company: второй шаг регистрации."""
    from savdex.web.directory import _named, listed_countries, type_options

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    assert ctx.user is not None
    company = company_of(ctx)

    # OnboardingController::stepOpen: компании нет — или юрлицо завело
    # её при регистрации, и город ещё не указан
    if company is not None and not (
        company["legal_form"] == "legal" and company["city_id"] is None
    ):
        return _redirect(ctx, "/cabinet")

    locale = ctx.locale
    cities = _named("cities", locale)
    categories = _named("categories", locale)
    account = _rows("select account_type from users where id = %s", [ctx.user["id"]])[0]
    services = _rows("select id from categories where slug = 'uslugi' order by id limit 1")

    return inertia.render(
        ctx,
        "auth/CompanyStep",
        {
            "countries": [
                {"id": c["id"], "name": c["name"], "code": c["code"]}
                for c in listed_countries(locale)
            ],
            "cities": [
                {"id": c["id"], "name": cities[c["id"]], "country_id": c["country_id"]}
                for c in _rows(
                    "select id, country_id from cities where is_active order by sort, id"
                )
            ],
            "categories": [
                {"id": c["id"], "slug": c["slug"], "name": categories[c["id"]]}
                for c in _rows(
                    "select id, slug from categories where parent_id is null and is_active "
                    "order by sort, id"
                )
            ],
            "types": type_options(locale),
            "accountType": account["account_type"]
            if account["account_type"] in LEGAL_FORMS
            else "legal",
            "personName": ctx.user["name"],
            # Компания заведена при регистрации — спрашиваем только недостающее
            "completing": ctx.user["company_id"] is not None,
            # Страна, выбранная при регистрации: молча Узбекистан не ставится
            "countryId": company["country_id"] if company is not None else None,
            "serviceCategories": [
                {"id": c["id"], "slug": c["slug"], "name": categories[c["id"]]}
                for c in _rows(
                    "select id, slug from categories where parent_id is not distinct from %s "
                    "and is_active order by sort, id",
                    [services[0]["id"] if services else None],
                )
            ],
        },
        _seo(ctx),
    )


def review_new(request: HttpRequest) -> HttpResponse:
    """ReviewsController::create: форма «Оцените SavdEx» — новый отзыв или правка своего."""
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    assert ctx.user is not None
    mine = _rows(
        "select * from platform_reviews where user_id = %s order by id limit 1", [ctx.user["id"]]
    )
    review = None

    if mine:
        row = mine[0]
        review = {
            "rating": row["rating"],
            **{field: int(row[field] or 0) for field in CRITERIA},
            "body": row["body"],
            "status": row["status"],
            "note": row["moderator_note"],
        }

    seo = _seo(ctx).title(ctx.t("platform_reviews.title"))
    seo.noindex = True

    return inertia.render(
        ctx,
        "reviews/Leave",
        {
            "review": review,
            "blocked": _blocked_reason(ctx),
            "criteria": {
                field: ctx.t(f"platform_reviews.criteria.{key}") for field, key in CRITERIA.items()
            },
            "minBody": MIN_BODY,
        },
        seo,
    )


def _blocked_reason(ctx: Context) -> str | None:
    """PlatformReviewService::blockedReason: почта не подтверждена, аккаунт или компания закрыты."""
    assert ctx.user is not None

    if ctx.user["email_verified_at"] is None:
        return ctx.t("messages.review.verify_email")

    status = _rows("select status from users where id = %s", [ctx.user["id"]])[0]["status"]
    company = company_of(ctx)

    if status != "active" or (company is not None and company["status"] == "blocked"):
        return ctx.t("messages.review.blocked")

    return None
