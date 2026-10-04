"""
Продвижение объявления за единицы — форма на Django (этап 5, шаг 44).
Копия App\\Http\\Controllers\\Cabinet\\PromotionController::store.

Только активное своё объявление; одно и то же продвижение дважды на
одном объявлении не продаётся (проверка и уникальный active_key); у типа
с ограничением мест — свободное место в категории. Списание единиц
(Wallet::spend) и запуск — одной транзакцией; затем уведомление компании.

Сверка с настоящим Laravel — tests/test_web_promo_actions.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web import eloquent, ui
from savdex.web import wallet as wallet_store
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _as_id, _notify_company, _stamp, refuse_blocked
from savdex.web.resume_actions import _exists
from savdex.web.validation import validate, validated
from savdex.web.views import not_found


class _InsufficientUnitsError(Exception):
    """Единиц на счёте меньше цены продвижения."""


def _free_slot(kind: dict[str, Any], category_id: int | None) -> bool:
    """PromotionType::hasFreeSlot: мест не ограничено или занято меньше."""
    if kind["slots"] is None:
        return True

    query = (
        "select count(*) as n from promotions where promotion_type_id = %s and status = 'active'"
    )
    params: list[Any] = [kind["id"]]

    if category_id is not None:
        query += " and category_id = %s"
        params.append(category_id)

    return int(_rows(query, params)[0]["n"]) < int(kind["slots"])


@form()
def store(request: HttpRequest) -> HttpResponse:
    """PromotionController::store (throttle:30,60)."""
    ctx = action(request, throttle=30, throttle_minutes=60, throttle_prefix="promo")
    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    if (refused := refuse_blocked(ctx, company["id"])) is not None:
        return refused

    data = input_of(request)
    rules: dict[str, list[Any]] = {
        "listing_id": ["required", "integer"],
        # Выключенный вид продвижения не купить и по прямому запросу
        "promotion_type_id": ["required", _exists("promotion_types", "is_active")],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {"listing_id.required": ctx.t("messages.promo.listing_required")},
    )

    if errors:
        return invalid(ctx, errors)

    valid = validated(data, rules)
    found = _rows(
        "select * from listings where company_id = %s and status = 'active' and id = %s "
        "and deleted_at is null limit 1",
        [company["id"], _as_id(valid["listing_id"])],
    )

    if not found:
        flash(ctx, "error", ctx.t("messages.promo.active_only"))

        return back(ctx)

    listing = found[0]
    kind = _rows(
        "select * from promotion_types where id = %s",
        [_as_id(valid["promotion_type_id"])],
    )[0]

    # Одно и то же продвижение дважды — деньги на ветер
    if _rows(
        "select 1 from promotions where company_id = %s and listing_id = %s "
        "and promotion_type_id = %s and status = 'active' limit 1",
        [company["id"], listing["id"], kind["id"]],
    ):
        flash(ctx, "error", ctx.t("messages.promo.already_running", name=kind["name"]))

        return back(ctx)

    if not _free_slot(kind, listing["category_id"]):
        flash(ctx, "error", ctx.t("messages.promo.slots_taken", name=kind["name"]))

        return back(ctx)

    wallets = _rows(
        "select * from wallets where company_id = %s order by id limit 1", [company["id"]]
    )

    if not wallets:
        flash(ctx, "error", ctx.t("messages.promo.no_wallet"))

        return back(ctx)

    wallet = wallets[0]

    try:
        with transaction.atomic():
            if not wallet_store.spend(
                wallet["id"],
                "promo_units",
                kind["cost_units"],
                "promotion",
                ("Listing", listing["id"]),
                ctx.user["id"],
            ):
                raise _InsufficientUnitsError

            moment = eloquent.now()
            now = _stamp(moment)
            ends = (
                _stamp(moment + timedelta(days=kind["duration_days"]))
                if kind["duration_days"] > 0
                else None
            )

            with allowed_writes("promotions"), connection.cursor() as cursor:
                cursor.execute(
                    "insert into promotions (listing_id, company_id, promotion_type_id, "
                    "category_id, units_spent, status, starts_at, ends_at, impressions_before, "
                    "active_key, updated_at, created_at) "
                    "values (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, %s)",
                    [
                        listing["id"],
                        company["id"],
                        kind["id"],
                        listing["category_id"],
                        kind["cost_units"],
                        now,
                        ends,
                        listing["impressions_count"],
                        f"{listing['id']}:{kind['id']}",
                        now,
                        now,
                    ],
                )
    except _InsufficientUnitsError:
        flash(
            ctx,
            "error",
            ctx.t("messages.promo.not_enough", need=kind["cost_units"], have=wallet["promo_units"]),
        )

        return back(ctx)
    except IntegrityError:
        flash(ctx, "error", ctx.t("messages.promo.already_running", name=kind["name"]))

        return back(ctx)

    _notify_company(
        ctx,
        company,
        "promotion",
        lambda locale: ui.t(
            "messages.promo.started_notice", locale, name=kind["name"], title=listing["title"]
        ),
        "success",
        "/cabinet/promo",
    )
    flash(
        ctx,
        "success",
        ctx.t("messages.promo.started", name=kind["name"], units=kind["cost_units"]),
    )

    return back(ctx)


def page(request: HttpRequest) -> HttpResponse:
    """/cabinet/promo: GET — страница, POST — запуск продвижения."""
    from savdex.web.cabinet import promo

    if request.method == "POST":
        return store(request)

    return promo(request)
