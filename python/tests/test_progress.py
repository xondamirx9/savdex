"""Ход переноса (savdex/progress.py): карта таблиц согласована с предохранителем."""

from __future__ import annotations

from collections import Counter

from savdex import progress
from savdex.guards import OWNED_TABLES


def test_каждая_таблица_в_одном_месте_карты():
    listed = [t for stage in progress.STAGES for t in stage.tables] + list(progress.SHARED)
    twice = [t for t, n in Counter(listed).items() if n > 1]

    assert twice == []


def test_у_python_только_таблицы_из_карты():
    """Перенесённая таблица без места в карте не попала бы в счёт."""
    assert OWNED_TABLES <= progress.MOVING
    assert not OWNED_TABLES & progress.SHARED


def test_оставленные_таблицы_принадлежат_своему_этапу():
    for stage in progress.STAGES:
        assert set(stage.kept) <= set(stage.tables), stage.title


def test_счёт_этапов():
    by_number = {p.stage.number: p for p in progress.stage_progress()}

    assert by_number[1].state == "done"
    # Этап 2 сделан целиком: поля категорий и типы продвижения — с шага 73
    # (справочники деплоя), способы оплаты и промокоды — с деньгами (шаг 72)
    assert (by_number[2].done, by_number[2].total, by_number[2].state) == (21, 21, "done")
    # Этап 3 без своих таблиц — по шагам: вход Laravel, первая страница, остальные
    assert (by_number[3].done, by_number[3].total, by_number[3].state) == (3, 3, "done")
    # Деньги — у Django с шага 72
    assert by_number[7].state == "done"
    # Этап 8: журнал, лента, сессии, очередь перевода и кэш — у Django
    assert by_number[6].kept.keys() == {"imports", "exports", "failed_import_rows"}
    assert by_number[8].state == "done"

    # Ничего не перенесено — этап 2 «впереди»
    assert progress.stage_progress(frozenset())[1].state == "ahead"


def test_общий_счёт():
    total = progress.summary()

    assert total["tables_done"] == len(OWNED_TABLES)
    # Служебные таблицы Filament (3 таблицы этапа 6) не переезжают
    assert total["tables_total"] == len(progress.MOVING) - 3
    assert total["percent"] == 100
