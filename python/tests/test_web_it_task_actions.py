"""
Свои IT-задачи на Django неотличимы от Laravel: закрыть (только
открытую), отметить выполненной (ссылка по правилу url, исполнитель
только из откликнувшихся), открыть заново, удалить задачу (файл с
диска, каскад файлов и разговоров, переход к списку) и файл задачи.
Чужая задача — 404. У администратора — строка журнала.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}
ФАЙЛ = "it-tasks/parity/spec.pdf"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'customer']);"
        "App\\Models\\Company::factory()->create(['slug' => 'dev']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def заказчик(admin: bool = False) -> int:
    return учётка("customer@savdex.uz", company_id=_компания("customer"), is_admin=admin)


def задача(status: str = "active", *, компания: str = "customer") -> Callable[[], None]:
    """Подготовка: одна задача с номером 1, файлом и откликом компании dev."""

    def run() -> None:
        sql("delete from message_threads")
        sql("delete from it_tasks")
        sql("delete from admin_actions where section = 'ittasks'")
        sql("select setval('it_tasks_id_seq', 1, false)")
        sql("select setval('it_task_files_id_seq', 1, false)")
        php(
            "$t = App\\Models\\ItTask::factory()->create(["
            f"'company_id' => {_компания(компания)}, 'status' => '{status}',"
            "'title' => 'Сайт магазина стройматериалов', 'description' => 'Каталог и корзина',"
            "'published_at' => now()->subDay(),"
            "'closed_at' => " + ("null" if status == "active" else "'2026-09-01 10:00:00'") + "]);"
            f"$t->files()->create(['title' => 'ТЗ', 'file_path' => '{ФАЙЛ}',"
            " 'file_size' => 3, 'mime' => 'application/pdf']);"
            "App\\Models\\MessageThread::create(['it_task_id' => $t->id,"
            f" 'buyer_company_id' => {_компания('dev')}, 'seller_company_id' => $t->company_id]);"
            "echo 'ok';",
            БЕЗ_ПЕРЕВОДА,
        )
        путь = Path(КОРЕНЬ) / "storage/app/private" / ФАЙЛ
        путь.parent.mkdir(parents=True, exist_ok=True)
        путь.write_bytes(b"pdf")

    return run


def снимок() -> Any:
    журнал = [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions "
            "where section = 'ittasks' order by id"
        )
    ]

    return {
        "tasks": sql(
            "select id, status, closed_at is not null, closed_at > now() - interval '1 hour', "
            "completed_at is not null, published_at > now() - interval '1 hour', result_url, "
            "result_summary, contractor_company_id, search_text, "
            "updated_at > now() - interval '1 hour' from it_tasks order by id"
        ),
        "files": sql("select id, it_task_id, file_path from it_task_files order by id"),
        "threads": sql("select it_task_id, buyer_company_id from message_threads order by id"),
        "disk": (Path(КОРЕНЬ) / "storage/app/private" / ФАЙЛ).exists(),
        "journal": журнал,
    }


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("verb", ["close", "reopen"])
@pytest.mark.parametrize("status", ["active", "closed", "completed"])
def test_закрыть_и_открыть(сайт, verb, status, admin):
    отправить(
        сайт,
        f"/cabinet/it-tasks/1/{verb}",
        задача(status),
        снимок,
        uid=заказчик(admin),
        headers=inertia(),
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"result_url": "https://shop.uz", "result_summary": "Сдали в срок", "contractor": True},
        {"result_url": "shop.uz"},
        {"result_url": "https://" + "a" * 250 + ".uz"},
        {"result_summary": "x" * 601},
        {"contractor_company_id": "abc"},
        {"contractor": "other"},
        {"result_url": "", "result_summary": "", "contractor_company_id": ""},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_выполнено(сайт, body, admin):
    body = dict(body)

    кто = body.pop("contractor", None)

    if кто is not None:
        body["contractor_company_id"] = _компания("other" if кто == "other" else "dev")

    отправить(
        сайт,
        "/cabinet/it-tasks/1/complete",
        задача("closed"),
        снимок,
        uid=заказчик(admin),
        body=body,
        headers=inertia(),
    )


def test_исполнитель_не_из_откликнувшихся(сайт):
    итог = отправить(
        сайт,
        "/cabinet/it-tasks/1/complete",
        задача(),
        снимок,
        uid=заказчик(),
        body={"contractor_company_id": _компания("other")},
        headers=inertia(),
    )

    assert '"contractor_company_id"' in итог["сессия"]["payload"]


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_удалить(сайт, admin, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/it-tasks/1",
        задача(),
        снимок,
        uid=заказчик(admin),
        method="DELETE",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303
    assert not итог["база"]["tasks"] and not итог["база"]["files"] and not итог["база"]["disk"]


@pytest.mark.parametrize("file_id", [1, 2])
def test_удалить_файл(сайт, file_id):
    итог = отправить(
        сайт,
        f"/cabinet/it-tasks/1/files/{file_id}",
        задача(),
        снимок,
        uid=заказчик(),
        method="DELETE",
        headers=inertia(),
    )

    assert итог["база"]["disk"] is (file_id != 1)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/cabinet/it-tasks/1/close"),
        ("POST", "/cabinet/it-tasks/1/complete"),
        ("DELETE", "/cabinet/it-tasks/1"),
    ],
)
def test_чужая_задача_404(сайт, method, path):
    итог = отправить(сайт, path, задача(компания="other"), снимок, uid=заказчик(), method=method)

    assert итог["ответ"]["status"] == 404
