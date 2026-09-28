"""
Журнал действий администраторов — копия App\\Support\\AdminLog.

С этапа 2 в журнал пишут обе половины (раздел 5.1 документа переноса):
правка в разделе админки на Django должна оставить ту же строку в
admin_actions, что и правка в Filament, — иначе вопрос «кто и когда
поменял» получит половину ответа. Совпадение строк с PHP проверяет
tests/test_audit_parity.py.

Таблица добавляемая (guards.APPEND_ONLY_SHARED): только вставка.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from django.db import transaction

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.http import HttpRequest

    from savdex.access import Admin

log = logging.getLogger(__name__)

#: AdminLog::SECRET — в журнал не попадают никогда, вместо значения «···»
SECRET = frozenset(
    {"password", "remember_token", "two_factor_secret", "two_factor_recovery_codes", "api_token"}
)

#: AdminLog::NOISE — меняются при каждом сохранении и ничего не сообщают
NOISE = frozenset({"updated_at", "created_at", "search_text"})

#: Поля, из которых берётся понятное название записи (AdminLog::label)
_LABEL_FIELDS = ("name", "title", "email", "code", "slug")


def shorten(value: Any) -> Any:  # noqa: ANN401
    """AdminLog::shorten(): строки длиннее 300 знаков обрезаются с «…»."""
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + "…"

    return value


def clean(changes: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """AdminLog::clean(): убрать шум, спрятать секреты, обрезать длинное."""
    cleaned: dict[str, dict[str, Any]] = {}

    for side in ("before", "after"):
        for field, value in (changes.get(side) or {}).items():
            if field in NOISE:
                continue

            cleaned.setdefault(side, {})[field] = "···" if field in SECRET else shorten(value)

    return cleaned


def label(attributes: Mapping[str, Any], basename: str, key: Any) -> str:  # noqa: ANN401
    """AdminLog::label(): имя, заголовок, почта, код или slug — иначе «Класс #id»."""
    for field in _LABEL_FIELDS:
        value = attributes.get(field)

        if isinstance(value, str) and value != "":
            return value[:200]

    return f"{basename} #{key}"


def client_ip(request: HttpRequest | None) -> str | None:
    """
    Адрес посетителя — как Request::ip() у Laravel с trustProxies('*').

    Laravel доверяет всем прокси и берёт самый левый адрес из
    X-Forwarded-For: его ставит балансировщик Render. Apache перед
    Django добавляет свой адрес справа, на выбор это не влияет.
    """
    if request is None:
        return None

    forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))

    for candidate in (forwarded.split(",")[0].strip(), request.META.get("REMOTE_ADDR")):
        # Мусор в заголовке — не адрес: столбец на 45 знаков, и Symfony
        # такое тоже отбрасывает
        try:
            return str(ipaddress.ip_address(str(candidate)))
        except ValueError:
            continue

    return None


def _php_json(value: Any) -> str:  # noqa: ANN401
    """
    Как каст array у Eloquent (json_encode без флагов): компактно, «/» и
    не-ASCII экранированы — столбец json хранит текст как есть, и строка
    журнала от Django не отличается от строки Laravel.
    """
    from savdex.web.session import _php_value

    return json.dumps(
        _php_value(value), separators=(",", ":"), ensure_ascii=True, default=str
    ).replace("/", "\\/")


def record(
    connection: BaseDatabaseWrapper,
    *,
    action: str,
    section: str,
    actor: Admin | None,
    subject_type: str | None = None,
    subject_id: int | None = None,
    subject_label: str | None = None,
    changes: Mapping[str, Mapping[str, Any]] | None = None,
    note: str | None = None,
    ip: str | None = None,
) -> None:
    """
    AdminLog::record(): одна строка журнала.

    Журнал никогда не роняет действие, которое записывает: оно уже
    совершено. Запись — в точке сохранения, чтобы ошибка не отменила
    чужую транзакцию (в PostgreSQL первая ошибка губит транзакцию
    целиком); неудача оставляет след в журнале приложения.
    """
    cleaned = clean(changes or {})

    try:
        with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
            cursor.execute(
                "insert into admin_actions (user_id, user_name, user_role, action, section, "
                "subject_type, subject_id, subject_label, changes, note, ip, created_at) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    actor.id if actor else None,
                    # Снимок имени: ссылка умрёт вместе с удалённым сотрудником
                    (actor.name if actor else "консоль")[:120],
                    actor.role if actor else None,
                    action,
                    section,
                    subject_type,
                    subject_id,
                    subject_label,
                    # default=str: значение, которое JSON не знает (дата, число
                    # с фиксированной точкой), пишется строкой, а не губит строку
                    # журнала целиком — так уже было со справочниками в PHP
                    _php_json(cleaned) if cleaned else None,
                    note,
                    ip,
                    datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                ],
            )
    except Exception:
        log.exception("Запись в журнал действий не удалась: %s %s", action, section)
