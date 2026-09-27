"""
Ограничение частоты — копия throttle у Laravel (ThrottleRequests и
RateLimiter), с общим счётчиком.

Laravel считает запросы одного посетителя в файловом кэше (на боевом
CACHE_STORE=file, та же служба): ключ — sha1 номера пользователя или,
у гостя, sha1(«домен маршрута|IP»). Маршрут в ключ не входит, так что
у всех адресов с throttle счётчик один — и у Django тоже должен быть
тот же, иначе половина сайта на Django удваивала бы лимит. Django
пишет те же файлы тем же форматом (laravel_cache).

Порядок, как у ThrottleRequests::handleRequest: сначала проверка
«слишком много» (тогда 429 без засчитывания), потом засчитать, потом
страница — с заголовками X-RateLimit-Limit и X-RateLimit-Remaining.
Не файловое хранилище (тесты с array) — ограничения нет: Laravel
считает у себя в памяти, общего счётчика не получится.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import replace

from django.http import HttpRequest, HttpResponse

from savdex import laravel_cache
from savdex.audit import client_ip
from savdex.web import locales
from savdex.web.request import context
from savdex.web.shared import Context

#: RateLimiter::hit($key, 60 * $decayMinutes) — у всех маршрутов сайта минута
DECAY_SECONDS = 60


def signature(ctx: Context, domain: str = "") -> str:
    """ThrottleRequests::resolveRequestSignature."""
    if ctx.visitor.user_id is not None:
        return hashlib.sha1(str(ctx.visitor.user_id).encode()).hexdigest()

    ip = client_ip(ctx.request) or ""

    return hashlib.sha1(f"{domain}|{ip}".encode()).hexdigest()


def attempts(key: str) -> int:
    return laravel_cache._to_int(laravel_cache.get(key) or 0)


def too_many(key: str, max_attempts: int) -> bool:
    """RateLimiter::tooManyAttempts: предел достигнут и окно ещё идёт."""
    if attempts(key) >= max_attempts:
        if laravel_cache.get(f"{key}:timer") is not None:
            return True

        laravel_cache.forget(key)

    return False


def hit(key: str, decay: int = DECAY_SECONDS) -> int:
    """RateLimiter::increment: метка окна, счётчик, +1."""
    laravel_cache.add(f"{key}:timer", int(time.time()) + decay, decay)
    added = laravel_cache.add(key, 0, decay)
    hits = laravel_cache.increment(key)

    if not added and hits == 1:
        laravel_cache.put(key, 1, decay)

    return hits


def throttled(
    request: HttpRequest, max_attempts: int, view: Callable[[Context], HttpResponse]
) -> HttpResponse:
    """
    throttle:max,1 вокруг страницы.

    У Laravel throttle стоит раньше SetLocale и HandleInertiaRequests:
    отказ 429 не уводит на запомненный язык, а страница ошибки собрана
    без общих пропсов, на языке из префикса адреса (views.error bare).
    Заголовки частоты получает любой ответ, в том числе переход на язык.
    """
    from savdex.web.views import error

    first = context(request, redirect=False)

    if isinstance(first, HttpResponse):
        return first

    if not laravel_cache.is_file_store():
        ctx = context(request)

        return ctx if isinstance(ctx, HttpResponse) else view(ctx)

    key = signature(first)

    if too_many(key, max_attempts):
        bare = replace(first, locale=first.url_locale or locales.DEFAULT)
        # Заголовков Retry-After и X-RateLimit-* у отказа нет: Laravel
        # собирает страницу ошибки Inertia заново, и заголовки исключения
        # теряются — Django повторяет
        return error(bare, 429, bare=True)

    hit(key)
    ctx = context(request)
    response = ctx if isinstance(ctx, HttpResponse) else view(ctx)
    response["X-RateLimit-Limit"] = str(max_attempts)
    response["X-RateLimit-Remaining"] = str(max(0, max_attempts - attempts(key)))

    return response
