"""
CRM сама: то, что менеджер иначе делал бы руками.

- Оплата → сделка (close_deal_on_payment): счёт компании оплачен —
  её открытая сделка переходит на этап «Выиграна». Сумма пустой сделки
  берётся из счёта, в заметку — строка «оплачен счёт №…», в журнал —
  смена этапа. Открытой сделки нет — ничего не создаётся: самостоятельные
  покупки на сайте сделками не становятся.
- Заявка с сайта → лид (lead_from_site): форма на странице «Контакты»
  создаёт лид с источником «Форма на сайте» на первом этапе доски.

Обе — после главного действия и не ломают его: оплата уже начислена,
заявка уже принята; сбой CRM — строка в журнале приложения.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import connections, transaction
from django.db.models import Case, IntegerField, Q, Value, When

from savdex import access, audit
from savdex.crm import stages
from savdex.crm.board import _append
from savdex.crm.models import CURRENCIES, Deal, Lead

log = logging.getLogger("savdex.crm")

DEAL = "App\\Models\\Crm\\Deal"
LEAD = "App\\Models\\Crm\\Lead"

#: Подпись в заметке сделки вместо имени сотрудника
AUTHOR = "автоматически"


def _money(amount: int, currency: str) -> str:
    return f"{amount:,}".replace(",", " ") + " " + CURRENCIES.get(currency, currency)


def _open_deal(company_id: int, amount: int, currency: str) -> Deal | None:
    """
    Открытая сделка компании, которую закрывает оплата: сначала — на ту
    же сумму, иначе — та, с которой работали последней.
    """
    found: Deal | None = (
        Deal.objects.filter(company_id=company_id)
        .exclude(stage__in=("won", "lost"))
        .annotate(
            same=Case(
                When(Q(amount=amount, currency=currency), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("same", "-updated_at", "-id")
        .first()
    )

    return found


def close_deal_on_payment(payment: dict[str, Any], *, actor_id: int | None = None) -> Deal | None:
    """
    Счёт оплачен — открытая сделка компании выиграна. actor_id —
    сотрудник, отметивший оплату («Деньги пришли»); шлюз — None.
    Возвращает закрытую сделку или None. Никогда не бросает.
    """
    try:
        return _close(payment, actor_id)
    except Exception:
        log.exception("CRM: сделка по оплате счёта %s не закрыта", payment.get("number"))

        return None


def _close(payment: dict[str, Any], actor_id: int | None) -> Deal | None:
    company_id = payment.get("company_id")

    if company_id is None:
        return None

    amount = int(payment.get("amount") or 0)
    currency = str(payment.get("currency") or "UZS")
    money = _money(amount, currency)

    with transaction.atomic():
        found = _open_deal(int(company_id), amount, currency)

        if found is None:
            return None

        # Под замком: две оплаты разом не закрывают одну сделку дважды
        deal: Deal | None = Deal.objects.select_for_update().filter(pk=found.pk).first()

        if deal is None or not deal.is_open:
            return None

        was = deal.stage
        before = {"stage": was, "amount": deal.amount, "currency": deal.currency}

        if deal.amount == 0 and amount > 0 and currency in CURRENCIES:
            deal.amount = amount
            deal.currency = currency

        deal.stage = "won"
        deal.note = _append(deal.note, f"оплачен счёт {payment['number']} ({money})", AUTHOR)
        deal.save()

    after = {"stage": deal.stage, "amount": deal.amount, "currency": deal.currency}
    changed = {k: v for k, v in after.items() if before[k] != v}
    names = stages.names("deals")

    audit.record(
        connections["default"],
        action="updated",
        section="deals",
        actor=_actor(actor_id),
        subject_type=DEAL,
        subject_id=deal.pk,
        subject_label=str(deal),
        changes={"before": {k: before[k] for k in changed}, "after": changed},
        note=(
            f"Этап: «{names.get(was, was)}» → «{names.get('won', 'Выиграна')}» — "
            f"автоматически, оплачен счёт {payment['number']} ({money})"
        ),
    )

    return deal


def _actor(actor_id: int | None) -> access.Admin | None:
    """Кто отметил оплату — в журнале его имя; шлюз — без имени."""
    if actor_id is None:
        return None

    from savdex import bridge

    return bridge.load_admin(connections["default"], actor_id)


def lead_from_site(
    *,
    name: str,
    phone: str | None,
    email: str | None,
    company: str | None,
    message: str,
    company_id: int | None = None,
    locale: str | None = None,
    ip: str | None = None,
) -> Lead:
    """
    Заявка с формы «Контакты» — лид на первом этапе, без ответственного:
    его берёт себе первый свободный менеджер («Взять себе» на доске).
    """
    text = " ".join(message.split())
    title = text if len(text) <= 120 else text[:119].rstrip() + "…"
    lines = [message.strip()]

    if company:
        lines.append(f"Компания (со слов): {company}")

    if locale:
        lines.append(f"Язык сайта: {locale}")

    lead = Lead(
        title=title or "Заявка с сайта",
        source="site",
        company_id=company_id,
        contact_name=name[:160],
        contact_phone=(phone or None) and phone[:40],
        contact_email=(email or None) and email[:160],
        status="new",
        note="\n".join(lines),
    )
    lead.save()

    from savdex.adminsite import SavdexModelAdmin

    audit.record(
        connections["default"],
        action="created",
        section="leads",
        actor=None,
        subject_type=LEAD,
        subject_id=lead.pk,
        subject_label=lead.title,
        changes={"after": SavdexModelAdmin.attributes(lead)},
        note="Заявка с сайта (страница «Контакты»)",
        ip=ip,
    )

    return lead
