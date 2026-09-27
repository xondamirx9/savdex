"""
Приём картинок, как App\\Support\\ImageStore у Laravel.

Файл пересобирается, а не кладётся как есть: снимок с телефона весит
восемь мегабайт и грузится первым экраном у всех посетителей сразу, а
в EXIF остаются координаты съёмки. Наружу выходит только то, что
удалось прочитать как пиксели, — вписанное в рамку макета и сжатое
в WebP, как делает Laravel.

- размеры проверяются по заголовку до распаковки: PNG со сплошной
  заливкой весит килобайты, а разворачивается в гигабайты («бомба
  распаковки»);
- вписать, а не обрезать; маленькое не растягивается;
- прозрачность сохраняется;
- имя случайное, 40 знаков, как Str::random(40).

Сверка с PHP-версией — tests/test_images.py.
"""

from __future__ import annotations

import io
import secrets
import string
from dataclasses import dataclass
from typing import IO

from PIL import Image, UnidentifiedImageError

from savdex import laravel_storage

#: ImageStore::MAX_PIXELS: 48 Мп ≈ 8000×6000
MAX_PIXELS = 48_000_000

#: ImageStore::MAX_SIZE_KB
MAX_BYTES = 8192 * 1024

#: Что принимаем на вход — ImageStore::ALLOWED_MIMES
FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

_ALPHABET = string.ascii_letters + string.digits


@dataclass(frozen=True)
class Frame:
    """Рамка, в которую вписывается картинка, и качество сжатия."""

    width: int
    height: int
    quality: int
    lossless: bool = False


#: ImageStore::BANNER — баннер во всю ширину
BANNER = Frame(2400, 1200, 82)

#: ImageStore::COVER — широкая обложка: визитка компании, новость
COVER = Frame(2000, 2000, 80)

#: ImageStore::BANNER_MOBILE — тот же баннер для телефона
BANNER_MOBILE = Frame(1000, 1400, 80)


class NotAnImageError(ValueError):
    """Файл не картинка из разрешённых — сообщение для формы."""


def _random_name() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(40))


def process(source: IO[bytes], frame: Frame) -> bytes:
    """Прочитать, проверить, вписать в рамку и сжать в WebP."""
    try:
        image = Image.open(source)
    except (UnidentifiedImageError, OSError) as error:
        raise NotAnImageError("Файл не является изображением.") from error

    if image.format not in FORMATS:
        raise NotAnImageError("Нужна картинка JPG, PNG или WebP.")

    # Размер из заголовка — до того, как растр распакован в память
    if image.width * image.height > MAX_PIXELS:
        raise NotAnImageError("Слишком большое изображение.")

    try:
        image.load()
    except (OSError, SyntaxError) as error:
        # Заголовок подделан, а внутри не картинка
        raise NotAnImageError("Файл не является изображением.") from error

    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    pixels = image.convert("RGBA" if has_alpha else "RGB")

    ratio = min(frame.width / pixels.width, frame.height / pixels.height)

    if ratio < 1:
        size = (round(pixels.width * ratio), round(pixels.height * ratio))
        pixels = pixels.resize(size, Image.Resampling.LANCZOS)

    out = io.BytesIO()
    # exif не передаётся — метаданные съёмки в файл не попадают
    pixels.save(out, "WEBP", quality=frame.quality, lossless=frame.lossless)

    return out.getvalue()


def prepare(upload: IO[bytes], frame: Frame) -> bytes:
    """Проверить и пересобрать — без записи на диск (для проверки формы)."""
    size = getattr(upload, "size", None)

    if size is not None and size > MAX_BYTES:
        raise NotAnImageError("Файл больше 8 МБ.")

    return process(upload, frame)


def write(binary: bytes, directory: str) -> str:
    """Записать уже пересобранную картинку на публичный диск, вернуть путь."""
    relative = f"{directory.strip('/')}/{_random_name()}.webp"
    target = laravel_storage.public_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(binary)

    return relative


def store(upload: IO[bytes], directory: str, frame: Frame) -> str:
    """ImageStore::store(): проверить, пересобрать, сохранить; вернуть путь."""
    return write(prepare(upload, frame), directory)


def delete(*paths: str | None) -> None:
    """ImageStore::delete(): удалить, молча пропустив уже отсутствующие."""
    root = laravel_storage.public_root().resolve()

    for path in paths:
        if not path:
            continue

        target = (root / path).resolve()

        # Путь из базы, но всё равно не даём выйти за пределы диска
        if root in target.parents:
            target.unlink(missing_ok=True)
