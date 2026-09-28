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
from collections.abc import Mapping
from typing import Any

from savdex.web import ui

#: Validator::$implicitRules (из тех, что есть здесь)
IMPLICIT = ("required",)

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


def _passes(rule: str, param: str | None, value: Any) -> bool:  # noqa: ANN401
    if rule == "required":
        if value is _MISSING or value is None:
            return False

        if isinstance(value, str):
            return value.strip() != ""

        return not (isinstance(value, dict | list) and len(value) == 0)

    if rule == "array":
        return isinstance(value, dict | list)

    if rule == "string":
        return isinstance(value, str)

    if rule == "boolean":
        return value in (True, False, 0, 1, "0", "1") and not isinstance(value, float)

    if rule == "in":
        allowed = (param or "").split(",")

        return not isinstance(value, dict | list) and _php_string(value) in allowed

    raise ValueError(f"Правило {rule} не перенесено")


def _php_string(value: Any) -> str:  # noqa: ANN401
    if value is True:
        return "1"

    if value is False or value is None:
        return ""

    return str(value)


def _displayable(attribute: str, implicit: bool) -> str:
    """Validator::getDisplayableAttribute без своих названий полей."""
    if implicit:
        return attribute

    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", attribute).lower()

    return snake.replace("_", " ")


def _message(
    rule: str, attribute: str, implicit: bool, locale: str, messages: Mapping[str, str]
) -> str:
    """FormatsMessages::getMessage и makeReplacements."""
    text = messages.get(f"{attribute}.{rule}") or messages.get(rule)

    if text is None:
        line = ui.group_node(f"validation.{rule}", locale)
        text = line if isinstance(line, str) else f"validation.{rule}"

    name = _displayable(attribute, implicit)

    return (
        text.replace(":attribute", name)
        .replace(":Attribute", name[:1].upper() + name[1:])
        .replace(":ATTRIBUTE", name.upper())
    )


def validate(
    data: Mapping[str, Any],
    rules: Mapping[str, list[str]],
    locale: str,
    messages: Mapping[str, str] | None = None,
) -> dict[str, list[str]]:
    """Ошибки по полям (пусто — ввод годится)."""
    errors: dict[str, list[str]] = {}

    for pattern, field_rules in rules.items():
        for attribute in _expand(data, pattern):
            value = _get(data, attribute.split("."))

            for spec in field_rules:
                rule, _, param = spec.partition(":")

                # Не implicit-правило для отсутствующего поля не проверяется
                # (isValidatable → presentOrRuleIsImplicit); пустая строка
                # после ConvertEmptyStringsToNull — это null, он «есть»
                if rule not in IMPLICIT and not _present(value):
                    continue

                if not _passes(rule, param or None, value):
                    errors.setdefault(attribute, []).append(
                        _message(rule, attribute, "*" in pattern, locale, messages or {})
                    )

                    if rule in IMPLICIT:
                        break

    return errors
