"""
Свои хосты (settings.ALLOWED_HOSTS): «*» — только у разработчика.

На боевом и тестовом без DJANGO_ALLOWED_HOSTS — домен из APP_URL,
мини-сайты с поддоменами, служебные адреса Render и локальные адреса.
Раньше умолчание было «*»: Django принимал любой Host.

Настройки читаются при запуске, поэтому каждый случай — отдельный процесс.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = Path(__file__).resolve().parent.parent
КОД = "import json; from savdex import settings; print(json.dumps(settings.ALLOWED_HOSTS))"
ЛИШНЕЕ = ("DJANGO_ALLOWED_HOSTS", "APP_URL", "MICROSITE_DOMAIN")


def _хосты(**env: str) -> list[str]:
    окружение = {k: v for k, v in os.environ.items() if k not in ЛИШНЕЕ}
    окружение |= {"DJANGO_SECRET_KEY": "test-secret", "PYTHONPATH": str(PYTHON), **env}
    итог = subprocess.run(
        [sys.executable, "-c", КОД],
        cwd=PYTHON,
        env=окружение,
        capture_output=True,
        text=True,
        check=True,
    )

    return list(json.loads(итог.stdout.splitlines()[-1]))


@pytest.mark.parametrize(
    ("env", "ждём"),
    [
        # Разработчик — любой хост
        ({"APP_ENV": "local"}, ["*"]),
        # Задано явно — ровно оно, с пробелами вокруг запятых
        (
            {"APP_ENV": "production", "DJANGO_ALLOWED_HOSTS": "savdex.uz, www.savdex.uz,"},
            ["savdex.uz", "www.savdex.uz"],
        ),
        # Явное «*» — выбор владельца, не умолчание
        ({"APP_ENV": "production", "DJANGO_ALLOWED_HOSTS": "*"}, ["*"]),
        # Боевой без списка — свой домен и локальные адреса, не «*»
        (
            {"APP_ENV": "production", "APP_URL": "https://savdex.uz"},
            ["localhost", "127.0.0.1", "[::1]", "savdex.uz", ".onrender.com"],
        ),
        (
            {
                "APP_ENV": "staging",
                "APP_URL": "https://staging.savdex.uz/",
                "MICROSITE_DOMAIN": "Savdex.Site",
            },
            [
                "localhost",
                "127.0.0.1",
                "[::1]",
                "staging.savdex.uz",
                ".savdex.site",
                ".onrender.com",
            ],
        ),
    ],
)
def test_свои_хосты(env, ждём):
    assert _хосты(**env) == ждём
