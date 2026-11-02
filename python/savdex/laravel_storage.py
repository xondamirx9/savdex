"""
Публичный диск Laravel — storage/app/public, на сайте /storage/…

Файлы, которые показывает витрина (логотип, фон первого экрана),
лежат там, куда их кладёт Laravel: витрина строит адрес через свой
публичный диск (Storage::disk('public')->url()). На боевом сервере
storage/app/public — ссылка на постоянный диск Render, и файл,
записанный Django, переживает деплой так же, как записанный Laravel.

Имя файла — случайное, как у Filament: 40 знаков и расширение.
Расширение берётся не из имени, а из содержимого файла.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

#: Как у Filament: до 8 МБ
MAX_BYTES = 8 * 1024 * 1024


class NotAnImageError(ValueError):
    """Файл не картинка из разрешённых."""


def public_root() -> Path:
    return Path(settings.LARAVEL_ROOT) / "storage/app/public"


def private_root() -> Path:
    """Диск local у Laravel — storage/app/private: документы компаний."""
    return Path(settings.LARAVEL_ROOT) / "storage/app/private"


def sniff(head: bytes, *, allow_svg: bool) -> str:
    """Расширение по первым байтам файла; не картинка — исключение."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"

    text = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()

    if allow_svg and (text.startswith(b"<svg") or (text.startswith(b"<?xml") and b"<svg" in text)):
        return "svg"

    raise NotAnImageError(
        "Нужна картинка PNG, JPEG или WebP" + (" либо SVG." if allow_svg else ".")
    )


#: Элементы SVG, которые выполняют код или встраивают чужое
_SVG_FORBIDDEN = frozenset(
    {"script", "foreignobject", "iframe", "embed", "object", "handler", "listener"}
)

#: Вшитая растровая картинка — можно; вложенный SVG — нет
_RASTER = re.compile(r"data:image/(png|jpe?g|gif|webp)[;,]")

#: Объявленная кодировка в заголовке <?xml … encoding="…"?>
_DECLARED = re.compile(r"﻿?\s*<\?xml[^>]*encoding=[\"']([^\"']+)")


def check_svg(data: bytes) -> None:
    """
    SVG — без скриптов, обработчиков событий и внешних ссылок; иначе
    NotAnImageError. Файл хранится как есть и с того же адреса, что и
    сайт: /storage/ отдаётся с CSP sandbox (docker/apache-python.conf), но
    второй замок — не пускать такой файл вовсе. DOCTYPE и сущности — тоже
    отказ: «миллиард смешков» и чтение файлов сервера разбором XML.
    """
    import xml.etree.ElementTree as ET

    refused = NotAnImageError("SVG со скриптами или внешними ссылками не принимается.")

    # Только UTF-8: в другой кодировке (UTF-16) DOCTYPE не найти поиском по байтам
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise NotAnImageError("SVG — только в кодировке UTF-8.") from None

    declared = _DECLARED.match(text)

    if declared and declared.group(1).lower().replace("_", "-") not in ("utf-8", "utf8"):
        raise NotAnImageError("SVG — только в кодировке UTF-8.")

    lowered = text.lower()

    if "<!doctype" in lowered or "<!entity" in lowered:
        raise refused

    def external_url(value: str) -> bool:
        """url(…) не на свой элемент (#id) — внешняя ссылка."""
        return "url(" in value.replace("url(#", "").replace("url('#", "").replace('url("#', "")

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise NotAnImageError("SVG не читается — сохраните его заново.") from None

    for node in root.iter():
        if not isinstance(node.tag, str) or node.tag.rsplit("}", 1)[-1].lower() in _SVG_FORBIDDEN:
            raise refused

        for name, value in node.attrib.items():
            local = name.rsplit("}", 1)[-1].lower()
            flat = "".join(value.split()).lower()

            if local.startswith("on") or "javascript:" in flat or "vbscript:" in flat:
                raise refused

            # Своё (#id) или вшитая растровая картинка; вложенный SVG — нет
            if local == "href" and not (flat.startswith("#") or _RASTER.match(flat)):
                raise refused

            if external_url(flat):
                raise refused

        body = "".join((node.text or "").split()).lower()

        if "@import" in body or "javascript:" in body or external_url(body):
            raise refused


def save_image(upload: UploadedFile[bytes], directory: str, *, allow_svg: bool = False) -> str:
    """Сохранить картинку на публичный диск; вернуть путь, как его хранит Laravel."""
    if upload.size is not None and upload.size > MAX_BYTES:
        raise NotAnImageError("Файл больше 8 МБ.")

    head = upload.read(2048)
    upload.seek(0)
    extension = sniff(head, allow_svg=allow_svg)

    if extension == "svg":
        # Целиком: до 8 МБ, проверено выше
        check_svg(upload.read())
        upload.seek(0)

    relative = f"{directory}/{secrets.token_urlsafe(30)[:40]}.{extension}"
    target = public_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as out:
        for chunk in upload.chunks():
            out.write(chunk)

    return relative
