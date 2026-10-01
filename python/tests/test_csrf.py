"""
CSRF Django — только для /py/ (savdex/csrf.py).

Формы сайта, адрес которых общий со страницей (/login, /register,
/cabinet/promo…), раньше получали 403 «CSRF cookie not set» от
CsrfViewMiddleware: браузер куки Django не имеет, а токен сессии
проверяет forms.action. Тестовый клиент Django CSRF не проверяет,
поэтому здесь — настоящая проверка (enforce_csrf_checks).
"""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve

from savdex.csrf import SavdexCsrfMiddleware


def проверка(path: str) -> HttpResponse | None:
    request = RequestFactory(enforce_csrf_checks=True).post(path, {})
    # Как у настоящего запроса: у RequestFactory флага пропуска нет
    request._dont_enforce_csrf_checks = False  # type: ignore[attr-defined]
    match = resolve(path)
    middleware = SavdexCsrfMiddleware(lambda r: HttpResponse())

    return middleware.process_view(request, match.func, match.args, match.kwargs)


@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/uz/register",
        "/forgot-password",
        "/password/change",
        "/onboarding/company",
        "/reviews/new",
        "/cabinet/promo",
        "/cabinet/site",
        "/cabinet/company",
        "/cabinet/it-tasks",
        "/cabinet/chats/5",
        "/cabinet/settings/telegram",
    ],
)
def test_формы_сайта_проверяет_токен_сессии(path):
    assert проверка(path) is None


def test_админка_под_защитой_django():
    ответ = проверка("/py/logout")

    assert ответ is not None and ответ.status_code == 403
