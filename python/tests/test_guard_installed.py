"""
Предохранитель включён в настоящем процессе, а не только в тестах.

Написан после того, как выяснилось: предохранители из первой правки
этапа 0 в работающем приложении не срабатывали вовсе. Получатель
сигнала `connection_created` регистрируется при импорте модуля,
а импортировать его было некому — ссылки в DATABASE_ROUTERS для
этого мало, маршрутизатор создаётся лениво, уже после соединения.

Все прежние проверки при этом проходили: тестовый файл импортирует
`savdex.guards` сам, и внутри pytest обёртка была на месте. Поэтому
здесь отдельный процесс — иначе та же ошибка вернётся незамеченной.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parent.parent

ПРОБА = """
import django
django.setup()

from django.db import connection

connection.ensure_connection()
print("обёрток:", len(connection.execute_wrappers))

try:
    with connection.cursor() as cursor:
        cursor.execute("insert into jobs (id) values (1)")
except Exception as error:
    print("отказ:", type(error).__name__)
else:
    print("отказа не было")
"""


def _в_отдельном_процессе() -> str:
    окружение = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "savdex.settings",
        # SQLite, чтобы проверке не требовалась поднятая база:
        # предохранитель разбирает текст запроса и до базы его
        # не доводит
        "DATABASE_URL": "sqlite://:memory:",
        "PYTHONPATH": str(КОРЕНЬ),
    }

    готово = subprocess.run(
        [sys.executable, "-c", ПРОБА],
        capture_output=True,
        text=True,
        cwd=КОРЕНЬ,
        env=окружение,
        check=True,
    )

    return готово.stdout


def test_обёртка_висит_на_соединении():
    assert "обёрток: 1" in _в_отдельном_процессе()


def test_запись_в_чужую_таблицу_отказывает():
    вывод = _в_отдельном_процессе()

    assert "отказ: WriteToForeignTableError" in вывод
    assert "отказа не было" not in вывод


ПРОБА_БЛОК = """
import django
django.setup()

from django.db import connection

def watch(execute, sql, params, many, context):
    return execute(sql, params, many, context)

# Соединение открывается внутри блока — как у наблюдателя медленных
# запросов, который оборачивает весь запрос к сайту
connection.close()
with connection.execute_wrapper(watch):
    with connection.cursor() as cursor:
        cursor.execute("select 1")

from savdex.guards import guard
print("предохранитель:", guard in connection.execute_wrappers)
print("наблюдатель:", watch in connection.execute_wrappers)

try:
    with connection.cursor() as cursor:
        cursor.execute("insert into jobs (id) values (1)")
except Exception as error:
    print("отказ:", type(error).__name__)
else:
    print("отказа не было")
"""


def test_предохранитель_переживает_блок_с_обёрткой():
    """
    Соединение открылось внутри `execute_wrapper(...)`: на выходе блок
    снимает свою обёртку, а не предохранитель. Раньше защита пропадала
    после первого запроса на новом соединении.
    """
    окружение = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "savdex.settings",
        "DATABASE_URL": "sqlite://:memory:",
        "PYTHONPATH": str(КОРЕНЬ),
    }
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА_БЛОК],
        capture_output=True,
        text=True,
        cwd=КОРЕНЬ,
        env=окружение,
        check=True,
    ).stdout

    assert "предохранитель: True" in вывод
    assert "наблюдатель: False" in вывод
    assert "отказ: WriteToForeignTableError" in вывод
