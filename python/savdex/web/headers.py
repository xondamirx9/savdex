"""
Защитные заголовки, которых SecurityMiddleware Django не ставит сам
(настройки HTTPS, HSTS и прочего — savdex/settings.py).

- Content-Security-Policy: frame-ancestors 'self' — современная замена
  X-Frame-Options: страницы площадки нельзя встроить в чужой сайт и
  подсунуть под невидимую кнопку. Остальной CSP не задаётся: сторонние
  счётчики, карты и платёжная форма потребовали бы списка, который легко
  сломать.
- Permissions-Policy — камера, микрофон и прочее площадке не нужны;
  геолокация — только своему сайту.
Ответ, где заголовок уже стоит, не трогается.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

FRAME_ANCESTORS = "frame-ancestors 'self'"
PERMISSIONS = "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)"


class SecurityHeadersMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = FRAME_ANCESTORS

        if "Permissions-Policy" not in response:
            response["Permissions-Policy"] = PERMISSIONS

        return response
