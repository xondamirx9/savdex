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

from savdex.export.compare import diff

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


def test_режим_сверки_для_php_отдаёт_итог(выгрузки, tmp_path):
    """
    Так Python-выгрузку вызывает админка на боевом сервере: рядом
    с PHP-книгами, с --compare-with и --json. Итог — строка с меткой,
    по которой PHP его находит.
    """
    import json

    php_dir, _, _, _ = выгрузки

    python = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "export_xlsx",
            f"--dir={tmp_path}",
            f"--compare-with={php_dir}",
            "--json",
        ],
        cwd=PYTHON,
        env={**os.environ, "DATABASE_URL": АДРЕС},
        capture_output=True,
        text=True,
        check=True,
    )

    line = next(x for x in python.stdout.splitlines() if x.startswith("SAVDEX-RESULT "))
    result = json.loads(line.removeprefix("SAVDEX-RESULT "))

    assert result["self_check"] is True
    assert result["compared"] is True
    assert result["differences"] == 0, result["problems"]


def test_снимок_показывает_базу_на_момент_снимка(выгрузки, tmp_path):
    """
    --snapshot: Python-версия читает базу такой, какой её видел
    вызывающий в момент снимка, а не такой, какой она стала потом.

    Держим снимок открытым, как держит его админка, пока работает
    Python; тем временем «посетители» добавляют по тысяче просмотров
    каждому тендеру. В книге обязаны оказаться прежние числа.
    """
    import psycopg

    with psycopg.connect(АДРЕС) as снимок, psycopg.connect(АДРЕС, autocommit=True) as сайт:
        снимок.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        идентификатор = снимок.execute("select pg_export_snapshot()").fetchone()[0]
        было = dict(снимок.execute("select id, views_count from tenders").fetchall())

        сайт.execute("update tenders set views_count = views_count + 1000")

        subprocess.run(
            [
                sys.executable,
                "manage.py",
                "export_xlsx",
                f"--dir={tmp_path}",
                f"--snapshot={идентификатор}",
            ],
            cwd=PYTHON,
            env={**os.environ, "DATABASE_URL": АДРЕС},
            capture_output=True,
            text=True,
            check=True,
        )

    assert было, "в базе нет тендеров — проверка слепа"
    assert _просмотры_тендеров(tmp_path) == было


def test_чужой_снимок_не_попадает_в_запрос(tmp_path):
    """
    SET TRANSACTION SNAPSHOT не принимает параметров запроса, значение
    вставляется в текст. Поэтому всё, что не похоже на снимок, —
    отказ до обращения к базе.
    """
    python = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "export_xlsx",
            f"--dir={tmp_path}",
            "--snapshot=00000003-0000001B-1'; drop table tenders; --",
        ],
        cwd=PYTHON,
        env={**os.environ, "DATABASE_URL": АДРЕС},
        capture_output=True,
        text=True,
    )

    assert python.returncode == 1
    assert "Неверный снимок базы" in python.stderr
    assert list(tmp_path.iterdir()) == []


def _просмотры_тендеров(каталог: Path) -> dict[int, int]:
    from openpyxl import load_workbook

    for книга in каталог.glob("savdex-*.xlsx"):
        листы = load_workbook(книга, read_only=True)

        if "Тендеры" not in листы.sheetnames:
            continue

        строки = iter(листы["Тендеры"].iter_rows(values_only=True))

        for шапка in строки:
            if "Просмотров" in шапка:
                break

        ид, просмотры = шапка.index("ID"), шапка.index("Просмотров")

        return {int(r[ид]): int(r[просмотры]) for r in строки if r[ид] is not None}

    raise AssertionError("в книгах нет листа «Тендеры»")


def test_выгрузка_на_живой_базе_сходится(выгрузки):
    """
    Выгрузка с кнопки, пока посетители смотрят тендеры и объявления.

    Так и было на боевом сервере: две сверки из пяти «расходились» на
    одну ячейку — «Тендеры, Просмотров: в базе 40, в файле 39». Кто-то
    открыл тендер посреди выгрузки, и сверка сравнивала файл со
    сдвинувшейся базой. Файлы при этом были верны; врала сверка.

    Здесь «посетители» — поток, который без остановки увеличивает
    счётчики просмотров всё время, пока идёт выгрузка. Без единого
    снимка базы сверка расходится почти наверняка; со снимком — никогда.
    """
    import threading

    import psycopg

    стоп = threading.Event()
    обновлений = 0

    def посетители() -> None:
        nonlocal обновлений

        with psycopg.connect(АДРЕС, autocommit=True) as соединение:
            while not стоп.is_set():
                соединение.execute("update tenders set views_count = views_count + 1")
                соединение.execute("update listing_stats set views = views + 1")
                обновлений += 1

    поток = threading.Thread(target=посетители, daemon=True)
    поток.start()

    try:
        итог = _laravel_run("artisan", "savdex:export-run")
    finally:
        стоп.set()
        поток.join(timeout=10)

    assert обновлений > 10, "поток посетителей не успел ничего поменять — проверка слепа"
    assert "Итог: done" in итог, итог
    assert "Сверка с Python: match" in итог, итог
    assert "Книги отдала версия: python" in итог, итог


def test_упавший_python_не_оставляет_без_файла():
    """
    Python — основная версия, но если он упал, администратор всё равно
    получает файл: книги PHP-версии встают на место скачиваемых.
    """
    итог = _laravel_run("artisan", "savdex:export-run", python="/bin/false")

    assert "Итог: done" in итог, итог
    assert "Книги отдала версия: php" in итог, итог
    assert "Сверка с Python: failed" in итог, итог
    assert "savdex-companies-" in итог and "savdex-listings-" in итог, итог


def _laravel_run(*command: str, python: str = sys.executable) -> str:
    """Как _laravel, но без check=True: нужен вывод и при неудаче."""
    окружение = {
        **os.environ,
        "DB_CONNECTION": "pgsql",
        "DB_URL": АДРЕС,
        "CACHE_STORE": "array",
        "SESSION_DRIVER": "array",
        "QUEUE_CONNECTION": "sync",
        "MACHINE_TRANSLATION_ENABLED": "false",
        # Та же Python-версия, что гоняет этот тест
        "SAVDEX_PYTHON": python,
    }

    result = subprocess.run(
        ["php", *command],
        cwd=КОРЕНЬ,
        env=окружение,
        capture_output=True,
        text=True,
    )

    return result.stdout + result.stderr
