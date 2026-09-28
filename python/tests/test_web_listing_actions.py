"""
Этап 5, шаг 23: «Мои объявления» на Django неотличимы от Laravel —
ответ, сессия (сообщение, ошибки) и что записано: статус, сроки, мягкое
удаление, search_text, лента кабинета и уведомления, журнал
администратора.

Продлить (срок от сегодня по тарифу, отклонённое — нет, лимит тарифа),
снять, удалить (DELETE от Inertia — 303), опубликовать заново
возвращённое (лимит, уведомление компании), пачкой (проверка ввода,
отклонённые не продлеваются, свободные слоты, trans_choice на языках).
Чужое объявление — 404.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'seller']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    # Как в контейнере: перевод у Laravel выключен, его ведёт Python
    # (docker/render-entrypoint.sh) — иначе синхронная очередь теста сразу
    # запускала бы TranslateListing после продления
    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
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
                int(
                    php(
                        "echo App\\Models\\Listing::factory()->create(["
                        f"'company_id' => {cid}, 'status' => '{status}',"
                        f"'title' => 'Цемент {i}', 'description' => 'Мешки по 50 кг',"
                        "'moderation_note' => 'Уточните цену',"
                        "'expires_at' => now()->addDay(), 'published_at' => "
                        f"{'null' if status == 'draft' else 'now()->subDays(10)'}"
                        "])->id;",
                        {"MACHINE_TRANSLATION_ENABLED": "false"},
                    ).splitlines()[-1]
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
            # Laravel берёт выбранные без сортировки (физический порядок
            # строк PostgreSQL), Django — по id: порядок строк журнала не сверяем
            "journal": sorted(журнал),
        }

    return run


def сверить(
    сайт: str,
    path: str,
    статусы: tuple[str, ...],
    *,
    uid: int,
    body: Any = None,
    method: str = "POST",
    id_index: int | None = 0,
) -> dict[str, Any]:
    """Отправить на обе стороны; номер объявления подставляется после подготовки."""
    подготовка = объявления(*статусы)
    ids = подготовка()
    адрес = path.format(id=ids[id_index] if id_index is not None and ids else 0, ids=ids)

    def body_of() -> Any:
        return body(ids) if callable(body) else body

    return отправить(
        сайт,
        адрес,
        lambda: _повторить(подготовка, ids),
        снимок(),
        uid=uid,
        body=body_of(),
        method=method,
        headers=inertia(),
    )


def _повторить(подготовка: Callable[[], list[int]], ids: list[int]) -> None:
    """Каждая сторона — с теми же номерами объявлений: сбросить последовательность."""
    sql("select setval('listings_id_seq', %s, false)", [min(ids) if ids else 1])
    новые = подготовка()
    assert новые == ids, (новые, ids)


# ── Одно объявление ─────────────────────────────────────────────────


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("status", ["active", "archived", "draft", "rejected"])
def test_продлить(сайт, status, admin):
    итог = сверить(сайт, "/cabinet/listings/{id}/renew", (status,), uid=продавец(admin))

    assert итог["ответ"]["status"] == 302
    assert ('"error":' in итог["сессия"]["payload"]) is (status == "rejected")


def test_продлить_сверх_лимита(сайт):
    """Free — 4 активных: пятое не продлевается, сообщение с подсказкой."""
    итог = сверить(
        сайт,
        "/cabinet/listings/{id}/renew",
        ("archived", "active", "active", "active", "active"),
        uid=продавец(),
    )

    assert '"error":' in итог["сессия"]["payload"]


@pytest.mark.parametrize("admin", [False, True])
def test_снять_и_удалить(сайт, admin):
    uid = продавец(admin)
    сверить(сайт, "/cabinet/listings/{id}/archive", ("active",), uid=uid)
    итог = сверить(сайт, "/cabinet/listings/{id}", ("active",), uid=uid, method="DELETE")

    assert итог["ответ"]["status"] == 303
    assert итог["база"]["listings"][0][5] is True


@pytest.mark.parametrize("status", ["needs_changes", "active", "rejected"])
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_опубликовать_заново(сайт, status, prefix):
    итог = сверить(сайт, prefix + "/cabinet/listings/{id}/resubmit", (status,), uid=продавец())

    assert bool(итог["база"]["notifications"]) is (status == "needs_changes")


def test_опубликовать_заново_сверх_лимита(сайт):
    итог = сверить(
        сайт,
        "/cabinet/listings/{id}/resubmit",
        ("needs_changes", "active", "active", "active", "active"),
        uid=продавец(),
    )

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


# ── Пачкой ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("what", ["renew", "archive", "delete"])
@pytest.mark.parametrize("prefix", ["", "/en", "/uz"])
def test_пачкой(сайт, what, prefix):
    итог = сверить(
        сайт,
        prefix + "/cabinet/listings/bulk",
        ("active", "archived", "rejected"),
        uid=продавец(True),
        body=lambda ids: {"action": what, "ids": [str(i) for i in ids]},
        id_index=None,
    )

    assert '"success":' in итог["сессия"]["payload"]


def test_пачкой_свободные_слоты(сайт):
    итог = сверить(
        сайт,
        "/cabinet/listings/bulk",
        ("archived", "archived", "active", "active", "active"),
        uid=продавец(),
        body=lambda ids: {"action": "renew", "ids": ids[:2]},
        id_index=None,
    )

    assert '"error":' in итог["сессия"]["payload"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"action": "boom", "ids": []},
        {"action": "archive", "ids": ["x", 1.5, None]},
        {"action": "renew", "ids": "7"},
        {"action": "renew", "ids": [999999]},
        {"action": "renew", "ids": [" 7 "]},
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_пачкой_ошибки(сайт, body, prefix):
    сверить(
        сайт,
        prefix + "/cabinet/listings/bulk",
        ("rejected",),
        uid=продавец(),
        body=body,
        id_index=None,
    )


def test_пачкой_только_отклонённые(сайт):
    итог = сверить(
        сайт,
        "/cabinet/listings/bulk",
        ("rejected",),
        uid=продавец(),
        body=lambda ids: {"action": "renew", "ids": ids},
        id_index=None,
    )

    assert '"error":' in итог["сессия"]["payload"]
