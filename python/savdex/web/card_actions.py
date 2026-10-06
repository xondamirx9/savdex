"""
Визитки компании для QR-кода: кабинет «Визитки» и страница визитки.

Визитка — либо фото настоящей визитки (обрезается в редакторе на
стороне браузера, сюда приходит готовый снимок), либо собранная
площадкой из четырёх полей: название компании, Ф.И.О., почта, телефон.
Визиток у компании может быть несколько.

У каждой визитки свой QR: он кодирует /card/<token>. Код случайный —
визитки соседей перебором номеров не найти, а страница не попадает
в каталог и поиск (noindex). Почта и телефон на ней открыты бесплатно:
владелец сам раздаёт свой QR, как бумажную визитку.
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web import eloquent, inertia, locales
from savdex.web.actions import form
from savdex.web.cabinet import _rows, _seo, company_of, page
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.request import context
from savdex.web.resume_actions import IMAGE_MIMES
from savdex.web.resumes import count_view
from savdex.web.seo import Seo
from savdex.web.shared import Context
from savdex.web.validation import Check, _passes, validate
from savdex.web.views import not_found

#: Больше визиток компании не нужно: по одной на сотрудника с запасом
LIMIT = 20

KINDS = ("photo", "generated")

#: Телефон — тот же шаблон, что у регистрации и контактов компании
PHONE = r"/^\+?\d[\d\s\-()]{8,17}$/"

_ALPHABET = string.ascii_letters + string.digits


def _token() -> str:
    """Случайный код адреса: 16 знаков из 62 — перебором не угадать."""
    while True:
        token = "".join(secrets.choice(_ALPHABET) for _ in range(16))

        if not _rows("select 1 from company_cards where token = %s", [token]):
            return token


def _image(ctx: Context, path: str | None) -> str | None:
    """Снимок визитки на текущем хосте: QR раздают и с адреса Render, и со своего домена."""
    return ctx.url("storage/" + path) if path else None


def card_url(ctx: Context, token: str) -> str:
    """Адрес визитки, который кодирует QR, — на языке владельца."""
    return locales.url(ctx.root, f"/card/{token}", ctx.locale)


def _row(ctx: Context, card: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": card["id"],
        "kind": card["kind"],
        "image": _image(ctx, card["image_path"]),
        "company_name": card["company_name"],
        "full_name": card["full_name"],
        "email": card["email"],
        "phone": card["phone"],
        "url": card_url(ctx, card["token"]),
        "views": card["views_count"],
    }


def _count(company_id: int) -> int:
    return int(
        _rows("select count(*) as n from company_cards where company_id = %s", [company_id])[0]["n"]
    )


# ── Кабинет ──────────────────────────────────────────────────────────


def cards(request: HttpRequest) -> HttpResponse:
    """GET /cabinet/cards: визитки компании и форма новой."""
    ctx = page(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    assert ctx.user is not None
    company = company_of(ctx)
    rows = (
        _rows(
            "select * from company_cards where company_id = %s order by created_at desc, id desc",
            [company["id"]],
        )
        if company is not None
        else []
    )
    user = _rows("select name, email, phone from users where id = %s", [ctx.user["id"]])[0]

    return inertia.render(
        ctx,
        "cabinet/Cards",
        {
            "hasCompany": company is not None,
            "cards": [_row(ctx, card) for card in rows],
            "limit": LIMIT,
            # Поля новой визитки заполнены из профиля — их можно поправить
            "defaults": {
                "company_name": company["name"] if company is not None else "",
                "full_name": user["name"] or "",
                "email": user["email"] or "",
                "phone": user["phone"] or "",
            },
        },
        _seo(ctx),
    )


@form()
def store(request: HttpRequest) -> HttpResponse:
    """POST /cabinet/cards: новая визитка — фото или из полей."""
    ctx = action(request, throttle=30, throttle_minutes=60, throttle_prefix="company-card")
    assert ctx.user is not None
    company = company_of(ctx)

    if company is None:
        flash(ctx, "error", ctx.t("messages.company.fill_first"))

        return back(ctx)

    if _count(company["id"]) >= LIMIT:
        flash(ctx, "error", ctx.t("messages.cards.limit", count=LIMIT))

        return back(ctx)

    data = {**input_of(request), **request.FILES.dict()}
    photo = data.get("kind") == "photo"
    image = Check("image", lambda value: _passes("mimes", IMAGE_MIMES, value))
    rules: dict[str, list[str | Check]] = {"kind": ["required", "in:" + ",".join(KINDS)]}

    if photo:
        rules["photo"] = ["required", image, "max:8192"]
    else:
        rules |= {
            "company_name": ["required", "string", "max:190"],
            "full_name": ["required", "string", "max:190"],
            "email": ["required", "email:rfc", "max:190"],
            "phone": ["required", "string", f"regex:{PHONE}"],
        }

    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "photo.required": ctx.t("messages.file.required"),
            "photo.image": ctx.t("messages.image.mimes"),
            "photo.max": ctx.t("messages.image.max"),
            "company_name.required": ctx.t("messages.cards.company_required"),
            "full_name.required": ctx.t("messages.cards.name_required"),
            "email.required": ctx.t("messages.register.email_required"),
            "email.email": ctx.t("messages.register.email_format"),
            "phone.required": ctx.t("messages.register.phone_required"),
            "phone.regex": ctx.t("messages.phone_format"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    path = None

    if photo:
        from savdex.web import image_store

        try:
            path = image_store.store(
                data["photo"].read(), f"companies/{company['id']}/cards", image_store.PHOTO
            )
        except image_store.UnreadableImageError:
            return invalid(ctx, {"photo": [ctx.t("messages.image.none_readable")]})

    now = _stamp(eloquent.now())

    with allowed_writes("company_cards"), connection.cursor() as cursor:
        cursor.execute(
            "insert into company_cards (company_id, user_id, token, kind, image_path, "
            "company_name, full_name, email, phone, created_at, updated_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                company["id"],
                ctx.user["id"],
                _token(),
                "photo" if photo else "generated",
                path,
                None if photo else data["company_name"],
                None if photo else data["full_name"],
                None if photo else data["email"],
                None if photo else data["phone"],
                now,
                now,
            ],
        )

    flash(ctx, "success", ctx.t("messages.cards.created"))

    return back(ctx)


@form("DELETE")
def destroy(request: HttpRequest, card_id: str) -> HttpResponse:
    """DELETE /cabinet/cards/<id>: визитка и её снимок; QR перестаёт открываться."""
    ctx = action(request)
    company = company_of(ctx)
    found = (
        _rows(
            "select * from company_cards where id = %s and company_id = %s",
            [int(card_id), company["id"]],
        )
        if company is not None
        else []
    )

    if not found:
        return not_found(ctx)

    with allowed_writes("company_cards"), connection.cursor() as cursor:
        cursor.execute("delete from company_cards where id = %s", [found[0]["id"]])

    from savdex.web import image_store

    image_store.delete(found[0]["image_path"])
    flash(ctx, "success", ctx.t("messages.cards.deleted"))

    return back(ctx)


def page_or_store(request: HttpRequest) -> HttpResponse:
    """/cabinet/cards: GET — страница, POST — новая визитка."""
    if request.method == "POST":
        return store(request)

    return cards(request)


# ── Страница визитки (по QR) ─────────────────────────────────────────


def show(request: HttpRequest, token: str) -> HttpResponse:
    """GET /card/<token>: визитка и кнопка на страницу компании."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    found = _rows(
        "select k.*, c.name as owner_name, c.slug as owner_slug, c.logo_path as owner_logo, "
        "c.status as owner_status from company_cards k "
        "join companies c on c.id = k.company_id and c.deleted_at is null "
        "where k.token = %s limit 1",
        [token],
    )

    if not found:
        return not_found(ctx)

    card = found[0]
    own = ctx.user is not None and ctx.user["company_id"] == card["company_id"]

    # Заблокированную компанию площадка не показывает — и её визитку тоже
    if card["owner_status"] == "blocked" and not own:
        return not_found(ctx)

    if not own:
        count_view("company_cards", card["id"])

    title = card["full_name"] or card["company_name"] or card["owner_name"]
    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(ctx.t("cards.page_title", name=title))
    seo.noindex = True

    return inertia.render(
        ctx,
        "cards/Show",
        {
            "card": {k: v for k, v in _row(ctx, card).items() if k not in ("id", "views")},
            "company": {
                "name": card["owner_name"],
                "url": locales.url(ctx.root, f"/company/{card['owner_slug']}", ctx.locale),
                "logo": _image(ctx, card["owner_logo"]),
            },
        },
        seo,
    )
