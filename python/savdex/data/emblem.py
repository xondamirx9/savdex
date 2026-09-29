"""
Эмблема компании — копия App\\Support\\CompanyEmblem: градиентная плашка
с инициалами вместо чужого логотипа.

Настоящие логотипы площадка использовать не может — авторское право, —
поэтому эмблема рисуется своя: квадрат со скруглением, цвет — по региону
компании (город, адрес, название), буквы — инициалы названия
(Company::initials). Компания без определимого региона получает
стабильный цвет по названию: одна и та же компания всегда одного цвета.

Файл — SVG на публичном диске, companies/<номер>/emblem.svg, байт в байт
как у PHP; путь встаёт обычным логотипом (logo_path), как forceFill()->save()
у Eloquent: search_text пересчитывается, у администратора — строка журнала.
Прежний файл логотипа PHP не удаляет — не удаляет и здесь.

Сверка с PHP — tests/test_company_emblem.py.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Any, cast

from django.http import HttpRequest

from savdex.laravel_storage import public_root
from savdex.web import eloquent
from savdex.web.cabinet import _rows
from savdex.web.company_profile_actions import CASTS, _search_text
from savdex.web.shared import Context, initials

#: Палитры регионов: верх и низ градиента. Порядок важен — по нему
#: выбирается цвет компании без региона
PALETTES: dict[str, tuple[str, str]] = {
    "tashkent": ("#2563ab", "#123f74"),  # фирменный синий
    "fergana": ("#b02a4c", "#701a34"),  # малиновый
    "samarkand": ("#1d5f9e", "#0e3a66"),  # глубокий синий
    "bukhara": ("#b07430", "#77471a"),  # бронза
    "karakalpak": ("#5d7268", "#39493f"),  # серо-зелёный
    "navoi": ("#8f8434", "#5c541e"),  # оливковое золото
    "surkhandarya": ("#b0472a", "#742c18"),  # терракота
    "khorezm": ("#2a8a84", "#175450"),  # бирюза
    "andijan": ("#7952a8", "#4c3070"),  # фиолетовый
    "namangan": ("#468a3c", "#2b5a24"),  # зелёный
    "kashkadarya": ("#a8552a", "#6e3418"),
    "jizzakh": ("#58748f", "#37485c"),
    "syrdarya": ("#3f8a9e", "#255866"),
}

#: Приметы региона в городе, адресе или названии — по порядку, первая
#: найденная решает. «ферг\u00e1n» с латинскими «á» и «n» — как в PHP
REGION_HINTS: dict[str, str] = {
    "ташкент": "tashkent", "toshkent": "tashkent", "tashkent": "tashkent",
    "фергана": "fergana", "ферг\u00e1n": "fergana", "farg": "fergana", "коканд": "fergana",
    "маргилан": "fergana",
    "самарканд": "samarkand", "samarqand": "samarkand",
    "бухар": "bukhara", "buxoro": "bukhara",
    "нукус": "karakalpak", "каракалпак": "karakalpak",
    "навои": "navoi", "navoiy": "navoi", "зарафшан": "navoi",
    "термез": "surkhandarya", "сурхандарь": "surkhandarya",
    "ургенч": "khorezm", "хорезм": "khorezm", "хива": "khorezm", "urganch": "khorezm",
    "андижан": "andijan", "andijon": "andijan",
    "наманган": "namangan", "namangan": "namangan",
    "карши": "kashkadarya", "кашкадарь": "kashkadarya", "qarshi": "kashkadarya",
    "джизак": "jizzakh", "jizzax": "jizzakh",
    "гулистан": "syrdarya", "сырдарь": "syrdarya", "guliston": "syrdarya",
}  # fmt: skip

#: Heredoc CompanyEmblem::svg — без перевода строки в конце
_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{top}"/>
      <stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="56" fill="url(#bg)"/>
  <text x="128" y="128" text-anchor="middle" dominant-baseline="central"
    font-family="Arial, Helvetica, sans-serif" font-weight="700"
    font-size="{size}" fill="#ffffff" letter-spacing="1">{initials}</text>
</svg>"""


def path_of(company_id: int) -> str:
    """Где лежит эмблема на публичном диске."""
    return f"companies/{company_id}/emblem.svg"


def _escape(text: str) -> str:
    """htmlspecialchars($text, ENT_QUOTES): апостроф — «&#039;», как у PHP."""
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def palette(name: str, city: str | None = None, address: str | None = None) -> tuple[str, str]:
    """
    CompanyEmblem::palette: регион по приметам в городе, адресе и
    названии; не найден — стабильный цвет по crc32 названия.
    """
    # array_filter: пустое и «0» выпадают, как у PHP
    parts = [p for p in (city, address, name) if p not in (None, "", "0")]
    haystack = " ".join(str(p) for p in parts).lower()

    for hint, region in REGION_HINTS.items():
        if hint in haystack:
            return PALETTES[region]

    # Регион неизвестен — у одной компании эмблема не меняется
    # от генерации к генерации
    colours = list(PALETTES.values())

    return colours[zlib.crc32(name.lower().encode()) % len(colours)]


def svg(name: str, city: str | None = None, address: str | None = None) -> str:
    """CompanyEmblem::svg: плашка компании с таким названием, городом и адресом."""
    top, bottom = palette(name, city, address)
    letters = _escape(initials(name))

    return _SVG.format(
        top=top,
        bottom=bottom,
        # Две буквы шире одной — кегль по длине (после экранирования, как у PHP)
        size=96 if len(letters) >= 2 else 120,
        initials=letters,
    )


def city_name(city_id: int | None) -> str | None:
    """City::name() на языке админки (ru): перевод, иначе адрес города."""
    if city_id is None:
        return None

    rows = _rows(
        "select coalesce((select name from city_translations where city_id = c.id "
        "and locale = 'ru' order by id limit 1), c.slug) as name from cities c where c.id = %s",
        [city_id],
    )

    return str(rows[0]["name"]) if rows else None


@dataclass
class _Staff:
    """
    Сколько нужно общим частям сайта (savdex.web.eloquent): кто действует
    и запрос — для адреса в журнале. Без запроса адрес пуст.
    """

    request: HttpRequest | None
    user: dict[str, Any] | None


def staff_context(admin_id: int | None, request: HttpRequest | None = None) -> Context:
    """
    Контекст сотрудника для eloquent.save и eloquent.journal: журнал
    пишется, только если это администратор (AdminLog::actorIsAdmin).
    """
    user = None

    if admin_id is not None:
        rows = _rows("select id, name, email, is_admin from users where id = %s", [admin_id])
        user = rows[0] if rows else None

    return cast(Context, _Staff(request=request, user=user))


def assign(
    company_id: int,
    *,
    admin_id: int | None = None,
    request: HttpRequest | None = None,
) -> str:
    """
    CompanyEmblem::assign: нарисовать эмблему, положить на публичный
    диск и назначить логотипом. Вернуть путь (logo_path).

    Прежний логотип заменяется в строке компании; его файл остаётся
    на диске, как у PHP. admin_id и request — для журнала действий
    (AuditObserver): кто и откуда.
    """
    rows = _rows("select * from companies where id = %s", [company_id])

    if not rows:
        raise LookupError(f"Компании {company_id} нет")

    company = rows[0]
    path = path_of(company_id)
    target = public_root() / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        svg(str(company["name"]), city_name(company["city_id"]), company["address"]).encode()
    )

    eloquent.save(
        staff_context(admin_id, request),
        "companies",
        company,
        {"logo_path": path},
        section="companies",
        model="Company",
        saving=_search_text,
        casts=CASTS,
    )

    return path
