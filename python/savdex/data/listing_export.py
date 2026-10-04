"""
Выгрузка объявлений: окно «Выгрузка» в разделе «Объявления» и общая
с внешними выгрузками (MEYOS) запись объявления в JSON.

Окно спрашивает формат (Excel, CSV, JSON), категории (раздел — вместе
с подразделами), статус и тип. «Плюс мебельные слова» добавляет
объявления из других категорий, в заголовке которых есть слово из списка
настройки furniture_keywords: ДСП, фурнитура, столешница… Слово
ищется с начала слова: «стул» найдёт «стулья», но не «пристулок».

В каждой строке — ссылка на объявление на сайте и в админке.
Контактов продавца в выгрузке нет: на площадке их открывают за плату.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet
from django.urls import reverse

from savdex.data.models import LISTING_STATUSES, LISTING_TYPES, Listing

#: Форматы окна «Выгрузка»
FORMATS = {"xlsx": "Excel", "csv": "CSV", "json": "JSON"}

#: Статусы окна: опубликованные или все (кроме корзины)
STATUSES = {"active": "Только опубликованные", "all": "Все, кроме удалённых"}

#: Раздел каталога «Мебель» (savdex/bootstrap/seeds.json)
FURNITURE_ROOT = "mebel"

#: Настройка со списком мебельных слов (через запятую или с новой строки)
KEYWORDS_SETTING = "furniture_keywords"

#: Слова по умолчанию — пока настройку не правили. Основы слов: ищутся
#: с начала слова в заголовке на любом языке объявления
DEFAULT_KEYWORDS = (
    "мебел",
    "mebel",
    "дсп",
    "лдсп",
    "мдф",
    "хдф",
    "фурнитур",
    "столешниц",
    "шкаф",
    "shkaf",
    "диван",
    "divan",
    "кресл",
    "kreslo",
    "стул",
    "stul",
    "кроват",
    "матрас",
    "комод",
    "тумб",
    "гарнитур",
)


# ── Мебельные слова ─────────────────────────────────────────────────


def keywords() -> list[str]:
    """Слова из настройки; пустая или нет её — слова по умолчанию."""
    from savdex.site.models import Setting

    raw = Setting.objects.filter(key=KEYWORDS_SETTING).values_list("value", flat=True).first()
    words = parse_keywords(raw if isinstance(raw, str) else "")

    return words or list(DEFAULT_KEYWORDS)


def keywords_url(staff: Any) -> str:  # noqa: ANN401
    """Ссылка на настройку со словами — тем, кто может её править."""
    from savdex.site.models import Setting

    pk = Setting.objects.filter(key=KEYWORDS_SETTING).values_list("pk", flat=True).first()

    if pk is None or not staff.can("settings.edit"):
        return ""

    return reverse("savdex_admin:site_setting_change", args=[pk])


def parse_keywords(text: str) -> list[str]:
    """«ДСП, фурнитура\\nстолешница» → ['дсп', 'фурнитура', 'столешница']: только буквы и цифры."""
    words = []

    for part in re.split(r"[,;\n]+", text):
        word = re.sub(r"[^\w\s-]", "", part.strip().lower(), flags=re.UNICODE).strip()

        if word and word not in words:
            words.append(word)

    return words


def keyword_q(words: Iterable[str]) -> Q:
    """
    Заголовок (и его переводы) содержит слово, начинающееся с одной из
    основ. \\m — начало слова в регулярных выражениях PostgreSQL.
    """
    stems = [re.escape(word) for word in words if word]

    if not stems:
        return Q(pk__in=[])

    pattern = r"\m(" + "|".join(stems) + ")"

    return Q(title__iregex=pattern) | Q(title_i18n__iregex=pattern)


# ── Категории ───────────────────────────────────────────────────────


def category_tree() -> list[dict[str, Any]]:
    """Разделы с подразделами — для окна: [{id, name, children: [...]}]."""
    from savdex.catalogs.models import Category

    rows = list(Category.objects.prefetch_related("translations").order_by("sort", "id"))
    tree: list[dict[str, Any]] = []
    by_parent: dict[int, list[dict[str, Any]]] = {}

    for category in rows:
        item: dict[str, Any] = {
            "id": category.pk,
            "slug": category.slug,
            "name": category.name(),
            "active": category.is_active,
            "children": [],
        }

        if category.parent_id is None:
            tree.append(item)
        else:
            by_parent.setdefault(category.parent_id, []).append(item)

    for item in tree:
        item["children"] = by_parent.get(item["id"], [])

    return tree


def expand(ids: Iterable[int]) -> set[int]:
    """Выбранные категории вместе с подразделами выбранных разделов."""
    from savdex.catalogs.models import Category

    chosen = {int(i) for i in ids}

    if not chosen:
        return set()

    children = Category.objects.filter(parent_id__in=chosen).values_list("pk", flat=True)

    return chosen | set(children)


def furniture_ids() -> list[int]:
    """Раздел «Мебель» и его подразделы."""
    from savdex.catalogs.models import Category

    root = Category.objects.filter(slug=FURNITURE_ROOT).values_list("pk", flat=True).first()

    return sorted(expand([root])) if root else []


def category_labels() -> dict[int, dict[str, Any]]:
    """Номер категории → {id, slug, name, parent} для строк выгрузки."""
    flat: dict[int, dict[str, Any]] = {}

    for section in category_tree():
        top = {"id": section["id"], "slug": section["slug"], "name": section["name"]}
        flat[section["id"]] = top

        for child in section["children"]:
            flat[child["id"]] = {
                "id": child["id"],
                "slug": child["slug"],
                "name": child["name"],
                "parent": top,
            }

    return flat


def category_path(label: Mapping[str, Any] | None) -> str:
    """«Мебель › Офисная мебель»."""
    if not label:
        return ""

    parent = label.get("parent")

    return f"{parent['name']} › {label['name']}" if parent else str(label["name"])


# ── Отбор ───────────────────────────────────────────────────────────


def select(
    *,
    categories: Iterable[int] = (),
    with_keywords: bool = False,
    status: str = "active",
    kind: str = "",
    words: Iterable[str] | None = None,
) -> QuerySet[Listing]:
    """
    Объявления для выгрузки: из выбранных категорий (раздел — с
    подразделами) и, если отмечено, ещё с мебельными словами в
    заголовке из любых категорий. Ничего не выбрано — все категории.
    Корзина не выгружается никогда.
    """
    queryset = Listing.objects.filter(deleted_at__isnull=True)

    if status != "all":
        queryset = queryset.filter(status="active")

    if kind in LISTING_TYPES:
        queryset = queryset.filter(type=kind)

    chosen = expand(categories)
    match = Q()

    if chosen:
        match |= Q(category_id__in=chosen)

    if with_keywords:
        match |= keyword_q(keywords() if words is None else words)

    if match:
        queryset = queryset.filter(match)

    return queryset.select_related("company").order_by("-published_at", "-id")


# ── Ссылки и запись в JSON ──────────────────────────────────────────


def site_url(path: str) -> str:
    """Адрес на сайте площадки (APP_URL)."""
    return (os.environ.get("APP_URL") or "http://localhost").rstrip("/") + path


def listing_url(listing: Listing) -> str:
    return site_url(f"/listing/{listing.slug}") if listing.slug else ""


def admin_url(listing: Listing) -> str:
    return site_url(reverse("savdex_admin:data_listing_change", args=[listing.pk]))


def photo_urls(listing: Listing) -> list[str]:
    """Фотографии по порядку, первая — обложка (images — из prefetch_related)."""
    from savdex.web.shared import public_url

    return [public_url(image.path) for image in listing.images.all()]


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None

    return int(value) if value == value.to_integral_value() else float(value)


def _when(value: Any) -> str | None:  # noqa: ANN401
    return value.isoformat() if value is not None else None


def as_json(
    listing: Listing,
    *,
    categories: Mapping[int, Mapping[str, Any]],
    cities: Mapping[int, str],
    internal: bool,
) -> dict[str, Any]:
    """
    Объявление для JSON-выгрузки. internal — для своих (админка): статус,
    счётчики и ссылка в админке; во внешней выгрузке их нет. Контактов
    продавца нет ни там, ни там.
    """
    company = listing.company
    category = categories.get(listing.category_id) if listing.category_id else None
    record: dict[str, Any] = {
        "id": listing.pk,
        "url": listing_url(listing),
        "type": listing.type,
        "title": listing.title,
        "title_i18n": listing.title_i18n or {},
        "description": listing.description or "",
        "category": dict(category) if category else None,
        "price": _number(listing.price),
        "bundle_price": _number(listing.bundle_price),
        "currency": listing.currency,
        "unit": listing.unit,
        "price_negotiable": bool(listing.price_negotiable),
        "min_order": listing.min_order,
        "delivery_terms": listing.delivery_terms or "",
        "payment_terms": listing.payment_terms or "",
        "city": cities.get(listing.city_id) if listing.city_id else None,
        "company": {
            "id": company.pk,
            "name": company.name,
            "url": site_url(f"/company/{company.slug}") if company.slug else "",
        }
        if company is not None
        else None,
        "photos": photo_urls(listing),
        "published_at": _when(listing.published_at),
        "updated_at": _when(listing.updated_at),
    }

    if internal:
        record.update(
            {
                "admin_url": admin_url(listing),
                "status": listing.status,
                "status_name": LISTING_STATUSES.get(listing.status, listing.status),
                "expires_at": _when(listing.expires_at),
                "views": listing.views_count,
                "impressions": listing.impressions_count,
                "unlocks": listing.unlocks_count,
            }
        )

    return record


def city_names() -> dict[int, str]:
    from savdex.geo.models import City

    return {city.pk: city.name() for city in City.objects.prefetch_related("translations")}
