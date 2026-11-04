"""
Счётчик неверных кодов (savdex/web/code_lock.py) — в настоящем файловом
кэше: параллельные неверные коды считаются все (Ж14).
"""

from __future__ import annotations

import threading
import time

import pytest

from savdex import laravel_cache
from savdex.web import code_lock


@pytest.fixture(autouse=True)
def _кэш(tmp_path, settings) -> None:
    settings.LARAVEL_ROOT = tmp_path


def test_параллельные_изменения_не_теряются() -> None:
    def прибавить(prev: object) -> laravel_cache.Value:
        текущее = prev if isinstance(prev, int) else 0
        time.sleep(0.005)  # окно гонки: между чтением и записью

        return текущее + 1

    потоки = [
        threading.Thread(target=laravel_cache.update, args=("счёт", прибавить, 60))
        for _ in range(20)
    ]
    for поток in потоки:
        поток.start()
    for поток in потоки:
        поток.join()

    assert laravel_cache.get("счёт", any_store=True) == 20


def test_параллельные_неверные_коды_блокируют(monkeypatch) -> None:
    цель = code_lock.phone("+998901112233")
    медленно = laravel_cache._serialize

    def с_задержкой(value: laravel_cache.Value) -> bytes:
        time.sleep(0.01)

        return медленно(value)

    monkeypatch.setattr(laravel_cache, "_serialize", с_задержкой)
    барьер = threading.Barrier(code_lock.MAX_FAILURES)

    def неверный() -> None:
        барьер.wait()
        code_lock.fail(цель)

    потоки = [threading.Thread(target=неверный) for _ in range(code_lock.MAX_FAILURES)]
    for поток in потоки:
        поток.start()
    for поток in потоки:
        поток.join()

    assert code_lock.locked_minutes(цель) == 15
