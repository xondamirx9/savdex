"""Теги для поисковика — копия App\\Support\\Seo."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from savdex.web import locales, ui


def _width(char: str) -> int:
    """mb_strwidth для знака: китайские иероглифы и т. п. — ширина 2."""
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def _limit(text: str, limit: int, end: str) -> str:
    """
    Str::limit: мерит ширину (mb_strwidth), а не число знаков —
    китайский заголовок обрезается вдвое короче русского.
    """
    if sum(_width(c) for c in text) <= limit:
        return text

    kept, width = [], 0

    for char in text:
        width += _width(char)

        if width > limit:
            break

        kept.append(char)

    return "".join(kept).rstrip() + end


class Seo:
    def __init__(self, root: str, current_path: str, locale: str) -> None:
        self.root = root
        #: url()->current() — адрес страницы без префикса и без запроса
        self.current_path = current_path
        self.locale = locale
        self._title = "SAVDEX"
        self.description_text = ""
        self._canonical: str | None = None
        self._image: str | None = None
        self.image_meta: dict[str, Any] | None = None
        self.type = "website"
        self.noindex = False
        self.bare_page = False
        self.schemas: list[dict[str, Any]] = []
        self.organization_details: dict[str, Any] = {}
        self.locales: list[str] | None = None

    def title(self, title: str) -> Seo:
        title = title.strip()
        title = title[:1].upper() + title[1:]
        self._title = _limit(title, 60, "")

        return self

    def description(self, text: str | None) -> Seo:
        if text is None:
            return self

        clean = re.sub(r"<[^>]*>", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        self.description_text = _limit(clean, 155, "…")

        return self

    def canonical(self, url: str) -> Seo:
        self._canonical = url

        return self

    def image(self, url: str | None) -> Seo:
        self._image = url

        return self

    def bare(self) -> Seo:
        self.bare_page = True
        self.noindex = True

        return self

    def schema(self, schema: dict[str, Any]) -> Seo:
        self.schemas.append(schema)

        return self

    # ── Для каркаса ──

    def get_title(self) -> str:
        return self._title if self._title == "SAVDEX" else f"{self._title} · SAVDEX"

    def _path(self) -> str:
        url = self._canonical or (self.root + self.current_path)
        path = url[len(self.root) :] if url.startswith(self.root) else url

        return path or "/"

    def get_canonical(self) -> str:
        locale = self.locale

        if self.locales is not None and locale not in self.locales:
            locale = locales.DEFAULT

        return locales.url(self.root, self._path(), locale)

    def get_alternates(self) -> dict[str, str]:
        path = self._path()
        links = {
            meta["hreflang"]: locales.url(self.root, path, code)
            for code, meta in locales.ALL.items()
            if self.locales is None or code in self.locales
        }
        links["x-default"] = locales.url(self.root, path, locales.DEFAULT)

        return links

    def get_image(self) -> str:
        return self._image or f"{self.root}/og-cover.png"

    def get_json_ld(self) -> str:
        organization = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "SAVDEX",
            "url": self.root,
            "description": ui.t("seo.organization_description", self.locale),
            "areaServed": ["UZ", "KZ", "KG", "TJ"],
            **self.organization_details,
        }
        schemas = [organization, *self.schemas]
        data = (
            schemas[0]
            if len(schemas) == 1
            else {"@context": "https://schema.org", "@graph": schemas}
        )

        return php_json(data, unescaped_unicode=True, hex_tags=True)


def _php_numbers(data: Any) -> Any:  # noqa: ANN401
    """Без JSON_PRESERVE_ZERO_FRACTION целое дробное PHP пишет без «.0»: 4.0 → 4."""
    if isinstance(data, float) and data.is_integer() and abs(data) < 1e15:
        return int(data)

    if isinstance(data, dict):
        return {k: _php_numbers(v) for k, v in data.items()}

    if isinstance(data, list | tuple):
        return [_php_numbers(v) for v in data]

    return data


def php_json(data: Any, *, unescaped_unicode: bool = False, hex_tags: bool = False) -> str:  # noqa: ANN401
    """
    json_encode PHP: «/» экранируется как «\\/»; без флага — и юникод
    (\\uXXXX). JSON_HEX_TAG | AMP | QUOT | APOS — «<», «>», «&», «"», «'»
    внутри строк как \\u003C и т. д.
    """
    text = json.dumps(_php_numbers(data), ensure_ascii=not unescaped_unicode, separators=(",", ":"))

    if hex_tags:
        # Экранировать нужно только внутри строк; вне строк этих знаков
        # в JSON не бывает, кроме кавычек-ограничителей
        def inside(match: re.Match[str]) -> str:
            body = match.group(0)[1:-1]

            for char, code in (("<", "003C"), (">", "003E"), ("&", "0026"), ("'", "0027")):
                body = body.replace(char, f"\\u{code}")

            body = body.replace('\\"', "\\u0022")

            return f'"{body}"'

        text = re.sub(r'"(?:[^"\\]|\\.)*"', inside, text)

    return text.replace("/", "\\/")
