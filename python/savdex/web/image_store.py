"""
Картинки на публичном диске — копия App\\Support\\ImageStore (GD) на Pillow.

Размеры читаются из заголовка и проверяются до распаковки растра
(«бомба распаковки»); картинка вписывается в рамку с сохранением
пропорций, маленькая не растягивается; результат — WebP со случайным
именем из 40 знаков. Байт в байт с GD файл не совпадает (другой
кодировщик), совпадают формат, размеры и путь по образцу.
"""

from __future__ import annotations

import io
import math
import secrets
import string
from collections.abc import Mapping
from typing import Any

from PIL import Image

from savdex.laravel_storage import public_root

#: ImageStore::MAX_PIXELS
MAX_PIXELS = 48_000_000

#: ImageStore::LOGO и ::COVER
LOGO: Mapping[str, Any] = {"w": 512, "h": 512, "quality": 85, "lossless": True}
COVER: Mapping[str, Any] = {"w": 2000, "h": 2000, "quality": 80}

#: ImageStore::PHOTO и ::THUMB
PHOTO: Mapping[str, Any] = {"w": 1600, "h": 1600, "quality": 82}
THUMB: Mapping[str, Any] = {"w": 400, "h": 400, "quality": 80}


class UnreadableImageError(RuntimeError):
    """RuntimeException у ImageStore: не картинка, слишком большая, не записалась."""


def _random(length: int) -> str:
    """Str::random: буквы и цифры."""
    alphabet = string.ascii_letters + string.digits

    return "".join(secrets.choice(alphabet) for _ in range(length))


def _read(data: bytes) -> Image.Image:
    """ImageStore::read: размер из заголовка до распаковки."""
    try:
        image = Image.open(io.BytesIO(data))
    except Exception as e:  # любой сбой разбора — «не картинка»
        raise UnreadableImageError("Файл не является изображением") from e

    width, height = image.size

    if width * height > MAX_PIXELS:
        raise UnreadableImageError("Слишком большое изображение")

    try:
        image.load()
    except Exception as e:
        raise UnreadableImageError("Файл не является изображением") from e

    return image


def _fit(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """ImageStore::fit: вписать в рамку, не увеличивая."""
    width, height = image.size
    ratio = min(max_width / width, max_height / height)

    if ratio >= 1:
        return image

    # round() у PHP — половина от нуля, а не к чётному
    size = (math.floor(width * ratio + 0.5), math.floor(height * ratio + 0.5))

    return image.resize(size, Image.Resampling.LANCZOS)


def store(data: bytes, directory: str, size: Mapping[str, Any]) -> str:
    """ImageStore::store: путь на публичном диске, как его хранит Laravel."""
    image = _read(data)
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    image = image.convert("RGBA" if has_alpha else "RGB")
    resized = _fit(image, int(size["w"]), int(size["h"]))
    out = io.BytesIO()

    if size.get("lossless"):
        resized.save(out, "WEBP", lossless=True)
    else:
        resized.save(out, "WEBP", quality=int(size["quality"]))

    path = f"{directory.strip('/')}/{_random(40)}.webp"
    target = public_root() / path

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out.getvalue())
    except OSError as e:
        raise UnreadableImageError("Файл не удалось сохранить") from e

    return path


def store_with_thumb(data: bytes, directory: str) -> dict[str, str]:
    """ImageStore::storeWithThumb: оригинал и уменьшенная копия."""
    return {
        "path": store(data, directory, PHOTO),
        "thumb_path": store(data, f"{directory}/thumb", THUMB),
    }


def delete(*paths: str | None) -> None:
    """ImageStore::delete: отсутствующий файл — не ошибка."""
    for path in paths:
        if path:
            (public_root() / path).unlink(missing_ok=True)
