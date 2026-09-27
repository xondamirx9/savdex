"""
Постраничный вывод — копия LengthAwarePaginator у Laravel.

Страница Inertia получает объект целиком (toArray): data, ссылки на
соседние страницы, окно номеров с «...» (UrlWindow) и подписи
«назад/вперёд». Подписи — __('pagination.previous'): у площадки нет
своего файла pagination, и перевод есть только у английского (из
самого фреймворка); на остальных языках Laravel отдаёт ключ как есть,
и Django — тоже.

Адреса страниц — как withQueryString(): параметры запроса в том
порядке, в каком пришли, без page — он всегда последним (appends()
его пропускает), всё собрано http_build_query с RFC 3986 (Arr::query).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from savdex.web.phpquery import build_query, laravel_input
from savdex.web.shared import Context

#: $onEachSide у Laravel по умолчанию
ON_EACH_SIDE = 3

#: FILTER_VALIDATE_INT: пробелы по краям, знак, без ведущих нулей
_VALID_INT = re.compile(r"^[ \t\n\r\v\f]*[+-]?(0|[1-9][0-9]*)[ \t\n\r\v\f]*$")

_LABELS = {
    "en": ("&laquo; Previous", "Next &raquo;"),
}


def current_page(ctx: Context, name: str = "page") -> int:
    """PaginationState: currentPageResolver."""
    value = laravel_input(ctx.query).get(name)

    if not isinstance(value, str) or not _VALID_INT.match(value):
        return 1

    page = int(value.strip())

    return page if 1 <= page < 2**63 else 1


@dataclass
class Page:
    """Страница выборки: элементы уже вырезаны запросом (LIMIT/OFFSET)."""

    items: Sequence[Any]
    total: int
    per_page: int
    current: int

    @property
    def last(self) -> int:
        return max(math.ceil(self.total / self.per_page), 1)

    @property
    def offset(self) -> int:
        return (self.current - 1) * self.per_page


def offset(ctx: Context, per_page: int) -> tuple[int, int]:
    """Номер страницы и сдвиг для запроса."""
    page = current_page(ctx)

    return page, (page - 1) * per_page


def _path(ctx: Context) -> str:
    """
    Request::url(): без строки запроса и без «/» в конце. Языкового
    префикса в нём нет — LocalizeUrl срезает его с адреса запроса, —
    так что ссылки на страницы у Laravel ведут без префикса.
    """
    return (ctx.root + ctx.path).rstrip("/")


def to_array(
    ctx: Context,
    page: Page,
    card: Callable[[Any], Any] = lambda item: item,
    on_each_side: int = ON_EACH_SIDE,
) -> dict[str, Any]:
    """LengthAwarePaginator::toArray после withQueryString() и through()."""
    return build(_path(ctx), ctx.query, ctx.locale, page, card, on_each_side)


def build(
    path: str,
    query_string: str,
    locale: str,
    page: Page,
    card: Callable[[Any], Any] = lambda item: item,
    on_each_side: int = ON_EACH_SIDE,
) -> dict[str, Any]:
    """toArray по адресу страницы (Request::url()), запросу и языку."""
    # withQueryString() берёт $request->query() — уже после TrimStrings
    # и ConvertEmptyStringsToNull: пустые параметры выпадают из ссылок
    query = laravel_input(query_string)
    current, last = page.current, page.last

    def url(number: int) -> str:
        number = max(number, 1)
        # appends() пропускает сам page, и array_merge ставит его в конец
        parameters = {**{k: v for k, v in query.items() if k != "page"}, "page": str(number)}

        return path + ("&" if "?" in path else "?") + build_query(parameters)

    def url_range(start: int, end: int) -> dict[int, str]:
        return {n: url(n) for n in range(start, end + 1)}

    prev_url = url(current - 1) if current > 1 else None
    next_url = url(current + 1) if current < last else None

    links: list[dict[str, Any]] = []
    previous, following = _LABELS.get(locale, ("pagination.previous", "pagination.next"))
    links.append(
        {
            "url": prev_url,
            "label": previous,
            "page": current - 1 if current > 1 else None,
            "active": False,
        }
    )

    for element in _elements(current, last, on_each_side, url_range):
        if element is None:
            links.append({"url": None, "label": "...", "active": False})
            continue

        for number, link in element.items():
            links.append(
                {"url": link, "label": str(number), "page": number, "active": current == number}
            )

    links.append(
        {
            "url": next_url,
            "label": following,
            "page": current + 1 if current < last else None,
            "active": False,
        }
    )

    count = len(page.items)
    first = page.offset + 1 if count else None

    return {
        "current_page": current,
        "data": [card(item) for item in page.items],
        "first_page_url": url(1),
        "from": first,
        "last_page": last,
        "last_page_url": url(last),
        "links": links,
        "next_page_url": next_url,
        "path": path,
        "per_page": page.per_page,
        "prev_page_url": prev_url,
        "to": first + count - 1 if first is not None else None,
        "total": page.total,
    }


def _elements(
    current: int,
    last: int,
    on_each_side: int,
    url_range: Callable[[int, int], dict[int, str]],
) -> list[dict[int, str] | None]:
    """UrlWindow и LengthAwarePaginator::elements: None — это «...»."""
    first: dict[int, str] | None
    slider: dict[int, str] | None = None
    end: dict[int, str] | None = None

    if last < on_each_side * 2 + 8:
        first = url_range(1, last)
    else:
        window = on_each_side + 4

        if current <= window:
            first = url_range(1, window + on_each_side)
            end = url_range(last - 1, last)
        elif current > last - window:
            first = url_range(1, 2)
            end = url_range(last - (window + (on_each_side - 1)), last)
        else:
            first = url_range(1, 2)
            slider = url_range(current - on_each_side, current + on_each_side)
            end = url_range(last - 1, last)

    # array_filter: пустые окна выпадают
    parts: list[dict[int, str] | None] = []

    for part, dots_before in ((first, False), (slider, True), (end, True)):
        if dots_before and part:
            parts.append(None)

        if part:
            parts.append(part)

    return parts
