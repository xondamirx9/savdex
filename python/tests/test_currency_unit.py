"""Чтение кэша Laravel без PHP: unserialize() и round() как у PHP."""

from __future__ import annotations

import math

import pytest

from savdex.web.currency import php_round, unserialize


def test_таблица_курсов():
    data = b'a:3:{s:3:"USD";d:12650.37;s:3:"EUR";d:13790;s:3:"JPY";d:86.1;}'

    assert unserialize(data) == {"USD": 12650.37, "EUR": 13790.0, "JPY": 86.1}


def test_скаляры_и_юникод():
    assert unserialize(b"N;") is None
    assert unserialize(b"b:1;") is True
    assert unserialize(b"i:-42;") == -42
    assert math.isinf(unserialize(b"d:INF;"))  # type: ignore[arg-type]
    # Длина строки — в байтах, а не в знаках
    assert unserialize('s:8:"курс";'.encode()) == "курс"
    assert unserialize(b"a:1:{i:0;a:0:{}}") == {0: {}}


@pytest.mark.parametrize("data", [b"", b"x:1;", b's:5:"abc";', b'a:1:{s:1:"a";', b"i:1;;"])
def test_испорченное_значение(data):
    with pytest.raises(ValueError):
        unserialize(data)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1897.5, 1898), (3162.5, 3163), (2.5, 3), (-2.5, -3), (1.49, 1), (0.0, 0)],
)
def test_округление_половины_от_нуля(value, expected):
    assert php_round(value) == expected
