"""
Сверка денег (этап 7, шаг 55): месяц параллельной работы.

По каждому свежему счёту заново выводится, что должна была оставить
выдача OrderService::settle (у Laravel) и settlement.mark_paid (у
Django), и сравнивается с тем, что лежит в базе. Проверка одна на обе
стороны: не важно, кто провёл платёж — колбэк на Django, колбэк на
Laravel или администратор в панели, — итог обязан быть одинаковым.

Что проверяется:

- номер счёта из id (SVD-000123);
- оплаченный счёт за тариф — ровно одна подписка «Оплата счёта N» на
  тот же тариф и компанию, по оплате, со сроком тарифа, начатая в
  момент оплаты; скидочный промокод счёта — связан с этой подпиской;
- оплаченный счёт за пакет — ровно одна запись истории кошелька:
  покупка, кредиты пакета;
- проведённая транзакция провайдера — только у оплаченного (или
  возвращённого) счёта, сумма — сумма счёта в тийинах;
- отменённый и ждущий счёт ничего не выдали; промокод ждущего счёта
  закреплён за его компанией.

Расхождение — строка в журнале приложения (ERROR) и письмо; одно и то
же расхождение письмом повторно не приходит (память — файл состояния).
Критерий шага: месяц без расхождений — Django становится хозяином таблиц
денег (docs/migration-to-python.md, этап 7).
"""

from __future__ import annotations

import html
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection

log = logging.getLogger("savdex.payments.reconcile")

#: Насколько подписка может начаться позже отметки об оплате: выдача
#: идёт одной транзакцией, но now() у Carbon и базы — разные вызовы
START_SLACK = timedelta(minutes=5)


@dataclass(frozen=True)
class Discrepancy:
    """Одно расхождение: счёт, код проверки и понятное объяснение."""

    number: str
    code: str
    message: str

    @property
    def key(self) -> str:
        return f"{self.number}:{self.code}"


def _rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        columns = [c[0] for c in cursor.description]

        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _one(query: str, params: list[Any]) -> dict[str, Any] | None:
    found = _rows(query, params)

    return found[0] if found else None


def check_payment(payment: dict[str, Any]) -> list[Discrepancy]:
    """Все проверки одного счёта."""
    number = payment["number"] or f"#{payment['id']}"
    found: list[Discrepancy] = []

    def fail(code: str, message: str) -> None:
        found.append(Discrepancy(number, code, message))

    if (payment["number"] or "").startswith("SVD-") and payment[
        "number"
    ] != f"SVD-{payment['id']:06d}":
        fail("number", f"номер не из id {payment['id']}")

    granted = _rows(
        "select * from subscriptions where grant_reason = %s order by id",
        [f"Оплата счёта {payment['number']}"],
    )
    credits = _rows(
        "select * from wallet_transactions where subject_type = 'App\\Models\\Payment' "
        "and subject_id = %s and reason = 'purchase' order by id",
        [payment["id"]],
    )
    status = payment["status"]

    if status == "paid" and payment["paid_at"] is None:
        fail("paid_at", "оплачен без даты оплаты")

    if status in ("paid", "refunded") and payment["purpose"] == "subscription":
        _check_plan(payment, granted, fail)
    elif status in ("paid", "refunded") and payment["purpose"] == "credits":
        _check_credits(payment, credits, fail)

    if status in ("pending", "failed"):
        if granted:
            fail("granted_unpaid", f"не оплачен ({status}), но выдана подписка")

        if credits:
            fail("credited_unpaid", f"не оплачен ({status}), но начислены кредиты")

        if payment["subscription_id"] is not None:
            fail("subscription_unpaid", f"не оплачен ({status}), но связан с подпиской")

    if status == "pending" and payment["promo_code_id"] is not None:
        promo = _one("select * from promo_codes where id = %s", [payment["promo_code_id"]])

        if promo is None or promo["used_by_company_id"] != payment["company_id"]:
            fail("promo_pending", "промокод ждущего счёта не закреплён за его компанией")

    for tx in _rows(
        "select * from payment_transactions where payment_id = %s and state = 'performed'",
        [payment["id"]],
    ):
        if status not in ("paid", "refunded"):
            fail(
                "tx_unpaid",
                f"транзакция {tx['provider_transaction_id']} проведена, счёт — {status}",
            )

        if tx["amount_minor"] is not None and tx["amount_minor"] != int(payment["amount"]) * 100:
            fail(
                "tx_amount",
                f"транзакция {tx['provider_transaction_id']} на {tx['amount_minor']} тийинов, "
                f"счёт — на {int(payment['amount']) * 100}",
            )

    return found


def _check_plan(payment: dict[str, Any], granted: list[dict[str, Any]], fail: Any) -> None:  # noqa: ANN401
    """Оплаченный тариф: одна подписка по оплате, как SubscriptionService::assign."""
    if len(granted) != 1:
        fail("plan_count", f"подписок по оплате — {len(granted)}, нужна одна")

    if not granted:
        return

    subscription = granted[0]
    plan = _one("select * from plans where id = %s", [payment["plan_id"]])

    if payment["subscription_id"] != subscription["id"]:
        fail("plan_link", "счёт не связан с выданной подпиской")

    if subscription["company_id"] != payment["company_id"]:
        fail("plan_company", "подписка выдана другой компании")

    if subscription["plan_id"] != payment["plan_id"]:
        fail("plan_plan", "подписка на другой тариф")

    # Выдал администратор (подтвердил перевод) — он же в granted_by;
    # колбэк провайдера — никто
    if subscription["source"] != "payment" or subscription["granted_by"] != payment["confirmed_by"]:
        fail("plan_source", "подписка выдана не по оплате этого счёта")

    if plan is not None:
        days = int(plan["period_days"])
        expected = subscription["started_at"] + timedelta(days=days) if days > 0 else None

        if subscription["ends_at"] != expected:
            fail("plan_period", f"срок подписки не {days} дн. от начала")

    paid = payment["paid_at"]

    if paid is not None and not (
        paid - START_SLACK <= subscription["started_at"] <= paid + START_SLACK
    ):
        fail("plan_start", "подписка начата не в момент оплаты")

    if payment["promo_code_id"] is not None:
        promo = _one("select * from promo_codes where id = %s", [payment["promo_code_id"]])

        if promo is None or promo["subscription_id"] != subscription["id"]:
            fail("plan_promo", "промокод счёта не связан с выданной подпиской")


def _check_credits(payment: dict[str, Any], credits: list[dict[str, Any]], fail: Any) -> None:  # noqa: ANN401
    """Оплаченный пакет: одна запись истории, как OrderService::grantCredits."""
    if len(credits) != 1:
        fail("credits_count", f"начислений кредитов — {len(credits)}, нужно одно")

    pack = _one("select * from credit_packs where id = %s", [payment["credit_pack_id"]])

    for entry in credits[:1]:
        if entry["kind"] != "credits":
            fail("credits_kind", f"начислено не в кредиты, а в {entry['kind']}")

        if pack is not None and entry["amount"] != pack["credits"]:
            fail("credits_amount", f"начислено {entry['amount']}, в пакете — {pack['credits']}")

        if entry["company_id"] != payment["company_id"]:
            fail("credits_company", "кредиты начислены другой компании")


def run(days: int = 2) -> list[Discrepancy]:
    """Сверить счета, тронутые за последние days дней (0 — все)."""
    if days > 0:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
        payments = _rows(
            "select * from payments where updated_at >= %s or paid_at >= %s order by id",
            [since, since],
        )
    else:
        payments = _rows("select * from payments order by id")

    found: list[Discrepancy] = []

    for payment in payments:
        found.extend(check_payment(payment))

    return found


# ── Сообщить ────────────────────────────────────────────────────────


def _state_path() -> Path:
    configured = os.environ.get("BILLING_RECONCILE_STATE")

    if configured:
        return Path(configured)

    return Path(settings.LARAVEL_ROOT) / "storage/app/billing-reconcile.json"


def _recipients() -> list[str]:
    """BILLING_RECONCILE_EMAIL через запятую, иначе — суперадмины."""
    configured = os.environ.get("BILLING_RECONCILE_EMAIL") or ""
    listed = [a.strip() for a in configured.split(",") if a.strip()]

    if listed:
        return listed

    return [
        r["email"]
        for r in _rows(
            "select email from users where is_admin and admin_role = 'superadmin' "
            "and deleted_at is null order by id"
        )
    ]


def report(found: list[Discrepancy]) -> list[Discrepancy]:
    """
    Журнал — каждое расхождение каждый раз; письмо — только о новых.
    Вернуть новые.
    """
    from savdex.web import mail

    for item in found:
        log.error("Расхождение в деньгах: %s — %s (%s)", item.number, item.message, item.code)

    path = _state_path()

    try:
        seen = set(json.loads(path.read_text()))
    except (OSError, ValueError):
        seen = set()

    fresh = [item for item in found if item.key not in seen]

    if fresh:
        lines = [f"{item.number}: {item.message} ({item.code})" for item in fresh]
        text = (
            "Сверка денег нашла новые расхождения:\n\n"
            + "\n".join(lines)
            + "\n\nПодробности — manage.py reconcile_billing --all."
        )
        body = (
            "<p>Сверка денег нашла новые расхождения:</p><ul>"
            + "".join(f"<li>{html.escape(line)}</li>" for line in lines)
            + "</ul>"
        )
        subject = f"SAVDEX: расхождения в деньгах ({len(fresh)})"
        sent = [mail.send(to, subject, body, text) for to in _recipients()]

        # Не дошло ни одно письмо — не запоминать: пусть придёт в следующий раз
        if not any(sent):
            return fresh

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(seen | {item.key for item in found})))
    except OSError:
        log.exception("Состояние сверки денег не записано: %s", path)

    return fresh
