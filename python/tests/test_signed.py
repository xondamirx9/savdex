"""Подписанные ссылки (savdex/web/signed.py): чужая подпись — отказ, не ошибка 500."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from savdex.web import signed


@pytest.fixture(autouse=True)
def _ключ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)


def test_своя_подпись_проходит() -> None:
    url = urlsplit(signed.temporary("https://savdex.uz", "/unsubscribe/1", 60))

    assert signed.valid("https://savdex.uz" + url.path, url.query)


@pytest.mark.parametrize("подпись", ["ф" * 64, "%D1%84", "abc"])
def test_чужая_подпись_отказ(подпись: str) -> None:
    url = urlsplit(signed.temporary("https://savdex.uz", "/unsubscribe/1", 60))
    query = url.query.rsplit("signature=", 1)[0] + "signature=" + подпись

    assert signed.valid("https://savdex.uz" + url.path, query) is False
