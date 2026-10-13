"""
Второй фактор входа в админку — страницы (логика кодов — savdex/twofactor.py).

- /py/admin/2fa/verify/ — ввод кода после пароля (или после входа на
  сайт): как страница входа, до входа в админку. Верный код — кука входа
  с отметкой «код введён» и туда, куда шёл.
- /py/admin/2fa/setup/ — «Вход по коду» для вошедшего сотрудника: QR-код
  для приложения, первый код — подключено; отключить — тоже кодом
  (если код не обязателен, SAVDEX_ADMIN_2FA_REQUIRED).

Попытки ввода кода считает тот же замок, что и пароль (login_attempts,
ключ «2fa:<номер>»): пять неудач с адреса за 15 минут — пауза.
"""

from __future__ import annotations

import math
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseBase, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache

from savdex import access, adminpanel, bridge, twofactor

WRONG = "Неверный код. Введите шесть цифр из приложения — код меняется каждые 30 секунд."


def _throttle(request: HttpRequest, admin: access.Admin) -> Any:  # noqa: ANN401
    from savdex.audit import client_ip
    from savdex.web.auth_actions import LoginThrottle

    return LoginThrottle(f"2fa:{admin.id}", client_ip(request) or "")


def _locked_message(throttle: Any) -> str:  # noqa: ANN401
    minutes = max(1, math.ceil(throttle.seconds_until_unlock() / 60))

    return f"Слишком много неверных кодов. Попробуйте через {minutes} мин."


def _agent(request: HttpRequest) -> str | None:
    return request.headers.get("User-Agent")


def _passed(response: HttpResponse, request: HttpRequest, admin: access.Admin) -> HttpResponse:
    """Код введён — кука входа с этой отметкой."""
    response.set_cookie(
        bridge.COOKIE,
        bridge.session_cookie(admin.id, admin.stamp, mfa=True),
        max_age=bridge.SESSION_TTL,
        path=bridge.COOKIE_PATH,
        secure=request.is_secure(),
        httponly=True,
        samesite="Lax",
    )

    return response


def _base(request: HttpRequest) -> dict[str, Any]:
    from savdex.adminsite import _theme_version, site
    from savdex.web import shared

    return {
        "site_header": site.site_header,
        "site_title": site.site_title,
        "site_url": site.site_url,
        "savdex_logo": shared.appearance_logo(shared.settings_values()),
        "savdex_theme_version": _theme_version(),
    }


@never_cache
def verify(request: HttpRequest) -> HttpResponseBase:
    """Ввод кода второго фактора после пароля."""
    admin, _, mfa, refusal = adminpanel.resolve(request)

    if refusal is not None:
        return refusal

    assert admin is not None
    target = bridge.safe_next(request.GET.get("next") or request.POST.get("next"))

    if not admin.two_factor or mfa:
        return HttpResponseRedirect(target)

    error, status = "", 200

    if request.method == "POST":
        throttle = _throttle(request, admin)

        if throttle.locked():
            error, status = _locked_message(throttle), 429
        elif twofactor.verify(admin.id, str(request.POST.get("code", ""))):
            throttle.record_success(_agent(request))

            return _passed(HttpResponseRedirect(target), request, admin)
        else:
            throttle.record_failure(_agent(request))
            error, status = WRONG, 422

    return TemplateResponse(
        request,
        "admin/savdex_2fa_verify.html",
        {
            **_base(request),
            "has_permission": False,
            "is_popup": False,
            "is_nav_sidebar_enabled": False,
            "title": "Код входа",
            "next": target,
            "error": error,
        },
        status=status,
    )


@never_cache
def setup(request: HttpRequest) -> HttpResponse:
    """«Вход по коду»: подключить или отключить второй фактор."""
    from savdex.adminsite import site

    admin: access.Admin = request.admin  # type: ignore[attr-defined]
    error, status, done = "", 200, ""

    if request.method == "POST":
        throttle = _throttle(request, admin)
        code = str(request.POST.get("code", ""))
        act = request.POST.get("act")

        if throttle.locked():
            error, status = _locked_message(throttle), 429
        elif act == "confirm" and not admin.two_factor:
            if twofactor.confirm(admin.id, code):
                throttle.record_success(_agent(request))
                response = HttpResponseRedirect(adminpanel.SETUP + "?done=on")

                return _passed(response, request, admin)

            throttle.record_failure(_agent(request))
            error, status = WRONG, 422
        elif act == "disable" and admin.two_factor and not twofactor.required():
            if twofactor.verify(admin.id, code):
                throttle.record_success(_agent(request))
                twofactor.reset(admin.id)

                return HttpResponseRedirect(adminpanel.SETUP + "?done=off")

            throttle.record_failure(_agent(request))
            error, status = WRONG, 422

    done = {"on": "Вход по коду подключён.", "off": "Вход по коду отключён."}.get(
        str(request.GET.get("done", "")), ""
    )
    secret = None if admin.two_factor else twofactor.pending_secret(admin.id)

    return TemplateResponse(
        request,
        "admin/savdex_2fa_setup.html",
        {
            **site.each_context(request),
            "title": "Вход по коду",
            "enrolled": admin.two_factor,
            "required": twofactor.required(),
            "secret": secret,
            # Ключ группами по четыре — так его проще перепечатать руками
            "secret_groups": " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))
            if secret
            else "",
            "uri": twofactor.otpauth_uri(admin.email, secret) if secret else "",
            "error": error,
            "done": done,
        },
        status=status,
    )
