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
import os
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

#: AdminLog::NOISE — меняются при каждом сохранении и ничего не сообщают;
#: stage_changed_at (когда карточка CRM пришла на этап) ставится сама, а
#: перевод журнал и так показывает этапом «было» и «стало»
NOISE = frozenset({"updated_at", "created_at", "search_text", "stage_changed_at"})


def update_action(before: Mapping[str, Any], changed: Mapping[str, Any]) -> str:
    """
    AuditObserver::name: блокировка называется блокировкой, а не
    «изменением» — её ищут отбором по действию («кто заблокировал»).
    """
    if "status" not in changed:
        return "updated"

    if changed["status"] == "blocked":
        return "blocked"

    return "unblocked" if before.get("status") == "blocked" else "updated"


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


#: Заголовки с адресом посетителя, которые ставит край сети (Cloudflare
#: перед Render) поверх присланного клиентом. Читаются, только если
#: запрос пришёл с адреса Cloudflare (CLOUDFLARE_NETWORKS): в обход
#: Cloudflare — напрямую на *.onrender.com или на сервер без него —
#: заголовок пишет сам посетитель. True-Client-IP не читается: без
#: тарифа Enterprise Cloudflare пропускает присланный клиентом как есть.
#: SAVDEX_CLIENT_IP_HEADERS — свой список через запятую, пусто — не читать
CLIENT_IP_HEADERS = "CF-Connecting-IP"

#: Адреса Cloudflare (https://www.cloudflare.com/ips/).
#: SAVDEX_EDGE_NETWORKS — свой список через запятую
CLOUDFLARE_NETWORKS = (
    "173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,"
    "141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,"
    "197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,"
    "104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,"
    "2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,"
    "2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32"
)


def _ip(value: object) -> str | None:
    # Мусор в заголовке — не адрес: столбец на 45 знаков, и Symfony
    # такое тоже отбрасывает
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def _hops() -> int:
    """SAVDEX_PROXY_HOPS: сколько прокси дописывают себя в X-Forwarded-For справа."""
    try:
        return max(int(os.environ.get("SAVDEX_PROXY_HOPS", "0")), 0)
    except ValueError:
        return 0


def _from_edge(peer: str | None) -> bool:
    """Пришёл ли запрос с края сети (Cloudflare) — тогда его заголовку можно верить."""
    if peer is None:
        return False

    address = ipaddress.ip_address(peer)
    networks = os.environ.get("SAVDEX_EDGE_NETWORKS", CLOUDFLARE_NETWORKS)

    for value in (n.strip() for n in networks.split(",")):
        try:
            if value and address in ipaddress.ip_network(value, strict=False):
                return True
        except ValueError:
            continue

    return False


def client_ip(request: HttpRequest | None) -> str | None:
    """
    Адрес посетителя — для журнала, сессий и замков от перебора.

    Render не чистит присланный клиентом X-Forwarded-For, а дописывает к
    нему справа: самый левый адрес (как Request::ip() у Laravel с
    trustProxies('*')) посетитель выбирает сам и обходит замок по IP.
    Поэтому сначала — заголовок края сети (CF-Connecting-IP), если
    запрос пришёл с адреса Cloudflare, затем X-Forwarded-For с заданным
    числом своих прокси справа (SAVDEX_PROXY_HOPS), и только без них —
    по-старому, самый левый.
    """
    if request is None:
        return None

    chain = [part.strip() for part in str(request.META.get("HTTP_X_FORWARDED_FOR", "")).split(",")]
    hops = _hops()
    # Кто подключился к нашим прокси: его адрес они дописали справа
    peer = _ip(chain[-hops]) if 0 < hops <= len(chain) else _ip(request.META.get("REMOTE_ADDR"))
    names = os.environ.get("SAVDEX_CLIENT_IP_HEADERS", CLIENT_IP_HEADERS)

    if _from_edge(peer):
        for name in (n.strip() for n in names.split(",")):
            if name and (found := _ip(request.headers.get(name, ""))) is not None:
                return found

    candidate = chain[-hops] if 0 < hops <= len(chain) else chain[0]

    for value in (candidate, request.META.get("REMOTE_ADDR")):
        if (found := _ip(value)) is not None:
            return found

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
