"""
Капча на входе и первом шаге регистрации: сетка 3×3, «отметьте все
картинки, где есть светофоры» (пешеходные переходы, витрины).

Картинки рисует сервер (Pillow), каждый раз заново: цвета, размер,
место, наклон, отражение, шум и сжатие JPEG случайны, так что набора,
который бот выучил бы по хешам, нет. Есть фотографии в CAPTCHA_PHOTOS_DIR
(подпапки traffic_light, crosswalk, storefront и other — «ничего из
этого») — берутся они.

Задание — в сессии (captcha.<для чего>): верные клетки и срок. Ответ
проверяется один раз — верный или нет, задание гасится: перебирать
сочетания на одном задании нельзя, форма просит новое. Выключить (демо,
проверки) — CAPTCHA_ENABLED=false.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from savdex import laravel_cache
from savdex.audit import client_ip
from savdex.web import session, throttle
from savdex.web.request import context

#: Для чего задание: у входа и регистрации свои — вкладки не гасят друг другу
PURPOSES = ("login", "register")
TARGETS = ("traffic_light", "crosswalk", "storefront")
GRID = 3
#: Сторона клетки в пикселях; рисуется вдвое крупнее и с запасом под наклон
TILE = 140
_SS = 2
_CANVAS = int(TILE * _SS * 1.2)
TTL_SECONDS = 600
MIN_TARGETS, MAX_TARGETS = 3, 4
#: Новых заданий с одного адреса в минуту: рисование — работа процессора
MAX_PER_MINUTE = 30

PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")

_rnd = secrets.SystemRandom()

Color = tuple[int, int, int]
Draw = ImageDraw.ImageDraw


def enabled() -> bool:
    """По умолчанию включена; CAPTCHA_ENABLED=false — выключена."""
    raw = (os.environ.get("CAPTCHA_ENABLED") or "").strip().lower()

    return raw not in ("0", "false", "(false)", "off", "no")


def _key(purpose: str) -> str:
    return "captcha." + purpose


# ── Проверка ответа ─────────────────────────────────────────────────


def _selection(raw: Any) -> set[int]:  # noqa: ANN401
    """Отмеченные клетки: список номеров (JSON Inertia) или «0,3,5». Мусор — {-1}."""
    if raw is None:
        return set()

    items = raw.split(",") if isinstance(raw, str) else raw if isinstance(raw, list) else [raw]
    picked: set[int] = set()

    for item in items:
        if isinstance(item, bool):
            return {-1}

        try:
            picked.add(int(str(item).strip()))
        except ValueError:
            return {-1}

    return picked


def verify(store: session.Store, purpose: str, raw: Any) -> str | None:  # noqa: ANN401
    """
    None — отмечено верно (или капча выключена), иначе код ошибки для
    поля captcha: required, expired, wrong. Задание гасится в любом случае.
    """
    if not enabled():
        return None

    key = _key(purpose)
    entry = store.get(key)
    store.forget(key)
    picked = _selection(raw)

    if not picked:
        return "required"

    if not isinstance(entry, dict) or _int(entry.get("expires")) < time.time():
        return "expired"

    answer = {int(n) for n in str(entry.get("answer") or "").split(",") if n.isdigit()}

    return None if answer and picked == answer else "wrong"


def _int(value: Any) -> int:  # noqa: ANN401
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


# ── Выдача задания ──────────────────────────────────────────────────


def challenge(request: HttpRequest) -> HttpResponse:
    """
    GET /captcha?for=login|register — новое задание: что искать и девять
    картинок (data: URI). Прежнее задание того же назначения гасится.
    """
    if request.method != "GET":
        return JsonResponse({"message": "method_not_allowed"}, status=405)

    ctx = context(request, redirect=False)

    if isinstance(ctx, HttpResponse):
        return ctx

    purpose = request.GET.get("for", "")

    if purpose not in PURPOSES or not enabled():
        return JsonResponse({"message": "not_found"}, status=404)

    started = session.start(request)

    if started is None:
        return JsonResponse({"message": "no_session"}, status=503)

    if laravel_cache.is_file_store():
        ip = client_ip(request) or ""
        limit = "captcha:" + hashlib.sha1(ip.encode()).hexdigest()

        if throttle.too_many(limit, MAX_PER_MINUTE):
            return JsonResponse({"message": "too_many"}, status=429)

        throttle.hit(limit)

    target, tiles, answer = build()
    started[0].put(
        _key(purpose),
        {
            # Строкой: список в сессии формата Laravel вернулся бы словарём
            "answer": ",".join(str(n) for n in answer),
            "expires": int(time.time()) + TTL_SECONDS,
        },
    )

    response = JsonResponse(
        {
            "target": target,
            "grid": GRID,
            "tiles": ["data:image/jpeg;base64," + base64.b64encode(t).decode() for t in tiles],
        }
    )
    response["Cache-Control"] = "no-store"

    return response


def build() -> tuple[str, list[bytes], list[int]]:
    """Что искать, девять картинок JPEG и номера верных клеток."""
    target = _rnd.choice(TARGETS)
    cells = GRID * GRID
    answer = sorted(_rnd.sample(range(cells), _rnd.randint(MIN_TARGETS, MAX_TARGETS)))
    photos = _photos()

    if photos is not None:
        return target, _photo_tiles(photos, target, answer), answer

    others = [t for t in TARGETS if t != target] + list(DISTRACTORS)
    # Без повторов, пока хватает видов: одинаковые соседи бросаются в глаза
    pool = _rnd.sample(others, len(others))
    tiles = []

    for i in range(cells):
        kind = target if i in answer else (pool.pop() if pool else _rnd.choice(others))
        tiles.append(_jpeg(_paint(kind)))

    return target, tiles, answer


# ── Фотографии ──────────────────────────────────────────────────────


def _photos() -> dict[str, list[Path]] | None:
    """Папки с фотографиями; мало картинок — None (тогда рисуем)."""
    root = (os.environ.get("CAPTCHA_PHOTOS_DIR") or "").strip()

    if root == "":
        return None

    found = {
        name: sorted(p for p in (Path(root) / name).glob("*") if p.suffix.lower() in PHOTO_SUFFIXES)
        for name in (*TARGETS, "other")
    }

    if any(len(found[t]) < MAX_TARGETS for t in TARGETS) or len(found["other"]) < GRID * GRID:
        return None

    return found


def _photo_tiles(photos: dict[str, list[Path]], target: str, answer: list[int]) -> list[bytes]:
    hits = _rnd.sample(photos[target], len(answer))
    misses_pool = [p for name, paths in photos.items() if name != target for p in paths]
    misses = _rnd.sample(misses_pool, GRID * GRID - len(answer))
    tiles = []

    for i in range(GRID * GRID):
        path = hits.pop() if i in answer else misses.pop()

        with Image.open(path) as source:
            image = source.convert("RGB")

        # Случайная рамка внутри снимка: одна и та же фотография не повторяется побайтно
        scale = _u(0.8, 1.0)
        side = int(min(image.size) * scale)
        left = _rnd.randint(0, image.width - side)
        top = _rnd.randint(0, image.height - side)
        image = image.crop((left, top, left + side, top + side)).resize(
            (TILE, TILE), Image.Resampling.LANCZOS
        )
        tiles.append(_jpeg(_grain(image)))

    return tiles


# ── Рисование: общее ────────────────────────────────────────────────


def _u(a: float, b: float) -> float:
    return _rnd.uniform(a, b)


def _clamp(v: float) -> int:
    return max(0, min(255, int(v)))


def _jit(color: Color, spread: int = 18) -> Color:
    r, g, b = color

    return (
        _clamp(r + _rnd.randint(-spread, spread)),
        _clamp(g + _rnd.randint(-spread, spread)),
        _clamp(b + _rnd.randint(-spread, spread)),
    )


def _mix(a: Color, b: Color, t: float) -> Color:
    return (
        _clamp(a[0] + (b[0] - a[0]) * t),
        _clamp(a[1] + (b[1] - a[1]) * t),
        _clamp(a[2] + (b[2] - a[2]) * t),
    )


GRASS: Color = (95, 150, 70)
PAVEMENT: Color = (150, 150, 145)
SAND: Color = (200, 185, 150)
ASPHALT: Color = (72, 74, 78)


def _sky(d: Draw, c: int, horizon: int) -> None:
    top = _jit(_rnd.choice([(95, 145, 215), (140, 180, 225), (170, 175, 185), (120, 160, 210)]), 14)
    bottom = _mix(top, (245, 245, 240), _u(0.35, 0.6))

    for y in range(horizon):
        d.line([(0, y), (c, y)], fill=_mix(top, bottom, y / max(1, horizon)))

    for _ in range(_rnd.randint(0, 3)):
        cx, cy = _u(0, c), _u(0, horizon * 0.7)
        w, h = c * _u(0.12, 0.3), c * _u(0.04, 0.08)
        d.ellipse([cx - w, cy - h, cx + w, cy + h], fill=_mix(bottom, (255, 255, 255), 0.6))


def _outdoor(d: Draw, c: int, ground: Color) -> int:
    """Небо и земля; возвращает линию горизонта."""
    horizon = int(c * _u(0.45, 0.68))
    _sky(d, c, horizon)
    d.rectangle([0, horizon, c, c], fill=_jit(ground))

    # Дальний план: невысокие силуэты без окон и вывесок
    for _ in range(_rnd.randint(0, 4)):
        x, w, h = _u(0, c), c * _u(0.04, 0.12), c * _u(0.03, 0.1)
        d.rectangle([x, horizon - h, x + w, horizon], fill=_jit((150, 160, 165), 12))

    return horizon


def _speckle(d: Draw, c: int, base: Color, count: int = 260) -> None:
    for _ in range(count):
        x, y, r = _u(0, c), _u(0, c), _u(1, 3)
        d.ellipse([x - r, y - r, x + r, y + r], fill=_jit(base, 22))


def _paint(kind: str) -> Image.Image:
    image = Image.new("RGB", (_CANVAS, _CANVAS), (200, 200, 200))
    PAINTERS[kind](image, ImageDraw.Draw(image), _CANVAS)

    return _finish(image)


def _finish(image: Image.Image) -> Image.Image:
    """Наклон, обрезка, уменьшение, цвет и шум."""
    image = image.rotate(_u(-7, 7), resample=Image.Resampling.BICUBIC)
    margin = (_CANVAS - TILE * _SS) // 2
    image = image.crop((margin, margin, margin + TILE * _SS, margin + TILE * _SS))
    image = image.resize((TILE, TILE), Image.Resampling.LANCZOS)

    if _rnd.random() < 0.5:
        image = ImageOps.mirror(image)

    return _grain(image)


def _grain(image: Image.Image) -> Image.Image:
    image = ImageEnhance.Brightness(image).enhance(_u(0.88, 1.1))
    image = ImageEnhance.Contrast(image).enhance(_u(0.88, 1.12))
    image = ImageEnhance.Color(image).enhance(_u(0.8, 1.2))
    noise = Image.effect_noise(image.size, _u(25, 45)).convert("RGB")
    image = Image.blend(image, noise, _u(0.04, 0.09))

    if _rnd.random() < 0.3:
        image = image.filter(ImageFilter.GaussianBlur(_u(0.3, 0.6)))

    return image


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=_rnd.randint(62, 80))

    return buffer.getvalue()


# ── Что ищем ────────────────────────────────────────────────────────

LAMPS: tuple[Color, Color, Color] = ((228, 45, 35), (246, 178, 25), (45, 205, 105))


def _traffic_light(image: Image.Image, d: Draw, c: int) -> None:
    _outdoor(d, c, _rnd.choice([GRASS, PAVEMENT, SAND]))
    housing = _jit(_rnd.choice([(28, 28, 30), (45, 50, 42), (205, 170, 35), (70, 70, 75)]), 10)
    edge = _mix(housing, (0, 0, 0), 0.4)
    pole = _jit((95, 98, 102), 12)
    horizontal = _rnd.random() < 0.25

    if horizontal:
        w = c * _u(0.5, 0.62)
        h = w / _u(2.6, 3.0)
        x0, y0 = c * _u(0.12, 0.25), c * _u(0.2, 0.4)
        # Консоль от столба справа
        d.rectangle([x0 + w * 0.9, y0 + h * 0.4, c, y0 + h * 0.6], fill=pole)
    else:
        h = c * _u(0.42, 0.56)
        w = h / _u(2.5, 3.0)
        x0, y0 = c * _u(0.32, 0.68) - w / 2, c * _u(0.12, 0.24)
        d.rectangle([x0 + w * 0.4, y0 + h * 0.9, x0 + w * 0.6, c], fill=pole)

    d.rounded_rectangle(
        [x0, y0, x0 + w, y0 + h], radius=min(w, h) * 0.18, fill=housing, outline=edge, width=4
    )
    lit = _rnd.randrange(3)
    r = min(w, h) * 0.32

    for i in range(3):
        if horizontal:
            cx, cy = x0 + w * (2 * i + 1) / 6, y0 + h / 2
        else:
            cx, cy = x0 + w / 2, y0 + h * (2 * i + 1) / 6

        # Козырёк над линзой
        d.chord([cx - r * 1.25, cy - r * 1.3, cx + r * 1.25, cy + r * 1.1], 180, 360, fill=edge)
        color = LAMPS[i] if i == lit else _mix(LAMPS[i], (25, 25, 25), 0.72)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

        if i == lit:
            hl = _mix(color, (255, 255, 255), 0.55)
            d.ellipse([cx - r * 0.55, cy - r * 0.6, cx - r * 0.1, cy - r * 0.2], fill=hl)


def _road(d: Draw, c: int, horizon: int) -> tuple[Callable[[float], tuple[float, float]], Color]:
    """Дорога в перспективе; функция t (0 — горизонт, 1 — низ) → края дороги."""
    asphalt = _jit(ASPHALT, 12)
    cx = c * _u(0.4, 0.6)
    far = c * _u(0.05, 0.11)
    left_bottom, right_bottom = -c * _u(0.3, 0.55), c + c * _u(0.3, 0.55)
    d.polygon(
        [(cx - far, horizon), (cx + far, horizon), (right_bottom, c), (left_bottom, c)],
        fill=asphalt,
    )

    def edges(t: float) -> tuple[float, float]:
        return (cx - far + (left_bottom - cx + far) * t, cx + far + (right_bottom - cx - far) * t)

    return edges, asphalt


def _crosswalk(image: Image.Image, d: Draw, c: int) -> None:
    paint = _jit((236, 236, 230), 10)

    if _rnd.random() < 0.45:
        # Сверху: асфальт и полосы под углом
        asphalt = _jit(ASPHALT, 12)
        d.rectangle([0, 0, c, c], fill=asphalt)
        _speckle(d, c, asphalt)
        layer = Image.new("RGBA", (c, c), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        n = _rnd.randint(5, 7)
        stripe = c / (n * 2 - 1) * _u(0.85, 1.0)
        y0, y1 = c * _u(0.12, 0.25), c * _u(0.75, 0.88)

        for i in range(n + 1):
            x = c * _u(-0.02, 0.02) + i * stripe * 2
            ld.rectangle([x, y0, x + stripe, y1], fill=(*paint, 255))

        layer = layer.rotate(_u(-35, 35), resample=Image.Resampling.BICUBIC)
        image.paste(layer, (0, 0), layer)

        # Стёртая краска
        for _ in range(_rnd.randint(10, 30)):
            x, y, s = _u(0, c), _u(0, c), _u(2, 6)
            d.ellipse([x - s, y - s, x + s, y + s], fill=_mix(paint, asphalt, 0.5))

        return

    horizon = _outdoor(d, c, PAVEMENT)
    edges, _ = _road(d, c, horizon)
    t0 = _u(0.28, 0.42)
    t1 = t0 + _u(0.28, 0.4)
    n = _rnd.randint(6, 9)

    def point(t: float, u: float) -> tuple[float, float]:
        left, right = edges(t)

        return left + (right - left) * u, horizon + (c - horizon) * t

    for i in range(n):
        u0, u1 = (2 * i + 0.5) / (2 * n), (2 * i + 1.5) / (2 * n)
        d.polygon([point(t0, u0), point(t0, u1), point(t1, u1), point(t1, u0)], fill=paint)


def _storefront(image: Image.Image, d: Draw, c: int) -> None:
    wall = _jit(
        _rnd.choice(
            [(225, 205, 175), (170, 85, 65), (205, 205, 200), (240, 235, 225), (125, 130, 140)]
        )
    )
    d.rectangle([0, 0, c, c], fill=wall)

    if _rnd.random() < 0.5:
        _sky(d, c, int(c * _u(0.06, 0.14)))

    sidewalk = c * _u(0.86, 0.93)
    d.rectangle([0, sidewalk, c, c], fill=_jit((165, 163, 158)))

    # Вывеска: «буквы» — светлые бруски, читаемого текста нет
    sy0, sh = c * _u(0.14, 0.22), c * _u(0.1, 0.14)
    sx0, sx1 = c * _u(0.08, 0.16), c - c * _u(0.08, 0.16)
    sign = _jit(
        _rnd.choice([(200, 30, 40), (20, 90, 170), (30, 130, 70), (250, 190, 30), (30, 30, 30)])
    )
    letters = (250, 250, 245) if sum(sign) < 450 else (30, 30, 30)
    d.rectangle([sx0, sy0, sx1, sy0 + sh], fill=sign)
    x = sx0 + sh * 0.5

    while x < sx1 - sh * 0.8:
        lw = sh * _u(0.25, 0.5)
        d.rectangle([x, sy0 + sh * 0.25, x + lw, sy0 + sh * 0.75], fill=letters)
        x += lw + sh * (_u(0.5, 0.8) if _rnd.random() < 0.15 else _u(0.12, 0.25))

    top = sy0 + sh

    if _rnd.random() < 0.75:
        # Маркиза в полоску
        ah = c * _u(0.07, 0.11)
        colors = (_jit(_rnd.choice([(200, 40, 40), (30, 110, 60), (30, 80, 160)])), (245, 245, 240))
        stripes = _rnd.randint(7, 11)
        width = (sx1 - sx0) / stripes

        for j in range(stripes):
            a, b = sx0 + j * width, sx0 + (j + 1) * width
            d.polygon(
                [
                    (a, top),
                    (b, top),
                    (b + (b - c / 2) * 0.08, top + ah),
                    (a + (a - c / 2) * 0.08, top + ah),
                ],
                fill=colors[j % 2],
            )

        top += ah

    wy0, wy1 = top + c * 0.04, sidewalk - c * 0.015
    frame = _jit((60, 60, 65), 10)
    glass = _jit((150, 195, 215), 18)
    door_w = c * _u(0.15, 0.2)
    door_x = _rnd.choice([sx0, sx1 - door_w, c / 2 - door_w / 2])
    panes = [(sx0, door_x - c * 0.02), (door_x + door_w + c * 0.02, sx1)]

    for a, b in panes:
        if b - a < c * 0.08:
            continue

        d.rectangle([a, wy0, b, wy1], fill=frame)
        d.rectangle([a + 5, wy0 + 5, b - 5, wy1 - 5], fill=glass)
        # Полка с товаром
        shelf = wy0 + (wy1 - wy0) * _u(0.55, 0.7)
        d.rectangle([a + 5, shelf, b - 5, shelf + 4], fill=frame)
        gx = a + 12

        while gx < b - 20:
            gw, gh = c * _u(0.025, 0.05), c * _u(0.04, 0.09)
            item = _jit(_rnd.choice([(220, 60, 60), (240, 200, 60), (70, 140, 220), (90, 180, 90)]))

            if _rnd.random() < 0.4:
                d.ellipse([gx, shelf - gw, gx + gw, shelf], fill=item)
            else:
                d.rectangle([gx, shelf - gh, gx + gw, shelf], fill=item)

            gx += gw + c * _u(0.01, 0.03)

        # Блик на стекле
        k = (b - a) * _u(0.2, 0.4)
        d.polygon(
            [
                (a + k, wy0 + 5),
                (a + k * 1.5, wy0 + 5),
                (a + k * 0.6, wy1 - 5),
                (a + k * 0.1, wy1 - 5),
            ],
            fill=_mix(glass, (255, 255, 255), 0.45),
        )

    d.rectangle([door_x, wy0, door_x + door_w, sidewalk], fill=frame)
    d.rectangle([door_x + 5, wy0 + 5, door_x + door_w - 5, sidewalk], fill=_mix(glass, frame, 0.2))
    hx = door_x + door_w * 0.8
    d.rectangle(
        [hx, (wy0 + sidewalk) / 2 - 10, hx + 4, (wy0 + sidewalk) / 2 + 10], fill=(200, 200, 200)
    )


# ── Прочее (не цель) ────────────────────────────────────────────────


def _house(image: Image.Image, d: Draw, c: int) -> None:
    horizon = _outdoor(d, c, GRASS)
    w = c * _u(0.5, 0.65)
    h = w * _u(0.55, 0.75)
    x0 = _u(c * 0.15, c * 0.85 - w)
    y1 = horizon + c * _u(0.08, 0.15)
    y0 = y1 - h
    wall = _jit(_rnd.choice([(235, 225, 205), (215, 190, 160), (200, 205, 210), (180, 120, 95)]))
    d.rectangle([x0, y0, x0 + w, y1], fill=wall)
    roof = _jit(_rnd.choice([(130, 60, 45), (90, 90, 95), (150, 90, 50)]))
    d.polygon(
        [(x0 - w * 0.08, y0), (x0 + w / 2, y0 - h * _u(0.45, 0.7)), (x0 + w * 1.08, y0)], fill=roof
    )
    cols, rows = _rnd.choice([(2, 1), (3, 1), (2, 2), (3, 2)])
    pane = min(w / (cols * 2.2), h / (rows * 2.6))
    glass = _jit((120, 145, 165), 12)

    for i in range(cols):
        for j in range(rows):
            px = x0 + w * (i + 0.5) / cols - pane / 2
            py = y0 + h * (j + 0.4) / (rows + 0.6)
            d.rectangle([px, py, px + pane, py + pane], fill=(245, 245, 245))
            d.rectangle([px + 3, py + 3, px + pane - 3, py + pane - 3], fill=glass)
            d.line([(px + pane / 2, py), (px + pane / 2, py + pane)], fill=(245, 245, 245), width=3)
            d.line([(px, py + pane / 2), (px + pane, py + pane / 2)], fill=(245, 245, 245), width=3)

    dw = w * 0.16
    dx = x0 + w * _u(0.1, 0.75)
    d.rectangle([dx, y1 - h * 0.42, dx + dw, y1], fill=_jit((110, 70, 40)))


def _car(image: Image.Image, d: Draw, c: int) -> None:
    horizon = _outdoor(d, c, _rnd.choice([PAVEMENT, ASPHALT]))
    length = c * _u(0.62, 0.8)
    x0 = (c - length) / 2 + c * _u(-0.05, 0.05)
    by = max(horizon + c * 0.12, c * _u(0.68, 0.78))
    body = _jit(
        _rnd.choice([(200, 40, 40), (40, 90, 180), (230, 230, 230), (40, 40, 45), (160, 160, 165)])
    )
    d.rounded_rectangle([x0, by - length * 0.22, x0 + length, by], radius=length * 0.06, fill=body)
    d.polygon(
        [
            (x0 + length * 0.2, by - length * 0.21),
            (x0 + length * 0.33, by - length * 0.4),
            (x0 + length * 0.68, by - length * 0.4),
            (x0 + length * 0.82, by - length * 0.21),
        ],
        fill=body,
    )
    glass = _jit((150, 180, 200), 10)
    d.polygon(
        [
            (x0 + length * 0.25, by - length * 0.23),
            (x0 + length * 0.35, by - length * 0.37),
            (x0 + length * 0.66, by - length * 0.37),
            (x0 + length * 0.77, by - length * 0.23),
        ],
        fill=glass,
    )
    d.rectangle(
        [x0 + length * 0.49, by - length * 0.38, x0 + length * 0.52, by - length * 0.22], fill=body
    )
    r = length * 0.1

    for wx in (x0 + length * 0.22, x0 + length * 0.78):
        d.ellipse([wx - r, by - r, wx + r, by + r], fill=(25, 25, 25))
        d.ellipse(
            [wx - r * 0.45, by - r * 0.45, wx + r * 0.45, by + r * 0.45], fill=(170, 170, 170)
        )

    d.rectangle(
        [x0 + length - 10, by - length * 0.17, x0 + length, by - length * 0.11],
        fill=(250, 220, 120),
    )
    d.rectangle([x0, by - length * 0.17, x0 + 10, by - length * 0.11], fill=(200, 30, 30))


def _tree(image: Image.Image, d: Draw, c: int) -> None:
    horizon = _outdoor(d, c, GRASS)
    cx = c * _u(0.35, 0.65)
    base = horizon + c * _u(0.1, 0.2)
    tw = c * _u(0.05, 0.08)
    crown = c * _u(0.18, 0.26)
    top = base - c * _u(0.35, 0.5)
    d.rectangle([cx - tw / 2, top, cx + tw / 2, base], fill=_jit((105, 70, 40)))
    green = _jit((60, 130, 55), 20)

    for _ in range(_rnd.randint(4, 7)):
        ox, oy = _u(-0.6, 0.6) * crown, _u(-0.5, 0.4) * crown
        rr = crown * _u(0.5, 0.8)
        d.ellipse([cx + ox - rr, top + oy - rr, cx + ox + rr, top + oy + rr], fill=_jit(green, 15))


def _lamp(image: Image.Image, d: Draw, c: int) -> None:
    _outdoor(d, c, _rnd.choice([PAVEMENT, GRASS]))
    px = c * _u(0.3, 0.55)
    top = c * _u(0.15, 0.25)
    pole = _jit((70, 75, 80), 10)
    d.rectangle([px - 6, top, px + 6, c], fill=pole)
    reach = c * _u(0.2, 0.3)
    d.rectangle([px, top, px + reach, top + 10], fill=pole)
    hx = px + reach
    d.polygon(
        [(hx - 30, top + 8), (hx + 30, top + 8), (hx + 18, top + 32), (hx - 18, top + 32)],
        fill=pole,
    )
    d.ellipse([hx - 16, top + 24, hx + 16, top + 40], fill=_jit((250, 235, 170), 8))


def _bicycle(image: Image.Image, d: Draw, c: int) -> None:
    horizon = _outdoor(d, c, _rnd.choice([PAVEMENT, GRASS]))
    r = c * _u(0.14, 0.18)
    by = max(horizon + r, c * _u(0.62, 0.72))
    x1 = c * _u(0.25, 0.32)
    x2 = x1 + r * _u(2.3, 2.7)
    tire = (30, 30, 30)

    for x in (x1, x2):
        d.ellipse([x - r, by - r, x + r, by + r], outline=tire, width=8)

    frame = _jit(_rnd.choice([(200, 40, 40), (40, 90, 180), (40, 140, 80), (240, 200, 40)]))
    seat = (x1 + r * 0.9, by - r * 1.3)
    bar = (x2 - r * 0.3, by - r * 1.4)
    crank = (x1 + r * 1.2, by)
    for a, b in (
        ((x1, by), seat),
        (seat, crank),
        (crank, (x1, by)),
        (crank, bar),
        (seat, bar),
        (bar, (x2, by)),
    ):
        d.line([a, b], fill=frame, width=7)

    d.rectangle([seat[0] - 18, seat[1] - 8, seat[0] + 14, seat[1]], fill=tire)
    d.line([bar, (bar[0] + 22, bar[1] - 10)], fill=tire, width=6)


def _plain_road(image: Image.Image, d: Draw, c: int) -> None:
    """Дорога без «зебры»: разметка только вдоль."""
    horizon = _outdoor(d, c, _rnd.choice([GRASS, SAND]))
    edges, _ = _road(d, c, horizon)
    line = _rnd.choice([(240, 240, 235), (240, 200, 60)])
    t = 0.05

    while t < 1:
        step = 0.06 + t * 0.12
        a, b = edges(t), edges(min(1, t + step * 0.5))
        y_a, y_b = horizon + (c - horizon) * t, horizon + (c - horizon) * min(1, t + step * 0.5)
        w = 2 + 10 * t
        mid_a, mid_b = (a[0] + a[1]) / 2, (b[0] + b[1]) / 2
        d.polygon(
            [(mid_a - w / 2, y_a), (mid_a + w / 2, y_a), (mid_b + w, y_b), (mid_b - w, y_b)],
            fill=line,
        )
        t += step


def _bus(image: Image.Image, d: Draw, c: int) -> None:
    horizon = _outdoor(d, c, _rnd.choice([PAVEMENT, ASPHALT]))
    length = c * _u(0.75, 0.88)
    x0 = (c - length) / 2
    by = max(horizon + c * 0.1, c * _u(0.7, 0.8))
    height = length * _u(0.36, 0.42)
    body = _jit(_rnd.choice([(240, 190, 40), (40, 120, 200), (210, 50, 50), (60, 150, 90)]))
    d.rounded_rectangle([x0, by - height, x0 + length, by], radius=14, fill=body)
    glass = _jit((140, 170, 190), 10)
    count = _rnd.randint(4, 6)
    ww = length / (count + 0.5)

    for i in range(count):
        wx = x0 + ww * (i + 0.25)
        d.rectangle([wx, by - height * 0.85, wx + ww * 0.8, by - height * 0.5], fill=glass)

    r = height * 0.18

    for wx in (x0 + length * 0.18, x0 + length * 0.8):
        d.ellipse([wx - r, by - r, wx + r, by + r], fill=(25, 25, 25))


def _sign(image: Image.Image, d: Draw, c: int) -> None:
    _outdoor(d, c, _rnd.choice([PAVEMENT, GRASS, SAND]))
    cx = c * _u(0.35, 0.65)
    cy = c * _u(0.28, 0.4)
    r = c * _u(0.13, 0.18)
    d.rectangle([cx - 5, cy, cx + 5, c], fill=_jit((140, 140, 145), 8))
    kind = _rnd.randrange(3)

    if kind == 0:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(210, 30, 35))
        d.rectangle(
            [cx - r * 0.65, cy - r * 0.18, cx + r * 0.65, cy + r * 0.18], fill=(250, 250, 250)
        )
    elif kind == 1:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 90, 190))
        d.polygon(
            [(cx - r * 0.5, cy + r * 0.1), (cx, cy - r * 0.55), (cx + r * 0.5, cy + r * 0.1)],
            fill=(250, 250, 250),
        )
        d.rectangle([cx - r * 0.15, cy, cx + r * 0.15, cy + r * 0.55], fill=(250, 250, 250))
    else:
        d.polygon(
            [(cx - r * 1.1, cy + r * 0.8), (cx, cy - r * 1.1), (cx + r * 1.1, cy + r * 0.8)],
            fill=(210, 30, 35),
        )
        d.polygon(
            [(cx - r * 0.75, cy + r * 0.6), (cx, cy - r * 0.7), (cx + r * 0.75, cy + r * 0.6)],
            fill=(250, 250, 250),
        )
        d.rectangle([cx - r * 0.08, cy - r * 0.25, cx + r * 0.08, cy + r * 0.2], fill=(20, 20, 20))
        d.ellipse([cx - r * 0.09, cy + r * 0.3, cx + r * 0.09, cy + r * 0.46], fill=(20, 20, 20))


def _landscape(image: Image.Image, d: Draw, c: int) -> None:
    horizon = int(c * _u(0.55, 0.7))
    _sky(d, c, horizon)
    d.rectangle([0, horizon, c, c], fill=_jit(_rnd.choice([GRASS, SAND])))
    rock = _jit((110, 115, 125), 12)

    for _ in range(_rnd.randint(2, 4)):
        cx, w, h = _u(0, c), c * _u(0.25, 0.45), c * _u(0.2, 0.38)
        d.polygon([(cx - w, horizon), (cx, horizon - h), (cx + w, horizon)], fill=_jit(rock, 10))
        d.polygon(
            [
                (cx - w * 0.25, horizon - h * 0.75),
                (cx, horizon - h),
                (cx + w * 0.25, horizon - h * 0.75),
            ],
            fill=(245, 245, 250),
        )


Painter = Callable[[Image.Image, Draw, int], None]

DISTRACTORS: dict[str, Painter] = {
    "house": _house,
    "car": _car,
    "tree": _tree,
    "lamp": _lamp,
    "bicycle": _bicycle,
    "road": _plain_road,
    "bus": _bus,
    "sign": _sign,
    "landscape": _landscape,
}

PAINTERS: dict[str, Painter] = {
    "traffic_light": _traffic_light,
    "crosswalk": _crosswalk,
    "storefront": _storefront,
    **DISTRACTORS,
}
