"""
Новая IT-задача и её правка на Django неотличимы от Laravel: проверка
ввода (бюджет: required_if и gte, стек, срок позже сегодня, до пяти
файлов по типу содержимого), чистка стека и бюджета, адрес из заголовка
и номера, файлы на диск local, переход к списку задач. Правку с файлами
браузер шлёт POST с _method=patch — Django подменяет метод, как Laravel;
так же _method=delete удаляет задачу. У администратора — строки журнала.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, php, sql, нужна_база, свежая_база
from .test_web_company_file_actions import PDF
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}
ДИСК = Path(КОРЕНЬ) / "storage/app/private/it-tasks"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'customer']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def заказчик(*, admin: bool = False, verified: bool = True) -> int:
    return учётка(
        "customer@savdex.uz",
        company_id=_компания("customer"),
        is_admin=admin,
        email_verified_at="2026-09-01 10:00:00" if verified else None,
    )


def задачи(файлов: int = 0, *, компания: str = "customer") -> Callable[[], None]:
    """Подготовка: задача номер 1 (или без задач, файлов = -1) с файлами."""

    def run() -> None:
        sql("delete from it_tasks")
        sql("delete from admin_actions where section = 'ittasks'")
        sql("select setval('it_tasks_id_seq', 1, false)")
        sql("select setval('it_task_files_id_seq', 1, false)")
        shutil.rmtree(ДИСК, ignore_errors=True)

        if файлов < 0:
            return

        sql(
            "insert into it_tasks (company_id, slug, title, description, service_type, stack, "
            "budget_type, budget_from, budget_to, currency, deadline_at, status, published_at, "
            "search_text, created_at, updated_at) values (%s, 'site-1', "
            "'Сайт магазина стройматериалов', 'Каталог, корзина и оплата картой для магазина', "
            "'web', '[\"php\",\"laravel\"]', 'range', 1000000, 5000000, 'UZS', '2099-01-15', "
            "'active', now() - interval '1 day', 'сайт', now() - interval '1 day', "
            "now() - interval '1 day')",
            [_компания(компания)],
        )

        for i in range(файлов):
            путь = f"it-tasks/1/old-{i}.pdf"
            (ДИСК / "1").mkdir(parents=True, exist_ok=True)
            (ДИСК / f"1/old-{i}.pdf").write_bytes(PDF)
            sql(
                "insert into it_task_files (it_task_id, title, file_path, file_size, mime, "
                "created_at, updated_at) values (1, %s, %s, 10, 'application/pdf', now(), now())",
                [f"ТЗ {i}.pdf", путь],
            )

    return run


RANDOM = r"[A-Za-z0-9]{40}"


def снимок() -> Any:
    журнал = [
        (a, label, re.sub(RANDOM, "<random>", re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch)))
        for a, label, ch in sql(
            "select action, subject_label, coalesce(changes::text, '') from admin_actions "
            "where section = 'ittasks' order by id"
        )
    ]

    return {
        "tasks": sql(
            "select id, company_id, user_id is not null, slug, title, description, service_type, "
            "stack::text, budget_type, budget_from::text, budget_to::text, currency, "
            "deadline_at::text, status, published_at > now() - interval '1 hour', search_text, "
            "updated_at > now() - interval '1 hour' from it_tasks order by id"
        ),
        "files": sql(
            f"select id, it_task_id, title, regexp_replace(file_path, '{RANDOM}', '<random>'), "
            "file_size, mime from it_task_files order by id"
        ),
        "disk": sorted(
            str(p.relative_to(ДИСК)) if "old-" in p.name else f"{p.parent.name}/<random>{p.suffix}"
            for p in ДИСК.rglob("*")
            if p.is_file()
        )
        if ДИСК.exists()
        else [],
        "journal": журнал,
    }


def multipart(поля: list[tuple[str, Any]]) -> tuple[str, str]:
    """Тело multipart/form-data, как у Inertia с forceFormData: повтор имён можно."""
    граница = "----savdexparity"
    части = []

    for name, value in поля:
        if isinstance(value, tuple):
            filename, data, тип = value
            части.append(
                f'--{граница}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\nContent-Type: {тип}\r\n\r\n'.encode()
                + data
                + b"\r\n"
            )
        else:
            части.append(
                f'--{граница}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n".encode()
            )

    тело = b"".join(части) + f"--{граница}--\r\n".encode()

    return "base64:" + base64.b64encode(тело).decode(), f"multipart/form-data; boundary={граница}"


ФОРМА = {
    "title": "Интернет-магазин цемента",
    "description": "Каталог товаров, корзина, оплата через Payme и Click, личный кабинет",
    "service_type": "web",
    "budget_type": "fixed",
    "budget_from": "15000000",
    "budget_to": "",
    "currency": "UZS",
    "deadline_at": "2099-06-30",
}
ТЗ = ("ТЗ магазина.pdf", PDF, "application/pdf")
ТЕКСТ = ("заметки.txt", "Нужна интеграция с 1С".encode(), "text/plain")
EXE = ("setup.exe", b"MZ" + b"\0" * 200, "application/x-msdownload")


def поля(изменения: dict[str, Any], стек: list[str], файлы: list[Any]) -> list[tuple[str, Any]]:
    форма = {**ФОРМА, **изменения}
    пары: list[tuple[str, Any]] = [(k, v) for k, v in форма.items() if v is not None]
    пары += [(f"stack[{i}]", t) for i, t in enumerate(стек)]
    пары += [(f"files[{i}]", f) for i, f in enumerate(файлы)]

    return пары


НОВЫЕ = [
    ({}, ["php", "laravel"], [ТЗ, ТЕКСТ]),
    ({"title": "Бот для заказов в Telegram"}, [" python ", "", "0", "python", "aiogram"], []),
    ({"budget_type": "negotiable", "budget_to": "20000000"}, [], []),
    ({"budget_type": "range", "budget_to": "20000000"}, [], [ТЗ]),
    ({"budget_type": "range", "budget_to": "1000"}, [], []),
    ({"budget_type": "range", "budget_to": ""}, [], []),
    ({"budget_from": ""}, [], []),
    ({"title": "Коротко", "service_type": "space", "currency": "EUR"}, [], []),
    ({"deadline_at": "2020-01-01"}, [], []),
    ({"deadline_at": "не дата"}, [], []),
    ({}, [f"tag{i}" for i in range(11)], []),
    ({}, ["x" * 31], []),
    ({}, [], [ТЗ] * 6),
    ({}, [], [EXE]),
]


@pytest.mark.parametrize(("изменения", "стек", "файлы"), НОВЫЕ)
@pytest.mark.parametrize("admin", [False, True])
def test_новая(сайт, изменения, стек, файлы, admin):
    тело, тип = multipart(поля(изменения, стек, файлы))
    итог = отправить(
        сайт,
        "/cabinet/it-tasks",
        задачи(-1),
        снимок,
        uid=заказчик(admin=admin),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )

    if (изменения, стек, файлы) == НОВЫЕ[0]:
        assert итог["база"]["tasks"][0][3] == "internet-magazin-tsementa-1"
        assert len(итог["база"]["files"]) == 2 and len(итог["база"]["disk"]) == 2


def test_новая_json(сайт):
    итог = отправить(
        сайт,
        "/en/cabinet/it-tasks",
        задачи(-1),
        снимок,
        uid=заказчик(),
        body={**ФОРМА, "stack": ["go", "go", "grpc"], "budget_from": 500},
        headers=inertia(),
    )

    assert json.loads(итог["база"]["tasks"][0][7]) == ["go", "grpc"]


def test_новая_без_почты(сайт):
    тело, тип = multipart(поля({}, [], []))
    отправить(
        сайт,
        "/cabinet/it-tasks",
        задачи(-1),
        снимок,
        uid=заказчик(verified=False),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )


ПРАВКИ = [
    ({"_method": "patch"}, [], [], 0),
    ({"_method": "patch", "title": "Сайт и мобильное приложение"}, ["php", "vue"], [ТЗ], 4),
    ({"_method": "PATCH", "budget_type": "negotiable"}, ["php", "laravel"], [ТЗ, ТЕКСТ], 4),
    ({"_method": "patch", "deadline_at": "2099-01-15"}, ["php", "laravel"], [], 0),
    ({"_method": "patch", "deadline_at": ""}, [], [], 0),
    ({"_method": "patch", "title": ""}, [], [], 0),
    ({"_method": "delete"}, [], [], 2),
]


@pytest.mark.parametrize(("изменения", "стек", "файлы", "было"), ПРАВКИ)
@pytest.mark.parametrize("admin", [False, True])
def test_правка_формой(сайт, изменения, стек, файлы, было, admin):
    тело, тип = multipart(поля(изменения, стек, файлы))
    итог = отправить(
        сайт,
        "/cabinet/it-tasks/1",
        задачи(было),
        снимок,
        uid=заказчик(admin=admin),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )

    if изменения["_method"] == "delete":
        assert итог["база"]["tasks"] == [] and итог["база"]["disk"] == []
    elif было == 4 and файлы:
        # Мест под файлы — одно: второй не сохраняется
        assert len(итог["база"]["files"]) == 5


@pytest.mark.parametrize("компания", ["customer", "other"])
def test_правка_json(сайт, компания):
    отправить(
        сайт,
        "/cabinet/it-tasks/1",
        задачи(0, компания=компания),
        снимок,
        uid=заказчик(),
        body={**ФОРМА, "budget_type": "range", "budget_from": "1000000.00", "budget_to": 5e6},
        method="PATCH",
        headers=inertia(),
    )
