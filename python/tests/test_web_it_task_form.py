"""
Новая IT-задача и её правка на Django: проверка
ввода (бюджет: required_if и gte, стек, срок позже сегодня, до пяти
файлов по типу содержимого), чистка стека и бюджета, адрес из заголовка
и номера, файлы на диск local, переход к списку задач. Правку с файлами
браузер шлёт POST с _method=patch — Django подменяет метод, как Laravel;
так же _method=delete удаляет задачу. У администратора — строки журнала.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
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

from .factories import компания
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_company_file_actions import PDF
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ДИСК = Path(КОРЕНЬ) / "storage/app/private/it-tasks"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="customer")
    компания(slug="other")

    with адрес() as root:
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


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Сообщение и ошибки проверки в сессии после ответа."""
    payload = json.loads(итог["сессия"]["payload"])
    ошибки = payload.get("errors", {}).get("default", {}).get("messages", {})

    return {"success": payload.get("success"), "errors": ошибки}


ОПУБЛИКОВАНА = "Задача опубликована в разделе «Доп. услуги». Отклики исполнителей придут в чаты."

#: (изменения, стек, файлы, ошибки проверки — или бюджет и число файлов новой задачи)
НОВЫЕ = [
    ({}, ["php", "laravel"], [ТЗ, ТЕКСТ], ("fixed", "15000000.00", None, 2)),
    # Пустой навык — не строка
    ({"title": "Бот для заказов в Telegram"}, [" python ", "", "0", "python", "aiogram"], [],
     ["stack.1"]),
    # Договорной — без бюджета, даже если границу прислали
    ({"budget_type": "negotiable", "budget_to": "20000000"}, [], [], ("negotiable", None, None, 0)),
    ({"budget_type": "range", "budget_to": "20000000"}, [], [ТЗ],
     ("range", "15000000.00", "20000000.00", 1)),
    ({"budget_type": "range", "budget_to": "1000"}, [], [], ["budget_to"]),
    ({"budget_type": "range", "budget_to": ""}, [], [], ["budget_to"]),
    ({"budget_from": ""}, [], [], ["budget_from"]),
    ({"title": "Коротко", "service_type": "space", "currency": "EUR"}, [], [],
     ["title", "service_type", "currency"]),
    ({"deadline_at": "2020-01-01"}, [], [], ["deadline_at"]),
    ({"deadline_at": "не дата"}, [], [], ["deadline_at"]),
    ({}, [f"tag{i}" for i in range(11)], [], ["stack"]),
    ({}, ["x" * 31], [], ["stack.0"]),
    ({}, [], [ТЗ] * 6, ["files"]),
    ({}, [], [EXE], ["files.0"]),
]  # fmt: skip


@pytest.mark.parametrize(("изменения", "стек", "файлы", "ожидание"), НОВЫЕ)
@pytest.mark.parametrize("admin", [False, True])
def test_новая(сайт, изменения, стек, файлы, ожидание, admin):
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
    ответ, база = итог["ответ"], итог["база"]
    итог_сессии = сессия(итог)

    assert ответ["status"] == 302

    if isinstance(ожидание, list):
        # Назад к форме с ошибками; ни задачи, ни файлов
        assert ответ["headers"]["location"] == сайт + "/cabinet/settings"
        assert sorted(итог_сессии["errors"]) == sorted(ожидание)
        assert база["tasks"] == [] and база["files"] == [] and база["disk"] == []
        assert база["journal"] == []
        return

    вид, от, до, файлов = ожидание
    [задача] = база["tasks"]

    assert ответ["headers"]["location"] == сайт + "/cabinet/it-tasks"
    assert итог_сессии["success"] == ОПУБЛИКОВАНА and not итог_сессии["errors"]
    # Адрес — из заголовка и номера; задача сразу активна
    assert задача[3] == "internet-magazin-tsementa-1" and задача[13] == "active"
    assert (задача[8], задача[9], задача[10]) == (вид, от, до)
    assert json.loads(задача[7]) == стек
    # Файлы — на диске local, под случайными именами
    assert len(база["files"]) == len(база["disk"]) == файлов
    assert [(a, label) for a, label, _ in база["journal"]] == (
        [("created", "Интернет-магазин цемента")] if admin else []
    )


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

    assert итог["ответ"]["headers"]["location"] == сайт + "/en/cabinet/it-tasks"
    # Повтор в стеке убран, бюджет — числом
    assert json.loads(итог["база"]["tasks"][0][7]) == ["go", "grpc"]
    assert итог["база"]["tasks"][0][9] == "500.00"


def test_новая_без_почты(сайт):
    тело, тип = multipart(поля({}, [], []))
    итог = отправить(
        сайт,
        "/cabinet/it-tasks",
        задачи(-1),
        снимок,
        uid=заказчик(verified=False),
        body=тело,
        content_type=тип,
        headers=inertia(),
    )

    # Почта не подтверждена — сначала подтвердить, задача не заводится
    assert (итог["ответ"]["status"], итог["ответ"]["headers"]["location"]) == (
        302,
        сайт + "/verify-email",
    )
    assert итог["база"]["tasks"] == []


#: (изменения, стек, файлы, было файлов, ошибки — или итог: название, бюджет, срок, файлов)
ПРАВКИ = [
    ({"_method": "patch"}, [], [], 0,
     ("Интернет-магазин цемента", "fixed", "2099-06-30", 0)),
    ({"_method": "patch", "title": "Сайт и мобильное приложение"}, ["php", "vue"], [ТЗ], 4,
     ("Сайт и мобильное приложение", "fixed", "2099-06-30", 5)),
    # Мест под файлы — одно: второй не сохраняется
    ({"_method": "PATCH", "budget_type": "negotiable"}, ["php", "laravel"], [ТЗ, ТЕКСТ], 4,
     ("Интернет-магазин цемента", "negotiable", "2099-06-30", 5)),
    ({"_method": "patch", "deadline_at": "2099-01-15"}, ["php", "laravel"], [], 0,
     ("Интернет-магазин цемента", "fixed", "2099-01-15", 0)),
    # Срок можно убрать
    ({"_method": "patch", "deadline_at": ""}, [], [], 0,
     ("Интернет-магазин цемента", "fixed", None, 0)),
    ({"_method": "patch", "title": ""}, [], [], 0, ["title"]),
    ({"_method": "delete"}, [], [], 2, None),
]  # fmt: skip


@pytest.mark.parametrize(("изменения", "стек", "файлы", "было", "ожидание"), ПРАВКИ)
@pytest.mark.parametrize("admin", [False, True])
def test_правка_формой(сайт, изменения, стек, файлы, было, ожидание, admin):
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
    ответ, база = итог["ответ"], итог["база"]
    итог_сессии = сессия(итог)

    # Метод из _method: ответ Inertia на PATCH и DELETE — 303
    assert ответ["status"] == 303

    if изменения["_method"] == "delete":
        # Задача удалена вместе с файлами на диске
        assert ответ["headers"]["location"] == сайт + "/cabinet/it-tasks"
        assert итог_сессии["success"] == "Задача удалена"
        assert база["tasks"] == [] and база["disk"] == []
        assert [a for a, _, _ in база["journal"]] == (["deleted"] if admin else [])
    elif isinstance(ожидание, list):
        assert ответ["headers"]["location"] == сайт + "/cabinet/settings"
        assert sorted(итог_сессии["errors"]) == ожидание
        # Задача прежняя
        assert база["tasks"][0][4] == "Сайт магазина стройматериалов"
        assert база["journal"] == []
    else:
        название, вид, срок, файлов = ожидание
        [задача] = база["tasks"]

        assert ответ["headers"]["location"] == сайт + "/cabinet/it-tasks"
        assert итог_сессии["success"] == "Задача обновлена"
        # Адрес задачи при правке не меняется
        assert (задача[3], задача[4], задача[8], задача[12]) == ("site-1", название, вид, срок)
        assert json.loads(задача[7]) == стек
        assert len(база["files"]) == len(база["disk"]) == файлов
        assert [(a, label) for a, label, _ in база["journal"]] == (
            [("updated", название)] if admin else []
        )


@pytest.mark.parametrize("компания", ["customer", "other"])
def test_правка_json(сайт, компания):
    итог = отправить(
        сайт,
        "/cabinet/it-tasks/1",
        задачи(0, компания=компания),
        снимок,
        uid=заказчик(),
        body={**ФОРМА, "budget_type": "range", "budget_from": "1000000.00", "budget_to": 5e6},
        method="PATCH",
        headers=inertia(),
    )
    [задача] = итог["база"]["tasks"]

    if компания == "other":
        # Чужая задача — 404, без изменений
        assert итог["ответ"]["status"] == 404
        assert задача[4] == "Сайт магазина стройматериалов"
    else:
        assert итог["ответ"]["status"] == 303
        assert (задача[4], задача[8], задача[9], задача[10]) == (
            "Интернет-магазин цемента",
            "range",
            "1000000.00",
            "5000000.00",
        )
