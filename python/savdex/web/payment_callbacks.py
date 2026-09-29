"""
Колбэки платёжного шлюза на Django (этап 7, шаг 54): Merchant API
Uzum — POST /payments/uzum/callback/{check|create|confirm|reverse|status}
(UzumMerchantController) — и вебхук кассы Uzum Checkout
POST /payments/{provider}/callback (WebhookController с
UzumGateway::verifyCallback, ::parseCallback и ::callbackResponse).

Публичные: без входа и без CSRF, с ограничением частоты 120 в минуту.
Выключенный провайдер — 404, как будто маршрута нет. Merchant API
защищён Basic-авторизацией из настроек и serviceId; вебхук — белым
списком адресов и перепроверкой успеха у самого Uzum (getOrderStatus):
колбэк не подписан, и начислять по нему одному нельзя.

Доступ открывает только settlement.mark_paid — одна точка выдачи на
обе стороны. Сверка с настоящим Laravel — tests/test_web_payment_callbacks.py.
"""

from __future__ import annotations

import base64
import calendar
import hmac
import logging
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from savdex import audit
from savdex.payments import checkout as cashier
from savdex.payments.uzum import UzumConfig, UzumError, _php_int, call
from savdex.web import eloquent, locales, orders, session, settlement
from savdex.web.cabinet import _rows
from savdex.web.forms import _throttle, input_of, rate_headers
from savdex.web.request import context
from savdex.web.seo import php_json
from savdex.web.shared import Context
from savdex.web.validation import _php_string

log = logging.getLogger("savdex.payments")

#: PaymentTransaction::STATE_*
CREATED = "created"
PERFORMED = "performed"
CANCELLED = "cancelled"

#: Коды ошибок Merchant API Uzum
ERROR_AUTH = 10001
ERROR_BAD_OPERATION = 10003
ERROR_PARAMS_MISSING = 10005
ERROR_BAD_SERVICE_ID = 10006
ERROR_INVOICE_NOT_FOUND = 10007
ERROR_ALREADY_PAID = 10008
ERROR_INVOICE_CANCELLED = 10009
ERROR_TRANSACTION_EXISTS = 10010
ERROR_BAD_AMOUNT = 10011
ERROR_TRANSACTION_NOT_FOUND = 10014
ERROR_TRANSACTION_CANCELLED = 10015
ERROR_ALREADY_CONFIRMED = 10016
ERROR_CANNOT_REVERSE = 10017
ERROR_ALREADY_REVERSED = 10018

STATE_LABELS = {CREATED: "CREATED", PERFORMED: "CONFIRMED", CANCELLED: "REVERSED"}

#: UzumGateway::ORDER_COMPLETED и имена поля статуса в ответе getOrderStatus
ORDER_COMPLETED = "COMPLETED"
STATUS_KEYS = ("status", "orderStatus", "state", "paymentStatus", "operationState")


# ── Общее ───────────────────────────────────────────────────────────


def _json(data: Any, status: int = 200) -> HttpResponse:  # noqa: ANN401
    """response()->json(): json_encode без флагов."""
    return HttpResponse(php_json(data), status=status, content_type="application/json")


def _ms(moment: datetime | None) -> int | None:
    """Carbon::getTimestampMs у даты из базы (UTC, целые секунды): секунды × 1000."""
    if moment is None:
        return None

    return calendar.timegm(moment.timetuple()) * 1000


def _callback(
    view: Callable[[Context, HttpRequest], HttpResponse],
) -> Callable[..., HttpResponse]:
    """
    Маршрут вне auth и CSRF, throttle:120,1 без приставки: сессия и
    язык — как у любой страницы, счётчик — по адресу отправителя.
    """

    @csrf_exempt
    def wrapped(request: HttpRequest, **route: str) -> HttpResponse:
        if request.method != "POST":
            from django.http import HttpResponseNotAllowed

            return HttpResponseNotAllowed(["POST"])

        first = context(request, redirect=False)

        if isinstance(first, HttpResponse):
            return first

        session.start(request)
        bare = replace(first, locale=first.url_locale or locales.DEFAULT)

        if (refused := _throttle(first, bare, 120)) is not None:
            return refused

        ctx = context(request)

        if isinstance(ctx, HttpResponse):
            return ctx

        request._savdex_route = route  # type: ignore[attr-defined]

        return rate_headers(request, view(ctx, request))

    return wrapped


def _transaction(trans_id: str) -> dict[str, Any] | None:
    if trans_id == "":
        return None

    found = _rows(
        "select * from payment_transactions where provider = 'uzum' "
        "and provider_transaction_id = %s limit 1",
        [trans_id],
    )

    return found[0] if found else None


def _payment(payment_id: int | None) -> dict[str, Any] | None:
    found = _rows("select * from payments where id = %s", [payment_id])

    return found[0] if found else None


def _save_tx(ctx: Context, tx: dict[str, Any], changes: dict[str, Any]) -> None:
    """PaymentTransaction: fill->save — только изменившееся, с updated_at; без журнала."""
    eloquent.save(
        ctx,
        "payment_transactions",
        tx,
        changes,
        section=None,
        model="PaymentTransaction",
        casts={"amount_minor": "int"},
    )


def _confirm_timeout() -> int:
    raw = os.environ.get("PAYMENTS_UZUM_CONFIRM_TIMEOUT")

    return 30 if raw is None else _php_int(raw)


# ── Merchant API ────────────────────────────────────────────────────


class _Merchant:
    """UzumMerchantController: ответы в формате Merchant API."""

    def __init__(self, ctx: Context, request: HttpRequest) -> None:
        self.ctx = ctx
        self.request = request
        self.data = input_of(request)

    def input(self, key: str) -> Any:  # noqa: ANN401
        value: Any = self.data

        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return None

            value = value[part]

        return value

    def error(
        self, code: int, extra: dict[str, Any] | None = None, status: int = 400
    ) -> HttpResponse:
        return _json(
            {
                "serviceId": self.input("serviceId"),
                "timestamp": self.input("timestamp"),
                "transId": self.input("transId"),
                "status": "FAILED",
                "errorCode": code,
                **(extra or {}),
            },
            status,
        )

    def authorized(self) -> bool:
        login = os.environ.get("PAYMENTS_UZUM_CALLBACK_LOGIN") or ""
        password = os.environ.get("PAYMENTS_UZUM_CALLBACK_PASSWORD") or ""
        header = self.request.headers.get("Authorization", "")
        user, secret = "", ""

        if header[:6].lower() == "basic ":
            try:
                decoded = base64.b64decode(header[6:].strip()).decode()
            except (ValueError, UnicodeDecodeError):
                decoded = ""

            if ":" in decoded:
                user, secret = decoded.split(":", 1)

        return (
            login != ""
            and password != ""
            and hmac.compare_digest(login.encode(), user.encode())
            and hmac.compare_digest(password.encode(), secret.encode())
        )

    def invoice_data(self, payment: dict[str, Any]) -> dict[str, Any]:
        return {
            "invoice": payment["number"],
            "description": payment["description"],
            "amount": int(payment["amount"]) * 100,
        }

    def payable(self) -> tuple[dict[str, Any] | None, int]:
        field = os.environ.get("PAYMENTS_UZUM_ACCOUNT_FIELD", "invoice")
        number = _php_string(self.input(f"params.{field}") or "")

        if number == "":
            return None, ERROR_PARAMS_MISSING

        found = _rows("select * from payments where number = %s limit 1", [number])

        if not found:
            return None, ERROR_INVOICE_NOT_FOUND

        payment = found[0]

        if payment["status"] == "paid":
            return None, ERROR_ALREADY_PAID

        if payment["status"] != "pending":
            return None, ERROR_INVOICE_CANCELLED

        return payment, 0

    def check(self) -> HttpResponse:
        payment, code = self.payable()

        if payment is None:
            return self.error(code)

        return _json(
            {
                "serviceId": self.input("serviceId"),
                "timestamp": self.input("timestamp"),
                "status": "OK",
                "data": self.invoice_data(payment),
            }
        )

    def create(self) -> HttpResponse:
        trans_id = _php_string(self.input("transId") or "")
        amount = self.input("amount")

        if trans_id == "" or not _numeric(amount):
            return self.error(ERROR_PARAMS_MISSING)

        existing = _transaction(trans_id)

        if existing is not None:
            return self.error(ERROR_TRANSACTION_EXISTS, {"transTime": _ms(existing["created_at"])})

        payment, code = self.payable()

        if payment is None:
            return self.error(code)

        if _php_int(amount) != int(payment["amount"]) * 100:
            return self.error(ERROR_BAD_AMOUNT)

        now = eloquent.now()
        tx = orders._insert(
            "payment_transactions",
            {
                "payment_id": payment["id"],
                "provider": "uzum",
                "provider_transaction_id": trans_id,
                "state": CREATED,
                "amount_minor": _php_int(amount),
                "currency": "UZS",
                "payload": audit._php_json(self.data),
                "updated_at": now,
                "created_at": now,
            },
        )

        return _json(
            {
                "serviceId": self.input("serviceId"),
                "transId": trans_id,
                "status": "CREATED",
                "transTime": _ms(now.replace(microsecond=0)),
                "data": self.invoice_data(payment),
                "amount": tx["amount_minor"],
            }
        )

    def confirm(self) -> HttpResponse:
        tx = _transaction(_php_string(self.input("transId") or ""))

        if tx is None:
            return self.error(ERROR_TRANSACTION_NOT_FOUND)

        if tx["state"] == CANCELLED:
            return self.error(ERROR_TRANSACTION_CANCELLED)

        if tx["state"] == PERFORMED:
            return self.error(ERROR_ALREADY_CONFIRMED, {"confirmTime": _ms(tx["performed_at"])})

        # Просроченную — гасим: Uzum вернёт деньги покупателю
        deadline = tx["created_at"] + timedelta(minutes=_confirm_timeout())

        if deadline < datetime.now(UTC).replace(tzinfo=None):
            _save_tx(self.ctx, tx, {"state": CANCELLED, "cancelled_at": eloquent.now()})

            return self.error(ERROR_TRANSACTION_CANCELLED)

        payment = _payment(tx["payment_id"])

        # Счёт успели оплатить переводом — второй раз не начисляем
        if payment is None or payment["status"] == "paid":
            return self.error(ERROR_ALREADY_PAID)

        settlement.mark_paid(
            self.ctx, payment, {"provider": "uzum", "external_id": tx["provider_transaction_id"]}
        )
        now = eloquent.now()
        _save_tx(self.ctx, tx, {"state": PERFORMED, "performed_at": now})

        return _json(
            {
                "serviceId": self.input("serviceId"),
                "transId": tx["provider_transaction_id"],
                "status": "CONFIRMED",
                "confirmTime": _ms(now.replace(microsecond=0)),
                "data": self.invoice_data(payment),
                "amount": tx["amount_minor"],
            }
        )

    def reverse(self) -> HttpResponse:
        tx = _transaction(_php_string(self.input("transId") or ""))

        if tx is None:
            return self.error(ERROR_TRANSACTION_NOT_FOUND)

        if tx["state"] == CANCELLED:
            return self.error(ERROR_ALREADY_REVERSED, {"reverseTime": _ms(tx["cancelled_at"])})

        if tx["state"] == PERFORMED:
            return self.error(ERROR_CANNOT_REVERSE)

        now = eloquent.now()
        _save_tx(self.ctx, tx, {"state": CANCELLED, "cancelled_at": now})
        payment = _payment(tx["payment_id"])

        return _json(
            {
                "serviceId": self.input("serviceId"),
                "transId": tx["provider_transaction_id"],
                "status": "REVERSED",
                "reverseTime": _ms(now.replace(microsecond=0)),
                "data": self.invoice_data(payment) if payment is not None else [],
                "amount": tx["amount_minor"],
            }
        )

    def status(self) -> HttpResponse:
        tx = _transaction(_php_string(self.input("transId") or ""))

        if tx is None:
            return self.error(ERROR_TRANSACTION_NOT_FOUND)

        payment = _payment(tx["payment_id"])

        return _json(
            {
                "serviceId": self.input("serviceId"),
                "transId": tx["provider_transaction_id"],
                "status": STATE_LABELS.get(tx["state"], tx["state"]),
                "transTime": _ms(tx["created_at"]),
                "confirmTime": _ms(tx["performed_at"]),
                "reverseTime": _ms(tx["cancelled_at"]),
                "data": self.invoice_data(payment) if payment is not None else [],
                "amount": tx["amount_minor"],
            }
        )


def _numeric(value: Any) -> bool:  # noqa: ANN401
    """is_numeric у PHP: число или строка-число (с пробелами впереди и позади)."""
    if isinstance(value, bool):
        return False

    if isinstance(value, int | float):
        return True

    if not isinstance(value, str):
        return False

    import re

    return bool(
        re.fullmatch(r"[ \t\n\r\v\f]*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?[ \t\n\r\v\f]*", value)
    )


def _merchant(ctx: Context, request: HttpRequest) -> HttpResponse:
    """UzumMerchantController::handle."""
    from savdex.web.views import not_found

    if not cashier.env_flag("PAYMENTS_UZUM_ENABLED"):
        return not_found(ctx)

    merchant = _Merchant(ctx, request)

    if not merchant.authorized():
        return merchant.error(ERROR_AUTH, status=401)

    configured = os.environ.get("PAYMENTS_UZUM_SERVICE_ID") or ""

    if configured != "" and _php_string(merchant.input("serviceId") or "") != configured:
        return merchant.error(ERROR_BAD_SERVICE_ID)

    operation = request._savdex_route.get("operation", "")  # type: ignore[attr-defined]
    handler = {
        "check": merchant.check,
        "create": merchant.create,
        "confirm": merchant.confirm,
        "reverse": merchant.reverse,
        "status": merchant.status,
    }.get(operation)

    return handler() if handler is not None else merchant.error(ERROR_BAD_OPERATION)


merchant = _callback(_merchant)


# ── Вебхук кассы ────────────────────────────────────────────────────


def _gateway_response(accepted: bool) -> HttpResponse:
    """UzumGateway::callbackResponse: 200 — доставлено, иначе Uzum повторит."""
    return _json(
        {"status": "OK" if accepted else "FAILED", "errorCode": None if accepted else 99999},
        200 if accepted else 400,
    )


def _completed(node: dict[Any, Any]) -> bool:
    return any(_php_string(node.get(k) or "").upper() == ORDER_COMPLETED for k in STATUS_KEYS)


def order_completed(config: UzumConfig, order_id: str) -> bool:
    """UzumGateway::orderCompleted: списаны ли деньги — спрашиваем сам Uzum."""
    import httpx

    from savdex.payments.uzum import СВЯЗЬ

    if order_id == "":
        return False

    try:
        if any(getattr(config, k).strip() == "" for k in ("base_url", "terminal_id", "secret_key")):
            raise UzumError("Uzum не настроен")

        with httpx.Client(timeout=СВЯЗЬ, proxy=config.proxy or None, trust_env=False) as client:
            result = call(config, "/api/v1/payment/getOrderStatus", {"orderId": order_id}, client)
    except UzumError as error:
        log.warning(
            "payment.uzum.status_check_failed", extra={"order": order_id, "error": str(error)}
        )

        return False

    if _completed(result):
        return True

    if any(isinstance(v, dict) and _completed(v) for v in result.values()):
        return True

    log.warning("payment.uzum.status_unrecognized", extra={"order": order_id})

    return False


def _webhook(ctx: Context, request: HttpRequest) -> HttpResponse:
    """WebhookController::handle для Uzum; другой провайдер — 404."""
    from savdex.web.views import not_found

    provider = request._savdex_route.get("provider", "")  # type: ignore[attr-defined]

    if not cashier.enabled(provider):
        return not_found(ctx)

    config = UzumConfig.from_env()
    ips = [ip for ip in (os.environ.get("PAYMENTS_UZUM_CALLBACK_IPS") or "").split(",") if ip]

    if ips and audit.client_ip(request) not in ips:
        log.warning("payment.callback.bad_signature", extra={"provider": provider})

        return _gateway_response(False)

    data = input_of(request) if (request.content_type or "").endswith("json") else {}
    order_id = data.get("orderId")
    state_raw = data.get("operationState")

    if not (isinstance(order_id, str) and order_id and isinstance(state_raw, str) and state_raw):
        log.warning("payment.callback.bad_signature", extra={"provider": provider})

        return _gateway_response(False)

    state = state_raw.upper()

    if state == "SUCCESS" and not order_completed(config, order_id):
        log.error("payment.callback.gateway_error", extra={"provider": provider})

        return _gateway_response(False)

    status = "paid" if state == "SUCCESS" else "pending"
    found = _rows(
        "select * from payments where number = %s or external_id = %s limit 1",
        [order_id, order_id],
    )

    if not found:
        log.warning("payment.callback.unknown_invoice", extra={"provider": provider})

        return _gateway_response(False)

    payment = found[0]
    existing = _rows(
        "select * from payment_transactions where provider = %s "
        "and provider_transaction_id = %s limit 1",
        [provider, order_id],
    )

    if existing and existing[0]["state"] == PERFORMED:
        return _gateway_response(True)

    fields = {
        "payment_id": payment["id"],
        "amount_minor": None,
        "currency": "UZS",
        "payload": audit._php_json(data),
    }

    if status == "paid":
        settlement.mark_paid(ctx, payment, {"provider": provider, "external_id": order_id})
        fields.update(state=PERFORMED, performed_at=eloquent.now())
    else:
        fields.update(state=CREATED)

    if existing:
        _save_tx(ctx, existing[0], fields)
    else:
        now = eloquent.now()
        orders._insert(
            "payment_transactions",
            {
                "provider": provider,
                "provider_transaction_id": order_id,
                **fields,
                "updated_at": now,
                "created_at": now,
            },
        )

    return _gateway_response(True)


webhook = _callback(_webhook)
