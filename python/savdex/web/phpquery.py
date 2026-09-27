"""
Строка запроса, как её видит Laravel: Request::normalizeQueryString.

Адрес страницы в объекте Inertia (и адрес перезагрузки при смене
сборки) Laravel берёт из $request->fullUrl(), а там параметры уже
разобраны parse_str, отсортированы ksort и собраны заново
http_build_query: «?type=platform&page=2» становится «?page=2&type=platform»,
из повторов остаётся последний, «+» — это «%20». Django отдаёт тот же
адрес, иначе браузер после перехода получал бы другую строку.

Строки PHP — байты, поэтому разбор идёт по байтам (latin-1 как
прозрачная обёртка): битый UTF-8 в адресе переживает круг без потерь.
"""

from __future__ import annotations

import math
import re
from functools import cmp_to_key
from typing import Union
from urllib.parse import quote_from_bytes, unquote_to_bytes

#: Значение после parse_str: строка или массив PHP (ключи — int или str)
Value = Union[str, "Array"]
Array = dict[int | str, Value]

_INT_KEY = re.compile(r"^(0|-?[1-9][0-9]*)$")
_NUMERIC = re.compile(r"^[ \t\n\r\v\f]*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?[ \t\n\r\v\f]*$")


def _urldecode(raw: str) -> str:
    """urldecode PHP: «+» — пробел, %XX — байт."""
    return unquote_to_bytes(raw.replace("+", " ")).decode("latin-1")


def _key(name: str) -> int | str:
    """Ключ массива PHP: каноническое целое становится int."""
    if _INT_KEY.match(name) and -(2**63) <= int(name) < 2**63:
        return int(name)

    return name


def _append_key(array: Array) -> int:
    ints = [k for k in array if isinstance(k, int)]

    return max(ints) + 1 if ints and max(ints) >= 0 else 0


def _assign(array: Array, path: list[str | None], value: str) -> None:
    """Запись по пути ключей; None — «[]», добавить в конец."""
    node = array

    for i, part in enumerate(path):
        key: int | str = _append_key(node) if part is None else _key(part)

        if i == len(path) - 1:
            node[key] = value
            return

        child = node.get(key)

        if not isinstance(child, dict):
            child = {}
            node[key] = child

        node = child


def _path(name: str) -> list[str | None] | None:
    """
    Разбор имени с квадратными скобками, как php_register_variable_ex.

    «a[b][]» → ["a", "b", None]. Незакрытая первая скобка — часть
    имени («a[b» → ключ «a[b», как после обратного превращения «_»
    у Symfony); текст после закрывающей скобки не из «[…]» — отбрасывается.
    """
    start = name.find("[")

    if start < 0:
        return [name]

    base, rest = name[:start], name[start:]
    parts: list[str | None] = [base]

    while rest.startswith("["):
        end = rest.find("]")

        if end < 0:
            if len(parts) == 1:
                return [name]

            break

        inner = rest[1:end]
        parts.append(inner if inner != "" else None)
        rest = rest[end + 1 :]

    return parts


def parse_query(qs: str) -> Array:
    """HeaderUtils::parseQuery: пары через «&», повтор — последний."""
    result: Array = {}

    for pair in qs.split("&"):
        pair = pair.split("\0", 1)[0]
        name, eq, raw = pair.partition("=")
        key = _urldecode(name).split("\0", 1)[0].lstrip(" ")

        if key == "":
            continue

        path = _path(key)

        if path is None or path[0] == "":
            continue

        _assign(result, path, _urldecode(raw) if eq else "")

    return result


def _php_compare(a: int | str, b: int | str) -> int:
    """Сравнение ключей у ksort в PHP 8: числа и числовые строки — как числа."""

    def numeric(x: int | str) -> float | None:
        if isinstance(x, int):
            return float(x)

        return float(x) if _NUMERIC.match(x) else None

    na, nb = numeric(a), numeric(b)

    if na is not None and nb is not None:
        return (na > nb) - (na < nb)

    sa, sb = str(a).encode("latin-1"), str(b).encode("latin-1")

    return (sa > sb) - (sa < sb)


def _sorted(array: Array) -> list[tuple[int | str, Value]]:
    """ksort: устойчивая сортировка по ключам (PHP 8)."""
    order = sorted(array, key=cmp_to_key(_php_compare))

    return [(key, array[key]) for key in order]


def _encode(text: str) -> str:
    """rawurlencode: всё, кроме A–Z a–z 0–9 - _ . ~"""
    return quote_from_bytes(text.encode("latin-1"), safe="")


def build_query(array: Array) -> str:
    """http_build_query(…, PHP_QUERY_RFC3986)."""
    out: list[str] = []

    def walk(prefix: str, value: Value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(f"{prefix}%5B{_encode(str(key))}%5D", child)
        else:
            out.append(f"{prefix}={_encode(value)}")

    for key, value in array.items():
        walk(_encode(str(key)), value)

    return "&".join(out)


def normalize(qs: str) -> str:
    """Request::normalizeQueryString: разобрать, отсортировать ksort, собрать."""
    if qs == "":
        return ""

    return build_query(dict(_sorted(parse_query(qs))))


def full_path(path: str, qs: str) -> str:
    """Путь и строка запроса, как в Request::fullUrl: корень с параметрами — «/?»."""
    query = normalize(qs)
    path = path.rstrip("/")

    if not query:
        return path

    return path + ("/?" if path == "" else "?") + query


#: (int) у PHP для строки: ведущие пробелы, знак, цифры, дробь и порядок
_PHP_NUMBER = re.compile(r"^[ \t\n\r\v\f]*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def php_int(value: str | None, default: int) -> int:
    """(int) $request->query(...): не число — 0, «2abc» — 2, «1e2» — 100."""
    if value is None:
        return default

    match = _PHP_NUMBER.match(value)

    if match is None:
        return 0

    number = float(match.group(1))

    return int(number) if math.isfinite(number) and abs(number) < 2**63 else 0
