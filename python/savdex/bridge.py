"""
Вход в админку Django по пропуску из Laravel.

Перенос идёт по частям: первые разделы админки переезжают на Django
раньше, чем Django научится читать сессию Laravel (этап 3). Поэтому
вход — через Laravel (App\\Support\\PythonBridge):

1. Сотрудник уже в админке Laravel и открывает /admin/python.
2. Laravel отдаёт форму, которая POST-ом приносит сюда пропуск:
   номер пользователя, адрес, срок в минуту, подпись HMAC-SHA256.
3. Здесь подпись и срок проверяются, а пользователь заново читается
   из базы: пропуск говорит только «это он», права решает Django.
4. Django ставит свою подписанную куку и дальше на каждом запросе
   снова читает пользователя: блокировка, снятая роль, удаление
   действуют сразу, а не когда истечёт вход.

Своих таблиц сессий у Django нет — кука подписана SECRET_KEY и хранит
только номер и время входа.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core import signing

from savdex import access

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

#: Адрес Django-админки и куда вести по умолчанию — как PythonBridge::HOME
HOME = "/py/admin/"

#: Кука входа: своя, путь — только разделы Django
COOKIE = "savdex_py_admin"
COOKIE_PATH = "/py/"

#: Сколько живёт вход без нового пропуска. Истёк — переход через Laravel
#: заново, для вошедшего в Laravel это незаметный круг
SESSION_TTL = 2 * 60 * 60

_SALT = "savdex.bridge.session"


class BridgeError(Exception):
    """Пропуск не годится. Текст — для журнала, не для посетителя."""


@dataclass(frozen=True)
class Pass:
    uid: int
    next: str


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def enabled() -> bool:
    """
    Вход работает только с настоящими ключами.

    Без APP_KEY подпись пропуска и куки — известным всем ключом
    разработчика: подделать вход мог бы кто угодно. Лучше отказать.
    """
    return bool(settings.SECRET_KEY_IS_REAL) and _bridge_key() is not None


def _bridge_key() -> bytes | None:
    """PythonBridge::key(): HMAC-SHA256 от APP_KEY с меткой."""
    from savdex.settings import _app_key

    key = _app_key()

    return hmac.new(key, b"savdex-django-bridge-v1", hashlib.sha256).digest() if key else None


def safe_next(value: Any) -> str:  # noqa: ANN401
    """PythonBridge::safeNext(): только адреса Django-админки."""
    text = value if isinstance(value, str) else ""

    if (
        not text.startswith(HOME)
        or "//" in text
        or "\\" in text
        or re.search(r"[\x00-\x1f\x7f]", text)
    ):
        return HOME

    return text


def verify(token: str, now: float | None = None) -> Pass:
    """Проверить пропуск. Не годится — BridgeError."""
    key = _bridge_key()

    if key is None:
        raise BridgeError("нет APP_KEY — пропуски не принимаются")

    payload, _, signature = token.partition(".")

    if not payload or not signature:
        raise BridgeError("пропуск без подписи")

    expected = hmac.new(key, payload.encode("ascii", "replace"), hashlib.sha256).digest()

    try:
        given = _b64decode(signature)
        data = json.loads(_b64decode(payload))
    except (ValueError, TypeError) as error:
        raise BridgeError("пропуск не разбирается") from error

    if not hmac.compare_digest(expected, given):
        raise BridgeError("подпись не сходится")

    if not isinstance(data, dict):
        raise BridgeError("пропуск не разбирается")

    uid, exp = data.get("uid"), data.get("exp")

    if not isinstance(uid, int) or isinstance(uid, bool) or not isinstance(exp, int):
        raise BridgeError("в пропуске нет номера или срока")

    if (now if now is not None else time.time()) > exp:
        raise BridgeError("пропуск просрочен")

    return Pass(uid=uid, next=safe_next(data.get("next")))


def session_cookie(uid: int) -> str:
    """Значение куки входа: номер, подписанный SECRET_KEY, со временем."""
    return signing.dumps({"uid": uid}, salt=_SALT, compress=False)


def session_uid(value: str | None) -> int | None:
    """Номер из куки входа, если подпись цела и вход не истёк."""
    if not value:
        return None

    try:
        data = signing.loads(value, salt=_SALT, max_age=SESSION_TTL)
    except signing.BadSignature:
        return None

    uid = data.get("uid") if isinstance(data, dict) else None

    return uid if isinstance(uid, int) and not isinstance(uid, bool) else None


def load_admin(connection: BaseDatabaseWrapper, uid: int) -> access.Admin | None:
    """
    Сотрудник, которому можно в админку, — или None.

    Те же условия, что у Laravel: User::canAccessPanel (администратор
    и активен), удалённых поиск не видит, а с невыданным ещё своим
    паролем RequirePasswordChange не пускает дальше смены пароля.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "select id, name, email, is_admin, admin_role, status, admin_permissions, "
            "must_change_password from users where id = %s and deleted_at is null",
            [uid],
        )
        row = cursor.fetchone()

    if row is None:
        return None

    permissions = row[6]

    if isinstance(permissions, str | bytes):
        try:
            permissions = json.loads(permissions)
        except ValueError:
            permissions = None

    admin = access.Admin(
        id=int(row[0]),
        name=str(row[1]),
        email=str(row[2]),
        is_admin=bool(row[3]),
        role=row[4],
        status=str(row[5]),
        permissions=permissions if isinstance(permissions, dict) else {},
    )

    if not admin.is_admin or admin.status != "active" or bool(row[7]):
        return None

    return admin
