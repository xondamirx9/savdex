"""
Настройки — формы на Django (этап 5, шаги 29–30): профиль (имя,
телефон, язык) — копия SettingsController::profile; привязка Telegram —
копия TelegramLinkController. Удаление учётной записи переезжает вместе
с выходом (Auth::logout).

Смена номера сбрасывает подтверждение телефона. Язык — и в профиль, и
в сессию. Правка администратора — строка журнала (раздел users).

Сверка с настоящим Laravel — tests/test_web_settings_actions.py.
"""

from __future__ import annotations

import os
import secrets
import string
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex import laravel_cache
from savdex.web import eloquent, locales, ui
from savdex.web.actions import form
from savdex.web.cabinet import _rows
from savdex.web.forms import _store, action, back, flash, input_of, invalid, previous
from savdex.web.validation import validate

#: SettingsController::profile — тот же шаблон, что у регистрации
PHONE = r"/^\+?\d[\d\s\-()]{8,17}$/"


@form("PATCH")
def profile(request: HttpRequest) -> HttpResponse:
    """SettingsController::profile."""
    ctx = action(request)
    assert ctx.user is not None
    data = input_of(request)
    errors = validate(
        data,
        {
            "name": ["required", "string", "min:2", "max:120"],
            "phone": ["required", "string", f"regex:{PHONE}"],
            "locale": ["required", "in:ru,uz,en,zh,tr"],
        },
        ctx.locale,
        {
            "name.required": ctx.t("messages.settings.name_required"),
            "phone.regex": ctx.t("messages.phone_format"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    changes = {"name": data["name"], "phone": data["phone"], "locale": data["locale"]}

    # Смена номера сбрасывает подтверждение: подтверждён был старый
    if data["phone"] != user["phone"]:
        changes = {"phone_verified_at": None, **changes}

    eloquent.save(ctx, "users", user, changes, section="users", model="User")
    _store(ctx).put("locale", data["locale"])

    if data["locale"] == ctx.locale:
        flash(ctx, "success", ctx.t("messages.settings.profile_saved"))

        return back(ctx)

    # Язык сменили — на ту же страницу, но на новом языке: back() вёл на
    # старый префикс, и тот перезаписывал только что сохранённый язык
    flash(ctx, "success", ui.t("messages.settings.profile_saved", data["locale"]))
    came_from = previous(ctx)
    path = came_from[len(ctx.root) :] if came_from.startswith(ctx.root) else "/cabinet/settings"
    response = HttpResponseRedirect(locales.switch_url(ctx.root, path or "/", data["locale"]))

    if ctx.request.headers.get("X-Inertia") and ctx.request.method in ("PUT", "PATCH", "DELETE"):
        response.status_code = 303

    return response


# ── Подтверждение телефона по SMS (Telnyx, savdex/web/sms.py) ─────

#: Номер, на который из профиля ушёл код
SESSION_PHONE = "settings.sms_phone"


def _profile_phone(user: dict[str, Any]) -> str | None:
    """Номер профиля в международном виде; без «+» — с кодом страны компании."""
    from savdex.web import sms
    from savdex.web.register_code import _dial_code

    country = _rows("select country_id from companies where id = %s", [user["company_id"] or 0])

    return sms.normalize(
        str(user["phone"] or ""), _dial_code(country[0]["country_id"] if country else None)
    )


@form()
def phone_send(request: HttpRequest) -> HttpResponse:
    """«Подтвердить по SMS»: код на номер профиля. Каждое SMS платное."""
    from savdex.web import sms

    ctx = action(request, throttle=5, throttle_minutes=10, throttle_prefix="settings-sms")
    assert ctx.user is not None
    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]

    if user["phone_verified_at"] is not None or not sms.configured():
        return back(ctx)

    phone = _profile_phone(user)

    if phone is None:
        return invalid(ctx, {"phone": [ctx.t("messages.phone_format")]})

    if sms.verified_elsewhere(phone, user["id"]):
        return invalid(ctx, {"phone": [ctx.t("messages.register.phone_taken")]})

    if sms.daily_limit_reached(phone):
        return invalid(ctx, {"phone": [ctx.t("messages.register.sms_limit")]})

    if not sms.send_code(phone):
        return invalid(ctx, {"phone": [ctx.t("messages.register.sms_failed")]})

    _store(ctx).put(SESSION_PHONE, phone)
    flash(ctx, "success", ctx.t("messages.register.sms_sent", phone=phone))

    return back(ctx)


@form()
def phone_confirm(request: HttpRequest) -> HttpResponse:
    """
    Код из SMS верный — телефон подтверждён. Код пропускали при регистрации —
    метка «Не подтверждено» и лимит снимаются: человек подтвердил номер.
    """
    from savdex.web import sms
    from savdex.web.account_actions import confirm_skipped

    ctx = action(request, throttle=10, throttle_minutes=1, throttle_prefix="settings-sms-code")
    assert ctx.user is not None
    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    store = _store(ctx)
    phone = store.get(SESSION_PHONE)

    if user["phone_verified_at"] is not None:
        return back(ctx)

    # Код уходил на номер, который с тех пор сменили в профиле, — заново
    if not isinstance(phone, str) or phone != _profile_phone(user):
        return invalid(ctx, {"sms_code": [ctx.t("messages.auth.sms_code_invalid")]})

    code = str(input_of(request).get("sms_code") or "").strip()

    if code == "":
        return invalid(ctx, {"sms_code": [ctx.t("messages.auth.code_required")]})

    if not sms.check_code(phone, code):
        return invalid(ctx, {"sms_code": [ctx.t("messages.auth.sms_code_invalid")]})

    if sms.verified_elsewhere(phone, user["id"]):
        return invalid(ctx, {"sms_code": [ctx.t("messages.register.phone_taken")]})

    eloquent.save(
        ctx,
        "users",
        user,
        {"phone": phone, "phone_verified_at": eloquent.now()},
        section="users",
        model="User",
    )
    confirm_skipped(user["id"])
    store.forget(SESSION_PHONE)
    flash(ctx, "success", ctx.t("messages.settings.phone_confirmed"))

    return back(ctx)


# ── Telegram ─────────────────────────────────────────────────────────

#: TelegramGateway::CACHE_PREFIX и LINK_TTL_MINUTES
LINK_PREFIX = "telegram.link."
LINK_TTL = 15 * 60


def _bot_username() -> str:
    """TelegramGateway::botUsername."""
    return os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")


def _telegram_configured() -> bool:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() != "" and _bot_username() != ""


def _str_random(length: int) -> str:
    """Str::random: буквы и цифры."""
    alphabet = string.ascii_letters + string.digits

    return "".join(secrets.choice(alphabet) for _ in range(length))


def telegram(request: HttpRequest) -> HttpResponse:
    """/cabinet/settings/telegram: POST — ссылка на бота, DELETE — отвязать."""
    if request.method == "DELETE":
        return telegram_unlink(request)

    return telegram_link(request)


@form()
def telegram_link(request: HttpRequest) -> HttpResponse:
    """
    TelegramLinkController::store (throttle:10,1): одноразовый токен в
    кэш на 15 минут — его заберёт вебхук Laravel, — и уход к боту.
    Inertia::location: запросу Inertia — 409 с X-Inertia-Location.
    """
    ctx = action(request, throttle=10, throttle_prefix="telegram-link")
    assert ctx.user is not None

    if not _telegram_configured():
        _store(ctx).flash(
            "errors",
            {
                "default": {
                    "format": ":message",
                    "messages": {"telegram": [ctx.t("messages.auth.telegram_unavailable")]},
                }
            },
        )

        return back(ctx)

    token = _str_random(32)

    if laravel_cache.is_file_store():
        laravel_cache.put(LINK_PREFIX + token, int(ctx.user["id"]), LINK_TTL)

    url = f"https://t.me/{_bot_username()}?start={token}"

    if request.headers.get("X-Inertia"):
        response = HttpResponse("", status=409)
        response["X-Inertia-Location"] = url

        return response

    return HttpResponseRedirect(url)


@form("DELETE")
def telegram_unlink(request: HttpRequest) -> HttpResponse:
    """TelegramLinkController::destroy."""
    ctx = action(request)
    assert ctx.user is not None
    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    eloquent.save(
        ctx,
        "users",
        user,
        {"telegram_chat_id": None, "telegram_username": None, "telegram_linked_at": None},
        section="users",
        model="User",
    )
    flash(ctx, "status", ctx.t("messages.auth.telegram_unlinked"))

    return back(ctx)


# ── Категории компании и рассылка новинок в Telegram ─────────────────

#: Сколько категорий у компании — как на втором шаге регистрации
CATEGORIES_MAX = 5


@form("PATCH")
def categories(request: HttpRequest) -> HttpResponse:
    """
    Категории компании (company_category): по ним бот присылает новые
    объявления и тендеры. Общие на компанию — меняет только владелец.
    """
    from savdex.web.onboarding_actions import _sync_to
    from savdex.web.resume_actions import _exists

    ctx = action(request, throttle=30, throttle_prefix="settings-categories")
    assert ctx.user is not None
    user = _rows("select company_id, company_role from users where id = %s", [ctx.user["id"]])[0]

    if user["company_id"] is None or user["company_role"] != "owner":
        return invalid(ctx, {"categories": [ctx.t("messages.settings.categories_owner_only")]})

    data = input_of(request)
    errors = validate(
        data,
        {
            "categories": ["array", f"max:{CATEGORIES_MAX}"],
            "categories.*": ["integer", _exists("categories")],
        },
        ctx.locale,
        {"categories.max": ctx.t("messages.company.categories_max")},
    )

    if errors:
        return invalid(ctx, errors)

    raw = data.get("categories") or []
    values = raw.values() if isinstance(raw, dict) else raw
    wanted = list(dict.fromkeys(int(str(c)) for c in values))
    current = [
        r["category_id"]
        for r in _rows(
            "select category_id from company_category where company_id = %s order by id",
            [user["company_id"]],
        )
    ]
    _sync_to(user["company_id"], current, wanted)
    flash(ctx, "success", ctx.t("messages.settings.categories_saved"))

    return back(ctx)


@form("PATCH")
def telegram_feed(request: HttpRequest) -> HttpResponse:
    """Новые объявления и тендеры в Telegram: включить или поставить на паузу."""
    from savdex.telegram_bot import _set_feed
    from savdex.web.actions import _php_bool

    ctx = action(request)
    assert ctx.user is not None
    data = input_of(request)
    errors = validate(data, {"on": ["required", "boolean"]}, ctx.locale)

    if errors:
        return invalid(ctx, errors)

    _set_feed(int(ctx.user["id"]), _php_bool(data.get("on")))
    flash(ctx, "success", ctx.t("messages.settings.notifications_saved"))

    return back(ctx)
