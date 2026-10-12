"""Настройки сайта с Render — в файл переменных для docker compose.

    ssh <служба Render> 'env -0' | python3 render-env.py > app.env

Читает окружение работающей службы Render (имя=значение, через NUL) и
пишет то, что сайт берёт из окружения: APP_KEY, почту, оплату,
Telegram, ключи Google и прочее, заданное в панели Render. Не переносит
то, что у машин Uztelecom своё: адрес базы (db.env), адрес сайта и роль
машины (role.env), служебное Render и самой оболочки SSH.

Значения не печатаются: в журнал Actions (он публичный) уходят только
имена — список в stderr.
"""

import re
import sys

# Своё у машин Uztelecom или служебное — не переносится
SKIP = {
    # Оболочка SSH и образ
    "_", "HOME", "HOSTNAME", "LANG", "LOGNAME", "MAIL", "OLDPWD", "PATH",
    "PWD", "SHELL", "SHLVL", "TERM", "USER", "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED", "PORT", "IS_PULL_REQUEST",
    # Render: число процессов gunicorn у него своё, у машин — своё
    "WEB_CONCURRENCY",
    # База — с машины базы (db.env)
    "DB_CONNECTION", "DB_URL", "DB_HOST", "DB_PORT", "DB_DATABASE",
    "DB_USERNAME", "DB_PASSWORD", "DATABASE_URL", "TARGET_DB_URL",
    "DJANGO_DATABASE_URL",
    # Адрес сайта и роль машины — role.env (deploy/server/prod-app.sh)
    "APP_URL", "DJANGO_ALLOWED_HOSTS", "SAVDEX_ROLE", "SAVDEX_MIGRATE",
    "SAVDEX_BACKGROUND", "SAVDEX_SCHEDULE_STATE", "PYTHON_WORKERS",
    "PYTHON_THREADS", "PYTHON_ADMIN_WORKERS", "PYTHON_ADMIN_THREADS",
    "PYTHON_WORKER_MB", "PYTHON_RESERVED_MB",
}
# KUBERNETES_* — адрес служебного API кластера, в котором Render держит
# службу; на машинах Uztelecom его нет
SKIP_PREFIXES = ("RENDER", "SSH_", "XDG_", "LC_", "GIT_", "KUBERNETES_")
REQUIRED = ("APP_KEY",)
NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def line(name: str, value: str) -> str:
    """Строка env_file docker compose: значение — как есть, без подстановок."""
    # В одинарных кавычках compose не подставляет $ПЕРЕМЕННЫЕ и не
    # трогает # и пробелы
    if "'" not in value and "\n" not in value:
        return f"{name}='{value}'"
    # Иначе — в двойных: экранировать \ " и $, перевод строки — \n
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$").replace("\n", "\\n")
    )
    return f'{name}="{escaped}"'


def main() -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    taken: dict[str, str] = {}
    for item in raw.split("\0"):
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        if not NAME.match(name) or name in SKIP or name.startswith(SKIP_PREFIXES):
            continue
        taken[name] = value

    missing = [name for name in REQUIRED if not taken.get(name)]
    if missing:
        print(f"ОШИБКА: в окружении Render нет {', '.join(missing)}.", file=sys.stderr)
        return 1

    print("# Перенесено с Render (deploy/server/render-env.py). Значения — только здесь.")
    for name in sorted(taken):
        print(line(name, taken[name]))
    print(f"Перенесено с Render: {len(taken)} — {', '.join(sorted(taken))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
