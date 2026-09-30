"""
Вход в админку на Django (шаг 67) — вместо страницы входа Filament.

Сотрудник — обычный пользователь площадки с is_admin, и вход у Filament
был входом в ту же сессию Laravel, что у сайта: вошёл в админку — вошёл
и на сайт. Здесь так же: пароль проверяется как у входа на сайт
(savdex/web/guard.py), сессия Laravel пишется той же записью
(guard.login), и сверху — кука разделов Django (savdex/bridge.py).
Поэтому после входа здесь открываются и сайт, и оставшиеся страницы
Filament, а вход на сайт пускает и в админку (adminpanel.AdminMiddleware
узнаёт сотрудника по сессии).

Как у Filament (App\\Filament\\Pages\\Auth\\Login):
- почта без учёта регистра и пробелов по краям;
- пароль — только как введён (без «забытой раскладки» сайта);
- не администратору и заблокированному — «неверная почта или пароль»:
  страница входа в админку не подтверждает, что учётка существует;
- пять попыток в минуту с адреса; плюс общий с сайтом замок по связке
  почта + IP (login_attempts);
- с выданным паролем — сначала его смена на сайте (RequirePasswordChange).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from savdex import bridge

LOGIN = "/py/admin/login/"
WRONG = "Неверная почта или пароль."


def _page(
    request: HttpRequest, *, email: str = "", error: str = "", status: int = 200
) -> TemplateResponse:
    from savdex.adminsite import _theme_version, site
    from savdex.web import session, shared

    started = session.start(request)

    return TemplateResponse(
        request,
        "admin/savdex_login.html",
        {
            # each_context собирает разделы для вошедшего — здесь только шапка
            "site_header": site.site_header,
            "site_title": site.site_title,
            "site_url": site.site_url,
            "has_permission": False,
            "is_popup": False,
            "is_nav_sidebar_enabled": False,
            "savdex_logo": shared.appearance_logo(shared.settings_values()),
            "savdex_theme_version": _theme_version(),
            "title": "Вход в админку",
            "token": started[0].token if started is not None else "",
            "next": bridge.safe_next(request.GET.get("next") or request.POST.get("next")),
            "email": email,
            "error": error,
        },
        status=status,
    )


def _session_cookie(response: HttpResponse, request: HttpRequest, uid: int) -> HttpResponse:
    response.set_cookie(
        bridge.COOKIE,
        bridge.session_cookie(uid),
        max_age=bridge.SESSION_TTL,
        path=bridge.COOKIE_PATH,
        secure=request.is_secure(),
        httponly=True,
        samesite="Lax",
    )

    return response


@never_cache
@csrf_exempt
def login_page(request: HttpRequest) -> HttpResponse:
    """
    /py/admin/login/: форма и вход. CSRF — токеном сессии Laravel, как у
    форм сайта (forms.action), а не джанговским: вход пишет сессию Laravel.
    """
    from django.db import connections

    from savdex.audit import client_ip
    from savdex.web import guard
    from savdex.web.auth_actions import LoginThrottle, _agent, _lockout, _session
    from savdex.web.forms import RefusedError, action, input_of

    if request.method != "POST":
        return _page(request)

    try:
        ctx = action(
            request, auth=False, throttle=5, throttle_minutes=1, throttle_prefix="admin-login"
        )
    except RefusedError as refused:
        return refused.response

    data = input_of(request)
    email = str(data.get("email") or "").strip(" \t\n\r\0\x0b").lower()
    password = str(data.get("password") or "")

    if email == "" or password == "":
        return _page(request, email=email, error="Введите почту и пароль.", status=422)

    throttle = LoginThrottle(email, client_ip(request) or "")

    if throttle.locked():
        return _page(request, email=email, error=_lockout(ctx, throttle), status=422)

    user = guard.attempt(ctx, email, password)
    admin = bridge.load_admin(connections["default"], int(user["id"])) if user is not None else None
    must_change = user is not None and bool(user.get("must_change_password"))

    # User::canAccessPanel: администратор и активен; с выданным паролем
    # пускаем — дальше смена пароля
    if user is None or not user["is_admin"] or user["status"] != "active":
        throttle.record_failure(_agent(request))

        return _page(request, email=email, error=WRONG, status=422)

    store = _session(ctx)
    guard.login(ctx, store, user, bool(data.get("remember")))
    throttle.record_success(_agent(request))
    store.migrate()

    if must_change or admin is None:
        # RequirePasswordChange: выданный пароль — сначала сменить
        return HttpResponseRedirect("/password/change")

    target = bridge.safe_next(data.get("next"))

    return _session_cookie(HttpResponseRedirect(target), request, admin.id)


@require_POST
@never_cache
def logout(request: HttpRequest) -> HttpResponse:
    """
    Выход — из админки и с сайта разом, как у Filament (одна сессия
    Laravel). Форма админки защищена джанговским CSRF.
    """
    from savdex import laravel_session
    from savdex.web import guard, session
    from savdex.web.request import context

    # Без куки сессии Laravel выходить с сайта не из чего — не создаём
    # пустую сессию ради того, чтобы её тут же закрыть
    if laravel_session.cookie_name() in request.COOKIES:
        started = session.start(request)
        ctx = context(request, redirect=False)

        if started is not None and not isinstance(ctx, HttpResponse):
            store = started[0]
            guard.logout(ctx, store)
            store.invalidate()
            store.regenerate_token()

    response = HttpResponseRedirect(LOGIN)
    response.delete_cookie(bridge.COOKIE, path=bridge.COOKIE_PATH)

    return response
