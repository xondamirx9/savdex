"""
Выгрузка Python против выгрузки PHP — на одной и той же базе.

Самая важная проверка переноса, и вот почему. Собственная сверка
выгрузки перечитывает базу тем же путём, каким писала, и ошибку этого
пути не видит: с неверным чтением полей JSON Python-версия честно
отвечала «все листы сошлись», а ячейки при этом расходились с PHP.
Поймать такое может только сравнение двух реализаций.

Порядок: схема строится миграциями Laravel (правило 4.2 — схема его),
база наполняется tests/fixtures/export_parity_fill.php с крайними
случаями, затем обе команды выгружают, и книги сравниваются ячейка
в ячейку.

Нужны PHP с установленными зависимостями и PostgreSQL. Адрес базы —
SAVDEX_PARITY_PG_URL; без неё проверка пропускается. В CI обе вещи
есть.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

from .xlsx_diff import diff

КОРЕНЬ = Path(__file__).resolve().parents[2]
PYTHON = Path(__file__).resolve().parents[1]
АДРЕС = os.environ.get("SAVDEX_PARITY_PG_URL", "")

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — сравнение требует PHP и PostgreSQL",
)


def _проверочная_ли(url: str) -> bool:
    """
    База пересоздаётся с нуля — только та, что названа проверочной.

    migrate:fresh стирает всё. Переменную окружения легко перепутать,
    и цена ошибки здесь — боевая база. Поэтому имя базы обязано
    содержать «test».
    """
    return "test" in urlparse(url).path.lstrip("/")


def _laravel(*command: str) -> subprocess.CompletedProcess[str]:
    окружение = {
        **os.environ,
        "DB_CONNECTION": "pgsql",
        "DB_URL": АДРЕС,
        "CACHE_STORE": "array",
        "SESSION_DRIVER": "array",
        "QUEUE_CONNECTION": "sync",
        "MACHINE_TRANSLATION_ENABLED": "false",
    }

    return subprocess.run(
        ["php", *command],
        cwd=КОРЕНЬ,
        env=окружение,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture(scope="module")
def выгрузки(tmp_path_factory):
    if not _проверочная_ли(АДРЕС):
        pytest.fail(
            "SAVDEX_PARITY_PG_URL ведёт в базу без «test» в имени. "
            "Сравнение стирает базу целиком — отказываюсь."
        )

    _laravel("artisan", "migrate:fresh", "--force")
    _laravel("artisan", "db:seed", "--force")
    _laravel("python/tests/fixtures/export_parity_fill.php")

    php_dir = tmp_path_factory.mktemp("php")
    py_dir = tmp_path_factory.mktemp("python")

    php = _laravel("artisan", "savdex:export-xlsx", f"--dir={php_dir}")

    python = subprocess.run(
        [sys.executable, "manage.py", "export_xlsx", f"--dir={py_dir}"],
        cwd=PYTHON,
        env={**os.environ, "DATABASE_URL": АДРЕС},
        capture_output=True,
        text=True,
        check=True,
    )

    return php_dir, py_dir, php.stdout, python.stdout


def test_адрес_проверочной_базы_распознаётся():
    assert _проверочная_ли("postgres://u:p@h:5432/savdex_test")
    assert not _проверочная_ли("postgres://u:p@h:5432/savdex")


def test_обе_выгрузки_сошлись_сами_с_собой(выгрузки):
    _, _, php, python = выгрузки

    assert "Все листы сошлись" in php
    assert "Все листы сошлись" in python


@pytest.mark.parametrize("книга", ["companies", "listings"])
def test_книги_совпадают_ячейка_в_ячейку(выгрузки, книга):
    php_dir, py_dir, _, _ = выгрузки

    php = next(php_dir.glob(f"savdex-{книга}-*.xlsx"))
    python = next(py_dir.glob(f"savdex-{книга}-*.xlsx"))

    assert diff(php, python) == []


def test_крайние_случаи_действительно_в_выгрузке(выгрузки):
    """
    Проверка самой проверки.

    Без крайних случаев сравнение проходило и с ошибкой в чтении JSON.
    Если наполнение однажды перестанет их создавать, сравнение снова
    станет слепым — этот тест заметит это первым.
    """
    from openpyxl import load_workbook

    php_dir, _, _, _ = выгрузки
    listings = load_workbook(next(php_dir.glob("savdex-listings-*.xlsx")))["Объявления"]
    values = [str(cell.value) for row in listings.iter_rows() for cell in row if cell.value]

    assert any("\\u0446" in v for v in values), "нет JSON с экранированной кириллицей"
    assert any('"en":  "Cement' in v for v in values), "нет JSON с неровными пробелами"

    companies = load_workbook(next(php_dir.glob("savdex-companies-*.xlsx")))["Компании"]
    cells = [str(cell.value) for row in companies.iter_rows() for cell in row if cell.value]

    assert any(v.endswith("[…обрезано]") for v in cells), "нет обрезанного длинного текста"
    assert "000123456" in cells, "нет ИНН с ведущими нулями"
