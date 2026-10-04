"""
Админка — отдельный процесс gunicorn рядом с сайтом (этап 0 плана
переезда): Apache передаёт её адреса на 127.0.0.1:8002, всё остальное —
сайту на 127.0.0.1:8001. Упавшая или занятая админка не трогает витрину.

Сам переход проверяет CI образа (docker.yml): там процесс админки
останавливают, и сайт должен отвечать дальше. Здесь — правило Apache
и лимит времени запросов админки к базе.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, нужна_база


def _правило_админки() -> re.Pattern[str]:
    """Условие REQUEST_URI перед правилом, ведущим на 127.0.0.1:8002."""
    conf = (КОРЕНЬ / "docker/apache-python.conf").read_text()
    [условие] = re.findall(
        r"RewriteCond %\{REQUEST_URI\} (\S+)\n(?:RewriteCond .*\n)*"
        r"RewriteRule \^ http://127\.0\.0\.1:8002",
        conf,
    )
    return re.compile(условие)


@pytest.mark.parametrize(
    "path",
    [
        "/py/admin/",
        "/py/admin",
        "/py/admin/login/",
        "/py/admin/exports/",
        "/py/login",
        "/py/logout",
    ],
)
def test_адреса_админки_идут_в_её_процесс(path):
    assert _правило_админки().search(path)


@pytest.mark.parametrize(
    "path",
    ["/py/up", "/py/whoami", "/py/static/admin/css/base.css", "/py/administrator", "/admin", "/"],
)
def test_остальное_остаётся_сайту(path):
    assert not _правило_админки().search(path)


def test_процесс_админки_запускается_на_своём_порту():
    скрипт = (КОРЕНЬ / "docker/render-entrypoint.sh").read_text()

    assert re.search(
        r"run_forever 5 \"Админка[^\"]*\" env SAVDEX_ROLE=admin \S+/gunicorn savdex\.wsgi \\\n"
        r"(?:\s+--.*\n)*?\s+--bind 127\.0\.0\.1:8002",
        скрипт,
    )


def _statement_timeout(**env: str) -> str:
    код = (
        "import django; django.setup()\n"
        "from django.db import connection\n"
        "with connection.cursor() as c:\n"
        "    c.execute('show statement_timeout')\n"
        "    print(c.fetchone()[0])\n"
    )
    окружение = {**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings"}
    окружение.pop("SAVDEX_ROLE", None)
    окружение.update(env)
    return subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        env=окружение,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@нужна_база
def test_админка_не_держит_базу_дольше_двух_минут():
    assert _statement_timeout(SAVDEX_ROLE="admin") == "2min"
    assert _statement_timeout(SAVDEX_ROLE="admin", SAVDEX_ADMIN_STATEMENT_TIMEOUT="0") == "0"


@нужна_база
def test_сайт_без_лимита():
    """Тяжёлые задачи сайта (карта сайта, перевод) лимит админки не задевает."""
    assert _statement_timeout() == "0"
