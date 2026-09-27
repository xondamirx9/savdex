"""
Текст из базы на языке посетителя — копии App\\Support\\ContentTranslation,
App\\Support\\PageBody и HasOwnTranslations.

- ContentTranslation: готовый машинный перевод — если есть; нет —
  оригинал, а текст встаёт в очередь (переводит задача Laravel
  translations:fill). Русская версия — всегда оригинал.
- PageBody: разметка текста страницы (подзаголовки, шаги, список,
  предупреждение) — блоками.
- own/localized: свой текст языка из *_i18n, иначе машинный перевод.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from typing import Any

from django.db import connection

from savdex.guards import allowed_writes

#: MachineTranslator::TARGETS
TARGETS = ("en", "uz", "tr", "zh")

#: preg_match('/\p{L}{2,}/u') — две буквы подряд, любой азбуки
_LETTERS = re.compile(r"[^\W\d_]{2,}")


class Translations:
    """ContentTranslation на время одного запроса: с памятью, как у Laravel."""

    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.memo: dict[str, str | None] = {}

    def _translatable(self, text: str | None) -> bool:
        return (
            self.locale != "ru"
            and self.locale in TARGETS
            and (text or "").strip() != ""
            and _LETTERS.search(text or "") is not None
        )

    def prefetch(self, texts: Iterable[str | None]) -> None:
        wanted = {}

        for text in texts:
            if self._translatable(text):
                source = (text or "").strip()
                digest = hashlib.sha1(source.encode()).hexdigest()

                if digest not in self.memo:
                    wanted[digest] = source

        if not wanted:
            return

        with connection.cursor() as cursor:
            cursor.execute(
                "select hash, translation from content_translations "
                "where locale = %s and hash = any(%s)",
                [self.locale, list(wanted)],
            )

            for digest, translation in cursor.fetchall():
                self.memo[digest] = translation

    def text(self, text: str | None) -> str | None:
        if not self._translatable(text):
            return text

        source = (text or "").strip()
        digest = hashlib.sha1(source.encode()).hexdigest()

        if digest not in self.memo:
            self.memo[digest] = self._lookup(digest, source)

        return self.memo[digest] or text

    def _lookup(self, digest: str, source: str) -> str | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "select translation from content_translations where hash = %s and locale = %s",
                [digest, self.locale],
            )
            row = cursor.fetchone()

            if row is not None:
                return row[0]  # type: ignore[no-any-return]

            # Перевода ещё нет — в очередь, как insertOrIgnore у Laravel
            with allowed_writes("content_translations"):
                cursor.execute(
                    "insert into content_translations (hash, locale, source, attempts, "
                    "created_at, updated_at) values (%s, %s, %s, 0, now(), now()) "
                    "on conflict do nothing",
                    [digest, self.locale, source],
                )

        return None


# ── Свои поля языков ────────────────────────────────────────────────


def own(row: Any, field: str, locale: str) -> str:  # noqa: ANN401
    """HasOwnTranslations::own: русский — основной столбец, иначе *_i18n."""
    if locale == "ru":
        return str(getattr(row, field) or "").strip()

    i18n = getattr(row, f"{field}_i18n", None)

    return str((i18n or {}).get(locale) or "").strip() if isinstance(i18n, dict) else ""


def localized(row: Any, field: str, translations: Translations) -> str:  # noqa: ANN401
    """HasOwnTranslations::localized: свой текст, иначе машинный перевод русского."""
    value = own(row, field, translations.locale)

    if value or translations.locale == "ru":
        return value

    return str(translations.text(getattr(row, field)) or "").strip()


# ── Разметка текста страницы ────────────────────────────────────────

#: \R\s*\R и \R — как в PageBody (\R: \r\n, \n или \r)
_PARAGRAPHS = re.compile(r"(?:\r\n|\n|\r)\s*(?:\r\n|\n|\r)")
_LINES = re.compile(r"\r\n|\n|\r")
_STEP = re.compile(r"^\d{1,2}[.)]\s")
_STEP_BODY = re.compile(r"^\d{1,2}[.)]\s+(.*)$")


def blocks(text: str | None) -> list[dict[str, Any]]:
    """PageBody::blocks."""
    result = []

    for chunk in _PARAGRAPHS.split((text or "").strip()):
        lines = [line.strip() for line in _LINES.split(chunk.strip())]
        lines = [line for line in lines if line]

        if lines:
            result.append(_block(lines))

    return result


def _join(lines: list[str]) -> str:
    return " ".join(lines).strip()


def _block(lines: list[str]) -> dict[str, Any]:
    first = lines[0]

    if first.startswith("## "):
        return {"type": "heading", "text": _join([first[3:], *lines[1:]])}

    if first.startswith("! "):
        return {"type": "note", "title": first[2:].strip(), "text": _join(lines[1:])}

    if _STEP.match(first):
        steps: list[dict[str, str]] = []

        for line in lines:
            match = _STEP_BODY.match(line)

            if match:
                steps.append({"title": match.group(1).strip(), "hint": ""})
            else:
                steps[-1]["hint"] = (steps[-1]["hint"] + " " + line).strip()

        return {"type": "steps", "items": steps}

    if first.startswith("- "):
        items: list[str] = []

        for line in lines:
            if line.startswith("- ") or not items:
                items.append(re.sub(r"^-\s", "", line).strip())
            else:
                items[-1] += " " + line

        return {"type": "list", "items": items}

    return {"type": "text", "text": _join(lines)}


def strings(value: Any) -> list[str]:  # noqa: ANN401
    """PageBody::strings: все строки блоков, кроме «type»."""
    found: list[str] = []

    def walk(node: Any, key: object = None) -> None:  # noqa: ANN401
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and key != "type" and node != "":
            found.append(node)

    walk(value)

    return found


def map_strings(value: Any, translate: Callable[[str], str], key: object = None) -> Any:  # noqa: ANN401
    """PageBody::map: каждая строка через translate, разметка не трогается."""
    if isinstance(value, dict):
        return {k: map_strings(v, translate, k) for k, v in value.items()}

    if isinstance(value, list):
        return [map_strings(v, translate) for v in value]

    if isinstance(value, str) and key != "type" and value != "":
        return translate(value)

    return value
