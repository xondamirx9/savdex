"""
Технические работы: настройка maintenance_until — время окончания по
Ташкенту. Пока оно впереди, общий проп maintenance несёт его в UTC, и
сайт закрывает заставка; пусто, не время или прошло — None.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from savdex.web.shared import maintenance

#: 13.10.2026 12:00 UTC = 17:00 по Ташкенту
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "until"),
    [
        ("2026-10-13 18:30", "2026-10-13T13:30:00Z"),
        ("2026-10-13 18:30:15", "2026-10-13T13:30:15Z"),
        ("2026-10-13T18:30", "2026-10-13T13:30:00Z"),
        ("13.10.2026 18:30", "2026-10-13T13:30:00Z"),
        ("  2026-10-14 02:00 ", "2026-10-13T21:00:00Z"),
    ],
)
def test_работы_впереди(value, until):
    assert maintenance({"maintenance_until": value}, NOW) == {"until": until}


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "завтра утром",
        "2026-10-13 17:00",  # ровно сейчас — уже не показываем
        "2026-10-13 16:59",
        "2026-10-12 23:00",
    ],
)
def test_работ_нет(value):
    values = {} if value is None else {"maintenance_until": value}

    assert maintenance(values, NOW) is None
