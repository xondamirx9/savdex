"""
Проверка ввода форм — как Validator у Laravel, для правил, которые
встречаются в перенесённых формах.

Правила и порядок — как у Laravel: звёздочка раскрывается по ключам
ввода на месте правила; правила поля идут подряд, провал «неявного»
(required) останавливает поле; ошибки — по полям в порядке правил.

Тексты — __('validation.<правило>'). Словаря validation в проекте нет,
поэтому по-английски Laravel берёт текст из самого фреймворка, а на
остальных языках отдаёт сам ключ («validation.required») — Django
повторяет и то и другое (словарь — savdex/locale/ui, выгрузка savdex:export-ui). Свои
тексты формы передаёт в messages: «поле.правило» или «правило».
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from savdex.web import ui


@dataclass(frozen=True)
class Check:
    """Правило-объект (Rule::unique и т. п.): имя для текста ошибки и проверка."""

    name: str
    passes: Callable[[Any], bool]


#: Validator::$implicitRules (из тех, что есть здесь)
IMPLICIT = ("required", "required_with", "required_if", "accepted")

_MISSING = object()


def _get(data: Any, path: list[str]) -> Any:  # noqa: ANN401
    node = data

    for part in path:
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return _MISSING

    return node


def _keys(node: Any) -> list[str]:  # noqa: ANN401
    if isinstance(node, dict):
        return [str(k) for k in node]

    if isinstance(node, list):
        return [str(i) for i in range(len(node))]

    return []


def _expand(data: Mapping[str, Any], attribute: str) -> list[str]:
    """ValidationRuleParser::explodeWildcardRules: «a.*.b» по ключам ввода."""
    if "*" not in attribute:
        return [attribute]

    head, _, tail = attribute.partition(".*")
    found = []

    for key in _keys(_get(data, head.split("."))):
        found += _expand(data, f"{head}.{key}{tail}")

    return found


def _present(value: Any) -> bool:  # noqa: ANN401
    return value is not _MISSING


def _passes(rule: str, param: str | None, value: Any, numeric: bool = False) -> bool:  # noqa: ANN401
    if rule == "required":
        if value is _MISSING or value is None:
            return False

        if _is_file(value):
            return True

        if isinstance(value, str):
            return value.strip() != ""

        return not (isinstance(value, dict | list) and len(value) == 0)

    if rule == "digits":
        # validateDigits: только цифры и ровно столько знаков
        text = _php_string(value) if isinstance(value, str | int | float) else None

        return (
            text is not None and text.isascii() and text.isdigit() and len(text) == int(param or 0)
        )

    if rule == "accepted":
        # validateAccepted: присутствует и одно из «да»
        return _passes("required", None, value) and value in ("yes", "on", "1", 1, True, "true")

    if rule == "numeric":
        # is_numeric: число или числовая строка
        if isinstance(value, bool):
            return False

        return isinstance(value, int | float) or (isinstance(value, str) and _is_numeric(value))

    if rule == "lowercase":
        # Str::lower($value) === $value
        return isinstance(value, str) and value.lower() == value

    if rule == "file":
        return _is_file(value)

    if rule == "date":
        # validateDate: strtotime понял и date_parse дал настоящий день (checkdate)
        parsed = _strtotime(value)

        return parsed is not None and parsed[1]

    if rule == "after":
        # compareDates: strtotime значения больше strtotime параметра
        parsed = _strtotime(value)
        bound = _strtotime(param)

        return parsed is not None and bound is not None and parsed[0] > bound[0]

    if rule == "mimes":
        # validateMimes: расширение по содержимому; jpg и jpeg — одно и то же
        extensions = set((param or "").split(","))

        if not _is_file(value) or _blocks_php(value, extensions):
            return False

        if extensions & {"jpg", "jpeg"}:
            extensions |= {"jpg", "jpeg"}

        return _guess_extension(value) in extensions

    if rule == "array":
        return isinstance(value, dict | list)

    if rule == "string":
        return isinstance(value, str)

    if rule == "boolean":
        return value in (True, False, 0, 1, "0", "1") and not isinstance(value, float)

    if rule == "integer":
        # filter_var(FILTER_VALIDATE_INT): целое, строка из цифр без
        # ведущих нулей (пробелы по краям допустимы), true — это 1
        if isinstance(value, bool):
            return value is True

        if isinstance(value, int):
            return True

        if isinstance(value, float):
            return value.is_integer()

        return (
            isinstance(value, str) and re.fullmatch(r"\s*[+-]?(0|[1-9]\d*)\s*", value) is not None
        )

    if rule == "between":
        size = _size(value, numeric)
        low, _, high = (param or "").partition(",")

        return size is not None and float(low) <= size <= float(high)

    if rule in ("min", "max"):
        size = _size(value, numeric)

        if size is None:
            return False

        return size >= float(param or 0) if rule == "min" else size <= float(param or 0)

    if rule == "regex":
        # validateRegex: только строки и числа, preg_match > 0
        if not isinstance(value, str | int | float) or isinstance(value, bool):
            return False

        return _php_regex(param or "").search(_php_string(value)) is not None

    if rule == "email":
        # validateEmail: без параметров и с rfc — RFCValidation
        from savdex.web.email_rfc import is_valid

        # «rfc,strict» — NoRFCWarningsValidation: и без предупреждений разбора
        return is_valid(value, strict="strict" in (param or "").split(","))

    if rule == "url":
        from savdex.web.url_rule import is_url

        return is_url(value, tuple(param.split(",")) if param else ())

    if rule == "in":
        allowed = (param or "").split(",")

        return not isinstance(value, dict | list) and _php_string(value) in allowed

    raise ValueError(f"Правило {rule} не перенесено")


def _php_regex(pattern: str) -> re.Pattern[str]:
    """Шаблон preg_match («/…/флаги»): без u — только ASCII в \\d, \\s, \\w."""
    delimiter = pattern[:1]
    closing = {"(": ")", "[": "]", "{": "}", "<": ">"}.get(delimiter, delimiter)
    end = pattern.rindex(closing)
    flags = 0 if "u" in pattern[end + 1 :] else re.ASCII

    for flag, value in (("i", re.I), ("m", re.M), ("s", re.S), ("x", re.X)):
        if flag in pattern[end + 1 :]:
            flags |= value

    return re.compile(pattern[1:end], flags)


def _size(value: Any, numeric: bool = False) -> float | None:  # noqa: ANN401
    """
    Validator::getSize: число при числовом правиле (numeric, integer), массив —
    число элементов, иначе длина строки.
    """
    if _is_file(value):
        # Размер файла — в килобайтах
        return float(value.size or 0) / 1024

    if numeric and not isinstance(value, bool):
        if isinstance(value, int | float):
            return float(value)

        if isinstance(value, str) and _is_numeric(value):
            return float(value)

    if isinstance(value, dict | list):
        return float(len(value))

    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(len(str(value)))

    if isinstance(value, str):
        return float(len(value))

    # mb_strlen($value ?? ''): null — ноль, true — «1», false — пусто
    if value is None or isinstance(value, bool):
        return float(len("1" if value is True else ""))

    return None


def _is_file(value: Any) -> bool:  # noqa: ANN401
    """Загруженный файл (UploadedFile у Laravel)."""
    from django.core.files.uploadedfile import UploadedFile

    return isinstance(value, UploadedFile)


def _required_if(data: Mapping[str, Any], param: str, value: Any) -> bool:  # noqa: ANN401
    """validateRequiredIf: поле нужно, когда другое поле равно одному из значений."""
    other, *values = param.split(",")
    current = _get(data, other.split("."))

    # Arr::has: условия нет во вводе — правило молчит
    if current is _MISSING:
        return True

    # parseDependentRuleParameters: для булева и null — строгие true/false/null
    if isinstance(current, bool) or current is None:
        choices = [{"true": True, "false": False, "null": None}.get(v, v) for v in values]
        hit = any(c is current for c in choices)
    else:
        hit = any(_php_string(current) == v for v in values)

    return not hit or _passes("required", None, value)


def _gte(
    data: Mapping[str, Any],
    field_rules: Sequence[str | Check],
    param: str,
    value: Any,  # noqa: ANN401
) -> bool:
    """validateGte с полем-сравнением: оба числа — сравнение чисел, иначе — нет."""
    other = _get(data, param.split("."))
    compared = None if other is _MISSING else other

    def number(v: Any) -> bool:  # noqa: ANN401
        return not isinstance(v, bool) and (
            isinstance(v, int | float) or (isinstance(v, str) and _is_numeric(v))
        )

    if _is_numeric(param):
        return compared is None and number(value) and float(str(value)) >= float(param)

    if _kind(field_rules, value) == "numeric" and number(value) and number(compared):
        return float(str(value).strip()) >= float(str(compared).strip())

    return False


def _guess_extension(upload: Any) -> str | None:  # noqa: ANN401
    """UploadedFile::guessExtension: по содержимому (finfo), не по имени."""
    from savdex.web.filetype import guess_extension

    data = upload.read()
    upload.seek(0)

    return guess_extension(data)


#: ValidatesAttributes::shouldBlockPhpUpload
_PHP_EXTENSIONS = ("php", "php3", "php4", "php5", "php7", "php8", "phtml", "phar")


def _blocks_php(upload: Any, extensions: set[str]) -> bool:  # noqa: ANN401
    """Файл с расширением PHP в имени от клиента отвергается, если php не разрешён явно."""
    if "php" in extensions:
        return False

    name = str(getattr(upload, "name", "") or "").replace("\\", "/").rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[1] if "." in name else ""

    return extension.lower().strip() in _PHP_EXTENSIONS


#: Даты, которые понимает strtotime и где date_parse видит год, месяц и
#: день: Y-m-d и Y/m/d, d.m.Y и d-m-Y, m/d/Y (американский), со временем
_DATES = (
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), ("y", "m", "d")),
    (re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"), ("y", "m", "d")),
    (re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})"), ("d", "m", "y")),
    (re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})"), ("d", "m", "y")),
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), ("m", "d", "y")),
    (re.compile(r"(\d{4})(\d{2})(\d{2})"), ("y", "m", "d")),
)
_TIME = re.compile(r"(?:[t ](\d{1,2}):(\d{2})(?::(\d{2}))?)?", re.ASCII)


def _strtotime(value: Any) -> tuple[datetime, bool] | None:  # noqa: ANN401
    """
    strtotime (часовой пояс приложения — UTC): момент и настоящий ли это
    день (checkdate). День сверх месяца strtotime переносит дальше
    («30 февраля» — 2 марта), checkdate такой день отвергает. Слова
    today, tomorrow и now — как у PHP, без года-месяца-дня. Прочие
    вольности strtotime (названия месяцев, часовые пояса буквой) не
    поддержаны: такая дата не проходит ни date, ни after.
    """
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None

    text = str(value).strip().lower()
    now = datetime.now(UTC).replace(tzinfo=None)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    words = {"today": midnight, "midnight": midnight, "now": now}

    if text in words:
        return words[text], False

    if text == "tomorrow":
        return midnight + timedelta(days=1), False

    if text == "yesterday":
        return midnight - timedelta(days=1), False

    for pattern, order in _DATES:
        match = pattern.match(text)

        if match is None:
            continue

        rest = _TIME.fullmatch(text[match.end() :])

        if rest is None:
            continue

        parts = dict(zip(order, (int(g) for g in match.groups()), strict=True))
        hour, minute, second = (int(g) if g else 0 for g in rest.groups())

        if parts["m"] > 12 or parts["d"] > 31 or hour > 23 or minute > 59:
            return None

        # Месяц 0 strtotime понимает как декабрь прошлого года
        year, month = (parts["y"] - 1, 12) if parts["m"] == 0 else (parts["y"], parts["m"])
        base = datetime(year, month, 1, hour, minute, second or 0)
        real = parts["m"] > 0 and 1 <= parts["d"] <= calendar.monthrange(year, month)[1]

        return base + timedelta(days=parts["d"] - 1), real

    return None


def _is_numeric(value: str) -> bool:
    """is_numeric: число с пробелами в начале (и в конце — с PHP 8), без пустой строки."""
    return (
        re.fullmatch(r"\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*", value, re.ASCII) is not None
    )


def _php_string(value: Any) -> str:  # noqa: ANN401
    if value is True:
        return "1"

    if value is False or value is None:
        return ""

    if isinstance(value, float):
        return php_float(value)

    return str(value)


def php_float(value: float) -> str:
    """(string) дробного в PHP 8: 14 значащих цифр (precision), 123456.0 — «123456»."""
    if value != value:
        return "NAN"

    if value in (float("inf"), float("-inf")):
        return "INF" if value > 0 else "-INF"

    text = f"{value:.14G}"

    if "E" in text:
        mantissa, exponent = text.split("E")
        mantissa = mantissa if "." in mantissa else mantissa + ".0"
        text = f"{mantissa}E{'-' if exponent.startswith('-') else '+'}{exponent[1:].lstrip('0')}"

    return text


def _kind(rules: Sequence[str | Check], value: Any) -> str:  # noqa: ANN401
    """
    Validator::getAttributeType: вид — по правилам (numeric/integer, array/list),
    не по значению: массив без правила array — «строка», файл — «файл».
    """
    names = [r.partition(":")[0] for r in rules if isinstance(r, str)]

    if any(r in ("numeric", "integer", "decimal") for r in names):
        return "numeric"

    if any(r in ("array", "list") for r in names):
        return "array"

    if _is_file(value):
        return "file"

    return "string"


def _displayable(attribute: str, implicit: bool) -> str:
    """Validator::getDisplayableAttribute без своих названий полей."""
    if implicit:
        return attribute

    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", attribute).lower()

    return snake.replace("_", " ")


def _wildcard_message(messages: Mapping[str, str], key: str) -> str | None:
    """getFromLocalArray: свой текст по образцу со «*» (Str::is)."""
    for pattern, text in messages.items():
        if "*" in pattern and re.fullmatch(
            ".*".join(re.escape(p) for p in pattern.split("*")), key
        ):
            return text

    return None


def _message(
    rule: str,
    attribute: str,
    implicit: bool,
    locale: str,
    messages: Mapping[str, str],
    kind: str = "string",
    param: str | None = None,
) -> str:
    """FormatsMessages::getMessage и makeReplacements."""
    text = messages.get(f"{attribute}.{rule}") or _wildcard_message(messages, f"{attribute}.{rule}")
    text = text or messages.get(rule)

    if text is None:
        # Правила размера — текст по виду значения (validation.min.array)
        sized = rule in ("min", "max", "between")
        key = f"validation.{rule}" + (f".{kind}" if sized else "")
        line = ui.group_node(key, locale)
        text = line if isinstance(line, str) else key

    name = _displayable(attribute, implicit)

    if param is not None and rule in ("min", "max"):
        text = text.replace(f":{rule}", param)

    if param is not None and rule == "between":
        low, _, high = param.partition(",")
        text = text.replace(":min", low).replace(":max", high)

    if param is not None and rule == "required_with":
        # replaceRequiredWith: поля-условия — как их показывает getDisplayableAttribute
        names = [_displayable(p, "." in p and p.split(".")[1].isdigit()) for p in param.split(",")]
        text = text.replace(":values", " / ".join(names))

    if param is not None and rule == "required_if":
        # replaceRequiredIf: :other — имя поля-условия, :value — его значение
        other, _, _ = param.partition(",")
        text = text.replace(":other", _displayable(other, False))

    if param is not None and rule == "gte":
        # replaceGte: :value — значение поля-сравнения
        text = text.replace(":value", param)

    if param is not None and rule == "after":
        # replaceAfter: дата-параметр как есть («today»)
        text = text.replace(":date", param)

    return (
        text.replace(":attribute", name)
        .replace(":Attribute", name[:1].upper() + name[1:])
        .replace(":ATTRIBUTE", name.upper())
    )


def _fill_asterisks(pattern: str, attribute: str, param: str) -> str:
    """Validator::replaceAsterisksInParameters: «*» каждого условия — ключами поля."""
    keys = [
        part
        for part, mask in zip(attribute.split("."), pattern.split("."), strict=False)
        if mask == "*"
    ]
    filled = []

    for item in param.split(","):
        for key in keys:
            item = item.replace("*", key, 1)

        filled.append(item)

    return ",".join(filled)


def validated(
    data: Mapping[str, Any], rules: Mapping[str, Sequence[str | Check]]
) -> dict[str, Any]:
    """
    Validator::validated() с excludeUnvalidatedArrayKeys: поле-массив, у
    которого есть правила вложенных ключей, берётся по этим ключам —
    лишние ключи ввода отбрасываются; отсутствующее поле пропускается.
    """
    expanded: list[tuple[str, Sequence[str | Check]]] = []
    wildcard: list[tuple[str, Sequence[str | Check]]] = []

    for pattern, field_rules in rules.items():
        if "*" in pattern:
            wildcard += [(a, field_rules) for a in _expand(data, pattern)]
        else:
            expanded.append((pattern, field_rules))

    keys = [k for k, _ in expanded + wildcard]
    result: dict[str, Any] = {}

    for key, field_rules in expanded + wildcard:
        value = _get(data, key.split("."))

        if value is _MISSING:
            continue

        nested = any(k.startswith(key + ".") for k in keys)

        if "array" in field_rules and value is not None and nested:
            continue

        node = result
        parts = key.split(".")

        for part in parts[:-1]:
            child = node.get(part)

            if not isinstance(child, dict):
                child = node[part] = {}

            node = child

        node[parts[-1]] = value

    return {k: _lists(v) for k, v in result.items()}


def _lists(node: Any) -> Any:  # noqa: ANN401
    """Массив PHP с ключами 0…n-1 по порядку — список (json_encode даст [])."""
    if not isinstance(node, dict):
        return node

    items = {k: _lists(v) for k, v in node.items()}

    if items and list(items) == [str(i) for i in range(len(items))]:
        return list(items.values())

    return items


def validate(
    data: Mapping[str, Any],
    rules: Mapping[str, Sequence[str | Check]],
    locale: str,
    messages: Mapping[str, str] | None = None,
) -> dict[str, list[str]]:
    """Ошибки по полям (пусто — ввод годится)."""
    errors: dict[str, list[str]] = {}

    # ValidationRuleParser::explodeRules: поля со звёздочкой раскрываются
    # в конец списка — их ошибки идут после ошибок обычных полей
    order = [(p, r) for p, r in rules.items() if "*" not in p] + [
        (p, r) for p, r in rules.items() if "*" in p
    ]

    for pattern, field_rules in order:
        for attribute in _expand(data, pattern):
            value = _get(data, attribute.split("."))
            nullable = "nullable" in field_rules

            for spec in field_rules:
                if isinstance(spec, Check):
                    rule, param = spec.name, ""
                else:
                    rule, _, param = spec.partition(":")

                # nullable — не правило, а пропуск остальных для null
                # (isNotNullIfMarkedAsNullable)
                if rule == "nullable" or (nullable and value is None and rule not in IMPLICIT):
                    continue

                # Не implicit-правило для отсутствующего поля не проверяется
                # (isValidatable → presentOrRuleIsImplicit); пустая строка
                # после ConvertEmptyStringsToNull — это null, он «есть»
                if rule not in IMPLICIT and not _present(value):
                    continue

                # hasNotFailedPreviousRuleIfPresenceRule: unique и exists —
                # только пока у поля нет ошибок
                if rule in ("unique", "exists") and attribute in errors:
                    continue

                if rule == "required_with":
                    # Звёздочки условий — индексами из самого поля
                    param = _fill_asterisks(pattern, attribute, param)
                    others = [_get(data, p.split(".")) for p in param.split(",")]
                    passed = all(not _passes("required", None, o) for o in others) or _passes(
                        "required", None, value
                    )
                elif rule == "required_if":
                    passed = _required_if(data, param, value)
                elif rule == "gte":
                    passed = _gte(data, field_rules, param, value)
                elif rule == "confirmed":
                    # validateConfirmed: строгое равенство с полем <имя>_confirmation
                    other = _get(data, (attribute + "_confirmation").split("."))
                    passed = other is not _MISSING and type(other) is type(value) and other == value
                else:
                    passed = (
                        spec.passes(value)
                        if isinstance(spec, Check)
                        else _passes(
                            rule, param or None, value, _kind(field_rules, value) == "numeric"
                        )
                    )

                if not passed:
                    text = _message(
                        rule,
                        attribute,
                        "*" in pattern,
                        locale,
                        messages or {},
                        _kind(field_rules, value),
                        param or None,
                    )
                    found = errors.setdefault(attribute, [])

                    # MessageBag::add: одинаковый текст у поля — один раз
                    if text not in found:
                        found.append(text)

                    if rule in IMPLICIT:
                        break

    return errors
