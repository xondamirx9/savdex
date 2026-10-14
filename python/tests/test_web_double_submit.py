"""
Двойной щелчок по форме (savdex/web/actions.form): второй запрос упёрся в
уникальный ключ — назад, а не 500. Прочие нарушения целостности — как были.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import RequestFactory

from savdex.web.actions import form


class _ПричинаError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _вид(sqlstate: str):
    @form()
    def view(request) -> HttpResponse:
        try:
            raise _ПричинаError(sqlstate)
        except _ПричинаError as cause:
            raise IntegrityError("duplicate key") from cause

    return view


def test_уникальный_ключ_назад():
    request = RequestFactory().post(
        "/cabinet/x", HTTP_REFERER="http://testserver/cabinet/favorites"
    )
    response = _вид("23505")(request)

    assert response.status_code == 303
    assert response["Location"] == "http://testserver/cabinet/favorites"


def test_чужой_адрес_не_назад():
    request = RequestFactory().post("/cabinet/x", HTTP_REFERER="https://evil.example/")

    assert _вид("23505")(request)["Location"] == "/"


def test_fetch_получает_409():
    request = RequestFactory().post("/cabinet/x", HTTP_ACCEPT="application/json")

    assert _вид("23505")(request).status_code == 409


def test_прочие_ошибки_целостности_не_глотаются():
    with pytest.raises(IntegrityError):
        _вид("23503")(RequestFactory().post("/cabinet/x"))
