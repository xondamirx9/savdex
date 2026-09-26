"""
Настройки Django принимают окружение Laravel как есть.

Python-выгрузку запускает PHP и передаёт ей своё окружение целиком.
Переменные с общими именами обязаны прочитаться, даже если у Laravel
для них другие соглашения.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

КОРЕНЬ = Path(__file__).resolve().parent.parent


def запуск(**env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup(); print('ok')"],
        cwd=КОРЕНЬ,
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "DATABASE_URL": "sqlite://:memory:",
            "PYTHONPATH": str(КОРЕНЬ),
            **env,
        },
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "level", ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]
)
def test_уровни_журнала_laravel_не_роняют_django(level):
    """
    LOG_LEVEL=debug из .env Laravel ронял Django ещё на старте.

    Laravel пишет уровни строчными и знает восемь уровней PSR-3,
    журнал Python — пять и прописными.
    """
    result = запуск(LOG_LEVEL=level)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_незнакомый_уровень_не_роняет():
    assert запуск(LOG_LEVEL="verbose").returncode == 0
