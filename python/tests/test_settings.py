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


АДРЕС_БАЗЫ = (
    "import django; django.setup(); from django.conf import settings; "
    "print(settings.DATABASES['default']['USER'])"
)


def _пользователь_базы(**env: str) -> str:
    окружение = {k: v for k, v in os.environ.items() if not k.endswith("DATABASE_URL")}

    return subprocess.run(
        [sys.executable, "-c", АДРЕС_БАЗЫ],
        cwd=КОРЕНЬ,
        env={
            **окружение,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(КОРЕНЬ),
            **env,
        },
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_своя_роль_python_важнее_общего_адреса():
    """
    На Render у службы может быть общий DATABASE_URL — с ролью Laravel.
    Своя роль Python с узкими правами обязана его перебить, иначе
    ограничение прав молча не действовало бы.
    """
    assert (
        _пользователь_базы(
            DJANGO_DATABASE_URL="postgres://savdex_django:x@db/savdex",
            DATABASE_URL="postgres://laravel:x@db/savdex",
        )
        == "savdex_django"
    )


def test_без_своей_роли_общий_адрес():
    assert _пользователь_базы(DATABASE_URL="postgres://laravel:x@db/savdex") == "laravel"
