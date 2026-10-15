"""
Капча на первом шаге регистрации, как у Google: галочка «Я не
робот», по ней — окно с картинкой из букв и цифр.

Два шага. Окно: GET /captcha — картинка, POST /captcha/verify —
проверка введённого; верно — одноразовый пропуск (captcha_pass.<для
чего>), галочка становится зелёной. Форма шлёт пропуск в поле captcha,
обработчик гасит его (confirm).

Картинку рисует сервер (Pillow), каждый раз заново: символы разного
размера, наклона и цвета, сдвинуты волной, поверх — линии и шум. Похожие
знаки (0 и O, 1, I и L) в набор не входят. Регистр не важен, пробелы
отбрасываются.

Ответ — в сессии (captcha.<для чего>) со сроком. Проверяется один раз —
верный или нет, задание гасится: подбирать на одной картинке нельзя,
форма просит новую. Выключить (демо, проверки) — CAPTCHA_ENABLED=false.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import os
import secrets
import time
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from savdex import laravel_cache
from savdex.audit import client_ip
from savdex.web import session, throttle
from savdex.web.request import context

#: Для чего задание. Пока только регистрация: она рассылает письма с кодом.
#: Вход капчу не спрашивает — его держит LoginThrottle (auth_actions)
PURPOSES = ("register",)
#: Без 0/O, 1/I/L: их путают и люди, и шрифт
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 5
WIDTH, HEIGHT = 200, 64
#: Рисуется вдвое крупнее и уменьшается — ровные края
_SS = 2
TTL_SECONDS = 600
#: Сколько живёт пропуск после пройденной проверки: успеть дописать форму
PASS_TTL_SECONDS = 600
#: Новых картинок с одного адреса в минуту: рисование — работа процессора
MAX_PER_MINUTE = 30

_rnd = secrets.SystemRandom()

Color = tuple[int, int, int]


def enabled() -> bool:
    """По умолчанию включена; CAPTCHA_ENABLED=false — выключена."""
    raw = (os.environ.get("CAPTCHA_ENABLED") or "").strip().lower()

    return raw not in ("0", "false", "(false)", "off", "no")


def _key(purpose: str) -> str:
    return "captcha." + purpose


def _pass_key(purpose: str) -> str:
    return "captcha_pass." + purpose


# ── Проверка ответа ─────────────────────────────────────────────────


def normalize(raw: Any) -> str:  # noqa: ANN401
    """Введённое: без пробелов, заглавными. Не строка — пусто."""
    if not isinstance(raw, str):
        return ""

    return "".join(raw.split()).upper()


def verify(store: session.Store, purpose: str, raw: Any) -> str | None:  # noqa: ANN401
    """
    None — введено верно (или капча выключена), иначе код ошибки для
    поля captcha: required, expired, wrong. Задание гасится в любом случае.
    """
    if not enabled():
        return None

    key = _key(purpose)
    entry = store.get(key)
    store.forget(key)
    typed = normalize(raw)

    if typed == "":
        return "required"

    if not isinstance(entry, dict) or _int(entry.get("expires")) < time.time():
        return "expired"

    answer = str(entry.get("answer") or "")

    return None if answer != "" and secrets.compare_digest(typed, answer) else "wrong"


def _int(value: Any) -> int:  # noqa: ANN401
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def confirm(store: session.Store, purpose: str, raw: Any) -> str | None:  # noqa: ANN401
    """
    Пропуск из формы: None — проверка пройдена (или капча выключена),
    иначе код ошибки: not_confirmed (галочки нет), confirm_expired
    (пропуск чужой, использован или устарел). Пропуск гасится в любом случае.
    """
    if not enabled():
        return None

    key = _pass_key(purpose)
    entry = store.get(key)
    store.forget(key)

    if not isinstance(raw, str) or raw == "":
        return "not_confirmed"

    if (
        not isinstance(entry, dict)
        or _int(entry.get("expires")) < time.time()
        or not secrets.compare_digest(raw.encode(), str(entry.get("token") or "").encode())
    ):
        return "confirm_expired"

    return None


# ── Окно: проверка введённого ───────────────────────────────────────


def check(request: HttpRequest) -> HttpResponse:
    """
    POST /captcha/verify?for=register {captcha: "K7MPX"} — окно «Я
    не робот». Верно — {token}: пропуск для формы; нет — 422 с текстом
    ошибки, картинка погашена, окно просит новую. Токен CSRF и частота —
    как у форм (forms.action).
    """
    # Отложенный импорт: actions тянет за собой кабинет и каталог
    from savdex.web.actions import form

    return form()(_check)(request)


def _check(request: HttpRequest) -> HttpResponse:
    from savdex.web.forms import _store, action, input_of

    ctx = action(
        request, auth=False, throttle=30, throttle_minutes=1, throttle_prefix="captcha-verify"
    )
    purpose = request.GET.get("for", "")

    if purpose not in PURPOSES or not enabled():
        return JsonResponse({"message": "not_found"}, status=404)

    store = _store(ctx)
    problem = verify(store, purpose, input_of(request).get("captcha"))

    if problem is not None:
        return JsonResponse(
            {"error": problem, "message": ctx.t(f"captcha.errors.{problem}")}, status=422
        )

    token = secrets.token_urlsafe(24)
    store.put(_pass_key(purpose), {"token": token, "expires": int(time.time()) + PASS_TTL_SECONDS})

    return JsonResponse({"token": token})


# ── Выдача задания ──────────────────────────────────────────────────


def challenge(request: HttpRequest) -> HttpResponse:
    """
    GET /captcha?for=register — новая картинка (data: URI) и число
    символов. Прежнее задание того же назначения гасится.
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

    text = code()
    started[0].put(_key(purpose), {"answer": text, "expires": int(time.time()) + TTL_SECONDS})

    response = JsonResponse(
        {
            "image": "data:image/png;base64," + base64.b64encode(render(text)).decode(),
            "length": len(text),
        }
    )
    response["Cache-Control"] = "no-store"

    return response


def code() -> str:
    return "".join(_rnd.choice(ALPHABET) for _ in range(LENGTH))


# ── Рисование ───────────────────────────────────────────────────────


def _u(a: float, b: float) -> float:
    return _rnd.uniform(a, b)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Шрифт, встроенный в Pillow (FreeType, Pillow ≥ 10.1); без FreeType —
    растровый по умолчанию: мелкий, но картинка всё равно соберётся.
    """
    try:
        return ImageFont.load_default(size=size)
    except (OSError, TypeError, ImportError):
        return ImageFont.load_default()


def _ink() -> Color:
    """Тёмный цвет символа: синий, зелёный, бордовый или графит."""
    return _rnd.choice(
        [
            (_rnd.randint(20, 60), _rnd.randint(40, 80), _rnd.randint(120, 170)),
            (_rnd.randint(20, 50), _rnd.randint(90, 120), _rnd.randint(50, 80)),
            (_rnd.randint(120, 160), _rnd.randint(20, 50), _rnd.randint(40, 70)),
            (_rnd.randint(30, 60), _rnd.randint(30, 60), _rnd.randint(40, 70)),
        ]
    )


def render(text: str) -> bytes:
    """PNG WIDTH×HEIGHT с текстом."""
    w, h = WIDTH * _SS, HEIGHT * _SS
    paper: Color = (_rnd.randint(235, 250), _rnd.randint(235, 250), _rnd.randint(230, 248))
    image = Image.new("RGB", (w, h), paper)
    draw = ImageDraw.Draw(image)

    # Фон: мелкие точки и бледные штрихи
    for _ in range(500):
        tone = _rnd.randint(170, 225)
        draw.point((_rnd.randrange(w), _rnd.randrange(h)), fill=(tone, tone, tone))

    for _ in range(6):
        tone = _rnd.randint(195, 225)
        draw.line(
            [(_u(0, w), _u(0, h)), (_u(0, w), _u(0, h))],
            fill=(tone, tone, _rnd.randint(200, 235)),
            width=2,
        )

    # Символы: каждый на своём слое — свой размер, наклон и цвет
    step = w / (len(text) + 0.6)
    x = step * 0.3

    for char in text:
        size = int(h * _u(0.56, 0.66))
        layer = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(
            (size, size), char, font=_font(size), fill=(*_ink(), 255), anchor="mm"
        )
        layer = layer.rotate(_u(-28, 28), resample=Image.Resampling.BICUBIC)
        top = int(h / 2 - size + _u(-h * 0.05, h * 0.05))
        image.paste(layer, (int(x + step / 2 - size + _u(-6, 6)), top), layer)
        x += step * _u(0.95, 1.05)

    image = _wave(image, paper)
    draw = ImageDraw.Draw(image)

    # Поверх: кривые через весь текст тем же цветом, что символы
    for _ in range(2):
        _curve(draw, w, h, _ink())

    image = image.filter(ImageFilter.SMOOTH)
    image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)

    return buffer.getvalue()


def _wave(image: Image.Image, paper: Color) -> Image.Image:
    """Сдвиг столбцов по синусоиде: строка символов «плывёт»."""
    w, h = image.size
    out = Image.new("RGB", (w, h), paper)
    amplitude = h * _u(0.03, 0.06)
    period = w / _u(1.2, 2.2)
    phase = _u(0, math.tau)

    for x in range(0, w, 2):
        dy = int(amplitude * math.sin(math.tau * x / period + phase))
        out.paste(image.crop((x, 0, x + 2, h)), (x, dy))

    return out


def _curve(draw: ImageDraw.ImageDraw, w: int, h: int, color: Color) -> None:
    amplitude = h * _u(0.12, 0.25)
    period = w / _u(0.6, 1.4)
    phase = _u(0, math.tau)
    base = h * _u(0.35, 0.65)
    points = [
        (float(x), base + amplitude * math.sin(math.tau * x / period + phase))
        for x in range(0, w + 8, 8)
    ]
    draw.line(points, fill=color, width=_rnd.randint(2, 4), joint="curve")
