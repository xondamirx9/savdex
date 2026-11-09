"""
Ограничения частоты (вход, регистрация, формы — savdex/web/forms.py,
_throttle) считают только в файловом кэше: с другим CACHE_STORE они
молча выключены. Боевой и тестовый сайт без них не запускаются — это
проверяет сам код (savdex/wsgi.py, его загружает gunicorn), а не только
образ и скрипт запуска. Команды manage.py запросов не принимают — им
можно.

Настройки читаются при запуске, поэтому каждый случай — отдельный процесс.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = Path(__file__).resolve().parent.parent


def _запуск(**env: str) -> subprocess.CompletedProcess[str]:
    окружение = {k: v for k, v in os.environ.items() if k not in ("CACHE_STORE", "APP_ENV")}
    окружение |= {"DJANGO_SECRET_KEY": "test-secret", "PYTHONPATH": str(PYTHON), **env}

    return subprocess.run(
        [sys.executable, "-c", "import savdex.wsgi; print('ok')"],
        cwd=PYTHON,
        env=окружение,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "env",
    [
        {"APP_ENV": "production", "CACHE_STORE": "array"},
        {"APP_ENV": "production", "CACHE_STORE": "database"},
        # Без CACHE_STORE — умолчание database, лимиты выключены
        {"APP_ENV": "production"},
        {"APP_ENV": "staging", "CACHE_STORE": "redis"},
    ],
)
def test_боевой_без_файлового_кэша_не_запускается(env):
    итог = _запуск(**env)

    assert итог.returncode != 0, итог.stdout
    assert "CACHE_STORE" in итог.stderr


@pytest.mark.parametrize(
    "env",
    [
        {"APP_ENV": "production", "CACHE_STORE": "file"},
        {"APP_ENV": "staging", "CACHE_STORE": "file"},
        # Разработчик и проверки — любое хранилище
        {"APP_ENV": "local", "CACHE_STORE": "array"},
        {"APP_ENV": "testing"},
    ],
)
def test_с_файловым_кэшем_и_у_разработчика_запускается(env):
    итог = _запуск(**env)

    assert итог.returncode == 0, итог.stderr
    assert итог.stdout.strip().endswith("ok")
