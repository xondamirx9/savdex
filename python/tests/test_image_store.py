"""
Фото объявления (savdex/web/image_store.py): распаковывается один раз на
оригинал и уменьшенную копию, большой JPEG — сразу уменьшенным (Н17).
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from savdex.web import image_store


@pytest.fixture(autouse=True)
def _диск(tmp_path, settings) -> None:
    settings.LARAVEL_ROOT = tmp_path


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (120, 80, 40)).save(buffer, "JPEG", quality=70)

    return buffer.getvalue()


def test_оригинал_и_копия_из_одной_распаковки(monkeypatch) -> None:
    открыто = []
    настоящий = image_store.Image.open

    def считать(*args, **kwargs):
        открыто.append(1)

        return настоящий(*args, **kwargs)

    monkeypatch.setattr(image_store.Image, "open", считать)

    пути = image_store.store_with_thumb(_jpeg(2400, 1800), "listings/1")

    assert len(открыто) == 1
    with Image.open(image_store.public_root() / пути["path"]) as фото:
        assert фото.size == (1600, 1200)
    with Image.open(image_store.public_root() / пути["thumb_path"]) as копия:
        assert копия.size == (400, 300)


def test_большой_jpeg_распаковывается_уменьшенным() -> None:
    картинка = image_store._read(_jpeg(6400, 4800), image_store.PHOTO)

    # Не 6400×4800 в памяти, а уменьшенная при распаковке — не меньше рамки
    width, height = картинка.size
    assert 1600 <= width < 6400 and 1200 <= height < 4800
