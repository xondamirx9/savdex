"""
Чат между компаниями — формы на Django (этап 5, шаг 26): сообщение в
разговор, отклик на объявление и на IT-задачу. Копия
App\\Http\\Controllers\\Cabinet\\ChatController и App\\Services\\ChatService.

Отклик тратит квоту тарифа (responses_limit) только на НОВЫЙ разговор:
условный update кошелька, как ChatService::spendResponse. Всё внутри
одной транзакции — отказ после списания (пустой после маскировки
текст) откатывает и списание, и разговор. Контакты в тексте
маскируются (ChatService::maskContacts), собеседник получает
уведомление только о первом непрочитанном сообщении.

Посредники: CSRF → auth → throttle → SetLocale → RequirePasswordChange
→ verified (EnsureEmailIsVerified не в списке приоритетов и остаётся
после посредников группы).

Сверка с настоящим Laravel — tests/test_web_chat_actions.py.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse

from savdex import audit
from savdex.guards import allowed_writes
from savdex.web import analytics, platform, ui
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of, company_plan
from savdex.web.forms import action, back, flash, input_of, invalid, previous, redirect
from savdex.web.listing_actions import _notify_company, _now, _stamp
from savdex.web.request import _expects_json
from savdex.web.shared import Context
from savdex.web.tenders import _admin
from savdex.web.validation import validate
from savdex.web.views import not_found

#: ChatService::MAX_LENGTH
MAX_LENGTH = 2000

#: ChatService::MASK
MASK = "[•••]"


class ChatRejectedError(Exception):
    """App\\Exceptions\\ChatRejected: причина отказа видна человеку."""


# ── Текст ────────────────────────────────────────────────────────────


def mask_contacts(text: str) -> str:
    """ChatService::maskContacts: почта, ссылки, ники, телефоны от девяти цифр."""
    masked = re.sub(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", MASK, text, flags=re.I)
    masked = re.sub(r"(?:https?://|www\.|t\.me/)\S+", MASK, masked, flags=re.I)
    masked = re.sub(r"(?<![\w.])@[a-z0-9_]{4,}", MASK, masked, flags=re.I)

    return re.sub(
        r"\+?[\d(][\d\s()-]{6,}\d",
        lambda m: MASK if len(re.findall(r"\d", m.group(0))) >= 9 else m.group(0),
        masked,
    )


def _width(ch: str) -> int:
    """mb_strwidth одного знака: широкие (W, F) — 2."""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def str_limit(value: str, limit: int, end: str = "...") -> str:
    """Str::limit: по ширине (mb_strwidth), обрезка mb_strimwidth и rtrim."""
    if sum(_width(ch) for ch in value) <= limit:
        return value

    width = 0
    cut = []

    for ch in value:
        width += _width(ch)

        if width > limit:
            break

        cut.append(ch)

    return "".join(cut).rstrip(" \t\n\r\0\x0b") + end


def _php_trim(value: str) -> str:
    return value.strip(" \t\n\r\0\x0b")


# ── Разговор ─────────────────────────────────────────────────────────


def _company(company_id: int | None) -> dict[str, Any] | None:
    if company_id is None:
        return None

    rows = _rows("select * from companies where id = %s and deleted_at is null", [company_id])

    return rows[0] if rows else None


def _read_column(thread: dict[str, Any], company_id: int) -> str:
    return "buyer_read_at" if thread["buyer_company_id"] == company_id else "seller_read_at"


def _unread_count(thread: dict[str, Any], company_id: int) -> int:
    """MessageThread::unreadCountFor."""
    read_at = thread.get(_read_column(thread, company_id))
    sql = "select count(*) as n from messages where thread_id = %s and company_id != %s"
    params: list[Any] = [thread["id"], company_id]

    if read_at is not None:
        sql += " and created_at > %s"
        params.append(read_at)

    return int(_rows(sql, params)[0]["n"])


def send_message(ctx: Context, thread: dict[str, Any], company: dict[str, Any], text: str) -> None:
    """ChatService::send."""
    cid = company["id"]

    if cid not in (thread["buyer_company_id"], thread["seller_company_id"]):
        raise ChatRejectedError(ctx.t("messages.chat.not_yours"))

    # Заблокированная компания не пишет никому — ни в старых разговорах,
    # ни новыми откликами (в транзакции: открытый разговор откатится)
    if company.get("status") == "blocked":
        raise ChatRejectedError(ctx.t("messages.chat.company_blocked"))

    body = mask_contacts(_php_trim(text))

    if body == "":
        raise ChatRejectedError(ctx.t("messages.chat.body_required"))

    recipient = _company(
        thread["seller_company_id"]
        if thread["buyer_company_id"] == cid
        else thread["buyer_company_id"]
    )
    had_unread = recipient is not None and _unread_count(thread, recipient["id"]) > 0
    now = _stamp(_now())
    assert ctx.user is not None

    with allowed_writes("messages", "message_threads"), connection.cursor() as cursor:
        cursor.execute(
            "insert into messages (thread_id, company_id, user_id, body, created_at, "
            "updated_at) values (%s, %s, %s, %s, %s, %s)",
            [thread["id"], cid, ctx.user["id"], str_limit(body, MAX_LENGTH, ""), now, now],
        )
        # last_message_at и markReadFor — обе записи ставят одно и то же время
        cursor.execute(
            f"update message_threads set last_message_at = %s, {_read_column(thread, cid)} = %s, "
            "updated_at = %s where id = %s",
            [now, now, now, thread["id"]],
        )

    if recipient is not None and not had_unread:
        _notify_company(
            ctx,
            recipient,
            "chat",
            lambda locale: ui.t("messages.chat.notify_title", locale, company=company["name"]),
            "info",
            f"/cabinet/chats/{thread['id']}",
            body=str_limit(body, 120),
        )


def _spend_response(ctx: Context, company: dict[str, Any]) -> None:
    """ChatService::spendResponse: условный update, а не проверка с записью."""
    plan = company_plan(company["id"])
    limit = plan.get("responses_limit")

    if limit is None:
        return

    if limit < 1:
        raise ChatRejectedError(ctx.t("messages.chat.plan_no_replies"))

    now = _stamp(_now())

    with allowed_writes("wallets"), connection.cursor() as cursor:
        # Wallet::firstOrCreate
        wallets = _rows("select id from wallets where company_id = %s limit 1", [company["id"]])

        if wallets:
            wallet_id = wallets[0]["id"]
        else:
            cursor.execute(
                "insert into wallets (company_id, created_at, updated_at) values (%s, %s, %s) "
                "returning id",
                [company["id"], now, now],
            )
            wallet_id = cursor.fetchone()[0]

        cursor.execute(
            "update wallets set responses_used_this_period = responses_used_this_period + 1, "
            "updated_at = %s where id = %s and responses_used_this_period < %s",
            [now, wallet_id, limit],
        )
        spent = cursor.rowcount

    if spent != 1:
        analytics.limit_reached(ctx, "replies", plan.get("code"))

        raise ChatRejectedError(ctx.t("messages.chat.replies_used_up", limit=limit))


def _open_thread(
    ctx: Context,
    company: dict[str, Any],
    other_id: int,
    column: str,
    subject_id: int,
    on_new: Any = None,  # noqa: ANN401
) -> dict[str, Any]:
    """Разговор покупателя по объявлению или задаче; новый — со списанием отклика."""
    found = _rows(
        f"select * from message_threads where {column} = %s and buyer_company_id = %s limit 1",
        [subject_id, company["id"]],
    )

    if found:
        return found[0]

    _spend_response(ctx, company)
    now = _stamp(_now())

    with allowed_writes("message_threads"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into message_threads ({column}, buyer_company_id, seller_company_id, "
            "updated_at, created_at) values (%s, %s, %s, %s, %s) returning id",
            [subject_id, company["id"], other_id, now, now],
        )
        thread_id = cursor.fetchone()[0]

    if on_new is not None:
        on_new()

    # Как у свежего MessageThread::create: отметок прочтения ещё нет
    return {
        "id": thread_id,
        column: subject_id,
        "buyer_company_id": company["id"],
        "seller_company_id": other_id,
        "buyer_read_at": None,
        "seller_read_at": None,
    }


# ── Посредник verified ───────────────────────────────────────────────


def _unverified(ctx: Context, strict: bool = False) -> HttpResponse | None:
    """
    EnsureEmailIsVerified: ждущему JSON — 403 (страница ошибки: JSON
    Laravel отдаёт только для api/*), иначе Redirect::guest на
    подтверждение почты. Пропустившего код при регистрации пускает
    (email_ok); strict — только подтвердившего почту (отзывы).
    """
    from savdex.web.forms import _store
    from savdex.web.shared import email_ok
    from savdex.web.views import error

    if ctx.user is None or ctx.user["email_verified_at"] is not None:
        return None

    if not strict and email_ok(ctx.user):
        return None

    if _expects_json(ctx.request):
        return error(ctx, 403)

    # Redirector::guest: страница (GET) — её адрес, остальное — previous()
    store = _store(ctx)
    store.put("url.intended", store.full_url if ctx.request.method == "GET" else previous(ctx))

    return redirect(ctx, ctx.url("/verify-email"))


def _body_errors(ctx: Context, data: dict[str, Any], required: str) -> dict[str, list[str]]:
    return validate(
        data,
        {"body": ["required", "string", f"max:{MAX_LENGTH}"]},
        ctx.locale,
        {
            "body.required": ctx.t(required),
            "body.max": ctx.t("messages.chat.body_max"),
        },
    )


def _rejected(ctx: Context, message: str) -> HttpResponse:
    """back()->withErrors(['body' => …]): ошибка без старого ввода."""
    from savdex.web.forms import _store

    _store(ctx).flash(
        "errors", {"default": {"format": ":message", "messages": {"body": [message]}}}
    )

    return back(ctx)


# ── Действия ─────────────────────────────────────────────────────────


def thread(request: HttpRequest, thread_id: str) -> HttpResponse:
    """/cabinet/chats/<id>: GET — разговор (cabinet.chat), POST — сообщение."""
    from savdex.web.cabinet import chat

    if request.method == "POST":
        return send(request, thread_id)

    return chat(request, thread_id)


@form()
def send(request: HttpRequest, thread_id: str) -> HttpResponse:
    """ChatController::send (verified, throttle:60,1)."""
    ctx = action(request, throttle=60, throttle_prefix="chat")

    if (refused := _unverified(ctx)) is not None:
        return refused

    company = company_of(ctx)

    if company is None:
        return not_found(ctx)

    found = _rows("select * from message_threads where id = %s", [int(thread_id)])

    if not found or company["id"] not in (
        found[0]["buyer_company_id"],
        found[0]["seller_company_id"],
    ):
        return not_found(ctx)

    data = input_of(request)
    errors = _body_errors(ctx, data, "messages.chat.body_required")

    if errors:
        return invalid(ctx, errors)

    thread = found[0]
    # Первый ответ продавца на отклик — до вставки, иначе он уже «не первый»
    first_reply = company["id"] == thread["seller_company_id"] and not _rows(
        "select 1 from messages where thread_id = %s and company_id = %s limit 1",
        [thread["id"], company["id"]],
    )

    try:
        with transaction.atomic():
            send_message(ctx, thread, company, data["body"])
    except ChatRejectedError as e:
        return _rejected(ctx, str(e))

    if first_reply:
        from savdex import product_events

        # created_at и _now() — UTC без пояса, как пишет площадка
        started = thread.get("created_at")
        product_events.record(
            "response_replied",
            company_id=company["id"],
            user_id=ctx.user["id"] if ctx.user else None,
            plan=product_events.plan_code(company["id"]),
            locale=ctx.locale,
            props={
                "thread_id": thread["id"],
                "listing_id": thread.get("listing_id"),
                "hours_to_reply": round((_now() - started).total_seconds() / 3600, 1)
                if isinstance(started, datetime)
                else None,
            },
        )

    return back(ctx)


@form()
def respond(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ChatController::respond (verified, throttle:60,60): отклик с карточки объявления."""
    ctx = action(request, throttle=60, throttle_minutes=60, throttle_prefix="listing-respond")

    if (refused := _unverified(ctx)) is not None:
        return refused

    company = company_of(ctx)

    if company is None:
        return _rejected(ctx, ctx.t("messages.chat.no_company"))

    listings = _rows(
        "select * from listings where id = %s and deleted_at is null", [int(listing_id)]
    )

    if not listings:
        return not_found(ctx)

    listing = listings[0]
    data = input_of(request)
    errors = _body_errors(ctx, data, "messages.chat.body_interest")

    if errors:
        return invalid(ctx, errors)

    try:
        seller = _company(listing["company_id"])

        # Заблокированная компания для откликов — как пропавшая
        if seller is None or seller["status"] != "active":
            raise ChatRejectedError(ctx.t("messages.chat.listing_gone"))

        if seller["id"] == company["id"]:
            raise ChatRejectedError(ctx.t("messages.chat.own_listing"))

        if listing["status"] != "active":
            raise ChatRejectedError(ctx.t("messages.chat.listing_off"))

        with transaction.atomic():
            thread = _open_thread(ctx, company, seller["id"], "listing_id", listing["id"])
            send_message(ctx, thread, company, data["body"])
    except ChatRejectedError as e:
        return _rejected(ctx, str(e))

    analytics.queue(
        ctx,
        "response_sent",
        {
            "listing_id": listing["id"],
            "is_platform_listing": platform.owns(listing, platform.service_company_id()),
        },
    )
    flash(ctx, "success", ctx.t("messages.chat.reply_sent"))

    return redirect(ctx, ctx.url(f"/cabinet/chats/{thread['id']}"))


@form()
def respond_task(request: HttpRequest, task_id: str) -> HttpResponse:
    """ChatController::respondTask (verified, throttle:60,60): отклик IT-исполнителя."""
    ctx = action(request, throttle=60, throttle_minutes=60, throttle_prefix="task-respond")

    if (refused := _unverified(ctx)) is not None:
        return refused

    company = company_of(ctx)

    if company is None:
        return _rejected(ctx, ctx.t("messages.chat.no_company"))

    tasks = _rows("select * from it_tasks where id = %s", [int(task_id)])

    if not tasks:
        return not_found(ctx)

    task = tasks[0]
    data = input_of(request)
    errors = _body_errors(ctx, data, "messages.chat.body_help")

    if errors:
        return invalid(ctx, errors)

    def count_response() -> None:
        """$task->increment('responses_count'): updated_at и журнал администратора."""
        with allowed_writes("it_tasks"), connection.cursor() as cursor:
            cursor.execute(
                "update it_tasks set responses_count = responses_count + 1, updated_at = %s "
                "where id = %s",
                [_stamp(_now()), task["id"]],
            )

        admin = _admin(ctx)

        if admin is not None:
            before = int(task["responses_count"] or 0)
            audit.record(
                connection,
                action="updated",
                section="ittasks",
                actor=admin,
                subject_type="App\\Models\\ItTask",
                subject_id=task["id"],
                subject_label=audit.label(task, "ItTask", task["id"]),
                changes={
                    "before": {"responses_count": before},
                    "after": {"responses_count": before + 1},
                },
                ip=audit.client_ip(ctx.request),
            )

    try:
        customer = _company(task["company_id"])

        if customer is None or customer["status"] != "active":
            raise ChatRejectedError(ctx.t("messages.chat.task_gone"))

        if customer["id"] == company["id"]:
            raise ChatRejectedError(ctx.t("messages.chat.own_task"))

        if task["status"] != "active":
            raise ChatRejectedError(ctx.t("messages.chat.task_closed"))

        if not company["is_it_provider"]:
            raise ChatRejectedError(ctx.t("messages.chat.it_role_needed"))

        with transaction.atomic():
            thread = _open_thread(
                ctx, company, customer["id"], "it_task_id", task["id"], count_response
            )
            send_message(ctx, thread, company, data["body"])
    except ChatRejectedError as e:
        return _rejected(ctx, str(e))

    flash(ctx, "success", ctx.t("messages.chat.reply_sent"))

    return redirect(ctx, ctx.url(f"/cabinet/chats/{thread['id']}"))
