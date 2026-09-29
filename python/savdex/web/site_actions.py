"""
Мини-сайт компании — формы на Django (этап 5, шаг 35): сохранить адрес
и оформление, опубликовать, снять с публикации, фон первого экрана.
Копия App\\Http\\Controllers\\Cabinet\\SiteController и CompanySite
(publish, unpublish, heroInUse).

Оформление проходит SiteTheme::normalize (savdex.web.cabinet.site_theme);
фон из формы не принимается — только загрузкой. Черновик и
опубликованное хранятся текстом json_encode (каст array). Прежний фон
удаляется, когда его не показывают ни черновик, ни сайт.

Сверка с настоящим Laravel — tests/test_web_site_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.audit import _php_json
from savdex.guards import allowed_writes
from savdex.web import eloquent, image_store
from savdex.web.actions import form
from savdex.web.cabinet import (
    SITE_FONTS,
    SITE_MODES,
    SITE_RADII,
    SITE_TEMPLATES,
    _rows,
    company_of,
    company_plan,
    site_theme,
)
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context
from savdex.web.validation import Check, validate, validated

#: SiteHost::PATTERN
SUBDOMAIN = r"/^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$/"

#: config('microsite.reserved')
RESERVED = (
    "www", "api", "app", "admin", "cabinet", "mail", "smtp", "imap", "pop", "ftp",
    "ns1", "ns2", "cdn", "static", "assets", "media", "img", "files",
    "help", "support", "status", "blog", "news", "docs",
    "dev", "test", "staging", "demo", "beta",
    "savdex", "official", "pay", "payment", "billing", "login", "auth", "account",
)  # fmt: skip

HEX = r"/^#[0-9a-fA-F]{6}$/"


def _available(company: dict[str, Any] | None) -> bool:
    """SiteController::available: не заблокирована и тариф с мини-сайтом."""
    return (
        company is not None
        and company["status"] != "blocked"
        and bool(company_plan(company["id"]).get("has_microsite"))
    )


def _site(company_id: int) -> dict[str, Any] | None:
    rows = _rows("select * from company_sites where company_id = %s limit 1", [company_id])

    return rows[0] if rows else None


def _save(ctx: Context, site: dict[str, Any], changes: dict[str, Any]) -> None:
    """forceFill()->save() у CompanySite: theme и published_theme — каст array."""
    eloquent.save(
        ctx,
        "company_sites",
        site,
        changes,
        section=None,
        model="CompanySite",
        casts={"theme": "json", "published_theme": "json"},
    )


def _hero_in_use(site: dict[str, Any], path: str) -> bool:
    """CompanySite::heroInUse."""
    theme = site["theme"] if isinstance(site["theme"], dict) else {}
    published = site["published_theme"] if isinstance(site["published_theme"], dict) else {}

    return theme.get("hero_image") == path or published.get("hero_image") == path


def _plan_required(ctx: Context) -> HttpResponse:
    flash(ctx, "error", ctx.t("messages.site.plan_required"))

    return back(ctx)


@form("PATCH")
def update(request: HttpRequest) -> HttpResponse:
    """SiteController::update (throttle:60,1): адрес и оформление черновика."""
    ctx = action(request, throttle=60)
    company = company_of(ctx)

    if company is None or not _available(company):
        return _plan_required(ctx)

    def unique(value: Any) -> bool:  # noqa: ANN401
        """Rule::unique('company_sites', 'subdomain')->ignore($company->id, 'company_id')."""
        return not _rows(
            "select 1 from company_sites where subdomain = %s and company_id <> %s limit 1",
            [str(value), company["id"]],
        )

    rules: dict[str, list[str | Check]] = {
        "subdomain": [
            "required",
            "string",
            "lowercase",
            f"regex:{SUBDOMAIN}",
            Check("reserved", lambda v: str(v) not in RESERVED),
            Check("unique", unique),
        ],
        "theme": ["required", "array"],
        "theme.template": ["required", "in:" + ",".join(SITE_TEMPLATES)],
        "theme.primary": ["required", f"regex:{HEX}"],
        "theme.accent": ["required", f"regex:{HEX}"],
        "theme.mode": ["required", "in:" + ",".join(SITE_MODES)],
        "theme.heading_font": ["required", "in:" + ",".join(SITE_FONTS)],
        "theme.body_font": ["required", "in:" + ",".join(SITE_FONTS)],
        "theme.radius": ["required", "in:" + ",".join(SITE_RADII)],
    }
    data = input_of(request)
    errors = validate(
        data,
        rules,
        ctx.locale,
        {
            "subdomain.regex": ctx.t("messages.site.subdomain_format"),
            "subdomain.unique": ctx.t("messages.site.subdomain_taken"),
            "subdomain.reserved": ctx.t("messages.site.subdomain_reserved"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    fields = validated(data, rules)
    site = _site(company["id"])
    current = site["theme"] if site and isinstance(site["theme"], dict) else {}
    theme = site_theme({**fields["theme"], "hero_image": current.get("hero_image")})
    subdomain = str(fields["subdomain"]).lower()
    changes: dict[str, Any] = {"subdomain": subdomain, "theme": theme}

    if site is not None:
        _save(ctx, site, changes)
    else:
        now = _stamp(eloquent.now())

        with allowed_writes("company_sites"), connection.cursor() as cursor:
            cursor.execute(
                "insert into company_sites (company_id, subdomain, theme, updated_at, "
                "created_at) values (%s, %s, %s, %s, %s)",
                [company["id"], subdomain, _php_json(theme), now, now],
            )

    flash(ctx, "success", ctx.t("messages.site.saved"))

    return back(ctx)


@form()
def publish(request: HttpRequest) -> HttpResponse:
    """SiteController::publish и CompanySite::publish."""
    ctx = action(request)
    company = company_of(ctx)

    if company is None or not _available(company):
        return _plan_required(ctx)

    site = _site(company["id"])

    if site is None:
        flash(ctx, "error", ctx.t("messages.site.save_first"))

        return back(ctx)

    published = site["published_theme"] if isinstance(site["published_theme"], dict) else {}
    previous = published.get("hero_image")
    _save(
        ctx,
        site,
        {
            "status": "published",
            "published_theme": site_theme(site["theme"]),
            "published_at": eloquent.now(),
        },
    )

    # Прежний фон больше нигде не показывается — файл не нужен
    if previous is not None and not _hero_in_use(site, previous):
        image_store.delete(previous)

    flash(ctx, "success", ctx.t("messages.site.published"))

    return back(ctx)


@form()
def unpublish(request: HttpRequest) -> HttpResponse:
    """SiteController::unpublish: и без тарифа — это отказ от услуги."""
    ctx = action(request)
    company = company_of(ctx)
    site = _site(company["id"]) if company is not None else None

    if site is not None:
        _save(ctx, site, {"status": "draft"})

    flash(ctx, "success", ctx.t("messages.site.unpublished"))

    return back(ctx)


def _replace_hero(ctx: Context, site: dict[str, Any], path: str | None) -> None:
    """SiteController::replaceHero: новый фон черновика, прежний — если не на сайте."""
    theme = site["theme"] if isinstance(site["theme"], dict) else {}
    previous = theme.get("hero_image")
    _save(ctx, site, {"theme": {**site_theme(site["theme"]), "hero_image": path}})

    if previous is not None and not _hero_in_use(site, previous):
        image_store.delete(previous)


@form()
def upload_hero(request: HttpRequest) -> HttpResponse:
    """SiteController::uploadHero (throttle:30,60)."""
    ctx = action(request, throttle=30, throttle_minutes=60)
    company = company_of(ctx)

    if company is None or not _available(company):
        return _plan_required(ctx)

    site = _site(company["id"])

    if site is None:
        flash(ctx, "error", ctx.t("messages.site.save_first"))

        return back(ctx)

    data = {**input_of(request), **request.FILES.dict()}
    errors = validate(
        data,
        {"hero": ["required", "file", "mimes:jpg,jpeg,png,webp", "max:8192"]},
        ctx.locale,
        {
            "hero.required": ctx.t("messages.file.required"),
            "hero.mimes": ctx.t("messages.image.mimes"),
            "hero.max": ctx.t("messages.image.max"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    try:
        path = image_store.store(data["hero"].read(), f"sites/{company['id']}", image_store.COVER)
    except image_store.UnreadableImageError:
        flash(ctx, "error", ctx.t("messages.image.unreadable"))

        return back(ctx)

    _replace_hero(ctx, site, path)
    flash(ctx, "success", ctx.t("messages.site.hero_saved"))

    return back(ctx)


@form("DELETE")
def remove_hero(request: HttpRequest) -> HttpResponse:
    """SiteController::removeHero."""
    ctx = action(request)
    company = company_of(ctx)
    site = _site(company["id"]) if company is not None else None

    if site is not None:
        _replace_hero(ctx, site, None)

    flash(ctx, "success", ctx.t("messages.site.hero_removed"))

    return back(ctx)


def page(request: HttpRequest) -> HttpResponse:
    """/cabinet/site: GET — редактор (cabinet), PATCH — сохранить."""
    from savdex.web.cabinet import site_page

    if request.method == "PATCH":
        return update(request)

    return site_page(request)


def hero(request: HttpRequest) -> HttpResponse:
    """/cabinet/site/hero: POST — загрузить фон, DELETE — убрать."""
    return remove_hero(request) if request.method == "DELETE" else upload_hero(request)
