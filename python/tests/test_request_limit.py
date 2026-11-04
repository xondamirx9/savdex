"""
Большие загрузки (savdex/web/validation.py, savdex/web/request_limit.py):
тип файла узнаётся по началу, а не по всему файлу; запрос больше предела —
413 до чтения тела.
"""

from __future__ import annotations

import io

from django.http import HttpResponse
from django.test import RequestFactory

from savdex.web import request_limit, validation


class _Файл(io.BytesIO):
    """Загрузка, которая помнит, сколько у неё попросили прочитать."""

    name = "photo.png"

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.просили: list[int | None] = []

    def read(self, size: int | None = -1) -> bytes:  # type: ignore[override]
        self.просили.append(size)
        return super().read(size)


def _png() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(out, "PNG")

    return out.getvalue()


def test_тип_по_началу_файла():
    png = _png()
    файл = _Файл(png + b"\x00" * (validation.SNIFF_BYTES + 1024))

    assert validation._guess_extension(файл) == "png"
    # Весь файл в память не читается
    assert файл.просили == [validation.SNIFF_BYTES]
    assert файл.tell() == 0


def _ответ(length: str) -> HttpResponse:
    middleware = request_limit.RequestLimitMiddleware(lambda request: HttpResponse("ok"))
    request = RequestFactory().post("/cabinet/listings/1/images", data=b"", content_type="x/y")
    request.META["CONTENT_LENGTH"] = length

    return middleware(request)


def test_большой_запрос_413():
    assert _ответ(str(request_limit.limit_bytes() + 1)).status_code == 413


def test_обычный_запрос_проходит():
    assert _ответ("1024").status_code == 200
    assert _ответ("").status_code == 200


def test_свой_предел(monkeypatch):
    monkeypatch.setenv("SAVDEX_MAX_REQUEST_MB", "2")
    assert request_limit.limit_bytes() == 2 * 1024 * 1024
    monkeypatch.setenv("SAVDEX_MAX_REQUEST_MB", "мусор")
    assert request_limit.limit_bytes() == request_limit.DEFAULT_MB * 1024 * 1024
