"""
Формы сайта на Django (этап 5) — то, что у Laravel делают посредники
и Redirector вокруг POST-запроса.

Порядок посредников Laravel после сортировки по приоритетам:
CSRF (PreventRequestForgery) → auth → throttle → SetLocale →
HandleInertiaRequests → RequirePasswordChange → контроллер. Отсюда
action(): сначала токен (иначе 419), потом вход, частота, язык из
адреса, смена пароля.

Ввод — как $request->input(): тело (JSON у Inertia, форма у обычной
отправки) поверх строки запроса, строки обрезаны (TrimStrings, кроме
паролей), пустые — null (ConvertEmptyStringsToNull).

Ответ формы — чаще всего back(): Referer, иначе адрес из сессии
(_previous.url), иначе корень; LocalizeUrl переводит адрес на язык
запроса. На PUT/PATCH/DELETE от Inertia 302 становится 303.
"""

from __future__ import annotations

import hmac
import json
from dataclasses import replace
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from savdex import laravel_session
from savdex.web import locales, phpquery, session
from savdex.web.request import context
from savdex.web.shared import Context

#: TrimStrings::$except — пароли не обрезаются
NEVER_TRIM = ("current_password", "password", "password_confirmation")

#: ValidationException: во flash не попадают (Handler::$dontFlash)
DONT_FLASH = ("current_password", "password", "password_confirmation")

_ATTR = "_savdex_form_input"
RATE_ATTR = "_savdex_form_rate"


class RefusedError(Exception):
    """Ответ посредника вместо страницы: 419, вход, 429, смена пароля."""

    def __init__(self, response: HttpResponse) -> None:
        self.response = response


# ── Ввод ─────────────────────────────────────────────────────────────


def _clean(value: Any, name: str) -> Any:  # noqa: ANN401
    """TrimStrings и ConvertEmptyStringsToNull над деревом ввода."""
    if isinstance(value, dict):
        return {k: _clean(v, f"{name}.{k}" if name else str(k)) for k, v in value.items()}

    if isinstance(value, list):
        return [_clean(v, f"{name}.{i}" if name else str(i)) for i, v in enumerate(value)]

    if isinstance(value, str):
        trimmed = value if name in NEVER_TRIM else _trim(value)

        return None if trimmed == "" else trimmed

    return value


def _trim(value: str) -> str:
    """Str::trim над строкой UTF-8."""
    return phpquery.text(phpquery.str_trim(value.encode("utf-8").decode("latin-1")))


def _from_query(data: phpquery.Array) -> dict[str, Any]:
    """Разбор parse_str (байты latin-1) — в строки UTF-8."""

    def convert(value: phpquery.Value) -> Any:  # noqa: ANN401
        if isinstance(value, dict):
            return {str(k): convert(v) for k, v in value.items()}

        return phpquery.text(value) if isinstance(value, str) else value

    return {str(k): convert(v) for k, v in data.items()}


def _string_keys(data: phpquery.Array) -> dict[str, Any]:
    """Ключи массива PHP — строками, значения как есть."""
    return {str(k): _string_keys(v) if isinstance(v, dict) else v for k, v in data.items()}


def input_of(request: HttpRequest) -> dict[str, Any]:
    """$request->input(): тело поверх строки запроса, очищенное."""
    cached = getattr(request, _ATTR, None)

    if cached is not None:
        return cached  # type: ignore[no-any-return]

    body: dict[str, Any] = {}
    content_type = request.content_type or ""

    if content_type == "application/json" or content_type.endswith("+json"):
        try:
            parsed = json.loads(request.body or b"{}")
        except ValueError:
            parsed = {}

        # json_decode(…, true): список — массив с ключами 0…n
        if isinstance(parsed, list):
            parsed = {str(i): v for i, v in enumerate(parsed)}

        body = parsed if isinstance(parsed, dict) else {}
    elif content_type == "application/x-www-form-urlencoded":
        body = _from_query(phpquery.parse_query(request.body.decode("latin-1"), native=True))
    elif content_type == "multipart/form-data":
        # $_POST: «stack[0]» и «stack[]» — массив, как у PHP
        body = _string_keys(
            phpquery.parse_pairs([(k, v) for k in request.POST for v in request.POST.getlist(k)])
        )

    query = _from_query(phpquery.parse_query(request.META.get("QUERY_STRING", ""), native=True))
    # getInputSource()->all() + query->all(): ключи тела впереди
    merged = {**body, **{k: v for k, v in query.items() if k not in body}}
    cleaned: dict[str, Any] = _clean(merged, "")
    setattr(request, _ATTR, cleaned)

    return cleaned


# ── Посредники ───────────────────────────────────────────────────────


def _token_from_request(request: HttpRequest, data: dict[str, Any]) -> Any:  # noqa: ANN401
    """PreventRequestForgery::getTokenFromRequest."""
    token = data.get("_token") or request.headers.get("X-CSRF-TOKEN")

    if not token and (header := request.headers.get("X-XSRF-TOKEN")):
        plain = laravel_session.decrypt(header, laravel_session.keys())
        # CookieValuePrefix::remove — первые 41 знак (подпись имени и «|»)
        token = plain[41:] if plain is not None else ""

    return token


def _csrf_ok(request: HttpRequest, store: session.Store) -> bool:
    """Sec-Fetch-Site: same-origin — пропуск; иначе токен из ввода или заголовка."""
    if request.headers.get("Sec-Fetch-Site") == "same-origin":
        return True

    token = _token_from_request(request, input_of(request))

    return isinstance(token, str) and hmac.compare_digest(store.token, token)


def action(
    request: HttpRequest,
    *,
    auth: bool = True,
    throttle: int | None = None,
    throttle_minutes: int = 1,
    password_change: bool = True,
) -> Context:
    """
    Контекст формы — или RefusedError с ответом посредника.

    throttle, throttle_minutes — throttle:N,M маршрута. GET (выгрузка
    файла) CSRF не проверяет — как PreventRequestForgery::isReading.
    """
    from savdex.web.cabinet import _authenticate, _require_password_change
    from savdex.web.views import error

    first = context(request, redirect=False)

    if isinstance(first, HttpResponse):
        raise RefusedError(first)

    started = session.start(request)
    bare = replace(first, locale=first.url_locale or locales.DEFAULT)

    # Без записи сессии (не database) токен не с чем сверить
    reading = request.method in ("GET", "HEAD", "OPTIONS")

    if not reading and (started is None or not _csrf_ok(request, started[0])):
        if started is not None:
            started[0].csrf_refused = True

        raise RefusedError(error(bare, 419, bare=True))

    if auth and (refused := _authenticate(first)) is not None:
        raise RefusedError(refused)

    if throttle is not None:
        refused = _throttle(first, bare, throttle, throttle_minutes)

        if refused is not None:
            raise RefusedError(refused)

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        raise RefusedError(ctx)

    if password_change and (refused := _require_password_change(ctx)) is not None:
        raise RefusedError(refused)

    return ctx


def _throttle(
    first: Context, bare: Context, max_attempts: int, minutes: int = 1
) -> HttpResponse | None:
    """
    throttle:N,M. Отказ Inertia-формы — назад с ошибкой поля body и
    сообщением error (bootstrap/app.php), иначе страница 429.
    """
    from savdex import laravel_cache
    from savdex.web import throttle
    from savdex.web.views import error

    if not laravel_cache.is_file_store():
        # Кэш не в файлах (array) — счётчик у Laravel живёт один запрос:
        # засчитан один, заголовки те же
        setattr(first.request, RATE_ATTR, (max_attempts, None))

        return None

    key = throttle.signature(first)

    if throttle.too_many(key, max_attempts):
        if first.request.headers.get("X-Inertia"):
            wait = "Слишком много действий подряд — подождите минуту и попробуйте ещё раз."
            store = _store(first)
            store.flash("errors", {"default": {"format": ":message", "messages": {"body": [wait]}}})
            store.flash("error", wait)

            return back(first)

        return error(bare, 429, bare=True)

    throttle.hit(key, 60 * minutes)
    # Заголовки частоты — на ответ формы (actions.form)
    setattr(first.request, RATE_ATTR, (max_attempts, key))

    return None


def rate_headers(request: HttpRequest, response: HttpResponse) -> HttpResponse:
    """ThrottleRequests::addHeaders: предел и остаток — у пропущенного запроса."""
    from savdex.web import throttle

    rate = getattr(request, RATE_ATTR, None)

    if rate is not None:
        max_attempts, key = rate
        used = throttle.attempts(key) if key is not None else 1
        response["X-RateLimit-Limit"] = str(max_attempts)
        response["X-RateLimit-Remaining"] = str(max(0, max_attempts - used))

    return response


def _store(ctx: Context) -> session.Store:
    started = session.start(ctx.request)
    assert started is not None

    return started[0]


# ── Ответы ──────────────────────────────────────────────────────────


def previous(ctx: Context) -> str:
    """UrlGenerator::previous: Referer, адрес из сессии, корень."""
    referer = ctx.request.headers.get("Referer")

    if referer:
        return _to(ctx, referer)

    saved = _store(ctx).get("_previous.url")

    return saved if isinstance(saved, str) and saved else ctx.url("/")


def _to(ctx: Context, target: str) -> str:
    """UrlGenerator::to: полный адрес как есть, путь — от корня сайта."""
    if target.startswith(("http://", "https://", "//", "mailto:", "tel:", "sms:", "#")):
        return target

    return ctx.url(target)


def redirect(ctx: Context, target: str) -> HttpResponse:
    """
    redirect($url) после LocalizeUrl и Inertia: адрес на хосте получает
    язык запроса; Inertia на PUT/PATCH/DELETE — 303.
    """
    target = _to(ctx, target)

    if ctx.url_locale is not None and target.startswith(ctx.root):
        target = locales.url(ctx.root, target[len(ctx.root) :] or "/", ctx.url_locale)

    response = HttpResponseRedirect(target)

    if ctx.request.headers.get("X-Inertia") and ctx.request.method in ("PUT", "PATCH", "DELETE"):
        response.status_code = 303

    return response


def back(ctx: Context) -> HttpResponse:
    """back()."""
    return redirect(ctx, previous(ctx))


def flash(ctx: Context, key: str, value: Any) -> None:  # noqa: ANN401
    """->with(key, value)."""
    _store(ctx).flash(key, value)


def invalid(ctx: Context, errors: dict[str, list[str]]) -> HttpResponse:
    """
    ValidationException у Laravel: назад, ввод (без паролей) — в
    _old_input, ошибки — в сессию (ViewErrorBag в виде JSON).
    """
    store = _store(ctx)
    old = {k: v for k, v in input_of(ctx.request).items() if k not in DONT_FLASH}
    store.flash("_old_input", old)
    store.flash("errors", {"default": {"format": ":message", "messages": errors}})

    return back(ctx)
