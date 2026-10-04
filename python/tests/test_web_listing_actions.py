"""
Этап 5, шаг 23: «Мои объявления» на Django — ответ, сессия (сообщение,
ошибки) и что записано: статус, сроки, мягкое удаление, search_text,
лента кабинета и уведомления, журнал администратора.

Продлить (срок от сегодня по тарифу, отклонённое — нет, лимит тарифа),
снять, удалить (DELETE от Inertia — 303), опубликовать заново
возвращённое (лимит, уведомление компании), пачкой (проверка ввода,
отклонённые не продлеваются, свободные слоты, trans_choice на языках).
Чужое объявление — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest

from .factories import Выражение, компания, объявление
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_catalog import справочники
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники("plans")
    компания(slug="seller")
    компания(slug="other")

    with адрес() as root:
        yield root


def _компания(slug: str = "seller") -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def продавец(admin: bool = False) -> int:
    uid = учётка("seller@savdex.uz", company_id=_компания(), is_admin=admin)
    коллега = учётка("colleague@savdex.uz", company_id=_компания())
    assert коллега

    return uid


def объявления(*статусы: str, компания: str = "seller") -> Callable[[], list[int]]:
    """Подготовка: у компании ровно эти объявления (статусы по порядку)."""

    def подготовить() -> list[int]:
        cid = _компания(компания)
        sql("delete from listings where company_id = %s", [cid])
        sql("delete from activity_events")
        sql("delete from user_notifications")
        sql("delete from admin_actions where section = 'listings'")
        ids = []

        for i, status in enumerate(статусы):
            ids.append(
                объявление(
                    company_id=cid,
                    status=status,
                    title=f"Цемент {i}",
                    description="Мешки по 50 кг",
                    moderation_note="Уточните цену",
                    expires_at=Выражение("now() + interval '1 day'"),
                    published_at=None
                    if status == "draft"
                    else Выражение("now() - interval '10 days'"),
                )
            )

        return ids

    return подготовить


def снимок(cid: int | None = None) -> Callable[[], Any]:
    def run() -> Any:
        журнал = [
            (u, a, s, sid, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
            for u, a, s, sid, label, ch in sql(
                "select user_id, action, section, subject_id, subject_label, changes::text "
                "from admin_actions where section = 'listings' order by id"
            )
        ]

        return {
            "listings": sql(
                "select title, status, moderation_note, expires_at::date, published_at::date, "
                "deleted_at is not null, search_text, updated_at > now() - interval '1 hour' "
                "from listings where company_id = %s order by id",
                [cid or _компания()],
            ),
            "events": sql("select type, tone, message, url from activity_events order by id"),
            "notifications": sql(
                "select user_id, company_id, type, title, tone, url from user_notifications "
                "order by id"
            ),
            # Порядок строк журнала у пачки не задан — сортируем
            "journal": sorted(журнал),
        }

    return run


def послать(
    сайт: str,
    path: str,
    статусы: tuple[str, ...],
    *,
    uid: int,
    body: Any = None,
    method: str = "POST",
    id_index: int | None = 0,
) -> dict[str, Any]:
    """Отправить форму; номер объявления подставляется после подготовки."""
    ids = объявления(*статусы)()
    путь = path.format(id=ids[id_index] if id_index is not None and ids else 0, ids=ids)

    return отправить(
        сайт,
        путь,
        lambda: None,
        снимок(),
        uid=uid,
        body=body(ids) if callable(body) else body,
        method=method,
        headers=inertia(),
    )


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


def через(дней: int) -> date:
    """Дата через столько-то дней от сегодня (по часам базы)."""
    return sql("select (now() + %s * interval '1 day')::date", [дней])[0][0]


# Строка снимка listings: title, status, moderation_note, expires_at,
# published_at, удалено, search_text, обновлено
СТАТУС, ЗАМЕТКА, СРОК, ОПУБЛИКОВАНО, УДАЛЕНО = 1, 2, 3, 4, 5


# ── Одно объявление ─────────────────────────────────────────────────


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("status", ["active", "archived", "draft", "rejected"])
def test_продлить(сайт, status, admin):
    итог = послать(сайт, "/cabinet/listings/{id}/renew", (status,), uid=продавец(admin))
    [строка] = итог["база"]["listings"]

    assert итог["ответ"]["status"] == 302

    if status == "rejected":
        # Отклонённое не продлевается: срок прежний, журнала нет
        assert "отклонено" in сессия(итог)["error"]
        assert строка[СТАТУС] == "rejected" and строка[СРОК] == через(1)
        assert итог["база"]["journal"] == []
    elif status == "draft":
        # Черновик — только через мастер с проверкой публикации
        assert сессия(итог)["error"].startswith("Черновик не продлевается")
        assert строка[СТАТУС] == "draft"
        assert итог["база"]["journal"] == []
    else:
        # Free — 30 дней от сегодня
        assert сессия(итог)["success"].startswith("Объявление продлено до ")
        assert строка[СТАТУС] == "active" and строка[СРОК] == через(30)
        assert строка[ОПУБЛИКОВАНО] == через(-10)
        # Журнал администратора — только когда правит сотрудник
        assert [j[1] for j in итог["база"]["journal"]] == (["updated"] if admin else [])


def test_продлить_сверх_лимита(сайт):
    """Free — 4 активных: пятое не продлевается, сообщение с подсказкой."""
    итог = послать(
        сайт,
        "/cabinet/listings/{id}/renew",
        ("archived", "active", "active", "active", "active"),
        uid=продавец(),
    )

    assert сессия(итог)["error"].startswith("Достигнут лимит тарифа Free: 4 активных")
    assert "Снимите ненужное" in сессия(итог)["error"]
    assert итог["база"]["listings"][0][СТАТУС] == "archived"


@pytest.mark.parametrize("admin", [False, True])
def test_снять_и_удалить(сайт, admin):
    uid = продавец(admin)
    снято = послать(сайт, "/cabinet/listings/{id}/archive", ("active",), uid=uid)

    assert снято["ответ"]["status"] == 302
    assert сессия(снято)["success"] == "Объявление снято с публикации"
    assert снято["база"]["listings"][0][СТАТУС] == "archived"

    итог = послать(сайт, "/cabinet/listings/{id}", ("active",), uid=uid, method="DELETE")

    assert итог["ответ"]["status"] == 303
    assert сессия(итог)["success"] == "Объявление удалено"
    # Мягкое удаление: строка на месте, отмечена удалённой
    assert итог["база"]["listings"][0][УДАЛЕНО] is True
    assert [j[1] for j in итог["база"]["journal"]] == (["deleted"] if admin else [])


def test_удалить_подменой_метода(сайт):
    """
    POST с _method=DELETE понимается как DELETE (шаг 62: Apache отдаёт
    такой POST Django, и Django подменяет метод, как это делал Laravel).
    """
    uid = продавец()
    итог = послать(сайт, "/cabinet/listings/{id}", ("active",), uid=uid, body={"_method": "DELETE"})

    assert итог["ответ"]["status"] == 303
    assert итог["база"]["listings"][0][УДАЛЕНО] is True


def test_удалить_заголовком_подмены(сайт):
    uid = продавец()
    ids = объявления("active")()
    итог = отправить(
        сайт,
        f"/cabinet/listings/{ids[0]}",
        lambda: None,
        снимок(),
        uid=uid,
        headers={**inertia(), "X-HTTP-Method-Override": "delete"},
    )

    assert итог["ответ"]["status"] == 303
    assert итог["база"]["listings"][0][УДАЛЕНО] is True


@pytest.mark.parametrize("status", ["needs_changes", "active", "rejected"])
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_опубликовать_заново(сайт, status, prefix):
    итог = послать(сайт, prefix + "/cabinet/listings/{id}/resubmit", (status,), uid=продавец())
    [строка] = итог["база"]["listings"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"].endswith(prefix + "/cabinet/settings")

    if status == "needs_changes":
        # На витрине снова: заметка модератора снята, срок — заново
        assert строка[СТАТУС] == "active" and строка[ЗАМЕТКА] is None
        assert строка[ОПУБЛИКОВАНО] == через(0)
        assert "success" in сессия(итог)
        # Уведомление — обоим сотрудникам компании, в ленту — одно событие
        assert {n[0] for n in итог["база"]["notifications"]} == {
            учётка("seller@savdex.uz"),
            учётка("colleague@savdex.uz"),
        }
        # На языке каждого получателя: продавец зашёл на /en — его язык теперь
        # английский, коллега остался на русском
        заголовки = {n[0]: n[3] for n in итог["база"]["notifications"]}
        по_русски = "Объявление «Цемент 0» опубликовано заново"
        assert заголовки[учётка("colleague@savdex.uz")] == по_русски
        assert заголовки[учётка("seller@savdex.uz")] == (
            "The listing “Цемент 0” has been published again" if prefix else по_русски
        )
        assert [e[0] for e in итог["база"]["events"]] == ["moderation"]
    else:
        assert "error" in сессия(итог)
        assert строка[СТАТУС] == status and строка[ЗАМЕТКА] == "Уточните цену"
        assert итог["база"]["notifications"] == [] and итог["база"]["events"] == []


def test_опубликовать_заново_сверх_лимита(сайт):
    итог = послать(
        сайт,
        "/cabinet/listings/{id}/resubmit",
        ("needs_changes", "active", "active", "active", "active"),
        uid=продавец(),
    )

    assert сессия(итог)["error"].startswith("Достигнут лимит тарифа Free")
    assert итог["база"]["listings"][0][СТАТУС] == "needs_changes"
    assert not итог["база"]["notifications"]


def test_чужое_объявление_404(сайт):
    чужое = объявления("active", компания="other")()[0]
    итог = отправить(
        сайт,
        f"/cabinet/listings/{чужое}/renew",
        lambda: None,
        снимок(_компания("other")),
        uid=продавец(),
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 404
    assert итог["база"]["listings"][0][СРОК] == через(1)


# ── Пачкой ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("what", ["renew", "archive", "delete"])
@pytest.mark.parametrize("prefix", ["", "/en", "/uz"])
def test_пачкой(сайт, what, prefix):
    итог = послать(
        сайт,
        prefix + "/cabinet/listings/bulk",
        ("active", "archived", "rejected"),
        uid=продавец(True),
        body=lambda ids: {"action": what, "ids": [str(i) for i in ids]},
        id_index=None,
    )
    строки = итог["база"]["listings"]
    журнал = итог["база"]["journal"]

    assert итог["ответ"]["status"] == 302

    if what == "renew":
        # Отклонённое не продлевается
        assert [r[СТАТУС] for r in строки] == ["active", "active", "rejected"]
        assert [r[СРОК] for r in строки] == [через(30), через(30), через(1)]
        assert [j[1] for j in журнал] == ["updated", "updated"]
        число = "2"
    elif what == "archive":
        assert [r[СТАТУС] for r in строки] == ["archived"] * 3
        # Уже снятое не меняется — в журнале его нет
        assert [j[1] for j in журнал] == ["updated", "updated"]
        число = "3"
    else:
        assert [r[УДАЛЕНО] for r in строки] == [True] * 3
        assert [j[1] for j in журнал] == ["deleted"] * 3
        число = "3"

    # trans_choice на языке адреса: «2 объявления», «2 ta e’lon»
    успех = сессия(итог)["success"]
    assert число in успех
    assert ("e’lon" in успех) is (prefix == "/uz")
    assert ("объявлени" in успех) is (prefix == "")


def test_пачкой_свободные_слоты(сайт):
    итог = послать(
        сайт,
        "/cabinet/listings/bulk",
        ("archived", "archived", "active", "active", "active"),
        uid=продавец(),
        body=lambda ids: {"action": "renew", "ids": ids[:2]},
        id_index=None,
    )

    # Свободен один слот из четырёх, а выбрано два — не продлевается ни одно
    assert сессия(итог)["error"].startswith("Достигнут лимит тарифа Free")
    assert [r[СТАТУС] for r in итог["база"]["listings"][:2]] == ["archived", "archived"]


@pytest.mark.parametrize(
    ("body", "ошибки"),
    [
        ({}, ["action", "ids"]),
        ({"action": "boom", "ids": []}, ["action", "ids"]),
        ({"action": "archive", "ids": ["x", 1.5, None]}, ["ids.0", "ids.1", "ids.2"]),
        ({"action": "renew", "ids": "7"}, ["ids"]),
        # Проверку прошло, но своих объявлений среди выбранных нет
        ({"action": "renew", "ids": [999999]}, None),
        ({"action": "renew", "ids": [" 7 "]}, None),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_пачкой_ошибки(сайт, body, ошибки, prefix):
    итог = послать(
        сайт,
        prefix + "/cabinet/listings/bulk",
        ("rejected",),
        uid=продавец(),
        body=body,
        id_index=None,
    )
    данные = сессия(итог)

    assert итог["ответ"]["status"] == 302

    if ошибки is None:
        assert данные["error"] == ("Nothing is selected" if prefix else "Ничего не выбрано")
    else:
        assert list(данные["errors"]["default"]["messages"]) == ошибки
        assert данные["_old_input"] == (body or [])

    assert итог["база"]["listings"][0][СТАТУС] == "rejected"
    assert итог["база"]["journal"] == []


def test_пачкой_только_отклонённые(сайт):
    итог = послать(
        сайт,
        "/cabinet/listings/bulk",
        ("rejected",),
        uid=продавец(),
        body=lambda ids: {"action": "renew", "ids": ids},
        id_index=None,
    )

    assert "отклонено" in сессия(итог)["error"]
    assert итог["база"]["listings"][0][СРОК] == через(1)
