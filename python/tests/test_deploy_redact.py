"""
Фильтр журналов выкладки (redact() в deploy/server/*.sh): журналы Actions
публичные, строка «| Пароль | … |» из manage.py admin в них не попадает.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "server"

#: Скрипты, которые пишут вывод контейнера (migrate → manage.py admin) в журнал
СКРИПТЫ = ["prod-app.sh", "deploy.sh", "preview.sh", "staging-reset.sh", "staging-restart.sh"]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="нужен bash")


def _redact(скрипт: str, текст: str) -> str:
    source = (DEPLOY / скрипт).read_text(encoding="utf-8")
    функция = re.search(r"^redact\(\) \{\n.*?^\}\n", source, re.S | re.M)
    assert функция is not None, скрипт

    итог = subprocess.run(
        ["bash", "-c", функция.group(0) + "redact"],
        input=текст,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    return итог.stdout


@pytest.mark.parametrize("скрипт", СКРИПТЫ)
def test_пароль_из_таблицы_скрыт(скрипт):
    вывод = (
        "| Адрес  | https://savdex.uz/admin |\n"
        "| Пароль | Ab3dE5gH7jK9mN |\n"
        "| Роль   | Суперадмин |\n"
    )

    итог = _redact(скрипт, вывод)

    assert "Ab3dE5gH7jK9mN" not in итог
    assert "Пароль" in итог and "Суперадмин" in итог
