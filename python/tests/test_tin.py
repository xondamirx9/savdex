"""Номер компании по стране (savdex/web/tin.py, ТЗ-02 §3). База не нужна."""

from __future__ import annotations

import pytest

from savdex.web.tin import normalize, problem


@pytest.mark.parametrize(
    ("сырой", "чистый"),
    [
        ("91510107ma6-xxx xxx", "91510107MA6XXXXXX"),
        (" 302 345 678 ", "302345678"),
        ("27aaaaa0000a1z5", "27AAAAA0000A1Z5"),
        (None, None),
    ],
)
def test_нормализация(сырой, чистый):
    assert normalize(сырой) == чистый


@pytest.mark.parametrize(
    ("номер", "страна", "физлицо", "ошибка"),
    [
        # Узбекистан — как раньше
        ("302345678", "uz", False, None),
        ("30234567", "uz", False, "uz_length"),
        ("30234567A", "uz", False, "digits_only"),
        ("12345678901234", "uz", True, None),
        ("12345678901234", "uz", False, "uz_length"),
        ("111111111", "uz", False, "invalid"),
        ("123456789", None, False, "invalid"),
        # Китай: 18 знаков, без I, O, S, V, Z
        # Тестовый номер из приёмки ТЗ-02
        ("91510107MA6XXXXXXX", "cn", False, None),
        ("91510107MA6CKQ8J7N", "cn", False, None),
        ("91510107MA6CKQ8J7", "cn", False, "cn_format"),
        ("91510107MA6CKQ8J7O", "cn", False, "cn_format"),
        ("915101075", "cn", False, "cn_format"),
        # Индия: GSTIN 15 знаков или PAN 10
        ("27AAAAA0000A1Z5", "in", False, None),
        ("AAAAA0000A", "in", False, None),
        ("27AAAAA0000A1Z", "in", False, "in_format"),
        # Казахстан, Россия, Турция
        ("123456789012", "kz", False, None),
        ("12345678901", "kz", False, "kz_length"),
        ("7701234567", "ru", False, None),
        ("770123456789", "ru", False, None),
        ("77012345678", "ru", False, "ru_length"),
        ("1234567890", "tr", False, None),
        ("12345678901", "tr", False, None),
        # Прочие: 5–20 латинских букв и цифр
        ("DE811569869", "de", False, None),
        ("AB12", "de", False, "other_format"),
        ("ПРИВЕТ123", "kg", False, "other_format"),
    ],
)
def test_правила_страны(номер, страна, физлицо, ошибка):
    assert problem(номер, страна, person=физлицо) == ошибка
