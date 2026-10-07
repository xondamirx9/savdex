"""
Свои тендеры в кабинете: список «Мои тендеры», форма «Создать тендер»,
правка, продлить, завершить, открыть снова и удалить.

Тендер, заведённый в кабинете (source = cabinet), живёт LIFETIME дней:
срок — «Приём заявок до», по умолчанию и не дальше чем через 30 дней.
«Продлить» — на 7, 14 или 30 дней, в любой момент, в том числе после
«Истёк». «Завершить» — в архив с итогом: договор заключён (с кем и на
какую сумму — по желанию), не договорились или закупку отменили. За три
дня до срока — предупреждение, по сроку — «Истёк» (savdex/tender_expiry.py).
Тендеры администратора (source = admin: админка и загрузка из Excel)
живут по своему сроку из источника.

Тендер заводит компания: заказчик по умолчанию — её название, автор —
вошедший (author_id). Как и IT-задача, новый тендер сразу на витрине
(status = published) — у заблокированной компании отказ, без
подтверждённой почты — сначала подтвердить. Перевод на другие языки
добирает фоновый обработчик (manage.py translate): при смене заголовка
или описания старые переводы сбрасываются.

«Мои» — тендеры, где author_id — вошедший: так в список попадают и
закупки, которые администратор завёл со своей учётки.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.tenders.slug import make_slug
from savdex.web import eloquent, inertia
from savdex.web.actions import form
from savdex.web.cabinet import _redirect, _rows, _seo, _store, company_of, page
from savdex.web.chat_actions import _unverified
from savdex.web.forms import action, back, flash, input_of, invalid, redirect
from savdex.web.it_task_actions import _spoofed
from savdex.web.it_tasks import _date, number_format
from savdex.web.listing_actions import _stamp, refuse_blocked
from savdex.web.search_text import index
from savdex.web.shared import Context
from savdex.web.validation import Check, _strtotime, validate, validated
from savdex.web.views import not_found

PUBLISHED, ARCHIVED, DRAFT, EXPIRED = "published", "archived", "draft", "expired"

#: Tender::STATUSES — подписи в кабинете: cabinet.tenders.statuses
STATUSES = (DRAFT, PUBLISHED, ARCHIVED, EXPIRED)

#: Сколько дней живёт тендер из кабинета — и самый дальний срок при создании
LIFETIME = 30

#: На сколько дней можно продлить
EXTEND_DAYS = (7, 14, 30)

#: Чем закончился тендер: подписи — cabinet.tenders.outcomes
OUTCOMES = ("contract", "no_deal", "cancelled")

CABINET = "cabinet"

#: Tender::CURRENCIES
CURRENCIES = ["UZS", "USD", "EUR", "RUB", "CNY", "KZT"]

#: Поля формы — столбцы tenders
FIELDS = (
    "title", "description", "customer", "category_id", "location", "budget", "currency",
    "deadline_at", "contact_name", "contact_phone", "contact_email",
)  # fmt: skip

CASTS = {"budget": "decimal:2", "deadline_at": "date", "category_id": "int"}

#: Столбцы перевода: при смене исходного текста — заново
_TRANSLATED = {"title": "title_i18n", "description": "description_i18n"}


def _search_text(row: dict[str, Any]) -> dict[str, Any]:
    """Tender::reindex: заголовок, описание, заказчик и переводы заголовка."""
    titles = row.get("title_i18n")
    parts = [
        row["title"],
        row.get("description") or "",
        row.get("customer") or "",
        *(titles.values() if isinstance(titles, dict) else []),
    ]

    return {"search_text": index(" ".join(str(p) for p in parts if p not in (None, "", "0")))}


def _owned(ctx: Context, tender_id: int) -> dict[str, Any] | None:
    """Свой тендер — иначе None (404: чужой не подтверждает, что существует)."""
    if ctx.user is None:
        return None

    rows = _rows(
        "select * from tenders where id = %s and author_id = %s", [tender_id, ctx.user["id"]]
    )

    return rows[0] if rows else None


def _category() -> Check:
    """Категория из справочника: раздел или подкатегория."""

    def passes(value: Any) -> bool:  # noqa: ANN401
        try:
            key = int(str(value).strip())
        except ValueError:
            return False

        return bool(_rows("select 1 from categories where id = %s limit 1", [key]))

    return Check("exists", passes)


def _end_of_day(moment: datetime) -> datetime:
    return moment.replace(hour=23, minute=59, second=59, microsecond=0)


def _default_deadline() -> datetime:
    """Срок нового тендера: конец дня через LIFETIME дней."""
    return _end_of_day(eloquent.now() + timedelta(days=LIFETIME))


def _validated(
    ctx: Context,
    request: HttpRequest,
    latest: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """
    Поля формы. latest — самый дальний срок «Приём заявок до» у тендера
    из кабинета: дальше — только через «Продлить».
    """
    data: dict[str, Any] = {**input_of(request)}
    rules: dict[str, list[str | Any]] = {
        "title": ["required", "string", "min:10", "max:190"],
        "description": ["required", "string", "min:30", "max:8000"],
        "customer": ["required", "string", "max:190"],
        "category_id": ["nullable", "integer", _category()],
        "location": ["nullable", "string", "max:190"],
        "budget": ["nullable", "numeric", "min:0", "max:99999999999999"],
        "currency": ["required", "in:" + ",".join(CURRENCIES)],
        "deadline_at": ["nullable", "date", "after:today"],
        "contact_name": ["nullable", "string", "max:190"],
        "contact_phone": ["nullable", "string", "max:40"],
        "contact_email": ["nullable", "email", "max:190"],
    }
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "title.required": ctx.t("messages.tender.title_required"),
            "title.min": ctx.t("messages.tender.title_min"),
            "description.required": ctx.t("messages.tender.description_required"),
            "description.min": ctx.t("messages.tender.description_min"),
            "customer.required": ctx.t("messages.tender.customer_required"),
            "deadline_at.after": ctx.t("messages.tender.deadline_future"),
        },
    )

    if errors:
        return {}, errors

    valid = validated(data, rules)
    row = {field: valid.get(field) for field in FIELDS}

    for field in ("location", "contact_name", "contact_phone", "contact_email"):
        text = str(row[field] or "").strip()
        row[field] = text or None

    row["title"] = str(row["title"]).strip()
    row["customer"] = str(row["customer"]).strip()
    row["category_id"] = int(row["category_id"]) if row["category_id"] is not None else None

    if row["deadline_at"] is not None:
        parsed = _strtotime(row["deadline_at"])
        assert parsed is not None
        # Приём заявок — до конца выбранного дня
        row["deadline_at"] = parsed[0].strftime("%Y-%m-%d 23:59:59")

        if latest is not None and row["deadline_at"] > latest.strftime("%Y-%m-%d %H:%M:%S"):
            limit = _date(latest, ctx.locale)
            message = ctx.t("messages.tender.deadline_max", days=LIFETIME, date=limit)

            return {}, {"deadline_at": [message]}

    return row, {}


def _contacts(ctx: Context, company: dict[str, Any]) -> dict[str, Any]:
    """Подстановка в новую форму: заказчик — компания, контакт — вошедший."""
    assert ctx.user is not None
    user = _rows("select name, email, phone from users where id = %s", [ctx.user["id"]])[0]

    return {
        "customer": company["name"],
        "contact_name": user["name"],
        "contact_phone": user["phone"] or "",
        "contact_email": user["email"],
    }


def _categories(ctx: Context) -> list[dict[str, Any]]:
    """Список для выбора: раздел, под ним его подкатегории."""
    from savdex.web.tenders import categories

    options: list[dict[str, Any]] = []

    for root in categories(ctx.locale):
        options.append({"value": str(root["id"]), "label": root["name"]})
        options += [{"value": str(c["id"]), "label": f"— {c['name']}"} for c in root["children"]]

    return options


def _budget(ctx: Context, row: dict[str, Any]) -> str | None:
    return _money(ctx, row["budget"], row["currency"])


def _money(ctx: Context, amount: Any, currency: Any) -> str | None:  # noqa: ANN401
    if amount is None:
        return None

    label = ctx.t("catalog.currency_uzs") if (currency or "UZS").strip() == "UZS" else currency

    return f"{number_format(float(amount), 0)} {label}"


def _days_left(row: dict[str, Any]) -> int | None:
    """Сколько дней до срока у тендера на витрине; иначе None."""
    if row["status"] != PUBLISHED or row["deadline_at"] is None:
        return None

    left: int = (row["deadline_at"].date() - eloquent.now().date()).days

    return max(0, left)


def _no_company(ctx: Context) -> HttpResponse:
    store = _store(ctx)

    if store is not None:
        store.flash("warning", ctx.t("messages.tender.no_company"))

    return _redirect(ctx, "/cabinet/company")


# ── Страницы ────────────────────────────────────────────────────────


def index_page(ctx: Context) -> HttpResponse:
    assert ctx.user is not None
    rows = _rows(
        "select * from tenders where author_id = %s order by created_at desc, id desc",
        [ctx.user["id"]],
    )

    return inertia.render(
        ctx,
        "cabinet/tenders/Index",
        {
            "hasCompany": company_of(ctx) is not None,
            "extendDays": list(EXTEND_DAYS),
            "tenders": [
                {
                    "id": r["id"],
                    "slug": r["slug"],
                    "title": r["title"],
                    "customer": r["customer"],
                    "budget": _budget(ctx, r),
                    "deadline": _date(r["deadline_at"], ctx.locale),
                    "days_left": _days_left(r),
                    "status": r["status"],
                    "outcome": r["outcome"],
                    "outcome_label": (
                        ctx.t(f"cabinet.tenders.outcomes.{r['outcome']}") if r["outcome"] else None
                    ),
                    "outcome_party": r["outcome_party"],
                    "outcome_amount": _money(ctx, r["outcome_amount"], r["currency"]),
                    "status_label": (
                        ctx.t(f"cabinet.tenders.statuses.{r['status']}")
                        if r["status"] in STATUSES
                        else r["status"]
                    ),
                    "views": r["views_count"],
                    "published": _date(r["published_at"], ctx.locale),
                }
                for r in rows
            ],
        },
        _seo(ctx),
    )


def create(request: HttpRequest) -> HttpResponse:
    """/cabinet/tenders/create: без компании — сначала профиль."""
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    company = company_of(ctx)

    if company is None:
        return _no_company(ctx)

    return inertia.render(
        ctx,
        "cabinet/tenders/Form",
        {
            "tender": None,
            "defaults": _contacts(ctx, company),
            "categories": _categories(ctx),
            "currencies": CURRENCIES,
        },
        _seo(ctx),
    )


def edit(request: HttpRequest, tender_id: str) -> HttpResponse:
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    found = _owned(ctx, int(tender_id))

    if found is None:
        return not_found(ctx)

    return inertia.render(
        ctx,
        "cabinet/tenders/Form",
        {
            "tender": {
                "id": found["id"],
                "title": found["title"],
                "description": found["description"] or "",
                "customer": found["customer"] or "",
                "category_id": str(found["category_id"]) if found["category_id"] else "",
                "location": found["location"] or "",
                "budget": (
                    format(found["budget"].normalize(), "f") if found["budget"] is not None else ""
                ),
                "currency": (found["currency"] or "UZS").strip(),
                "deadline_at": (
                    found["deadline_at"].strftime("%Y-%m-%d") if found["deadline_at"] else ""
                ),
                "contact_name": found["contact_name"] or "",
                "contact_phone": found["contact_phone"] or "",
                "contact_email": found["contact_email"] or "",
            },
            "defaults": None,
            "categories": _categories(ctx),
            "currencies": CURRENCIES,
        },
        _seo(ctx),
    )


# ── Формы ───────────────────────────────────────────────────────────


@form()
def store(request: HttpRequest) -> HttpResponse:
    """Новый тендер — сразу на витрине."""
    ctx = action(request, throttle=20, throttle_minutes=60, throttle_prefix="tender-create")

    if (refused := _unverified(ctx)) is not None:
        return refused

    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        return _no_company(ctx)

    if (refused := refuse_blocked(ctx, company["id"])) is not None:
        return refused

    latest = _default_deadline()
    valid, errors = _validated(ctx, request, latest)

    if errors:
        return invalid(ctx, errors)

    now = _stamp(eloquent.now())
    row: dict[str, Any] = {
        **valid,
        # Срок не выбран — 30 дней
        "deadline_at": valid["deadline_at"] or latest.strftime("%Y-%m-%d %H:%M:%S"),
        "author_id": ctx.user["id"],
        "status": PUBLISHED,
        "published_at": now,
        "source": CABINET,
    }
    row.update(_search_text(row))
    row.update(updated_at=now, created_at=now)
    columns = list(row)

    with allowed_writes("tenders"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into tenders ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [eloquent._written(CASTS.get(c), row[c]) for c in columns],
        )
        row["id"] = cursor.fetchone()[0]
        # Событие created: адрес из заголовка и номера
        row["slug"] = make_slug(str(row["title"]), row["id"])
        cursor.execute("update tenders set slug = %s where id = %s", [row["slug"], row["id"]])

    after = {c: eloquent._written(CASTS.get(c), v) for c, v in row.items()}
    eloquent.journal(ctx, "created", "tenders", "Tender", row, {"after": after})
    flash(ctx, "success", ctx.t("messages.tender.published"))

    return redirect(ctx, ctx.url("/cabinet/tenders"))


@form("PATCH")
def update(request: HttpRequest, tender_id: str) -> HttpResponse:
    ctx = action(request)
    tender = _owned(ctx, int(tender_id))

    if tender is None:
        return not_found(ctx)

    cabinet = tender["source"] == CABINET
    latest = None

    if cabinet:
        # Правкой срок не уходит дальше 30 дней от сегодня или уже продлённого
        current = tender["deadline_at"]
        latest = max(_default_deadline(), current) if current else _default_deadline()

    valid, errors = _validated(ctx, request, latest)

    if errors:
        return invalid(ctx, errors)

    # Срок стёрли — у кабинетного тендера остаётся прежний
    if cabinet and valid["deadline_at"] is None:
        valid["deadline_at"] = tender["deadline_at"] or latest

    for field, column in _TRANSLATED.items():
        if valid[field] != tender[field]:
            valid[column] = None

    eloquent.save(
        ctx,
        "tenders",
        tender,
        valid,
        section="tenders",
        model="Tender",
        saving=_search_text,
        casts={**CASTS, "title_i18n": "json", "description_i18n": "json"},
    )
    flash(ctx, "success", ctx.t("messages.tender.updated"))

    return redirect(ctx, ctx.url("/cabinet/tenders"))


@form("DELETE")
def destroy(request: HttpRequest, tender_id: str) -> HttpResponse:
    ctx = action(request)
    tender = _owned(ctx, int(tender_id))

    if tender is None:
        return not_found(ctx)

    with allowed_writes("tenders"), connection.cursor() as cursor:
        cursor.execute("delete from tenders where id = %s", [tender["id"]])

    eloquent.journal(ctx, "deleted", "tenders", "Tender", tender, None)
    flash(ctx, "success", ctx.t("messages.tender.deleted"))

    return redirect(ctx, ctx.url("/cabinet/tenders"))


@form()
def finish(request: HttpRequest, tender_id: str) -> HttpResponse:
    """
    «Завершить»: тендер в архив с итогом — договор заключён (с кем и на
    какую сумму — по желанию), не договорились или закупку отменили.
    """
    ctx = action(request)
    tender = _owned(ctx, int(tender_id))

    if tender is None:
        return not_found(ctx)

    data = input_of(request)
    errors = validate(
        data,
        {
            "outcome": ["required", "in:" + ",".join(OUTCOMES)],
            "party": ["nullable", "string", "max:190"],
            "amount": ["nullable", "numeric", "min:0", "max:99999999999999"],
        },
        ctx.locale,
        {"outcome.required": ctx.t("messages.tender.outcome_required")},
    )

    if errors:
        return invalid(ctx, errors)

    if tender["status"] in (PUBLISHED, EXPIRED):
        contract = data["outcome"] == "contract"
        party = str(data.get("party") or "").strip()
        amount = data.get("amount")
        eloquent.save(
            ctx,
            "tenders",
            tender,
            {
                "status": ARCHIVED,
                "outcome": data["outcome"],
                "outcome_party": (party or None) if contract else None,
                "outcome_amount": (
                    Decimal(str(amount)) if contract and amount not in (None, "") else None
                ),
                "finished_at": eloquent.now(),
            },
            section="tenders",
            model="Tender",
            casts={"outcome_amount": "decimal:2"},
        )

    flash(ctx, "success", ctx.t("messages.tender.finished"))

    return back(ctx)


@form()
def extend(request: HttpRequest, tender_id: str) -> HttpResponse:
    """
    «Продлить» на 7, 14 или 30 дней: от прежнего срока, а если он уже
    прошёл — от сегодня. Истёкший тендер возвращается на витрину.
    """
    ctx = action(request)
    tender = _owned(ctx, int(tender_id))

    if tender is None:
        return not_found(ctx)

    company = company_of(ctx)

    if company is not None and (refused := refuse_blocked(ctx, company["id"])) is not None:
        return refused

    data = input_of(request)
    errors = validate(
        data, {"days": ["required", "in:" + ",".join(str(d) for d in EXTEND_DAYS)]}, ctx.locale
    )

    if errors:
        return invalid(ctx, errors)

    if tender["status"] not in (PUBLISHED, EXPIRED):
        return back(ctx)

    now = eloquent.now()
    start = tender["deadline_at"] if tender["deadline_at"] and tender["deadline_at"] > now else now
    deadline = _end_of_day(start + timedelta(days=int(str(data["days"]))))
    eloquent.save(
        ctx,
        "tenders",
        tender,
        {
            "status": PUBLISHED,
            "deadline_at": deadline,
            "expiry_warned_at": None,
            "extended_at": now,
        },
        section="tenders",
        model="Tender",
    )
    flash(ctx, "success", ctx.t("messages.tender.extended", date=_date(deadline, ctx.locale)))

    return back(ctx)


@form()
def reopen(request: HttpRequest, tender_id: str) -> HttpResponse:
    """
    Снова на витрину — только закрытый автором. Черновик — это тендер,
    который сняла модерация: его автору не вернуть.
    """
    ctx = action(request)
    tender = _owned(ctx, int(tender_id))

    if tender is None:
        return not_found(ctx)

    company = company_of(ctx)

    if company is not None and (refused := refuse_blocked(ctx, company["id"])) is not None:
        return refused

    if tender["status"] == ARCHIVED:
        changes: dict[str, Any] = {
            "status": PUBLISHED,
            "published_at": eloquent.now(),
            "outcome": None,
            "outcome_party": None,
            "outcome_amount": None,
            "finished_at": None,
        }

        # Срок кабинетного тендера уже прошёл — снова 30 дней
        deadline = tender["deadline_at"]

        if tender["source"] == CABINET and (deadline is None or deadline <= eloquent.now()):
            changes.update(deadline_at=_default_deadline(), expiry_warned_at=None)

        eloquent.save(ctx, "tenders", tender, changes, section="tenders", model="Tender")

    flash(ctx, "success", ctx.t("messages.tender.reopened"))

    return back(ctx)


# ── Маршруты ────────────────────────────────────────────────────────


def tenders(request: HttpRequest) -> HttpResponse:
    """/cabinet/tenders: GET — список, POST — новый тендер."""
    if request.method == "POST":
        return store(request)

    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    return index_page(ctx)


def tender(request: HttpRequest, tender_id: str) -> HttpResponse:
    """/cabinet/tenders/<id>: PATCH и DELETE (и POST с _method)."""
    method = _spoofed(request)

    if method in ("PATCH", "DELETE"):
        request.method = method

    if request.method == "DELETE":
        return destroy(request, tender_id)

    return update(request, tender_id)
