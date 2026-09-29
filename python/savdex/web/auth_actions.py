"""
Вход, выход, регистрация — формы на Django (этап 5, шаг 45). Копия
AuthenticatedSessionController, RegisteredUserController и
App\\Services\\Auth\\LoginThrottle.

Вход: единое сообщение для «нет такого» и «неверный пароль» с остатком
попыток; пять неудач за 15 минут по связке почта + IP — блокировка с
обратным отсчётом; заблокированного не пускает и с верным паролем.
Успех: счётчик сброшен, сессия под новым номером, метка последнего
входа, выданный пароль — на смену, иначе — туда, куда шёл (url.intended).

Сверка с настоящим Laravel — tests/test_web_auth_actions.py.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from datetime import datetime, timedelta
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex import laravel_cache
from savdex.audit import client_ip
from savdex.guards import allowed_writes
from savdex.web import eloquent, guard, locales, throttle
from savdex.web.actions import form
from savdex.web.forms import _store, action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.session import Store
from savdex.web.shared import Context
from savdex.web.validation import validate

# ── LoginThrottle ───────────────────────────────────────────────────

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
WINDOW_MINUTES = 15


class LoginThrottle:
    """Неудачные попытки входа по связке почта + IP — в таблице login_attempts."""

    def __init__(self, email: str, ip: str) -> None:
        self.email = email
        self.ip = ip

    def _since(self) -> datetime:
        return eloquent.now() - timedelta(minutes=WINDOW_MINUTES)

    def failed_attempts(self) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from login_attempts where email = %s and ip = %s "
                "and successful = false and created_at >= %s",
                [self.email, self.ip, _stamp(self._since())],
            )
            return int(cursor.fetchone()[0])

    def remaining(self) -> int:
        return max(0, MAX_ATTEMPTS - self.failed_attempts())

    def locked(self) -> bool:
        return self.remaining() == 0

    def seconds_until_unlock(self) -> int:
        """unlocksAt: самая ранняя из пяти последних неудач плюс 15 минут."""
        if not self.locked():
            return 0

        with connection.cursor() as cursor:
            cursor.execute(
                "select created_at from login_attempts where email = %s and ip = %s "
                "and successful = false and created_at >= %s "
                "order by created_at desc limit %s",
                [self.email, self.ip, _stamp(self._since()), MAX_ATTEMPTS],
            )
            # ->value(): первая строка выборки
            row = cursor.fetchone()

        unlocks = (row[0] if row else eloquent.now()) + timedelta(minutes=LOCKOUT_MINUTES)

        return max(0, int((unlocks - eloquent.now()).total_seconds()))

    def _record(self, successful: bool, user_agent: str | None) -> None:
        with allowed_writes("login_attempts"), connection.cursor() as cursor:
            cursor.execute(
                "insert into login_attempts (email, ip, successful, user_agent_hash, created_at) "
                "values (%s, %s, %s, %s, %s)",
                [
                    self.email,
                    self.ip,
                    successful,
                    hashlib.sha256(user_agent.encode()).hexdigest() if user_agent else None,
                    _stamp(eloquent.now()),
                ],
            )

    def record_failure(self, user_agent: str | None) -> None:
        self._record(False, user_agent)

    def record_success(self, user_agent: str | None) -> None:
        """Успешный вход обнуляет счётчик."""
        self._record(True, user_agent)

        with allowed_writes("login_attempts"), connection.cursor() as cursor:
            cursor.execute(
                "delete from login_attempts where email = %s and ip = %s and successful = false",
                [self.email, self.ip],
            )


def _lockout(ctx: Context, throttle: LoginThrottle) -> str:
    minutes = math.ceil(throttle.seconds_until_unlock() / 60)

    return ctx.t("messages.auth.locked_out", minutes=max(1, minutes))


# ── Общее ───────────────────────────────────────────────────────────


def _session(ctx: Context) -> Store:
    store = _store(ctx)
    assert store is not None

    return store


def _to(ctx: Context, path: str) -> HttpResponse:
    """redirect($url): адрес на хосте — на язык запроса (LocalizeUrl)."""
    target = path if path.startswith("http") else ctx.url(path)

    if ctx.url_locale is not None and target.startswith(ctx.root):
        target = locales.url(ctx.root, target[len(ctx.root) :] or "/", ctx.url_locale)

    return HttpResponseRedirect(target)


def _intended(ctx: Context, default: str) -> HttpResponse:
    """redirect()->intended(route(default))."""
    store = _session(ctx)
    saved = store.get("url.intended")
    store.forget("url.intended")

    return _to(ctx, saved if isinstance(saved, str) else default)


def _guest(ctx: Context) -> HttpResponse | None:
    """RedirectIfAuthenticated: вошедшему форма входа не нужна — на главную."""
    return _to(ctx, "/") if ctx.user is not None else None


def _agent(request: HttpRequest) -> str | None:
    return request.headers.get("User-Agent")


# ── Вход и выход ────────────────────────────────────────────────────


@form()
def login(request: HttpRequest) -> HttpResponse:
    """AuthenticatedSessionController::store (guest, throttle:20,1,login)."""
    ctx = action(request, auth=False, throttle=20, throttle_minutes=1, throttle_prefix="login")

    if (refused := _guest(ctx)) is not None:
        return refused

    data = input_of(request)
    errors = validate(
        data,
        {"email": ["required", "string", "email"], "password": ["required", "string"]},
        ctx.locale,
        {
            "email.required": ctx.t("messages.auth.email_required"),
            "email.email": ctx.t("messages.auth.email_invalid"),
            "password.required": ctx.t("messages.auth.password_required"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    email = str(data["email"]).strip(" \t\n\r\0\x0b").lower()
    throttle = LoginThrottle(email, client_ip(request) or "")

    if throttle.locked():
        return invalid(ctx, {"email": [_lockout(ctx, throttle)]})

    remember = _boolean(data.get("remember"))
    user = guard.attempt(ctx, email, str(data["password"])) or guard.attempt_forgiving(
        ctx, email, str(data["password"])
    )

    if user is None:
        throttle.record_failure(_agent(request))
        fresh = LoginThrottle(email, client_ip(request) or "")
        message = (
            _lockout(ctx, fresh)
            if fresh.locked()
            else ctx.t(
                "messages.auth.wrong_credentials", left=fresh.remaining(), total=MAX_ATTEMPTS
            )
        )

        return invalid(ctx, {"email": [message]})

    store = _session(ctx)
    guard.login(ctx, store, user, remember)

    # Заблокированного не пускаем даже с верным паролем
    if user["status"] != "active":
        guard.logout(ctx, store)
        store.invalidate()

        return invalid(ctx, {"email": [ctx.t("messages.auth.blocked")]})

    throttle.record_success(_agent(request))
    store.migrate()
    row = _row(user["id"])
    eloquent.save(
        ctx,
        "users",
        row,
        {"last_login_at": eloquent.now(), "last_login_ip": client_ip(request)},
        section="users",
        model="User",
    )

    # Пароль, выданный вручную, обязателен к смене
    if row["must_change_password"]:
        return _to(ctx, "/password/change")

    return _intended(ctx, "/cabinet")


def _row(user_id: int) -> dict[str, Any]:
    from savdex.web.cabinet import _rows

    return _rows("select * from users where id = %s", [user_id])[0]


def _boolean(value: Any) -> bool:  # noqa: ANN401
    """$request->boolean(): FILTER_VALIDATE_BOOLEAN."""
    from savdex.web.company_contact_actions import _php_boolean

    return _php_boolean(value)


@form()
def logout(request: HttpRequest) -> HttpResponse:
    """AuthenticatedSessionController::destroy (auth)."""
    ctx = action(request)
    store = _session(ctx)
    guard.logout(ctx, store)
    store.invalidate()
    store.regenerate_token()

    # redirect('/') — адрес без языка; LocalizeUrl его не трогает только
    # для внешних, здесь — хост площадки
    return _to(ctx, "/")


def either(
    get: Any,  # noqa: ANN401
    post: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Один адрес: GET — страница, POST — форма (маршруты Laravel с тем же путём)."""

    def view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        handler = post if request.method == "POST" else get

        return handler(request, *args, **kwargs)  # type: ignore[no-any-return]

    return view


# ── Регистрация ─────────────────────────────────────────────────────


def _unique_email() -> Any:  # noqa: ANN401
    """Rule::unique('users', 'email')->withoutTrashed(): отключённый адрес не держит."""
    from savdex.web.cabinet import _rows
    from savdex.web.validation import Check

    def passes(value: Any) -> bool:  # noqa: ANN401
        return not _rows(
            "select 1 from users where email = %s and deleted_at is null limit 1", [str(value)]
        )

    return Check("unique", passes)


def _ordered(errors: dict[str, list[str]], order: list[str]) -> dict[str, list[str]]:
    """Ошибки полей в порядке правил, как их копит MessageBag (правило «x.*» — все «x.N»)."""
    result: dict[str, list[str]] = {}

    for rule in order:
        if rule.endswith(".*"):
            head = rule[:-1]
            result.update({k: v for k, v in errors.items() if k.startswith(head)})
        elif rule in errors:
            result[rule] = errors[rule]

    return result


@form()
def register(request: HttpRequest) -> HttpResponse:
    """
    RegisteredUserController::store (guest, throttle:20,10,register) и
    RegisterRequest — третий шаг регистрации, анкета. Почта — не из формы,
    а подтверждённая кодом на втором шаге (сессия register.verified_email);
    без неё — к первому шагу. Шаги 1–2 (/register/email, /register/code) —
    у Laravel.
    """
    from savdex.web import password_rule
    from savdex.web.company_profile_actions import _tin, _unique_tin
    from savdex.web.resumes import SERVICE_SECTIONS

    ctx = action(request, auth=False, throttle=20, throttle_minutes=10, throttle_prefix="register")

    if (refused := _guest(ctx)) is not None:
        return refused

    store = _session(ctx)
    verified = store.get(SESSION_VERIFIED)

    if not (isinstance(verified, str) and verified != "" and verified == store.get(SESSION_EMAIL)):
        return _to(ctx, "/register")

    data = input_of(request)
    kind = _account_type(data.get("account_type"))
    legal, freelancer = kind == "legal", kind == "freelancer"

    # prepareForValidation: почта — строчными без пробелов, имя и название —
    # без пробелов, из ИНН и ПИНФЛ — пробелы и дефисы вставленного номера
    data["email"] = verified.strip(" \t\n\r\0\x0b").lower()
    data["name"] = _php_string(data.get("name")).strip(" \t\n\r\0\x0b")
    data["company_name"] = _php_string(data.get("company_name")).strip(" \t\n\r\0\x0b")

    for key in ("tin", "pinfl"):
        number = re.sub(r"[\s\-]+", "", _php_string(data.get(key)))
        data[key] = number if number not in ("", "0") else None

    custom = {
        "name.required": ctx.t("messages.register.full_name_required"),
        "name.min": ctx.t("messages.register.name_min"),
        "email.required": ctx.t("messages.register.email_required"),
        "email.email": ctx.t("messages.register.email_format"),
        "email.unique": ctx.t("messages.register.email_taken"),
        "phone.required": ctx.t("messages.register.phone_required"),
        "phone.regex": ctx.t("messages.phone_format"),
        "password.required": ctx.t("messages.auth.password_new"),
        "password.confirmed": ctx.t("messages.auth.password_mismatch"),
        **password_rule.custom_messages(ctx.t),
        "terms.accepted": ctx.t("messages.register.terms"),
        "account_type.in": ctx.t("messages.register.account_type"),
        "company_name.required": ctx.t("messages.company.name_required"),
        "company_name.min": ctx.t("messages.company.name_required"),
        "tin.unique": ctx.t("messages.company.tin_unique"),
        "categories.required": ctx.t("messages.register.categories_required"),
        "categories.min": ctx.t("messages.register.categories_required"),
        "categories.max": ctx.t("messages.company.categories_max"),
        "pinfl.required": ctx.t("messages.register.pinfl_required"),
        "pinfl.unique": ctx.t("messages.register.pinfl_unique"),
        "service_section.required": ctx.t("messages.register.service_section_required"),
        "service_section.in": ctx.t("messages.register.service_section_required"),
    }
    tin_messages: list[str] = []
    rules: dict[str, list[Any]] = {
        "name": ["required", "string", "min:2", "max:120"],
        "email": ["required", "string", "email:rfc,strict", "max:190", _unique_email()],
        "phone": ["required", "string", r"regex:/^\+?\d[\d\s\-()]{8,17}$/"],
        "password": ["required", "string", "confirmed"],
        "terms": ["accepted"],
        "account_type": ["nullable", "in:legal,individual,freelancer"],
        "locale": ["nullable", "string", "in:ru,uz,en,zh,tr"],
    }

    # Набор полей — по тому, кто регистрируется; остальное — exclude
    if legal:
        rules["company_name"] = ["required", "string", "min:2", "max:190"]
        rules["tin"] = [
            "nullable",
            "string",
            "max:20",
            _tin(ctx, "uz", tin_messages),
            _unique_tin(None),
        ]
        rules["categories"] = ["required", "array", "min:1", "max:5"]
        rules["categories.*"] = ["integer", _top_category()]
    else:
        rules["pinfl"] = [
            "required" if freelancer else "nullable",
            "string",
            _pinfl(ctx, tin_messages),
            _unique_tin(None),
        ]

    if freelancer:
        rules["service_section"] = ["required", "string", "in:" + ",".join(SERVICE_SECTIONS)]

    errors = validate(data, rules, ctx.locale, custom)
    password = data.get("password")
    confirmed_failed = custom["password.confirmed"] in errors.get("password", [])

    # Password::defaults() — после required, string и confirmed
    if _filled(password):
        extra = password_rule.messages("password", password, ctx.locale, custom)
        merged = errors.get("password", [])
        merged += [m for m in extra if m not in merged]

        if merged:
            errors["password"] = merged

    # Текст ошибки правил Tin и Pinfl выбирает само правило
    for key, rule in (("tin", "validation.tin"), ("pinfl", "validation.pinfl")):
        if key in errors and tin_messages:
            errors[key] = [tin_messages[0] if m == rule else m for m in errors[key]]

    errors = _ordered(errors, list(rules))

    # after(): «пароли не совпадают» — и под вторым полем
    if confirmed_failed:
        errors["password_confirmation"] = [custom["password.confirmed"]]

    # after(): почта без «@» или без точки после неё — своя подсказка
    email = data["email"]

    if email != "" and "email" in errors and errors["email"] != [custom["email.unique"]]:
        hint = None

        if "@" not in email:
            hint = ctx.t("messages.register.email_no_at")
        elif "." not in email[email.index("@") :]:
            hint = ctx.t("messages.register.email_incomplete")

        if hint is not None:
            del errors["email"]
            errors["email"] = [hint]

    if errors:
        return invalid(ctx, errors)

    # Созданные аккаунты с одного адреса сети — не больше MAX_PER_HOUR в час
    limit = "register:" + (client_ip(ctx.request) or "")
    counted = laravel_cache.is_file_store()

    if counted and throttle.too_many(limit, MAX_REGISTRATIONS_PER_HOUR):
        timer = laravel_cache._to_int(laravel_cache.get(f"{limit}:timer") or 0)
        minutes = max(1, math.ceil(max(0, timer - int(time.time())) / 60))
        flash(ctx, "error", ctx.t("messages.register.too_many", minutes=minutes))

        return back(ctx)

    now = _stamp(eloquent.now())

    with transaction.atomic():
        company_id = _register_company(ctx, data, kind)
        locale = data.get("locale", "ru")
        row: dict[str, Any] = {
            "name": _php_string(data.get("name")),
            "email": email,
            "phone": _php_string(data.get("phone")),
            "password": guard.make(str(password)),
            "locale": _php_string(locale),
            "account_type": kind,
            "company_id": company_id,
            "company_role": "owner",
            "updated_at": now,
            "created_at": now,
            # Почта подтверждена кодом ещё до анкеты (markEmailAsVerified)
            "email_verified_at": now,
        }

        columns = list(row)

        with allowed_writes("users"), connection.cursor() as cursor:
            cursor.execute(
                f"insert into users ({', '.join(columns)}) "
                f"values ({', '.join(['%s'] * len(columns))}) returning id",
                list(row.values()),
            )
            row["id"] = cursor.fetchone()[0]

    if counted:
        throttle.hit(limit, 3600)

    user = _row(row["id"])
    store.forget(SESSION_EMAIL)
    store.forget(SESSION_VERIFIED)

    # Registered: почта уже подтверждена — второго письма нет
    guard.login(ctx, _session(ctx), user)

    # Второй шаг — данные компании — только у юрлица; остальным —
    # туда, куда шли (оплата тарифа), иначе в кабинет
    if legal:
        return _to(ctx, "/onboarding/company")

    flash(ctx, "success", ctx.t("messages.company.created_onboarding"))

    return _intended(ctx, "/cabinet")


#: RegisteredUserController::MAX_PER_HOUR: созданные аккаунты, не отправки формы
MAX_REGISTRATIONS_PER_HOUR = 5

#: RegisteredUserController::SESSION_EMAIL и SESSION_VERIFIED
SESSION_EMAIL = "register.email"
SESSION_VERIFIED = "register.verified_email"


def _account_type(value: Any) -> str:  # noqa: ANN401
    """RegisterRequest::accountType: без выбора — юрлицо."""
    kind = _php_string(value)

    return kind if kind in ("legal", "individual", "freelancer") else "legal"


def _top_category() -> Any:  # noqa: ANN401
    """Rule::exists('categories')->whereNull('parent_id')->where('is_active', true)."""
    from savdex.web.cabinet import _rows
    from savdex.web.validation import Check

    def passes(value: Any) -> bool:  # noqa: ANN401
        if isinstance(value, dict | list) or value is None:
            return False

        try:
            key = int(str(value).strip())
        except ValueError:
            return False

        return bool(
            _rows(
                "select 1 from categories where id = %s and parent_id is null and is_active "
                "limit 1",
                [key],
            )
        )

    return Check("exists", passes)


def _pinfl(ctx: Context, messages: list[str]) -> Any:  # noqa: ANN401
    """App\\Rules\\Pinfl: ровно 14 цифр, не повтор одной цифры."""
    from savdex.web.validation import Check

    def passes(value: Any) -> bool:  # noqa: ANN401
        pinfl = _php_string(value)

        if re.fullmatch(r"\d{14}", pinfl, re.ASCII) is None:
            messages.append(ctx.t("messages.register.pinfl_format"))

            return False

        if re.fullmatch(r"(\d)\1+", pinfl, re.ASCII):
            messages.append(ctx.t("messages.register.pinfl_invalid"))

            return False

        return True

    return Check("pinfl", passes)


def _register_company(ctx: Context, data: dict[str, Any], kind: str) -> int:
    """
    RegisteredUserController::companyData и Company::create: профиль
    заводится вместе с человеком; у юрлица — и выбранные разделы каталога.
    """
    from savdex.web.company_profile_actions import CASTS, _search_text, _slug
    from savdex.web.it_tasks import types_under

    row: dict[str, Any] = {"legal_form": kind, "status": "active", "primary_role": "both"}

    if kind == "legal":
        row.update(name=data["company_name"], tin=data.get("tin"))
    else:
        row.update(name=data["name"], tin=data.get("pinfl"))

    if kind == "freelancer":
        # $base += [...]: primary_role уже есть — остаётся «both»
        row.update(
            is_it_provider=True,
            it_specializations=types_under(_php_string(data.get("service_section"))),
        )

    row.update(_search_text(row))
    row["slug"] = _slug(str(row["name"]))
    now = _stamp(eloquent.now())
    row.update(updated_at=now, created_at=now)
    columns = list(row)

    with allowed_writes("companies"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into companies ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [eloquent._written(CASTS.get(c), row[c]) for c in columns],
        )
        company_id = int(cursor.fetchone()[0])

    if kind == "legal":
        from savdex.web.onboarding_actions import _sync_categories

        _sync_categories(company_id, list(data.get("categories") or []))

    return company_id


def _php_string(value: Any) -> str:  # noqa: ANN401
    """$request->string(): (string) значения, null — пусто."""
    if value is None:
        return ""

    if value is True:
        return "1"

    if value is False:
        return ""

    return str(value)


def _filled(value: Any) -> bool:  # noqa: ANN401
    return value is not None and not (isinstance(value, str) and value.strip() == "")
