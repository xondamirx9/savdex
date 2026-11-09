"""
Секреты выкладки (.github/workflows): боевые ключи — в защищённом
окружении production (одобрение владельца, только основная ветка), а не
на уровне репозитория, где их достаёт любая ветка и код из PR.

Проверка по тексту workflow: PyYAML в зависимостях проекта нет, а
структура, которую надо удержать, видна по отступам.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
MAIN = "refs/heads/claude/website-copy-new-design-xaxsr0"


def _текст(имя: str) -> str:
    return (WORKFLOWS / имя).read_text(encoding="utf-8")


def _задачи(текст: str) -> dict[str, str]:
    """Задачи workflow: имя → её строки (отступ задачи — два пробела)."""
    после = текст.split("\njobs:\n", 1)[1]
    части = re.split(r"^  ([A-Za-z0-9_-]+):\n", после, flags=re.M)

    return dict(zip(части[1::2], части[2::2], strict=True))


def _окружение(задача: str) -> str | None:
    найдено = re.search(r"^    environment:\n      name: (\S+)", задача, re.M)

    return найдено.group(1) if найдено else None


@pytest.mark.parametrize("имя", ["prod.yml", "alerts.yml"])
def test_секреты_только_нужному_шагу(имя):
    """Секрет — в env шага (отступ 10), не в env всей задачи (отступ 6)."""
    for номер, строка in enumerate(_текст(имя).splitlines(), 1):
        if "${{ secrets." in строка:
            отступ = len(строка) - len(строка.lstrip())
            assert отступ >= 10, f"{имя}:{номер}: секрет на уровне задачи"


@pytest.mark.parametrize("имя", ["prod.yml", "alerts.yml"])
def test_секреты_только_в_окружении_production(имя):
    for название, задача in _задачи(_текст(имя)).items():
        if "${{ secrets." in задача:
            assert _окружение(задача) == "production", f"{имя}: {название}"


def test_prod_только_с_основной_ветки():
    задачи = _задачи(_текст("prod.yml"))

    assert MAIN in задачи["plan"].split("\n    runs-on:", 1)[0]
    assert "needs: plan" in задачи["deploy"]


def test_тревоги_pr_без_секретов():
    """Код из PR проверяет только файл правил; ключи — задаче основной ветки."""
    задачи = _задачи(_текст("alerts.yml"))

    for название, задача in задачи.items():
        if "secrets." in задача or "${{ github.token }}" in задача:
            условие = задача.split("\n    runs-on:", 1)[0]
            assert "github.event_name != 'pull_request'" in условие, название
            assert MAIN in условие, название
