"""
Выдача доступа в админку: PHP-команда против Python-команды на одной базе.

Первая перенесённая команда, которая пишет. Поэтому сверяется не вывод,
а итог в базе: на одних и тех же входах обе команды обязаны оставить
в users одинаковые строки (кроме соли в хеше и времени), одинаково
отказать и одинаково ответить. И отдельно — главный вопрос: пустит ли
Laravel администратора, заведённого Python-версией.

Каждый случай готовится дважды с нуля: состояние → PHP → снимок строки,
то же состояние → Python → снимок, затем сравнение.

Нужны PHP с зависимостями и PostgreSQL (SAVDEX_PARITY_PG_URL); без
них проверка пропускается. В CI есть обе вещи.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

КОРЕНЬ = Path(__file__).resolve().parents[2]
PYTHON = Path(__file__).resolve().parents[1]
АДРЕС = os.environ.get("SAVDEX_PARITY_PG_URL", "")

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — сравнение требует PHP и PostgreSQL",
)

#: Общее окружение обеих команд: одна база, один адрес сайта, одна
#: стоимость bcrypt (малая — ради скорости; совпадение цены тоже сверяется)
ОКРУЖЕНИЕ = {
    **os.environ,
    "DB_CONNECTION": "pgsql",
    "DB_URL": АДРЕС,
    "DATABASE_URL": АДРЕС,
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "QUEUE_CONNECTION": "sync",
    "APP_URL": "https://savdex.uz",
    "BCRYPT_ROUNDS": "4",
}

#: Столбцы, которые обязаны совпасть буква в букву
СТОЛБЦЫ = (
    "name",
    "email",
    "is_admin",
    "admin_role",
    "admin_permissions",
    "status",
    "must_change_password",
    "locale",
    "company_role",
    "company_id",
    "deleted_at",
)


@pytest.fixture(scope="module", autouse=True)
def база():
    if "test" not in urlparse(АДРЕС).path:
        pytest.fail("SAVDEX_PARITY_PG_URL ведёт в базу без «test» в имени — отказываюсь стирать")

    subprocess.run(
        ["php", "artisan", "migrate:fresh", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        check=True,
    )


def _sql(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        курсор = соединение.execute(query, params or [])

        return курсор.fetchall() if курсор.description else []


def _php(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["php", "artisan", "savdex:admin", *args],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        text=True,
    )


def _python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", "admin", *args],
        cwd=PYTHON,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        text=True,
    )


def _строка(email: str) -> dict[str, Any] | None:
    rows = _sql(
        f"select {', '.join(СТОЛБЦЫ)}, password, email_verified_at, created_at, updated_at "
        "from users where email = %s",
        [email],
    )

    if not rows:
        return None

    row = dict(
        zip(
            (*СТОЛБЦЫ, "password", "email_verified_at", "created_at", "updated_at"),
            rows[0],
            strict=True,
        )
    )

    # Соль у каждого хеша своя; совпасть обязаны алгоритм и цена
    row["password"] = row["password"][:7]

    return row


def _вывод(text: str) -> str:
    """Вывод без пароля и с нормализованными пробелами (SymfonyStyle их схлопывает)."""
    text = re.sub(r"(\| Пароль\s+\| )\S+", r"\1***", text)

    return re.sub(r"[ \t]+", " ", text).strip()


def _сравнить(
    подготовка: list[str], email: str, *args: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Одно и то же состояние → обе команды → итоги для сравнения."""
    итоги = []

    for команда in (_php, _python):
        _sql("delete from users where email = %s", [email])

        for query in подготовка:
            _sql(query)

        до = _строка(email)
        результат = команда(*args)
        после = _строка(email)

        итоги.append(
            {
                "код": результат.returncode,
                # Одним текстом: Laravel печатает ошибки в stdout,
                # Python-команды — в stderr, как положено. Слова те же
                "вывод": _вывод(результат.stdout + результат.stderr),
                "строка": после,
                "до": до,
            }
        )

    return итоги[0], итоги[1]


def _без_времени(итог: dict[str, Any]) -> dict[str, Any]:
    итог = dict(итог)

    if итог["строка"] is not None:
        строка = dict(итог["строка"])

        for поле in ("created_at", "updated_at"):
            строка[поле] = строка[поле] is not None

        # Подтверждение: у новых — «сейчас», у подтверждённых — прежнее
        if итог["до"] is None or итог["до"]["email_verified_at"] is None:
            строка["email_verified_at"] = строка["email_verified_at"] is not None

        итог["строка"] = строка

    итог.pop("до")

    return итог


СУЩЕСТВУЮЩИЙ = (
    "insert into users (name, email, password, status, email_verified_at, created_at, updated_at) "
    "values ('Старый', 'old@savdex.uz', 'x', 'blocked', {verified}, now(), now())"
)


@pytest.mark.parametrize(
    ("подготовка", "email", "args"),
    [
        pytest.param(
            [],
            "boss@savdex.uz",
            ("boss@savdex.uz", "--password=Savdex2026!x"),
            id="новый суперадмин",
        ),
        pytest.param(
            [],
            "fin@savdex.uz",
            ("fin@savdex.uz", "--role=finance", "--name=Финансы Ташкент"),
            id="новый с ролью и именем",
        ),
        pytest.param([], "mod@savdex.uz", ("mod@savdex.uz", "--moderator"), id="модератор"),
        pytest.param(
            [],
            "caps@savdex.uz",
            ("  CAPS@Savdex.UZ ", "--role=support"),
            id="почта с пробелами и прописными",
        ),
        pytest.param(
            [],
            "zero@savdex.uz",
            ("zero@savdex.uz", "--password=0", "--role=0", "--name=0"),
            id="ноль как пусто",
        ),
        pytest.param(
            [СУЩЕСТВУЮЩИЙ.format(verified="null")],
            "old@savdex.uz",
            ("old@savdex.uz", "--role=sales"),
            id="существующий заблокированный без подтверждения",
        ),
        pytest.param(
            [СУЩЕСТВУЮЩИЙ.format(verified="'2026-01-02 03:04:05'")],
            "old@savdex.uz",
            ("old@savdex.uz",),
            id="существующий подтверждённый",
        ),
        pytest.param(
            [
                "insert into users (name, email, password, created_at, updated_at, deleted_at) "
                "values ('Ушёл', 'gone@savdex.uz', 'x', now(), now(), '2026-05-06 07:08:09')"
            ],
            "gone@savdex.uz",
            ("gone@savdex.uz",),
            id="удалённая учётка",
        ),
        pytest.param(
            [], "new@savdex.uz", ("new@savdex.uz", "--role=sales-manager"), id="неизвестная роль"
        ),
        pytest.param([], "не-почта", ("не-почта",), id="не почта"),
        pytest.param([], "a@b", ("a@b",), id="почта без домена верхнего уровня"),
    ],
)
def test_обе_команды_оставляют_одно_и_то_же(подготовка, email, args):
    php, python = _сравнить(подготовка, email, *args)

    assert _без_времени(python) == _без_времени(php)


def test_случаи_различают():
    """Сверка слепа, если все случаи кончаются одинаково — проверка самой проверки."""
    удачный = _php("check-ok@savdex.uz", "--password=Savdex2026!x")
    неудачный = _php("check-bad@savdex.uz", "--role=нет")

    assert удачный.returncode == 0
    assert неудачный.returncode != 0


def _laravel_о(email: str, password: str) -> dict[str, Any]:
    вывод = subprocess.run(
        ["php", "python/tests/fixtures/admin_probe.php", email, password],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    return json.loads(вывод)


def test_laravel_пускает_администратора_от_python():
    """
    Главное: пароль, выданный Python-версией, принимает сам Laravel —
    той же проверкой, что при входе, — и видит того же администратора,
    что после PHP-команды.
    """
    итоги = {}

    for имя, команда in (("php", _php), ("python", _python)):
        email = f"login-{имя}@savdex.uz"
        _sql("delete from users where email = %s", [email])

        результат = команда(email, "--role=content_manager")
        assert результат.returncode == 0, результат.stderr

        пароль = re.search(r"\| Пароль\s+\| (\S+)", результат.stdout)
        assert пароль is not None, результат.stdout
        assert len(пароль.group(1)) == 14

        итоги[имя] = _laravel_о(email, пароль.group(1))

    assert итоги["python"]["password_ok"] is True, итоги["python"]
    assert итоги["python"] == итоги["php"]
