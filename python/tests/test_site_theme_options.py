"""
Оформление мини-сайта: готовые сочетания, шрифты и подписи согласованы.

Сочетание с неизвестным шрифтом сервер молча заменил бы умолчанием
(site_theme), а шрифт без записи в microsite.FONTS уронил бы страницу
сайта. Подписи сочетаний — в словаре каждого языка.
"""

from __future__ import annotations

import json
import re

import pytest

from savdex.web.cabinet import SITE_FONTS, SITE_MODES, SITE_PRESETS, SITE_RADII, site_theme
from savdex.web.microsite import FONTS, variables
from savdex.web.ui import directory

LOCALES = ("ru", "uz", "en", "zh", "tr")


def test_шрифты_одни_и_те_же():
    assert set(FONTS) == set(SITE_FONTS)
    assert {k: v[0] for k, v in FONTS.items()} == SITE_FONTS


@pytest.mark.parametrize("key", list(SITE_PRESETS))
def test_сочетание_допустимо(key):
    preset = SITE_PRESETS[key]

    assert re.fullmatch(r"#[0-9a-f]{6}", preset["primary"])
    assert re.fullmatch(r"#[0-9a-f]{6}", preset["accent"])
    assert preset["mode"] in SITE_MODES and preset["radius"] in SITE_RADII
    assert preset["heading_font"] in SITE_FONTS and preset["body_font"] in SITE_FONTS
    # Сервер принимает сочетание как есть и рисует его без ошибок
    theme = site_theme(preset)
    assert {k: theme[k] for k in preset} == preset
    assert variables(theme)["--ms-primary"] == preset["primary"]


def test_сочетаний_больше_и_есть_тёмные():
    modes = [p["mode"] for p in SITE_PRESETS.values()]

    assert len(SITE_PRESETS) >= 18 and modes.count("dark") >= 4
    assert len({(p["primary"], p["accent"]) for p in SITE_PRESETS.values()}) == len(SITE_PRESETS)


@pytest.mark.parametrize("locale", LOCALES)
def test_подписи_на_всех_языках(locale):
    site = json.loads((directory() / f"{locale}.json").read_text(encoding="utf-8"))["translations"][
        "cabinet"
    ]["site"]

    assert set(site["preset_names"]) >= set(SITE_PRESETS)
    for key in ("swap_colors", "random_colors", "pick_color", "hex_invalid", "font_preview"):
        assert site[key].strip()
