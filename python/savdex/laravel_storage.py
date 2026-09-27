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


def save_image(upload: UploadedFile[bytes], directory: str, *, allow_svg: bool = False) -> str:
    """Сохранить картинку на публичный диск; вернуть путь, как его хранит Laravel."""
    if upload.size is not None and upload.size > MAX_BYTES:
        raise NotAnImageError("Файл больше 8 МБ.")

    head = upload.read(2048)
    upload.seek(0)
    extension = sniff(head, allow_svg=allow_svg)

    relative = f"{directory}/{secrets.token_urlsafe(30)[:40]}.{extension}"
    target = public_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as out:
        for chunk in upload.chunks():
            out.write(chunk)

    return relative
