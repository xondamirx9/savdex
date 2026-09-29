"""
Раскрытие контактов компании — форма на Django (этап 5, шаг 40).
Копия App\\Http\\Controllers\\Public\\ContactUnlockController и
App\\Services\\ContactUnlockService.

Посредники verified и throttle:30,60. Платят за компанию: повторное
раскрытие ничего не списывает. Сначала расходуется месячный лимит тарифа
(contacts_used_this_period), сверх него — кредит с записью в историю
кошелька (Wallet::spend). Остаток читается под блокировкой строки
кошелька в той же транзакции, что и списание; гонка на unique(company_id,
target_company_id) откатывает всё и отдаёт уже открытый контакт.
После транзакции — счётчик раскрытий объявления и дневная статистика
(StatsRecorder::unlock), уведомление компании, чьи контакты открыли.

Сверка с настоящим Laravel — tests/test_web_unlock_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web import eloquent
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of, company_plan
from savdex.web.catalog import bump_daily
from savdex.web.chat_actions import _unverified
from savdex.web.forms import action, back, flash, input_of
from savdex.web.listing_actions import _notify_company, _stamp
from savdex.web.phpquery import php_int
from savdex.web.shared import Context
from savdex.web.tenders import _admin
from savdex.web.views import not_found

BLOCKED = "blocked"


def _filled(value: Any) -> bool:  # noqa: ANN401
    """$request->filled(): массив и булево — заполнены, строка — не из одних пробелов."""
    if value is None:
        return False

    if isinstance(value, bool | list | dict):
        return True

    return str(value).strip() != ""


def _integer(value: Any) -> int:  # noqa: ANN401
    """$request->integer(): intval() PHP."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int | float):
        return int(value)

    if isinstance(value, list | dict):
        return 1 if value else 0

    return php_int(str(value), 0)


def _existing(company_id: int, target_id: int) -> dict[str, Any] | None:
    rows = _rows(
        "select * from contact_unlocks where company_id = %s and target_company_id = %s limit 1",
        [company_id, target_id],
    )

    return rows[0] if rows else None


def _spend_credit(wallet_id: int, user_id: int, target: dict[str, Any]) -> bool:
    """Wallet::spend('credits', 1, 'unlock', $target, $userId): условное списание и история."""
    now = _stamp(eloquent.now())

    with allowed_writes("wallets", "wallet_transactions"), connection.cursor() as cursor:
        cursor.execute(
            "update wallets set credits = credits - 1, updated_at = %s "
            "where id = %s and credits >= 1",
            [now, wallet_id],
        )

        if cursor.rowcount == 0:
            return False

        fresh = _rows("select company_id, credits from wallets where id = %s", [wallet_id])[0]
        cursor.execute(
            "insert into wallet_transactions (company_id, user_id, kind, amount, "
            "balance_after, reason, subject_type, subject_id, updated_at, created_at) "
            "values (%s, %s, 'credits', -1, %s, 'unlock', 'App\\Models\\Company', %s, %s, %s)",
            [fresh["company_id"], user_id, fresh["credits"], target["id"], now, now],
        )

    return True


def _charge(
    ctx: Context,
    company: dict[str, Any],
    target: dict[str, Any],
    listing: dict[str, Any] | None,
) -> tuple[str, str | None] | None:
    """
    ContactUnlockService::charge — внутри транзакции. Вернёт (сообщение,
    ключ) при успехе и None, если лимит исчерпан и кредитов нет.
    """
    assert ctx.user is not None
    plan = company_plan(company["id"])

    with transaction.atomic():
        locked = _rows("select * from wallets where id = %s for update", [company["wallet_id"]])

        if not locked:
            return None

        wallet = locked[0]
        limit = plan.get("contacts_limit")

        if limit is None or wallet["contacts_used_this_period"] < limit:
            now = _stamp(eloquent.now())

            with allowed_writes("wallets"), connection.cursor() as cursor:
                cursor.execute(
                    "update wallets set contacts_used_this_period = "
                    "contacts_used_this_period + 1, updated_at = %s where id = %s",
                    [now, wallet["id"]],
                )

            spent = 0
        else:
            if not _spend_credit(wallet["id"], ctx.user["id"], target):
                return None

            spent = 1

        now = _stamp(eloquent.now())

        with allowed_writes("contact_unlocks"), connection.cursor() as cursor:
            cursor.execute(
                "insert into contact_unlocks (company_id, target_company_id, user_id, "
                "listing_id, credits_spent, status, updated_at, created_at) "
                "values (%s, %s, %s, %s, %s, 'new', %s, %s)",
                [
                    company["id"],
                    target["id"],
                    ctx.user["id"],
                    None if listing is None else listing["id"],
                    spent,
                    now,
                    now,
                ],
            )

    return ctx.t("messages.unlock.opened"), "success"


def _stats(ctx: Context, listing: dict[str, Any]) -> None:
    """StatsRecorder::unlock: $listing->increment('unlocks_count') и строка дня."""
    now = _stamp(eloquent.now())

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute(
            "update listings set unlocks_count = unlocks_count + 1, updated_at = %s where id = %s",
            [now, listing["id"]],
        )

    admin = _admin(ctx)

    if admin is not None:
        before = listing["unlocks_count"]
        audit.record(
            connection,
            action="updated",
            section="listings",
            actor=admin,
            subject_type="App\\Models\\Listing",
            subject_id=listing["id"],
            subject_label=audit.label(listing, "Listing", listing["id"]),
            changes={
                "before": {"unlocks_count": before},
                "after": {"unlocks_count": before + 1},
            },
            ip=audit.client_ip(ctx.request),
        )

    bump_daily([listing["id"]], "unlocks")


def _after(
    ctx: Context, company: dict[str, Any], target: dict[str, Any], listing: dict[str, Any] | None
) -> None:
    """ContactUnlockService::afterUnlock: вне денежной транзакции."""
    if listing is not None:
        _stats(ctx, listing)

    _notify_company(
        ctx,
        target,
        "contact_unlocked",
        f"Компания «{company['name']}» открыла ваши контакты",
        "success",
        "/cabinet/incoming",
        f"По объявлению «{listing['title']}». Это тёплый лид: за контакт заплатили."
        if listing is not None
        else "Это тёплый лид: за контакт заплатили.",
    )


def _unlock(
    ctx: Context, target: dict[str, Any], listing: dict[str, Any] | None
) -> tuple[bool, str]:
    """ContactUnlockService::unlock: (удалось ли, сообщение)."""
    assert ctx.user is not None
    user = _rows("select * from users where id = %s", [ctx.user["id"]])[0]
    company = company_of(ctx)

    if company is None:
        return False, ctx.t("messages.unlock.no_company")

    if company["id"] == target["id"]:
        return False, ctx.t("messages.unlock.own_company")

    # Причина отказа называется точно
    if user.get("email_verified_at") is None:
        return False, ctx.t("messages.unlock.verify_email")

    if user.get("must_change_password"):
        return False, ctx.t("messages.unlock.change_password")

    if user.get("status") != "active":
        return False, ctx.t("messages.unlock.blocked")

    if company["status"] == BLOCKED:
        return False, ctx.t("messages.unlock.company_blocked")

    if target["status"] == BLOCKED:
        return False, ctx.t("messages.unlock.target_blocked")

    # Уже открыт — повторно не списываем
    if _existing(company["id"], target["id"]) is not None:
        return True, ctx.t("messages.unlock.already_open")

    wallets = _rows(
        "select * from wallets where company_id = %s order by id limit 1", [company["id"]]
    )

    if not wallets:
        return False, ctx.t("messages.promo.no_wallet")

    wallet = wallets[0]

    try:
        charged = _charge(ctx, {**company, "wallet_id": wallet["id"]}, target, listing)
    except IntegrityError:
        # Гонка: второе раскрытие той же компании упёрлось в unique —
        # транзакция откатилась целиком, отдаём уже открытый контакт
        if _existing(company["id"], target["id"]) is not None:
            return True, ctx.t("messages.unlock.already_open")

        raise

    if charged is None:
        resets = wallet["period_resets_at"]
        message = ctx.t("messages.unlock.no_credits")

        if resets is not None:
            message += " " + ctx.t("messages.unlock.resets", date=resets.strftime("%d.%m.%Y"))

        return False, message + " " + ctx.t("messages.unlock.buy_pack")

    _after(ctx, company, target, listing)

    return True, charged[0]


@form()
def unlock(request: HttpRequest, slug: str) -> HttpResponse:
    """ContactUnlockController::store (verified, throttle:30,60)."""
    ctx = action(request, throttle=30, throttle_minutes=60)

    if (refused := _unverified(ctx)) is not None:
        return refused

    targets = _rows(
        "select * from companies where slug = %s and deleted_at is null limit 1", [slug]
    )

    if not targets:
        return not_found(ctx)

    target = targets[0]
    listing = None
    value = input_of(request).get("listing_id")

    # Объявление — только для отчётности: чужое или несуществующее не мешает
    if _filled(value):
        found = _rows(
            "select * from listings where company_id = %s and id = %s and deleted_at is null "
            "limit 1",
            [target["id"], _integer(value)],
        )
        listing = found[0] if found else None

    ok, message = _unlock(ctx, target, listing)
    flash(ctx, "success" if ok else "error", message)

    return back(ctx)
