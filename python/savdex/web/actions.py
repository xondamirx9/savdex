"""
Формы кабинета на Django (этап 5, шаг 21) — первые, без событий моделей:
прочтение уведомлений, избранное, настройки уведомлений, смена языка.

Посредники, ввод и ответы — savdex/web/forms.py; проверка ввода —
savdex/web/validation.py. Сверка с настоящим Laravel (ответ, сессия и
то, что записано в базу) — tests/test_web_forms.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web import locales, session
from savdex.web.cabinet import NOTIFICATION_EVENTS, _rows
from savdex.web.catalog import bump_daily
from savdex.web.forms import (
    RefusedError,
    action,
    back,
    flash,
    input_of,
    invalid,
    rate_headers,
    redirect,
)
from savdex.web.shared import Context
from savdex.web.tenders import _admin
from savdex.web.validation import validate
from savdex.web.views import not_found


def form(
    method: str = "POST",
) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """
    Вид формы: только свой метод (POST с _method Apache отдаёт Laravel),
    свой CSRF (токен Laravel, forms.action) вместо джанговского, ответ
    посредника — как есть.
    """

    def decorate(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @csrf_exempt
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if request.method != method:
                return HttpResponseNotAllowed([method])

            try:
                return rate_headers(request, view(request, *args, **kwargs))
            except RefusedError as refused:
                return refused.response

        return wrapped

    return decorate


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


# ── Уведомления ──────────────────────────────────────────────────────


@form()
def notification_read(request: HttpRequest, notification_id: str) -> HttpResponse:
    """
    NotificationController::read: своё уведомление — прочитано; адрес
    внутри площадки — туда, иначе назад.
    """
    ctx = action(request)
    assert ctx.user is not None
    rows = _rows(
        "select id, url, read_at from user_notifications where user_id = %s and id = %s",
        [ctx.user["id"], int(notification_id)],
    )

    if not rows:
        return not_found(ctx)

    row = rows[0]

    if row["read_at"] is None:
        stamp = _now()

        with allowed_writes("user_notifications"), connection.cursor() as cursor:
            cursor.execute(
                "update user_notifications set read_at = %s, updated_at = %s where id = %s",
                [stamp, stamp, row["id"]],
            )

    url = row["url"]

    return redirect(ctx, url) if url is not None and url.startswith("/") else back(ctx)


@form()
def notifications_read_all(request: HttpRequest) -> HttpResponse:
    """NotificationController::readAll."""
    ctx = action(request)
    assert ctx.user is not None
    stamp = _now()

    with allowed_writes("user_notifications"), connection.cursor() as cursor:
        cursor.execute(
            "update user_notifications set read_at = %s, updated_at = %s "
            "where user_id = %s and read_at is null",
            [stamp, stamp, ctx.user["id"]],
        )

    flash(ctx, "success", ctx.t("messages.notifications.all_read"))

    return back(ctx)


# ── Избранное ────────────────────────────────────────────────────────


@form()
def favorite_toggle(request: HttpRequest, listing_id: str) -> HttpResponse:
    """
    FavoriteController::toggle: было в избранном — убрать (счётчик не
    ниже нуля); не было — добавить живое объявление, счётчик и дневная
    строка — только если строка вставилась.
    """
    ctx = action(request, throttle=60)
    assert ctx.user is not None
    uid, lid = ctx.user["id"], int(listing_id)
    stamp = _now()

    with allowed_writes("favorites"), connection.cursor() as cursor:
        cursor.execute("delete from favorites where user_id = %s and listing_id = %s", [uid, lid])
        deleted = cursor.rowcount

    if deleted > 0:
        with allowed_writes("listings"), connection.cursor() as cursor:
            cursor.execute(
                "update listings set favorites_count = favorites_count - 1, updated_at = %s "
                "where id = %s and favorites_count > 0",
                [stamp, lid],
            )

        return back(ctx)

    rows = _rows(
        "select * from listings where id = %s and status = 'active' and deleted_at is null", [lid]
    )

    if not rows:
        return not_found(ctx)

    listing = rows[0]

    with allowed_writes("favorites"), connection.cursor() as cursor:
        cursor.execute(
            "insert into favorites (user_id, listing_id, created_at, updated_at) "
            "values (%s, %s, %s, %s) on conflict do nothing",
            [uid, lid, stamp, stamp],
        )
        added = cursor.rowcount

    if added > 0:
        _favorite_counted(ctx, listing)

    return back(ctx)


def _favorite_counted(ctx: Context, listing: dict[str, Any]) -> None:
    """
    StatsRecorder::favorite: $listing->increment('favorites_count') —
    событие updated модели, у администратора строка журнала (AuditObserver).
    """
    stamp = _now()

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            "update listings set favorites_count = favorites_count + 1, updated_at = %s "
            "where id = %s",
            [stamp, listing["id"]],
        )

    admin = _admin(ctx)

    if admin is not None:
        before = listing["favorites_count"]
        audit.record(
            connection,
            action="updated",
            section="listings",
            actor=admin,
            subject_type="App\\Models\\Listing",
            subject_id=listing["id"],
            subject_label=audit.label(listing, "Listing", listing["id"]),
            changes={
                "before": {"favorites_count": before},
                "after": {"favorites_count": before + 1},
            },
            ip=audit.client_ip(ctx.request),
        )

    bump_daily([listing["id"]], "favorites")


# ── Настройки ────────────────────────────────────────────────────────


@form("PATCH")
def settings_notifications(request: HttpRequest) -> HttpResponse:
    """SettingsController::notifications: по строке на событие, как updateOrCreate."""
    ctx = action(request)
    assert ctx.user is not None
    data = input_of(request)
    events = ",".join(NOTIFICATION_EVENTS)
    errors = validate(
        data,
        {
            "notifications": ["required", "array"],
            "notifications.*.event": ["required", "string", f"in:{events}"],
            "notifications.*.email": ["boolean"],
            "notifications.*.telegram": ["boolean"],
        },
        ctx.locale,
    )

    if errors:
        return invalid(ctx, errors)

    rows = data["notifications"]

    for row in rows.values() if isinstance(rows, dict) else rows:
        _save_preference(
            ctx.user["id"],
            row["event"],
            _php_bool(row.get("email")),
            _php_bool(row.get("telegram")),
        )

    flash(ctx, "success", ctx.t("messages.settings.notifications_saved"))

    return back(ctx)


def _php_bool(value: Any) -> bool:  # noqa: ANN401
    """(bool) у PHP: «0», пустая строка, 0 и пустой массив — ложь."""
    return value not in (None, False, 0, "0", "") and value != {} and value != []


def _save_preference(user_id: int, event: str, email: bool, telegram: bool) -> None:
    """updateOrCreate: новая строка; у старой — запись, только если что-то сменилось."""
    stamp = _now()

    with (
        allowed_writes("notification_preferences"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "select id, email, telegram from notification_preferences "
            "where user_id = %s and event = %s limit 1",
            [user_id, event],
        )
        found = cursor.fetchone()

        if found is None:
            cursor.execute(
                "insert into notification_preferences (user_id, event, email, telegram, "
                "created_at, updated_at) values (%s, %s, %s, %s, %s, %s)",
                [user_id, event, email, telegram, stamp, stamp],
            )
        elif (found[1], found[2]) != (email, telegram):
            cursor.execute(
                "update notification_preferences set email = %s, telegram = %s, "
                "updated_at = %s where id = %s",
                [email, telegram, stamp, found[0]],
            )


# ── Язык ─────────────────────────────────────────────────────────────


@form()
def locale_update(request: HttpRequest, locale: str) -> HttpResponse:
    """
    LocaleController::update: язык — в сессию и профиль, назад на ту же
    страницу на новом языке (префикс выбран здесь — LocalizeUrl не трогает).
    """
    ctx = action(request, auth=False, password_change=False)

    if locale not in locales.ALL:
        return not_found(ctx)

    started = session.start(request)
    assert started is not None
    started[0].put("locale", locale)

    if ctx.visitor.user_id is not None:
        session.save_user_locale(request, ctx.visitor.user_id, locale)

    referer = request.headers.get("Referer")
    path = (
        referer[len(ctx.root) :]
        if isinstance(referer, str) and referer.startswith(ctx.root)
        else "/"
    )

    return HttpResponseRedirect(locales.url(ctx.root, path or "/", locale))
