"""
Пересборка картинок (savdex/images.py) — то же, что ImageStore у Laravel.

Без базы: картинки собираются здесь же, в памяти.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from savdex import images


def _picture(size: tuple[int, int], fmt: str = "JPEG", mode: str = "RGB", **save) -> io.BytesIO:
    out = io.BytesIO()
    colour = {"RGBA": (200, 30, 30, 128), "RGB": (200, 30, 30)}.get(mode, 1)
    Image.new(mode, size, colour).save(out, fmt, **save)
    out.seek(0)

    return out


def _open(binary: bytes) -> Image.Image:
    return Image.open(io.BytesIO(binary))


def test_вписывается_в_рамку_с_сохранением_пропорций():
    result = _open(images.process(_picture((4800, 1600)), images.BANNER))

    assert result.format == "WEBP"
    assert result.size == (2400, 800)


def test_маленькая_не_растягивается():
    assert _open(images.process(_picture((600, 200)), images.BANNER)).size == (600, 200)


def test_прозрачность_сохраняется():
    result = _open(images.process(_picture((100, 100), "PNG", "RGBA"), images.BANNER))

    assert result.mode == "RGBA"


def test_метаданные_съёмки_не_попадают():
    exif = Image.Exif()
    exif[0x010F] = "Камера с координатами"
    result = _open(images.process(_picture((100, 100), exif=exif.tobytes()), images.BANNER))

    assert not result.getexif()


@pytest.mark.parametrize(
    "source",
    [
        io.BytesIO(b"<?php echo 1; ?>"),
        _picture((10, 10), "GIF", "P"),
        io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64),  # заголовок PNG, внутри мусор
    ],
)
def test_не_картинка_отказ(source):
    with pytest.raises(images.NotAnImageError):
        images.process(source, images.BANNER)


def test_бомба_распаковки_отвергается_до_распаковки():
    """PNG 9000×9000 сплошной заливкой весит килобайты — но 81 Мп."""
    with pytest.raises(images.NotAnImageError, match="Слишком большое"):
        images.process(_picture((9000, 9000), "PNG", "L"), images.BANNER)


def test_запись_и_удаление(settings, tmp_path):
    settings.LARAVEL_ROOT = tmp_path

    path = images.store(_picture((100, 100)), "banners", images.BANNER)

    assert path.startswith("banners/") and path.endswith(".webp")
    assert len(path) == len("banners/") + 40 + len(".webp")
    assert (tmp_path / "storage/app/public" / path).exists()

    images.delete(path, None, "")
    assert not (tmp_path / "storage/app/public" / path).exists()


def test_удаление_не_выходит_за_диск(settings, tmp_path):
    settings.LARAVEL_ROOT = tmp_path
    secret = tmp_path / "secret.txt"
    secret.write_text("x")

    images.delete("../../secret.txt")

    assert secret.exists()
