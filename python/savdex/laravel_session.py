"""
Кто вошёл на сайт — по сессии Laravel (этап 3 переноса, шаг 1).

Страницы сайта переезжают на Django по одной, и посетитель ходит между
страницами Laravel и Django, не замечая шва: вошёл на одной — вошёл и на
другой. Вход по-прежнему ведёт Laravel; Django сессию только **читает**
(запись — за Laravel до этапа 5), так же, как её читает сам Laravel:

1. Кука сессии («savdex-session») зашифрована APP_KEY — как
   Illuminate\\Encryption\\Encrypter: AES-256-CBC, подпись HMAC-SHA256
   поверх base64 вектора и шифротекста. Подпись сверяется до
   расшифровки: подменённую куку отбрасываем, не расшифровывая.
2. Внутри — «префикс|номер сессии»; префикс — HMAC-SHA1 от имени куки
   (CookieValuePrefix), он не даёт подсунуть расшифрованное значение
   одной куки под именем другой.
3. Строка таблицы sessions: полезная нагрузка — base64 от JSON
   (config/session.php, 'serialization' => 'json'), просроченная
   (last_activity старше SESSION_LIFETIME) не считается, как в
   DatabaseSessionHandler.
4. Номер пользователя — ключ login_web_<sha1(SessionGuard)>.
5. Нет сессии, но есть кука «запомнить меня» (remember_web_…) —
   Laravel впускает по ней: «номер|токен|хеш», токен сверяется с
   users.remember_token. Django делает то же, но новую сессию не
   заводит — это запись.

Пользователь в корзине (deleted_at) не вошёл: EloquentUserProvider его
не находит. Прочее (блокировка, роль) решает страница, как и в Laravel.

Сверка с настоящим Laravel — tests/test_laravel_session.py: вход на
странице Laravel → Django узнаёт того же пользователя.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

#: sha1(Illuminate\Auth\SessionGuard::class) — часть имён ключа и куки
_GUARD = hashlib.sha1(b"Illuminate\\Auth\\SessionGuard").hexdigest()

#: SessionGuard::getName() и getRecallerName() для охранника web
LOGIN_KEY = f"login_web_{_GUARD}"
REMEMBER_COOKIE = f"remember_web_{_GUARD}"


@dataclass(frozen=True)
class Visitor:
    """Кто пришёл: номер пользователя (None — гость) и откуда это известно."""

    user_id: int | None = None
    session_id: str | None = None
    #: Узнан по куке «запомнить меня», а не по сессии
    via_remember: bool = False
    #: Содержимое сессии (язык, сообщения, ошибки форм) — только чтение
    session: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def authenticated(self) -> bool:
        return self.user_id is not None


GUEST = Visitor()


# ── Ключи и имена ───────────────────────────────────────────────────


def _parse_key(raw: str) -> bytes | None:
    """Encrypter::parseKey: «base64:…» или ключ как есть."""
    raw = raw.strip()

    if raw.startswith("base64:"):
        try:
            return base64.b64decode(raw[7:], validate=True)
        except (binascii.Error, ValueError):
            return None

    return raw.encode() if raw else None


def keys() -> list[bytes]:
    """
    APP_KEY и прежние ключи (APP_PREVIOUS_KEYS через запятую) — как
    config/app.php: после смены ключа Laravel ещё читает старые куки.
    """
    found = [_parse_key(os.environ.get("APP_KEY", ""))]
    found += [_parse_key(k) for k in os.environ.get("APP_PREVIOUS_KEYS", "").split(",")]

    # AES-256 — ключ ровно 32 байта; другой Laravel бы тоже не принял
    return [k for k in found if k is not None and len(k) == 32]


def _slug(text: str) -> str:
    """Str::slug для имени приложения: латиница, цифры, дефисы."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def cookie_name() -> str:
    """config/session.php: SESSION_COOKIE или «<slug(APP_NAME)>-session»."""
    return (
        os.environ.get("SESSION_COOKIE")
        or f"{_slug(os.environ.get('APP_NAME', 'laravel'))}-session"
    )


def lifetime() -> int:
    """SESSION_LIFETIME в секундах (по умолчанию 120 минут, как в config)."""
    try:
        return int(os.environ.get("SESSION_LIFETIME", "120")) * 60
    except ValueError:
        return 120 * 60


# ── Кука ────────────────────────────────────────────────────────────


def decrypt(payload: str, key_list: list[bytes]) -> str | None:
    """
    Encrypter::decrypt без unserialize — куки Laravel не сериализует.

    Любая порча — None, а не исключение: битая кука значит «гость».
    """
    try:
        data = json.loads(base64.b64decode(unquote(payload), validate=False))
        iv_b64, value_b64, mac = str(data["iv"]), str(data["value"]), str(data["mac"])
        iv = base64.b64decode(iv_b64, validate=True)
        ciphertext = base64.b64decode(value_b64, validate=True)
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None

    if len(iv) != 16:
        return None

    for key in key_list:
        expected = hmac.new(key, (iv_b64 + value_b64).encode(), hashlib.sha256).hexdigest()

        # Байтами: строка с не-ASCII знаками в подделанной куке уронила бы
        # compare_digest исключением — это 500 вместо «гостя»
        if not hmac.compare_digest(expected.encode(), mac.encode()):
            continue

        try:
            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            plain = unpadder.update(padded) + unpadder.finalize()

            return plain.decode()
        except (ValueError, UnicodeDecodeError):
            return None

    return None


def encrypt(plain: str, key: bytes) -> str:
    """
    Encrypter::encrypt($value, serialize: false) — как EncryptCookies
    шифрует куку: AES-256-CBC со случайным вектором, подпись HMAC-SHA256
    поверх base64 вектора и шифротекста, всё — JSON в base64.
    """
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    iv_b64 = base64.b64encode(iv).decode()
    value_b64 = base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()
    mac = hmac.new(key, (iv_b64 + value_b64).encode(), hashlib.sha256).hexdigest()
    # JSON_UNESCAPED_SLASHES, порядок ключей — compact('iv', 'value', 'mac', 'tag')
    payload = json.dumps(
        {"iv": iv_b64, "value": value_b64, "mac": mac, "tag": ""}, separators=(",", ":")
    )

    return base64.b64encode(payload.encode()).decode()


def cookie_prefix(name: str, key: bytes) -> str:
    """CookieValuePrefix::create: HMAC-SHA1 от «<имя>v2» и черта."""
    return hmac.new(key, f"{name}v2".encode(), hashlib.sha1).hexdigest() + "|"


def encrypt_cookie(name: str, value: str, key: bytes) -> str:
    """Значение куки, как его ставит EncryptCookies: префикс имени и шифр."""
    return encrypt(cookie_prefix(name, key) + value, key)


def cookie_value(name: str, raw: str | None, key_list: list[bytes]) -> str | None:
    """Значение куки без префикса CookieValuePrefix — или None, если не наше."""
    if not raw:
        return None

    plain = decrypt(raw, key_list)

    if plain is None:
        return None

    for key in key_list:
        prefix = cookie_prefix(name, key)

        if plain.startswith(prefix):
            return plain[len(prefix) :]

    return None


# ── Сессия и «запомнить меня» ───────────────────────────────────────


def session_data(connection: BaseDatabaseWrapper, session_id: str) -> dict[str, Any] | None:
    """Полезная нагрузка сессии, как её вернул бы DatabaseSessionHandler."""
    if not re.fullmatch(r"[A-Za-z0-9]{40}", session_id):
        # Session::isValidId: 40 букв и цифр — иначе Laravel выдал бы новую
        return None

    with connection.cursor() as cursor:
        cursor.execute("select payload, last_activity from sessions where id = %s", [session_id])
        row = cursor.fetchone()

    if row is None or int(row[1]) < int(time.time()) - lifetime():
        return None

    try:
        data = json.loads(base64.b64decode(row[0]))
    except (ValueError, binascii.Error):
        return None

    return data if isinstance(data, dict) else None


def _live_user(connection: BaseDatabaseWrapper, user_id: int) -> tuple[Any, ...] | None:
    """
    Строка пользователя, если он есть, не в корзине и не заблокирован:
    (id, remember_token). Заблокированный — гость во всех открытых сессиях.
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
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        return None

    return user_id if user_id > 0 else None


def identify(cookies: Mapping[str, str], connection: BaseDatabaseWrapper) -> Visitor:
    """Кто пришёл с этими куками — так, как решил бы Laravel."""
    key_list = keys()

    if not key_list:
        # Без настоящего ключа не расшифровать ничего — все гости
        return GUEST

    session_id = cookie_value(cookie_name(), cookies.get(cookie_name()), key_list)
    data: dict[str, Any] = {}

    if session_id:
        data = session_data(connection, session_id) or {}
        user_id = _as_id(data.get(LOGIN_KEY))

        if user_id is not None and _live_user(connection, user_id) is not None:
            return Visitor(user_id, session_id, session=data)

    recaller = cookie_value(REMEMBER_COOKIE, cookies.get(REMEMBER_COOKIE), key_list)

    if recaller and recaller.count("|") >= 2:
        raw_id, token = recaller.split("|", 2)[:2]
        user_id = _as_id(raw_id)
        row = _live_user(connection, user_id) if user_id is not None and token else None

        if row is not None and row[1] and hmac.compare_digest(str(row[1]).encode(), token.encode()):
            return Visitor(user_id, session_id, via_remember=True, session=data)

    return Visitor(session_id=session_id, session=data)
