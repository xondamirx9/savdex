"""
Растровое превью объявления для og:image (/og/listing/<номер>.jpg) —
копия OgImageController (этап 5, шаг 50).

Боты мессенджеров не понимают SVG, поэтому JPEG 1200×630 собирается из
первой по порядку картинки объявления (заполнить рамку, лишнее обрезать
по центру, прозрачное — на белом) и кэшируется рядом с ней:
listings/<номер>/og-<номер картинки>.jpg. Ответ — переход на файл;
картинки нет или она не читается — на общую обложку og-cover.png.
Картинка собирается Pillow, а не GD: байты другие, рамка та же.
"""

from __future__ import annotations

import io
import math

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from PIL import Image

from savdex.laravel_storage import public_root
from savdex.web.cabinet import _rows
from savdex.web.request import context
from savdex.web.shared import _php_round

WIDTH = 1200
HEIGHT = 630
QUALITY = 84


def _render(source: str, target: str) -> bool:
    try:
        image = Image.open(io.BytesIO((public_root() / source).read_bytes()))
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        return False

    width, height = image.size

    if width == 0 or height == 0:
        return False

    # cover: заполнить рамку целиком, лишнее обрезать по центру
    scale = max(WIDTH / width, HEIGHT / height)
    crop_width = int(_php_round(WIDTH / scale))
    crop_height = int(_php_round(HEIGHT / scale))
    left = math.trunc((width - crop_width) / 2)
    top = math.trunc((height - crop_height) / 2)

    # JPEG прозрачность не хранит — прозрачное кладётся на белый
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    rgba = image.convert("RGBA")
    part = rgba.crop((left, top, left + crop_width, top + crop_height)).resize(
        (WIDTH, HEIGHT), Image.Resampling.LANCZOS
    )
    canvas.paste(part, (0, 0), part)

    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=QUALITY)
    path = public_root() / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())

    return True


def listing(request: HttpRequest, listing_id: str) -> HttpResponse:
    """OgImageController::__invoke."""
    from savdex.web.views import not_found

    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    found = _rows("select id from listings where id = %s and deleted_at is null", [int(listing_id)])

    if not found:
        return not_found(ctx)

    cover = HttpResponseRedirect(ctx.url("og-cover.png"))
    images = _rows(
        "select id, path from listing_images where listing_id = %s order by sort, id",
        [found[0]["id"]],
    )
    source = next(
        (
            i
            for i in images
            if not str(i["path"] or "").lower().endswith(".svg")
            and (public_root() / str(i["path"] or "")).is_file()
        ),
        None,
    )

    if source is None:
        return cover

    cached = f"listings/{found[0]['id']}/og-{source['id']}.jpg"

    if not (public_root() / cached).is_file() and not _render(str(source["path"]), cached):
        return cover

    return HttpResponseRedirect(ctx.url(f"storage/{cached}"))
