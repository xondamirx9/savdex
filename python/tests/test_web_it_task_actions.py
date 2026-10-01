"""
Свои IT-задачи на Django: закрыть (только
открытую), отметить выполненной (ссылка по правилу url, исполнитель
только из откликнувшихся), открыть заново, удалить задачу (файл с
диска и строки файлов, разговоры остаются без задачи, переход к
списку) и файл задачи.
Чужая задача — 404. У администратора — строка журнала.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .factories import Выражение, it_задача, компания
from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база
ФАЙЛ = "it-tasks/parity/spec.pdf"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    for slug in ("customer", "dev", "other"):
        компания(slug=slug)

    with адрес() as root:
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
        владелец = _компания(компания)
        pk = it_задача(
            company_id=владелец,
            status=status,
            title="Сайт магазина стройматериалов",
            description="Каталог и корзина",
            published_at=Выражение("now() - interval '1 day'"),
            closed_at=None if status == "active" else "2026-09-01 10:00:00",
        )
        sql(
            "insert into it_task_files (it_task_id, title, file_path, file_size, mime, "
            "created_at, updated_at) values (%s, 'ТЗ', %s, 3, 'application/pdf', now(), now())",
            [pk, ФАЙЛ],
        )
        # Отклик компании dev — разговор по задаче
        sql(
            "insert into message_threads (it_task_id, buyer_company_id, seller_company_id, "
            "created_at, updated_at) values (%s, %s, %s, now(), now())",
            [pk, _компания("dev"), владелец],
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


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


def _ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    return dict(((_сессия(итог).get("errors") or {}).get("default") or {}).get("messages") or {})


ЗАКРЫТА = "Задача закрыта — на витрине её больше нет, чаты остались"
ОТКРЫТА = "Задача снова открыта для откликов"
ВЫПОЛНЕНА = "Задача отмечена выполненной — она попала в «Выполненные» на витрине"
ТОЛЬКО_ОТКЛИКНУВШИЕСЯ = "Исполнителем можно отметить только компанию, которая откликалась на задачу"


#: (действие, статус) → (статус после, закрыта, закрыта сейчас, опубликована сейчас,
#: правка в журнале администратора или None)
ПЕРЕХОДЫ = {
    ("close", "active"): (
        "closed", True, True, False,
        '{"before":{"status":"active","closed_at":null},"after":{"status":"closed",'
        '"closed_at":"T"}}',
    ),
    # Закрыть можно только открытую — прочее не меняется
    ("close", "closed"): ("closed", True, False, False, None),
    ("close", "completed"): ("completed", True, False, False, None),
    ("reopen", "active"): ("active", False, None, False, None),
    # Открыта заново — снова на витрине с сегодняшней датой
    ("reopen", "closed"): (
        "active", False, None, True,
        '{"before":{"status":"closed","published_at":"T","closed_at":"T"},"after":{'
        '"status":"active","published_at":"T","closed_at":null}}',
    ),
    ("reopen", "completed"): (
        "active", False, None, True,
        '{"before":{"status":"completed","published_at":"T","closed_at":"T"},"after":{'
        '"status":"active","published_at":"T","closed_at":null}}',
    ),
}  # fmt: skip


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("verb", ["close", "reopen"])
@pytest.mark.parametrize("status", ["active", "closed", "completed"])
def test_закрыть_и_открыть(сайт, verb, status, admin):
    итог = отправить(
        сайт,
        f"/cabinet/it-tasks/1/{verb}",
        задача(status),
        снимок,
        uid=заказчик(admin),
        headers=inertia(),
    )
    после, закрыта, сейчас, опубликована, правка = ПЕРЕХОДЫ[(verb, status)]
    [task] = итог["база"]["tasks"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
    assert _сессия(итог)["success"] == (ЗАКРЫТА if verb == "close" else ОТКРЫТА)
    assert task[1:6] == (после, закрыта, сейчас, False, опубликована)
    assert итог["база"]["journal"] == (
        [("updated", "ittasks", "Сайт магазина стройматериалов", правка)]
        if admin and правка
        else []
    )


@pytest.mark.parametrize(
    ("body", "ждём"),
    [
        # ждём: (ссылка, итог, исполнитель) выполненной задачи — или ошибки
        ({}, (None, None, None)),
        (
            {"result_url": "https://shop.uz", "result_summary": "Сдали в срок", "contractor": True},
            ("https://shop.uz", "Сдали в срок", "dev"),
        ),
        ({"result_url": "shop.uz"}, {"result_url": ["Ссылка должна начинаться с http:// или https://"]}),
        ({"result_url": "https://" + "a" * 250 + ".uz"}, {"result_url": ["validation.max.string"]}),
        ({"result_summary": "x" * 601}, {"result_summary": ["validation.max.string"]}),
        (
            {"contractor_company_id": "abc"},
            {"contractor_company_id": ["validation.integer", ТОЛЬКО_ОТКЛИКНУВШИЕСЯ]},
        ),
        ({"contractor": "other"}, {"contractor_company_id": [ТОЛЬКО_ОТКЛИКНУВШИЕСЯ]}),
        # Пустые поля — null
        ({"result_url": "", "result_summary": "", "contractor_company_id": ""}, (None, None, None)),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_выполнено(сайт, body, ждём, admin):
    body = dict(body)

    кто = body.pop("contractor", None)

    if кто is not None:
        body["contractor_company_id"] = _компания("other" if кто == "other" else "dev")

    итог = отправить(
        сайт,
        "/cabinet/it-tasks/1/complete",
        задача("closed"),
        снимок,
        uid=заказчик(admin),
        body=body,
        headers=inertia(),
    )
    [task] = итог["база"]["tasks"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"

    if isinstance(ждём, dict):
        assert _ошибки(итог) == ждём
        # Задача как была — закрыта, не выполнена
        assert task[1:9] == ("closed", True, False, False, False, None, None, None)
        assert итог["база"]["journal"] == []

        return

    url, summary, кто_сделал = ждём
    исполнитель = _компания(кто_сделал) if кто_сделал else None
    assert _сессия(итог)["success"] == ВЫПОЛНЕНА
    assert task[1:9] == ("completed", True, False, True, False, url, summary, исполнитель)
    assert [(a, s, label) for a, s, label, _ in итог["база"]["journal"]] == (
        [("updated", "ittasks", "Сайт магазина стройматериалов")] if admin else []
    )

    if admin:
        правка = json.loads(итог["база"]["journal"][0][3])
        assert правка["after"]["status"] == "completed"
        assert правка["after"].get("contractor_company_id") == исполнитель


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

    assert _ошибки(итог) == {"contractor_company_id": [ТОЛЬКО_ОТКЛИКНУВШИЕСЯ]}
    assert итог["база"]["tasks"][0][1] == "active"


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
    assert итог["ответ"]["headers"]["location"] == f"{сайт}{prefix}/cabinet/it-tasks"
    assert _сессия(итог)["success"] == ("Задача удалена" if not prefix else "The project has been deleted")
    assert not итог["база"]["tasks"] and not итог["база"]["files"] and not итог["база"]["disk"]
    # Разговор с откликнувшимся остаётся, но уже без задачи
    assert итог["база"]["threads"] == [(None, _компания("dev"))]
    assert итог["база"]["journal"] == (
        [("deleted", "ittasks", "Сайт магазина стройматериалов", "")] if admin else []
    )


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

    if file_id == 1:
        assert итог["ответ"]["status"] == 303
        assert _сессия(итог)["success"] == "Файл удалён"
        assert итог["база"]["files"] == []
    else:
        # Нет такого файла у задачи — 404
        assert итог["ответ"]["status"] == 404
        assert итог["база"]["files"] == [(1, 1, ФАЙЛ)]


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
    assert итог["база"]["tasks"][0][1:3] == ("active", False)
    assert итог["база"]["disk"] is True
