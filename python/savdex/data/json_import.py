"""
Приём объявлений в JSON — от MEYOS (Ассоциации мебельщиков) и других
партнёров. Формат — docs/meyos.md, «Приём объявлений».

Каждая запись проходит тот же путь, что строка книги Excel
(savdex/data/workbook.py, _Import.row): поиск существующего объявления
(по savdex_id, иначе по заголовку и компании), компания, категория и
город из справочников, тип, цена, переводы; новое — на проверку, если не
отмечено «Сразу опубликовать»; запись, которую не загрузить, — в отчёт,
остальные загружаются дальше.

Фотографии — ссылками: скачиваются по http(s), не больше MAX_PHOTOS на
запись и MAX_PHOTO_BYTES каждая, и только с публичных адресов — ссылка
на внутренний адрес сервера (localhost, 10.0.0.0/8…) не скачивается:
JSON приходит от партнёра, а не пишется своими руками. Картинка, которая
не скачалась или не открылась, — заметка, объявление загружается без неё.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from django.db import connection

from savdex import audit
from savdex.data.workbook import WorkbookResult, _actor, _empty, _Import

log = logging.getLogger(__name__)

#: Фотографий на запись и размер одной
MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 10 * 1024 * 1024

#: Сколько ждать картинку и сколько переадресаций пройти
TIMEOUT = 15.0
MAX_REDIRECTS = 3

#: Языки переводов (кроме русского — он основной)
LOCALES = ("uz", "en", "zh", "tr")

#: Тексты с переводами: поле → поле переводов
TRANSLATED = {
    "title": "title_i18n",
    "description": "description_i18n",
    "delivery_terms": "delivery_terms_i18n",
    "payment_terms": "payment_terms_i18n",
}

_TYPES = {"supply": "Предложение", "demand": "Запрос"}


class UnreadableJsonError(ValueError):
    """Файл — не JSON или в нём нет списка объявлений."""


# ── Разбор ──────────────────────────────────────────────────────────


def records(content: bytes) -> list[Any]:
    """{"items": [...]} или просто [...]."""
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as error:
        raise UnreadableJsonError("Файл не читается как JSON") from error

    items = data.get("items") if isinstance(data, dict) else data

    if not isinstance(items, list):
        raise UnreadableJsonError('В файле нет списка объявлений: ждём {"items": [...]}')

    return items


def _text(value: Any) -> str:  # noqa: ANN401
    if value is None or isinstance(value, dict | list):
        return ""

    if isinstance(value, bool):
        return ""

    return str(value).strip()


def _company(value: Any) -> str:  # noqa: ANN401
    """Строка — название; объект — ИНН (точнее), иначе название."""
    if isinstance(value, Mapping):
        return _text(value.get("tin") or value.get("inn")) or _text(value.get("name"))

    return _text(value)


def _category(value: Any) -> str:  # noqa: ANN401
    """«Раздел → Подраздел», как в книге Excel."""
    if isinstance(value, Mapping):
        name = _text(value.get("name"))
        parent = value.get("parent")
        parent_name = _text(parent.get("name")) if isinstance(parent, Mapping) else ""

        return f"{parent_name} → {name}" if parent_name and name else name

    return _text(value)


def fields_of(item: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Запись JSON → поля строки и переводы, как у листов книги Excel."""
    price = _text(item.get("price"))

    if price == "" and item.get("price_negotiable") is True:
        price = "договорная"

    kind = _text(item.get("type"))
    fields = {
        "id": _text(item.get("savdex_id")),
        "title": _text(item.get("title")),
        "description": _text(item.get("description")),
        "unit": _text(item.get("unit")),
        "delivery_terms": _text(item.get("delivery_terms")),
        "payment_terms": _text(item.get("payment_terms")),
        "company": _company(item.get("company")),
        "category_id": _category(item.get("category")),
        "city_id": _text(item.get("city")),
        "type": _TYPES.get(kind, kind),
        "price": price,
        "currency": _text(item.get("currency")),
        "min_order": _text(item.get("min_order")),
    }
    texts: dict[str, dict[str, str]] = {}

    for name, column in TRANSLATED.items():
        translations = item.get(column)

        if not isinstance(translations, Mapping):
            continue

        for locale in LOCALES:
            value = _text(translations.get(locale))

            if value:
                texts.setdefault(locale, {})[name] = value

    return {k: v for k, v in fields.items() if v != ""}, texts


# ── Фотографии ──────────────────────────────────────────────────────


def _public(host: str) -> bool:
    """Все адреса хоста — публичные: ссылка не ведёт внутрь сервера."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False

    return bool(infos) and all(
        ipaddress.ip_address(str(info[4][0]).split("%", 1)[0]).is_global for info in infos
    )


def download(url: str, into: Path, number: int) -> Path:
    """Картинка по ссылке — во временный файл; не вышло — ValueError с причиной."""
    current = url

    with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(current)

            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise ValueError("ссылка не http(s)")

            if not _public(parts.hostname):
                raise ValueError("адрес не публичный")

            with client.stream("GET", current) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue

                if response.status_code != 200:
                    raise ValueError(f"ответ {response.status_code}")

                path = into / f"photo-{number}"
                size = 0

                with path.open("wb") as file:
                    for chunk in response.iter_bytes():
                        size += len(chunk)

                        if size > MAX_PHOTO_BYTES:
                            raise ValueError("больше 10 МБ")

                        file.write(chunk)

                return path

    raise ValueError("слишком много переадресаций")


def _photos(item: Mapping[str, Any], into: Path) -> tuple[list[Path], list[str]]:
    urls = [u for u in item.get("photos") or [] if isinstance(u, str) and u.strip()]
    files: list[Path] = []
    notes: list[str] = []

    if len(urls) > MAX_PHOTOS:
        notes.append(f"фотографий {len(urls)} — загружены первые {MAX_PHOTOS}")

    for number, url in enumerate(urls[:MAX_PHOTOS], 1):
        try:
            files.append(download(url.strip(), into, number))
        except (ValueError, httpx.HTTPError, OSError) as error:
            reason = str(error) if isinstance(error, ValueError) else "не скачалась"
            notes.append(f"фото {number} ({url.strip()[:80]}) пропущено: {reason}")

    return files, notes


# ── Загрузка ────────────────────────────────────────────────────────


def import_json(
    content: bytes,
    *,
    admin_id: int,
    replace: bool = False,
    ip: str | None = None,
    default_company: int | None = None,
    default_type: str = "supply",
    publish: bool = False,
    source: str = "JSON",
) -> WorkbookResult:
    """
    Записи файла — объявлениями, как строки книги Excel; строка журнала
    «imported» с итогами. Файл не JSON — UnreadableJsonError, ничего не
    загружено.
    """
    items = records(content)
    actor = _actor(admin_id)
    importer = _Import(
        author_id=admin_id,
        replace=replace,
        observer=actor if actor is not None and actor.is_admin else None,
        ip=ip,
        default_company=default_company,
        default_type="demand" if default_type == "demand" else "supply",
        publish=publish,
    )
    result = _empty()

    with tempfile.TemporaryDirectory(prefix="listing-json-") as directory:
        for number, item in enumerate(items, 1):
            if not isinstance(item, Mapping):
                result["rows"] += 1
                result["errors"].append(f"Запись {number}: не объект — пропущена")
                continue

            fields, texts = fields_of(item)
            title = fields.get("title", "")
            where = f"Запись {number}" + (f" «{title[:60]}»" if title else "")
            folder = Path(directory) / str(number)
            folder.mkdir()
            files, notes = _photos(item, folder)
            importer.row(where, fields, texts, files, result, notes)

    audit.record(
        connection,
        action="imported",
        section="listings",
        actor=actor,
        note=(
            f"{source}: записей {len(items)}, создано: {result['created']}, "
            f"обновлено: {result['updated']}, фотографий: {result['photos']}"
        ),
        ip=ip,
    )

    return result
