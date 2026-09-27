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

#: Значение после parse_str: строка или массив PHP (ключи — int или str);
#: None — после ConvertEmptyStringsToNull (laravel_input)
Value = Union[str, None, "Array"]
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


_MANGLE = str.maketrans({" ": "_", ".": "_"})
_MANGLE_TAIL = str.maketrans({" ": "_", ".": "_", "[": "_"})


def _native_name(name: str) -> str:
    """
    Имя параметра, как его портит parse_str самого PHP ($_GET): в имени
    до «[» пробел и точка становятся «_»; незакрытая первая «[» — тоже
    «_», и в остатке ещё и «[». Symfony (parseQuery) имена не портит.
    """
    start = name.find("[")
    base = (name if start < 0 else name[:start]).translate(_MANGLE)

    if start < 0:
        return base

    if "]" not in name[start:]:
        return base + "_" + name[start + 1 :].translate(_MANGLE_TAIL)

    return base + name[start:]


def parse_query(qs: str, native: bool = False) -> Array:
    """
    HeaderUtils::parseQuery: пары через «&», повтор — последний.
    native=True — как parse_str самого PHP, то есть $_GET и
    $request->query() (имена параметров портятся, см. _native_name).
    """
    result: Array = {}

    for pair in qs.split("&"):
        pair = pair.split("\0", 1)[0]
        name, eq, raw = pair.partition("=")
        key = _urldecode(name).split("\0", 1)[0].lstrip(" ")

        if key == "":
            continue

        if native:
            key = _native_name(key)

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
        elif value is not None:
            # null http_build_query пропускает
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


#: Str::trim: \s с /u (Юникод), невидимые символы и trim() по умолчанию
_INVISIBLE = (
    "\u0009\u0020\u00a0\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u200b\u200c\u200d\u200e\u200f\u202f\u205f\u2060\u2061\u2062\u2063"
    "\u2064\u2065\u206a\u206b\u206c\u206d\u206e\u206f\u3000\u2800\u3164"
    "\ufeff\uffa0\U0001d159\U0001d173\U0001d174\U0001d175\U0001d176\U0001d177"
    "\U0001d178\U0001d179\U0001d17a\U000e0020"
)
_STR_TRIM = re.compile(f"^[\\s{_INVISIBLE} \n\r\t\v\0]+|[\\s{_INVISIBLE} \n\r\t\v\0]+$")

#: TrimStrings::$except
_NEVER_TRIM = ("current_password", "password", "password_confirmation")


def text(value: str) -> str:
    """Строка PHP (байты в виде latin-1) → текст UTF-8."""
    return value.encode("latin-1").decode("utf-8", errors="replace")


def str_trim(value: str) -> str:
    """
    Str::trim без списка символов — над строкой PHP (байты в виде
    latin-1). Не UTF-8 — preg_replace с /u отказывает, и Laravel
    берёт обычный trim().
    """
    try:
        decoded = value.encode("latin-1").decode("utf-8")
    except UnicodeDecodeError:
        return value.strip(" \t\n\r\0\x0b")

    return _STR_TRIM.sub("", decoded).encode("utf-8").decode("latin-1")


def laravel_input(qs: str) -> Array:
    """
    $request->query() после TrimStrings и ConvertEmptyStringsToNull:
    строки обрезаны (Str::trim), пустые — null. Этот массив видят
    контроллеры и withQueryString() постраничного вывода.
    """

    def clean(data: Array, prefix: str) -> Array:
        out: Array = {}

        for key, value in data.items():
            name = f"{prefix}{key}"

            if isinstance(value, dict):
                out[key] = clean(value, name + ".")
            elif isinstance(value, str):
                trimmed = value if name in _NEVER_TRIM else str_trim(value)
                out[key] = trimmed if trimmed != "" else None
            else:
                out[key] = value

        return out

    return clean(parse_query(qs, native=True), "")
