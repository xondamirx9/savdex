"""
Сборка фронта: теги и версия — как Illuminate\\Foundation\\Vite и Inertia.

Страница Django подключает те же файлы сборки, что страница Laravel
(@vite в resources/views/app.blade.php), в том же порядке: предзагрузка
стилей, затем скриптов, затем стили и скрипты. Версия страницы Inertia —
xxh128 от manifest.json, как Inertia\\Middleware::version: при равной
версии переход между страницами Laravel и Django идёт без перезагрузки.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import xxhash
from django.conf import settings

#: @vite(['resources/css/app.css', 'resources/js/app.tsx'])
ENTRIES = ("resources/css/app.css", "resources/js/app.tsx")

BUILD = "build"

_CSS = re.compile(r"\.(css|less|sass|scss|styl|stylus|pcss|postcss)(\?[^.]*)?$")

#: Атрибут, который в Laravel добавляет к стилям и скриптам Livewire
#: (Filament) — его слышит его навигация; для совпадения с Laravel он тот же
TRACK = ' data-navigate-track="reload"'

_cache: dict[str, tuple[float, dict[str, Any], str]] = {}


def _manifest_path() -> Path:
    return Path(settings.LARAVEL_ROOT) / "public" / BUILD / "manifest.json"


def _load() -> tuple[dict[str, Any], str]:
    path = _manifest_path()
    mtime = path.stat().st_mtime
    cached = _cache.get("m")

    if cached is None or cached[0] != mtime:
        raw = path.read_bytes()
        cached = (mtime, json.loads(raw), xxhash.xxh3_128_hexdigest(raw))
        _cache["m"] = cached

    return cached[1], cached[2]


def version() -> str:
    """Inertia\\Middleware::version — xxh128 от manifest.json."""
    return _load()[1]


def _is_css(path: str) -> bool:
    return _CSS.search(path) is not None


def _imports(manifest: dict[str, Any], chunk: dict[str, Any], seen: set[str]) -> list[str]:
    """Vite::resolveImports — рекурсивно, без повторов."""
    found: list[str] = []

    for name in chunk.get("imports", []):
        if name in seen:
            continue

        seen.add(name)
        found.append(name)

        if name in manifest:
            found += _imports(manifest, manifest[name], seen)

    return found


def _tag(url: str) -> str:
    if _is_css(url):
        return f'<link rel="stylesheet" href="{url}"{TRACK} />'

    return f'<script type="module" src="{url}"{TRACK}></script>'


def _preload(url: str) -> str:
    if _is_css(url):
        return f'<link rel="preload" as="style" href="{url}" />'

    return f'<link rel="modulepreload" as="script" href="{url}" />'


def assets(root: str) -> tuple[str, list[str]]:
    """
    Теги для <head> и предзагружаемые адреса (для заголовка Link) —
    порядок Vite::__invoke.
    """
    manifest, _ = _load()
    base = f"{root}/{BUILD}/"
    preloads: list[str] = []
    tags: list[str] = []

    def css_of(chunk: dict[str, Any]) -> None:
        for css in chunk.get("css", []):
            preloads.append(base + css)
            tags.append(_tag(base + css))

    for entry in ENTRIES:
        chunk = manifest[entry]
        preloads.append(base + chunk["file"])

        for name in _imports(manifest, chunk, set()):
            preloads.append(base + manifest[name]["file"])
            css_of(manifest[name])

        tags.append(_tag(base + chunk["file"]))
        css_of(chunk)

    unique_tags = list(dict.fromkeys(tags))
    styles = [t for t in unique_tags if t.startswith("<link")]
    scripts = [t for t in unique_tags if not t.startswith("<link")]
    # Стили предзагружаются первыми — sortByDesc(isCssPath), порядок
    # внутри групп сохраняется
    urls = list(dict.fromkeys(preloads))
    urls = [u for u in urls if _is_css(u)] + [u for u in urls if not _is_css(u)]

    return "".join(_preload(u) for u in urls) + "".join(styles) + "".join(scripts), urls


def link_header(urls: list[str]) -> str:
    """AddLinkHeadersForPreloadedAssets: тот же список заголовком Link."""
    return ", ".join(
        f'<{u}>; rel="preload"; as="style"'
        if _is_css(u)
        else f'<{u}>; rel="modulepreload"; as="script"'
        for u in urls
    )
