"""
Проверка ввода форм — как Validator у Laravel, для правил, которые
встречаются в перенесённых формах.

Правила и порядок — как у Laravel: звёздочка раскрывается по ключам
ввода на месте правила; правила поля идут подряд, провал «неявного»
(required) останавливает поле; ошибки — по полям в порядке правил.

Тексты — __('validation.<правило>'). Словаря validation в проекте нет,
поэтому по-английски Laravel берёт текст из самого фреймворка, а на
остальных языках отдаёт сам ключ («validation.required») — Django
повторяет и то и другое (словарь выгружает savdex:export-ui). Свои
тексты формы передаёт в messages: «поле.правило» или «правило».
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from savdex.web import ui


@dataclass(frozen=True)
class Check:
    """Правило-объект (Rule::unique и т. п.): имя для текста ошибки и проверка."""

    name: str
    passes: Callable[[Any], bool]


#: Validator::$implicitRules (из тех, что есть здесь)
IMPLICIT = ("required", "required_with")

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

    if rule == "lowercase":
        # Str::lower($value) === $value
        return isinstance(value, str) and value.lower() == value

    if rule == "file":
        return _is_file(value)

    if rule == "mimes":
        # validateMimes: расширение по содержимому; jpg и jpeg — одно и то же
        extensions = set((param or "").split(","))

        if extensions & {"jpg", "jpeg"}:
            extensions |= {"jpg", "jpeg"}

        return _is_file(value) and _guess_extension(value) in extensions

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

        return is_valid(value)

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

    return None


def _is_file(value: Any) -> bool:  # noqa: ANN401
    """Загруженный файл (UploadedFile у Laravel)."""
    from django.core.files.uploadedfile import UploadedFile

    return isinstance(value, UploadedFile)


def _guess_extension(upload: Any) -> str | None:  # noqa: ANN401
    """UploadedFile::guessExtension: по первым байтам (finfo), не по имени."""
    head = upload.read(64)
    upload.seek(0)

    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"

    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"

    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"

    if head.startswith(b"%PDF-"):
        return "pdf"

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

    return str(value)


def _kind(rules: Sequence[str | Check], value: Any) -> str:  # noqa: ANN401
    """Validator::getAttributeType: numeric/integer в правилах, массив, иначе строка."""
    names = [r.partition(":")[0] for r in rules if isinstance(r, str)]

    if any(r in ("numeric", "integer", "decimal") for r in names):
        return "numeric"

    if isinstance(value, dict | list):
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
    text = messages.get(f"{attribute}.{rule}") or messages.get(rule)

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
