"""
Рассылка по сегменту — копия Notifier::broadcast и
BroadcastForm::countRecipients: получатели — действующие пользователи
сегмента, по уведомлению каждому (вставка пачками по 500), затем число
получателей и время отправки у рассылки.
"""

from __future__ import annotations

from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from savdex.guards import allowed_writes
from savdex.system.models import Broadcast

#: Действующая подписка компании (Company::subscription — последняя из них)
_PLAN = """
    exists (
        select 1 from subscriptions s join plans p on p.id = s.plan_id
        where s.id = (
            select max(s2.id) from subscriptions s2
            where s2.company_id = users.company_id and s2.status = 'active'
              and (s2.ends_at is null or s2.ends_at > %s)
        ) and p.code = %s
    )
"""


def _segment(audience: str | None, value: str | None) -> tuple[str, list[Any]]:
    """Notifier::audienceQuery: условие на users и его параметры."""
    base = "users.status = 'active' and users.deleted_at is null"

    if audience == "plan":
        return f"{base} and {_PLAN}", [timezone.now().replace(tzinfo=None), value]

    if audience == "verified":
        return (
            f"{base} and exists (select 1 from companies c where c.id = users.company_id "
            "and c.deleted_at is null and c.verification_level > 0)",
            [],
        )

    if audience == "unverified":
        return (
            f"{base} and exists (select 1 from companies c where c.id = users.company_id "
            "and c.deleted_at is null and c.verification_level = 0)",
            [],
        )

    if audience == "no_company":
        return f"{base} and users.company_id is null", []

    return base, []


def count_recipients(audience: str | None, value: str | None) -> int:
    where, params = _segment(audience, value)

    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from users where {where}", params)

        return int(cursor.fetchone()[0])


def send(broadcast: Broadcast, sender_id: int) -> int | None:
    """
    Уведомления сегменту пачками по 500, потом — сколько и когда. Всё в
    одной транзакции под замком рассылки: два «Отправить» разом слали
    каждому дважды. Уже отправленная — None, второй раз не уходит.
    """
    with transaction.atomic():
        locked = Broadcast.objects.select_for_update().get(pk=broadcast.pk)

        if locked.sent_at is not None:
            return None

        return _send(broadcast, sender_id)


def _send(broadcast: Broadcast, sender_id: int) -> int:
    broadcast.sent_by_id = sender_id
    broadcast.save()
    where, params = _segment(broadcast.audience, broadcast.audience_value)
    now = timezone.now().replace(microsecond=0, tzinfo=None)
    total = 0
    last = 0

    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                f"select id, company_id from users where {where} and users.id > %s "
                "order by id limit 500",
                [*params, last],
            )
            users = cursor.fetchall()

        if not users:
            break

        rows = [
            (
                uid,
                company,
                "broadcast",
                broadcast.tone or "info",
                broadcast.title,
                broadcast.body,
                broadcast.url,
                sender_id,
                True,
                now,
                now,
            )
            for uid, company in users
        ]

        with allowed_writes("user_notifications"), connection.cursor() as cursor:
            cursor.executemany(
                "insert into user_notifications (user_id, company_id, type, tone, title, body, "
                "url, sent_by, is_broadcast, created_at, updated_at) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                rows,
            )

        total += len(rows)
        last = int(users[-1][0])

    broadcast.recipients_count = total
    broadcast.sent_at = timezone.now().replace(microsecond=0)
    broadcast.save()

    return total
