"""
Сессия Laravel на страницах Django — запись, как у StartSession (этап 5).

До этапа 5 Django сессию только читал (laravel_session.identify), и у
этого были последствия: страница на Django не продлевала сессию
(человек, листающий каталог два часа, выходил из кабинета), не
стирала одноразовые сообщения («Сохранено» всплывало снова на
следующей странице Laravel), а гость, впервые пришедший на страницу
Django, не получал ни сессии, ни куки XSRF-TOKEN — и первая же форма
отвечала «страница устарела» (419).

Теперь каждая страница сайта на Django ведёт сессию ровно как
Laravel на GET-запросе:

1. StartSession: номер — из куки (40 букв и цифр), иначе новый; строка
   sessions читается, просроченная — пустая, но с тем же номером
   (DatabaseSessionHandler::read); нет _token — новый.
2. SessionGuard::user: кто вошёл — по ключу login_web_…; нет — по куке
   «запомнить меня», и тогда вход записывается в сессию, а сама сессия
   получает новый номер, старая строка удаляется (migrate(true)).
3. SetLocale: язык из префикса адреса запоминается в сессии и в
   профиле (users.locale) — выбор переживает вход с другого устройства.
4. После страницы: полный (не XHR) GET запоминает адрес и имя маршрута
   (_previous.url/_previous.route), ответ получает куки сессии и
   XSRF-TOKEN, одноразовые сообщения стареют (ageFlashData), строка
   sessions пишется с номером пользователя, IP и User-Agent.

Полезная нагрузка — base64 от JSON ('serialization' => 'json' в
config/session.php), кодируется как json_encode у PHP.

Сверка с настоящим Laravel — tests/test_web_session.py.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import os
import re
import secrets
import string
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse

from savdex import laravel_session
from savdex.audit import client_ip
from savdex.guards import allowed_writes

log = logging.getLogger(__name__)

_ALNUM = string.ascii_letters + string.digits

#: Где запрос хранит свою сессию: одна на запрос, сколько бы раз
#: страница ни собирала контекст (ограничение частоты — дважды)
_ATTR = "_savdex_laravel_session"


def random_string(length: int = 40) -> str:
    """Str::random: буквы и цифры."""
    return "".join(secrets.choice(_ALNUM) for _ in range(length))


# ── json_encode PHP ─────────────────────────────────────────────────


def _php_value(value: Any) -> Any:  # noqa: ANN401
    """
    Массив PHP после json_decode(…, true): объект с ключами 0…n-1 по
    порядку — это список, пустой объект — пустой массив «[]».
    """
    if isinstance(value, dict):
        if list(value) == [str(i) for i in range(len(value))]:
            return [_php_value(v) for v in value.values()]

        return {k: _php_value(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_php_value(v) for v in value]

    if isinstance(value, float) and value.is_integer():
        # json_encode без JSON_PRESERVE_ZERO_FRACTION: 3.0 → 3
        return int(value)

    return value


def php_json_encode(value: Any) -> str:  # noqa: ANN401
    """json_encode без флагов: «/» экранируется, не-ASCII — \\uXXXX."""
    return json.dumps(_php_value(value), separators=(",", ":"), ensure_ascii=True).replace(
        "/", "\\/"
    )


# ── Точечные ключи (Arr::get / Arr::set / Arr::forget) ──────────────


def arr_get(data: dict[str, Any], key: str, default: Any = None) -> Any:  # noqa: ANN401
    if key in data:
        return data[key]

    current: Any = data

    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return default

    return current


def arr_set(data: dict[str, Any], key: str, value: Any) -> None:  # noqa: ANN401
    parts = key.split(".")
    current = data

    for part in parts[:-1]:
        if not isinstance(current.get(part), dict):
            # Arr::set: не массив на пути — заменяется пустым массивом
            current[part] = {}

        current = current[part]

    current[parts[-1]] = value


def arr_forget(data: dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        if key in data:
            del data[key]
            continue

        parts = str(key).split(".")
        current: Any = data

        for part in parts[:-1]:
            if isinstance(current, dict) and isinstance(current.get(part), dict):
                current = current[part]
            else:
                current = None
                break

        if isinstance(current, dict):
            current.pop(parts[-1], None)


# ── Хранилище (Illuminate\Session\Store) ────────────────────────────


@dataclass
class Store:
    id: str
    data: dict[str, Any] = field(default_factory=dict)
    #: Строка в sessions есть (в том числе просроченная) — запись UPDATE
    exists: bool = False
    #: Номер пользователя для столбца user_id (Auth::id())
    user_id: int | None = None
    #: Request::fullUrl() после LocalizeUrl — для _previous.url
    full_url: str = ""
    #: Корень сайта: https — кука с флагом secure
    root: str = ""
    #: Форма отклонена по токену CSRF (419) — без куки XSRF-TOKEN
    csrf_refused: bool = False
    #: Cookie::queue: (имя, значение или None — забыть, минуты жизни)
    queued: list[tuple[str, str | None, int]] = field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return arr_get(self.data, key, default)

    def put(self, key: str, value: Any) -> None:  # noqa: ANN401
        arr_set(self.data, key, value)

    def forget(self, key: str) -> None:
        arr_forget(self.data, [key])

    @property
    def token(self) -> str:
        return str(self.data.get("_token", ""))

    def flash(self, key: str, value: Any) -> None:  # noqa: ANN401
        """Store::flash: значение, ключ — в новые, из старых — убрать."""
        self.put(key, value)
        new = self.get("_flash.new", [])
        new = list(new.values()) if isinstance(new, dict) else list(new)
        self.put("_flash.new", [*new, key])
        old = self.get("_flash.old", [])
        items = old.items() if isinstance(old, dict) else enumerate(old)
        # array_diff сохраняет ключи: без первого элемента список станет
        # объектом {"1": …} — ровно так его и запишет json_encode
        kept = {str(i): v for i, v in items if v != key}
        self.put("_flash.old", kept)

    def age_flash(self) -> None:
        """Store::ageFlashData."""
        old = self.get("_flash.old", [])
        arr_forget(self.data, [str(k) for k in (old if isinstance(old, list) else old.values())])
        self.put("_flash.old", self.get("_flash.new", []))
        self.put("_flash.new", [])

    def migrate(self) -> None:
        """Store::migrate(true): старая строка удаляется, номер — новый."""
        with allowed_writes("sessions"), connection.cursor() as cursor:
            cursor.execute("delete from sessions where id = %s", [self.id])

        self.exists = False
        self.id = random_string()

    def regenerate_token(self) -> None:
        """Store::regenerateToken."""
        self.data["_token"] = random_string()

    def invalidate(self) -> None:
        """Store::invalidate: всё прочь, номер — новый."""
        self.data.clear()
        self.migrate()


def _read(session_id: str) -> tuple[dict[str, Any], bool]:
    """DatabaseSessionHandler::read: (данные, есть ли строка)."""
    with connection.cursor() as cursor:
        cursor.execute("select payload, last_activity from sessions where id = %s", [session_id])
        row = cursor.fetchone()

    if row is None:
        return {}, False

    if int(row[1]) < int(time.time()) - laravel_session.lifetime():
        return {}, True

    try:
        data = json.loads(base64.b64decode(row[0] or ""))
    except (ValueError, binascii.Error):
        return {}, True

    return (data if isinstance(data, dict) else {}), True


def _live_user(user_id: int) -> tuple[Any, ...] | None:
    """
    Учётка, под которой можно быть вошедшим: не в корзине и не
    заблокирована — заблокированного выводит из всех открытых сессий.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "select id, remember_token from users where id = %s and deleted_at is null "
            "and status = 'active'",
            [user_id],
        )
        row: tuple[Any, ...] | None = cursor.fetchone()

    return row


def _as_id(value: Any) -> int | None:  # noqa: ANN401
    if isinstance(value, bool):
        return None

    try:
        user_id = int(value)
    except (TypeError, ValueError):
        return None

    return user_id if user_id > 0 else None


def start(request: HttpRequest) -> tuple[Store, laravel_session.Visitor] | None:
    """
    Сессия запроса — одна на запрос. None — без APP_KEY (Laravel без
    ключа не отвечает вовсе) или не в базе: тогда Django только читает.
    """
    cached = getattr(request, _ATTR, None)

    if cached is not None:
        return cached  # type: ignore[no-any-return]

    key_list = laravel_session.keys()

    # Сессии не в базе (array в проверке контейнера, file) — Laravel
    # держит их там, куда Django не пишет: остаётся только чтение
    if not key_list or os.environ.get("SESSION_DRIVER", "database") != "database":
        return None

    name = laravel_session.cookie_name()
    from_cookie = laravel_session.cookie_value(name, request.COOKIES.get(name), key_list)

    # Session::setId: чужой или битый номер — новый
    if from_cookie and re.fullmatch(r"[A-Za-z0-9]{40}", from_cookie):
        data, exists = _read(from_cookie)
        store = Store(from_cookie, data, exists)
    else:
        store = Store(random_string())

    # Store::start
    if "_token" not in store.data:
        store.data["_token"] = random_string()

    visitor = _authenticate(request, store, key_list)
    store.user_id = visitor.user_id
    result = (store, visitor)
    setattr(request, _ATTR, result)

    return result


def _authenticate(
    request: HttpRequest, store: Store, key_list: list[bytes]
) -> laravel_session.Visitor:
    """SessionGuard::user."""
    user_id = _as_id(store.data.get(laravel_session.LOGIN_KEY))

    if user_id is not None and _live_user(user_id) is not None:
        return laravel_session.Visitor(user_id, store.id, session=store.data)

    recaller = laravel_session.cookie_value(
        laravel_session.REMEMBER_COOKIE,
        request.COOKIES.get(laravel_session.REMEMBER_COOKIE),
        key_list,
    )

    if recaller:
        segments = recaller.split("|")

        # Recaller::valid: три части, номер и токен не пустые
        if len(segments) >= 3 and segments[0].strip() != "" and segments[1].strip() != "":
            user_id = _as_id(segments[0])
            row = _live_user(user_id) if user_id is not None else None

            if (
                row is not None
                and row[1]
                and hmac.compare_digest(str(row[1]).encode(), segments[1].encode())
            ):
                # updateSession: вход — в сессию, сессия — под новым номером
                store.data[laravel_session.LOGIN_KEY] = user_id
                store.migrate()

                return laravel_session.Visitor(
                    user_id, store.id, via_remember=True, session=store.data
                )

    return laravel_session.Visitor(session_id=store.id, session=store.data)


def remember_locale(request: HttpRequest, store: Store, locale: str) -> None:
    """
    SetLocale: язык из префикса — в сессию и в профиль. Сравнение
    обязательно, как у Laravel: иначе каждая страница писала бы UPDATE.
    """
    store.put("locale", locale)

    if store.user_id is not None:
        save_user_locale(request, store.user_id, locale)


def save_user_locale(request: HttpRequest, user_id: int, locale: str) -> None:
    """
    $user->update(['locale' => …]): запись, только если язык сменился.
    Правка администратора — строка журнала, как AuditObserver (раздел users).
    """
    from savdex import access, audit

    with connection.cursor() as cursor:
        cursor.execute(
            "select locale, name, email, is_admin, admin_role, status from users where id = %s",
            [user_id],
        )
        row = cursor.fetchone()

    if row is None or row[0] == locale:
        return

    before, name, email, is_admin, role, status = row
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    with allowed_writes("users"), connection.cursor() as cursor:
        cursor.execute(
            "update users set locale = %s, updated_at = %s where id = %s",
            [locale, stamp, user_id],
        )

    if is_admin:
        admin = access.Admin(
            id=user_id, name=name, email=email, is_admin=True, role=role, status=status
        )
        audit.record(
            connection,
            action="updated",
            section="users",
            actor=admin,
            subject_type="App\\Models\\User",
            subject_id=user_id,
            subject_label=audit.label({"name": name, "email": email}, "User", user_id),
            changes={"before": {"locale": before}, "after": {"locale": locale}},
            ip=client_ip(request),
        )


# ── После страницы: адрес, куки, запись ─────────────────────────────


def _env_bool(name: str, default: bool | None) -> bool | None:
    """env() Laravel для флага: true/false, null — не задано."""
    raw = os.environ.get(name)

    if raw is None:
        return default

    value = raw.strip().lower().strip("()")

    if value == "true":
        return True

    if value == "false":
        return False

    if value in ("null", ""):
        return None if value == "null" else default

    return bool(raw)


def _env_str(name: str, default: str | None) -> str | None:
    raw = os.environ.get(name)

    if raw is None:
        return default

    if raw.strip().lower() in ("null", "(null)"):
        return None

    return raw


def _set_cookie(
    response: HttpResponse,
    store: Store,
    name: str,
    value: str,
    key: bytes,
    *,
    http_only: bool,
    session_cookie: bool,
) -> None:
    """Кука, как её собирает Symfony Cookie и шифрует EncryptCookies."""
    secure = _env_bool("SESSION_SECURE_COOKIE", None)

    if secure is None:
        # null — «как у запроса» (Response::prepare → setSecureDefault)
        secure = store.root.startswith("https://")

    same_site = _env_str("SESSION_SAME_SITE", "lax")
    expire_on_close = bool(_env_bool("SESSION_EXPIRE_ON_CLOSE", False))

    response.set_cookie(
        name,
        # Symfony: rawurlencode значения
        quote(laravel_session.encrypt_cookie(name, value, key), safe=""),
        max_age=None if (session_cookie and expire_on_close) else laravel_session.lifetime(),
        path=_env_str("SESSION_PATH", "/") or "/",
        domain=_env_str("SESSION_DOMAIN", None) or None,
        secure=secure,
        httponly=http_only,
        samesite=_same_site(same_site),
    )


def _queued_cookie(
    response: HttpResponse,
    store: Store,
    name: str,
    value: str | None,
    minutes: int,
    key: bytes,
) -> None:
    """CookieJar::make и ::forget (значение null, срок в прошлом), зашифрованные."""
    secure = _env_bool("SESSION_SECURE_COOKIE", None)

    if secure is None:
        secure = store.root.startswith("https://")

    response.set_cookie(
        name,
        quote(laravel_session.encrypt_cookie(name, value or "", key), safe=""),
        max_age=max(0, minutes * 60),
        expires=None if value is not None else "Thu, 01 Jan 1970 00:00:00 GMT",
        path=_env_str("SESSION_PATH", "/") or "/",
        domain=_env_str("SESSION_DOMAIN", None) or None,
        secure=secure,
        httponly=True,
        samesite=_same_site(_env_str("SESSION_SAME_SITE", "lax")),
    )


def _same_site(value: str | None) -> Literal["Lax", "Strict", "None"] | None:
    """same_site из config/session.php — так, как его понимает Django."""
    match (value or "").lower():
        case "lax":
            return "Lax"
        case "strict":
            return "Strict"
        case "none":
            return "None"

    return None


def _prefetch(request: HttpRequest) -> bool:
    """Request::prefetch."""
    return any(
        (request.headers.get(h) or "").lower() == "prefetch"
        for h in ("X-Moz", "Purpose", "Sec-Purpose")
    )


def _user_agent(request: HttpRequest) -> str:
    """substr((string) User-Agent, 0, 500) — байты, как у PHP."""
    raw = (request.headers.get("User-Agent") or "").encode()[:500]

    return raw.decode(errors="ignore")


def finish(request: HttpRequest, response: HttpResponse) -> HttpResponse:
    """StartSession после страницы: storeCurrentUrl, куки, save."""
    started = getattr(request, _ATTR, None)

    if started is None:
        return response

    store: Store = started[0]
    key = laravel_session.keys()[0]

    if (
        request.method == "GET"
        and request.headers.get("X-Requested-With") != "XMLHttpRequest"
        and not _prefetch(request)
    ):
        store.put("_previous.url", store.full_url)
        match = request.resolver_match
        store.put("_previous.route", match.url_name if match else None)

    _set_cookie(
        response,
        store,
        laravel_session.cookie_name(),
        store.id,
        key,
        http_only=_env_bool("SESSION_HTTP_ONLY", True) is not False,
        session_cookie=True,
    )
    # PreventRequestForgery: XSRF-TOKEN — на каждый ответ, читается скриптом;
    # отказ по токену (419) куку не получает — её ставит сам посредник
    if not store.csrf_refused:
        _set_cookie(
            response, store, "XSRF-TOKEN", store.token, key, http_only=False, session_cookie=False
        )

    # AddQueuedCookiesToResponse: «запомнить меня» и её удаление
    for name, value, minutes in store.queued:
        _queued_cookie(response, store, name, value, minutes, key)

    store.age_flash()

    try:
        _write(request, store)
    except DatabaseError:
        # Страница уже собрана: несохранённая сессия — это старое
        # поведение Django (только чтение), а не повод отдать 500
        log.exception("Сессия %s не сохранена", store.id[:6])

    return response


def _write(request: HttpRequest, store: Store) -> None:
    """DatabaseSessionHandler::write: UPDATE, если строка есть, иначе INSERT."""
    row: dict[str, Any] = {
        "payload": base64.b64encode(php_json_encode(store.data).encode()).decode(),
        "last_activity": int(time.time()),
        "user_id": store.user_id,
        "ip_address": client_ip(request),
        "user_agent": _user_agent(request),
    }
    columns = list(row)

    with allowed_writes("sessions"), connection.cursor() as cursor:
        if store.exists:
            cursor.execute(
                "update sessions set " + ", ".join(f"{c} = %s" for c in columns) + " where id = %s",
                [*row.values(), store.id],
            )
        else:
            # performInsert: гонка с параллельным запросом — тогда UPDATE
            cursor.execute(
                f"insert into sessions (id, {', '.join(columns)}) "
                f"values (%s, {', '.join(['%s'] * len(columns))}) "
                "on conflict (id) do update set "
                + ", ".join(f"{c} = excluded.{c}" for c in columns),
                [store.id, *row.values()],
            )

    store.exists = True


class SessionMiddleware:
    """Сохраняет сессию Laravel после страницы сайта, если она её начала."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return finish(request, self.get_response(request))
