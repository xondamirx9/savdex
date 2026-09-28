"""
Детали товара — копия App\\Support\\ProductSpecs для страниц на Django.

Блок «Информация о товаре» в мастере объявления: набор полей зависит
от категории. Значения лежат в listing_attributes с ключами spec_*
кодами («25 kg», «black»), на карточке товара выводятся на языке
посетителя. Подписи — словарь lang/<язык>/specs.php из выгрузки
(savdex/web/ui.py, groups.specs).

Здесь только чтение: форма для мастера и строки для карточки.
Проверка значений (ProductSpecs::clean) — при записи, её делает Laravel.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from savdex.web import ui

PREFIX = "spec_"

# ContentTranslation::text: перевод свободного текста
Text = Callable[[str | None], str | None]

FIELDS: dict[str, dict[str, Any]] = {
    "weight": {"type": "measure", "units": ["kg", "t", "g"]},
    "dimensions": {"type": "dims", "units": ["cm", "mm", "m"]},
    "length": {"type": "measure", "units": ["mm", "m"]},
    "thickness": {"type": "measure", "units": ["mm"]},
    "diameter": {"type": "measure", "units": ["mm"]},
    "width": {"type": "measure", "units": ["cm", "m"]},
    "density": {"type": "measure", "units": ["gsm"]},
    "capacity": {"type": "measure", "units": ["l"]},
    "load": {"type": "measure", "units": ["kg", "t"]},
    "power": {"type": "measure", "units": ["kw"]},
    "shelf_life": {"type": "measure", "units": ["months", "days", "years"]},
    "warranty": {"type": "measure", "units": ["months", "years"]},
    "year": {"type": "number"},
    "color": {"type": "select", "options": "color", "custom": True},
    "material": {"type": "select", "options": "material", "custom": True},
    "composition": {"type": "select", "options": "material", "custom": True},
    "coating": {"type": "select", "options": "coating", "custom": True},
    "packaging": {"type": "select", "options": "packaging", "custom": True},
    "storage": {"type": "select", "options": "storage", "custom": True},
    "condition": {"type": "select", "options": "condition"},
    "voltage": {"type": "select", "options": "voltage", "custom": True},
    "grade": {"type": "text"},
    "sizes": {"type": "text"},
    "brand": {"type": "text"},
    "origin": {"type": "text"},
}

_METAL = ["material", "grade", "weight", "length", "thickness", "diameter", "coating", "origin"]

SETS: dict[str, list[str]] = {
    "stroymaterialy": [
        "weight", "dimensions", "material", "color", "grade", "packaging", "brand", "origin",
    ],
    "metally": _METAL,
    "tekstil": [
        "composition", "color", "density", "width", "sizes", "weight", "brand", "origin",
    ],
    "produkty": ["weight", "packaging", "shelf_life", "storage", "grade", "brand", "origin"],
    "upakovka": ["material", "dimensions", "capacity", "load", "color", "weight", "origin"],
    "oborudovanie": [
        "condition", "power", "voltage", "weight", "dimensions", "year", "warranty", "brand",
        "origin",
    ],
    "mebel": ["dimensions", "material", "color", "weight", "warranty", "brand", "origin"],
    "vystavki": [],
    "logistika": [],
    "uslugi": [],
}  # fmt: skip

CHILD_SETS: dict[str, list[str]] = {
    "metalloprokat": _METAL,
    "krovlya-fasad": [
        "material", "dimensions", "thickness", "color", "coating", "weight", "brand", "origin",
    ],
    "cement-beton": ["weight", "packaging", "grade", "brand", "origin"],
    "kirpich-blok": ["dimensions", "material", "weight", "color", "grade", "brand", "origin"],
    "gotovaya-odezhda": ["composition", "color", "sizes", "brand", "origin"],
    "zerno-muka": ["weight", "packaging", "grade", "shelf_life", "storage", "origin"],
    "poddony-tara": ["material", "dimensions", "load", "weight", "origin"],
}  # fmt: skip

DEFAULT_SET = ["weight", "dimensions", "color", "material", "brand", "origin"]

MATERIALS: dict[str, list[str]] = {
    "stroymaterialy": [
        "concrete", "ceramic", "stone", "gypsum", "wood", "metal", "steel", "plastic", "glass",
    ],
    "metally": [
        "steel", "stainless", "cast_iron", "aluminium", "copper", "brass", "bronze", "zinc",
        "lead", "titanium",
    ],
    "tekstil": [
        "cotton", "polyester", "cotton_poly", "viscose", "wool", "silk", "linen", "nylon",
        "leather",
    ],
    "upakovka": ["cardboard", "paper", "polyethylene", "plastic", "wood", "glass", "metal"],
    "oborudovanie": ["steel", "stainless", "cast_iron", "aluminium", "plastic"],
    "mebel": [
        "solid_wood", "mdf", "chipboard", "metal", "plastic", "glass", "fabric", "leather",
        "eco_leather",
    ],
    "metalloprokat": ["steel", "stainless", "cast_iron", "aluminium", "copper", "brass", "zinc"],
    "krovlya-fasad": ["steel", "aluminium", "ceramic", "concrete", "plastic", "glass", "wood"],
    "poddony-tara": ["wood", "plastic", "metal", "cardboard"],
}  # fmt: skip

DEFAULT_MATERIALS = ["metal", "wood", "plastic", "glass", "fabric", "paper", "ceramic", "rubber"]

COMPOSITION = ["cotton", "polyester", "cotton_poly", "viscose", "wool", "silk", "linen", "nylon"]


def enabled() -> bool:
    """
    Детали товара есть у Laravel — выгружен словарь lang/ru/specs.php.
    Пока его нет (ProductSpecs не влит), страницы Django без блока, как
    Laravel; появился — блок включается сам, без выкладки Django.
    """
    return ui.group_node("specs.fields", "ru") is not None


def owns(key: str) -> bool:
    """ProductSpecs::owns: ключ характеристики — деталь товара."""
    return key.startswith(PREFIX) and key[len(PREFIX) :] in FIELDS and enabled()


def form(parent_slug: str | None, child_slug: str | None, locale: str) -> list[dict[str, Any]]:
    """ProductSpecs::form: поля блока для мастера — на языке сайта."""
    return [
        _describe(f, parent_slug, child_slug, locale) for f in _set_for(parent_slug, child_slug)
    ]


def present(key: str, value: str, locale: str, text: Text) -> dict[str, str] | None:
    """
    ProductSpecs::present: подпись и значение для карточки товара.
    text — ContentTranslation::text (перевод свободного текста).
    """
    if not owns(key) or value.strip() == "":
        return None

    field = key[len(PREFIX) :]
    spec = FIELDS[field]

    if spec["type"] == "measure":
        shown = _present_measure(value, locale)
    elif spec["type"] == "dims":
        shown = _present_dims(value, locale)
    elif spec["type"] == "select":
        shown = _present_option(spec.get("options", ""), value, locale, text)
    else:
        shown = str(text(value) or "")

    return {"key": ui.group_t("specs.fields." + field, locale), "value": shown}


def _set_for(parent_slug: str | None, child_slug: str | None) -> list[str]:
    if child_slug is not None and child_slug in CHILD_SETS:
        return CHILD_SETS[child_slug]

    return SETS[parent_slug] if parent_slug is not None and parent_slug in SETS else DEFAULT_SET


def _describe(
    field: str, parent_slug: str | None, child_slug: str | None, locale: str
) -> dict[str, Any]:
    spec = FIELDS[field]
    group = spec.get("options")

    if group is None:
        options: list[str] = []
    elif group == "material":
        options = (
            COMPOSITION
            if field == "composition"
            else MATERIALS.get(child_slug or "")
            or MATERIALS.get(parent_slug or "")
            or DEFAULT_MATERIALS
        )
    else:
        # array_keys(trans('specs.options.<group>', locale: 'ru'))
        node = ui.group_node("specs.options." + group, "ru")
        options = list(node) if isinstance(node, dict) else []

    return {
        "key": PREFIX + field,
        "label": ui.group_t("specs.fields." + field, locale),
        "type": spec["type"],
        "units": [
            {"value": u, "label": ui.group_t("specs.units." + u, locale)}
            for u in spec.get("units", [])
        ],
        "options": [
            {"value": o, "label": ui.group_t(f"specs.options.{group}.{o}", locale)} for o in options
        ],
        "custom": bool(spec.get("custom", False)),
    }


def _present_measure(value: str, locale: str) -> str:
    number, _, unit = value.partition(" ")

    return f"{number} {_unit(unit, locale)}".strip()


def _present_dims(value: str, locale: str) -> str:
    sizes, _, unit = value.partition(" ")
    parts = ["—" if p == "" else p for p in sizes.split("x")]

    return " × ".join(parts) + " " + _unit(unit, locale)


def _present_option(group: str, value: str, locale: str, text: Text) -> str:
    key = f"specs.options.{group}.{value}"

    # Свой вариант («Другое») — как написан, с переводом свободного текста
    if ui.group_node(key, locale) is not None:
        return ui.group_t(key, locale)

    return str(text(value) or "")


def _unit(code: str, locale: str) -> str:
    key = "specs.units." + code

    return (
        ui.group_t(key, locale) if code != "" and ui.group_node(key, locale) is not None else code
    )
