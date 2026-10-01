"""
Выдача доступа в админку: команда manage.py admin на настоящей базе.

Команда пишет, поэтому проверяется не только вывод, но и итог в базе:
строка users после команды (кроме соли в хеше и времени), отказы и их
тексты — те же, что были у PHP-команды savdex:admin. И отдельно —
главный вопрос: пускает ли вход сайта администратора с выданным паролем.

Каждый случай готовится с нуля: состояние → команда → снимок строки.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); без него проверка пропускается.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import bcrypt
import pytest

from savdex import laravel_session

from .pg_admin import свежая_база

PYTHON = Path(__file__).resolve().parents[1]
АДРЕС = os.environ.get("SAVDEX_PARITY_PG_URL", "")

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — проверка требует PostgreSQL",
)

#: Окружение команды: база, адрес сайта, стоимость bcrypt (малая — ради
#: скорости; цена тоже проверяется)
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

#: Столбцы строки users, которые проверяются буква в букву
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
    свежая_база()


def _sql(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        курсор = соединение.execute(query, params or [])

        return курсор.fetchall() if курсор.description else []


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
        # Удалённая и действующая на одной почте — смотрим действующую
        "from users where email = %s order by deleted_at is not null, id",
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


def _выполнить(подготовка: list[str], email: str, *args: str) -> dict[str, Any]:
    """Состояние с нуля → команда → код, вывод и строка users после неё."""
    _sql("delete from users where email = %s", [email])

    for query in подготовка:
        _sql(query)

    до = _строка(email)
    результат = _python(*args)
    после = _строка(email)

    return {
        "код": результат.returncode,
        # Одним текстом: ошибки команда печатает в stderr
        "вывод": _вывод(результат.stdout + результат.stderr),
        "пароль": re.search(r"\| Пароль\s+\| (\S+)", результат.stdout),
        "строка": после,
        "до": до,
    }


СУЩЕСТВУЮЩИЙ = (
    "insert into users (name, email, password, status, email_verified_at, created_at, updated_at) "
    "values ('Старый', 'old@savdex.uz', 'x', 'blocked', {verified}, now(), now())"
)

РОЛИ = (
    "superadmin, admin, sales, supplier_manager, buyer_manager, moderator, finance, support, "
    "content_manager"
)


def администратор(name: str, email: str, role: str) -> dict[str, Any]:
    """Строка users администратора, которого выдала команда."""
    return {
        "name": name,
        "email": email,
        "is_admin": True,
        "admin_role": role,
        "admin_permissions": None,
        "status": "active",
        # Выданный пароль знают двое — при первом входе его надо сменить
        "must_change_password": True,
        "locale": "ru",
        "company_role": "owner",
        "company_id": None,
        "deleted_at": None,
        # bcrypt, цена BCRYPT_ROUNDS=4, в виде PHP ($2y$)
        "password": "$2y$04$",
    }


@pytest.mark.parametrize(
    ("подготовка", "email", "args", "строка", "вывод"),
    [
        pytest.param(
            [],
            "boss@savdex.uz",
            ("boss@savdex.uz", "--password=Savdex2026!x"),
            администратор("boss", "boss@savdex.uz", "superadmin"),
            "Администратор создан.",
            id="новый суперадмин",
        ),
        pytest.param(
            [],
            "fin@savdex.uz",
            ("fin@savdex.uz", "--role=finance", "--name=Финансы Ташкент"),
            администратор("Финансы Ташкент", "fin@savdex.uz", "finance"),
            "| Роль | Финансы |",
            id="новый с ролью и именем",
        ),
        pytest.param(
            [],
            "mod@savdex.uz",
            ("mod@savdex.uz", "--moderator"),
            администратор("mod", "mod@savdex.uz", "moderator"),
            "| Роль | Модератор |",
            id="модератор",
        ),
        pytest.param(
            [],
            "caps@savdex.uz",
            ("  CAPS@Savdex.UZ ", "--role=support"),
            администратор("caps", "caps@savdex.uz", "support"),
            "| Почта | caps@savdex.uz |",
            id="почта с пробелами и прописными",
        ),
        pytest.param(
            [],
            "zero@savdex.uz",
            ("zero@savdex.uz", "--password=0", "--role=0", "--name=0"),
            # «0» у PHP — ложь: пароль сгенерирован, роль и имя — по умолчанию
            администратор("zero", "zero@savdex.uz", "superadmin"),
            "| Роль | Суперадмин |",
            id="ноль как пусто",
        ),
        pytest.param(
            [СУЩЕСТВУЮЩИЙ.format(verified="null")],
            "old@savdex.uz",
            ("old@savdex.uz", "--role=sales"),
            администратор("Старый", "old@savdex.uz", "sales"),
            "Роль выдана существующему пользователю, пароль заменён.",
            id="существующий заблокированный без подтверждения",
        ),
        pytest.param(
            [СУЩЕСТВУЮЩИЙ.format(verified="'2026-01-02 03:04:05'")],
            "old@savdex.uz",
            ("old@savdex.uz",),
            администратор("Старый", "old@savdex.uz", "superadmin"),
            "Роль выдана существующему пользователю, пароль заменён.",
            id="существующий подтверждённый",
        ),
        pytest.param(
            [
                "insert into users (name, email, password, created_at, updated_at, deleted_at) "
                "values ('Ушёл', 'gone@savdex.uz', 'x', now(), now(), '2026-05-06 07:08:09')"
            ],
            "gone@savdex.uz",
            ("gone@savdex.uz",),
            None,
            "Учётка gone@savdex.uz удалена 06.05.2026. Восстановите её в админке или выберите "
            "другую почту.",
            id="удалённая учётка",
        ),
        pytest.param(
            [
                "insert into users (name, email, password, created_at, updated_at, deleted_at) "
                "values ('Ушёл', 'same@savdex.uz', 'x', now(), now(), '2026-05-06 07:08:09')",
                "insert into users (name, email, password, created_at, updated_at) "
                "values ('Вернулся', 'same@savdex.uz', 'x', now(), now())",
            ],
            "same@savdex.uz",
            ("same@savdex.uz", "--role=support"),
            администратор("Вернулся", "same@savdex.uz", "support"),
            "Роль выдана существующему пользователю, пароль заменён.",
            id="удалённая и действующая на одной почте",
        ),
        pytest.param(
            [],
            "new@savdex.uz",
            ("new@savdex.uz", "--role=sales-manager"),
            None,
            f"Роли «sales-manager» нет. Доступны: {РОЛИ}.",
            id="неизвестная роль",
        ),
        pytest.param(
            [],
            "не-почта",
            ("не-почта",),
            None,
            "«не-почта» не похоже на адрес почты.",
            id="не почта",
        ),
        pytest.param(
            [],
            "a@b",
            ("a@b",),
            None,
            "«a@b» не похоже на адрес почты.",
            id="почта без домена верхнего уровня",
        ),
    ],
)
def test_команда_оставляет_в_базе(подготовка, email, args, строка, вывод):
    итог = _выполнить(подготовка, email, *args)

    assert вывод in итог["вывод"], итог["вывод"]

    if строка is None:
        # Отказ: код ошибки, строка — какой была до команды
        assert итог["код"] == 1
        assert итог["строка"] == итог["до"]

        return

    assert итог["код"] == 0, итог["вывод"]
    assert (
        "Пароль показан один раз. При первом входе система попросит его сменить." in итог["вывод"]
    )
    assert {k: итог["строка"][k] for k in строка} == строка
    assert итог["строка"]["created_at"] is not None and итог["строка"]["updated_at"] is not None

    # Подтверждение: у новых — «сейчас», у подтверждённых — прежнее
    if итог["до"] is not None and итог["до"]["email_verified_at"] is not None:
        assert итог["строка"]["email_verified_at"] == итог["до"]["email_verified_at"]
    else:
        assert итог["строка"]["email_verified_at"] is not None

    # Свой пароль печатается как есть; пустой или «0» — сгенерирован:
    # 14 букв и цифр (Str::password(14, symbols: false))
    assert итог["пароль"] is not None
    пароль = итог["пароль"].group(1)
    свой = next((a.split("=", 1)[1] for a in args if a.startswith("--password=")), "0")

    if свой != "0":
        assert пароль == свой
    else:
        assert re.fullmatch(r"[A-Za-z0-9]{14}", пароль), пароль

    # В базе — хеш именно этого пароля (Hash::check у Laravel: $2y$ = $2b$)
    [(хеш,)] = _sql("select password from users where email = %s and deleted_at is null", [email])
    assert bcrypt.checkpw(пароль.encode(), ("$2b$" + хеш[4:]).encode())


def test_случаи_различают():
    """Проверка слепа, если все случаи кончаются одним и тем же — проверка самой проверки."""
    удачный = _python("check-ok@savdex.uz", "--password=Savdex2026!x")
    неудачный = _python("check-bad@savdex.uz", "--role=нет")

    assert удачный.returncode == 0
    assert неудачный.returncode != 0


def test_вход_пускает_администратора():
    """
    Главное: пароль, выданный командой, принимает вход сайта (та же
    проверка bcrypt, что у Laravel) — и после входа администратор должен
    сменить пароль.
    """
    from .test_web_forms import отправить
    from .web_site import адрес, сессия_из, строка

    email = "login-python@savdex.uz"
    _sql("delete from users where email = %s", [email])

    результат = _python(email, "--role=content_manager")
    assert результат.returncode == 0, результат.stderr

    пароль = re.search(r"\| Пароль\s+\| (\S+)", результат.stdout)
    assert пароль is not None, результат.stdout
    assert len(пароль.group(1)) == 14
    [(uid,)] = _sql("select id from users where email = %s", [email])

    with адрес() as сайт:
        итог = отправить(
            сайт,
            "/login",
            lambda: None,
            body={"email": email, "password": пароль.group(1)},
        )
        неверный = отправить(
            сайт,
            "/login",
            lambda: None,
            body={"email": email, "password": "не-тот-пароль"},
        )

    # Вошёл: сессия под новым номером (migrate), в ней — он; первым делом —
    # смена пароля
    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"].endswith("/password/change")
    assert итог["сессия"] is None
    новая = строка(сессия_из(итог["ответ"]))
    assert новая is not None and новая["user_id"] == uid
    assert f'"{laravel_session.LOGIN_KEY}":{uid}' in новая["payload"]

    # Чужой пароль — назад с ошибкой, не вошёл
    assert неверный["ответ"]["status"] == 302
    assert неверный["сессия"]["user_id"] is None
    assert laravel_session.LOGIN_KEY not in неверный["сессия"]["payload"]
    assert '"errors":' in неверный["сессия"]["payload"]


def test_деплой_не_сбрасывает_пароль():
    """
    --if-missing (шаг 73, вместо проверки через tinker в entrypoint): уже
    администратор — ничего не меняется; ещё нет — выдаётся, как обычно.
    """
    email = "deploy@savdex.uz"
    _sql("delete from users where email = %s", [email])

    первый = _python(email, "--if-missing", "--password=Первый-пароль-1")
    assert первый.returncode == 0 and "создан" in первый.stdout, первый.stderr
    было = _sql("select password, updated_at from users where email = %s", [email])

    второй = _python(email, "--if-missing", "--password=Другой-пароль-2")

    assert второй.returncode == 0 and "уже есть" in второй.stdout
    assert _sql("select password, updated_at from users where email = %s", [email]) == было
