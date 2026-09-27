"""Языки площадки и адреса с префиксом — копия App\\Support\\Locales."""

from __future__ import annotations

DEFAULT = "ru"

#: Locales::ALL
ALL: dict[str, dict[str, str]] = {
    "ru": {"label": "Русский", "short": "RU", "hreflang": "ru"},
    "uz": {"label": "O‘zbekcha", "short": "UZ", "hreflang": "uz"},
    "en": {"label": "English", "short": "EN", "hreflang": "en"},
    "zh": {"label": "中文", "short": "ZH", "hreflang": "zh-Hans"},
    "tr": {"label": "Türkçe", "short": "TR", "hreflang": "tr"},
}

CODES: tuple[str, ...] = tuple(ALL)

#: Locales::prefixed(): у русского префикса нет
PREFIXED: tuple[str, ...] = tuple(code for code in CODES if code != DEFAULT)


def supports(locale: object) -> bool:
    return isinstance(locale, str) and locale in ALL


def prefix(locale: str) -> str:
    return "" if locale == DEFAULT else f"/{locale}"


def split(path: str) -> tuple[str | None, str]:
    """Locales::split: («uz», «/help») из «/uz/help»; без префикса — (None, путь)."""
    path = "/" + path.lstrip("/")

    for code in PREFIXED:
        if path == f"/{code}":
            return code, "/"

        if path.startswith(f"/{code}/"):
            return code, path[len(code) + 1 :]

    return None, path


def url(root: str, path: str, locale: str) -> str:
    """Locales::url: адрес на языке — с префиксом, без хвостового «/»."""
    query = ""

    if "?" in path:
        path, query = path.split("?", 1)
        query = "?" + query

    _, clean = split(path)
    clean = (prefix(locale) + clean).rstrip("/")

    # url('/') у Laravel — корень без «/» в конце
    return root + clean + query


def switch_url(root: str, path: str, locale: str) -> str:
    """
    Locales::switchUrl: на русский — с ?hl=ru, иначе запомненный язык
    вернул бы человека обратно.
    """
    target = url(root, path, locale)

    if locale != DEFAULT:
        return target

    return target + ("&" if "?" in target else "?") + f"hl={DEFAULT}"
