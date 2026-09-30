"""
Этап 5, шаг 65: просьбы оставить отзыв (reviews:ask у Laravel) —
задача reviews_ask расписания Django (savdex/schedule.py).

На одних данных задача Django оставляет те же уведомления, что команда
Laravel: о площадке — через неделю после регистрации, не админу, не
неподтверждённому, не отключённому, не тому, кто уже написал отзыв или
уже получил просьбу; о компании — через 3–30 дней после раскрытия, одна
на пару «человек — компания» (первое раскрытие), не удалённой и не заблокированной
компании, не после жалобы, не при уже написанном отзыве и не повторно.
Язык — профиля человека.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}
ЦЕЛИ = ("t-ok", "t-gone", "t-blocked", "t-fresh", "t-old", "t-complaint", "t-reviewed", "t-asked")


@pytest.fixture(scope="module")
def компании() -> dict[str, int]:
    свежая_база()
    php(
        "foreach (['buyer', 'other', 'other2', 'other3', "
        + ", ".join(f"'{slug}'" for slug in ЦЕЛИ)
        + "] as $s) { App\\Models\\Company::factory()->create(['slug' => $s, "
        "'name' => 'ООО '.$s, 'status' => 'active']); } echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    return {r[0]: r[1] for r in sql("select slug, id from companies")}


def подготовка(компании: dict[str, int]) -> dict[str, int]:
    sql(
        "truncate user_notifications, platform_reviews, contact_unlocks, reviews "
        "restart identity cascade"
    )
    sql("delete from users")
    sql("update companies set deleted_at = null, status = 'active'")
    buyer = компании["buyer"]
    люди: dict[str, int] = {}
    # Одна компания раскрывает контакты другой один раз (уникальный ключ):
    # у каждого, кто раскрывает t-ok, — своя компания
    своя = {"fresh": "other", "gone": "other2", "blocked": "other3"}

    # (имя, язык, подтверждён, дней с регистрации, админ, статус, отключён)
    for name, locale, verified, days, admin, status, deleted in (
        ("uz-week", "uz", True, 10, False, "active", False),
        ("fresh", "ru", True, 3, False, "active", False),
        ("wrote", "ru", True, 10, False, "active", False),
        ("asked", "ru", True, 10, False, "active", False),
        ("unverified", "ru", False, 10, False, "active", False),
        ("admin", "ru", True, 10, True, "active", False),
        ("gone", "ru", True, 10, False, "active", True),
        ("blocked", "ru", True, 10, False, "blocked", False),
        ("en-week", "en", True, 10, False, "active", False),
    ):  # fmt: skip
        [(uid,)] = sql(
            "insert into users (name, email, password, company_id, locale, email_verified_at, "
            "is_admin, status, deleted_at, created_at, updated_at) values (%s, %s, 'x', %s, "
            "%s, %s, %s, %s, %s, now() - make_interval(days => %s), now()) returning id",
            [
                name, f"{name}@example.uz", компании[своя.get(name, "buyer")], locale,
                "2026-01-01" if verified else None, admin, status,
                "2026-09-01" if deleted else None, days,
            ],
        )  # fmt: skip
        люди[name] = uid

    sql(
        "insert into platform_reviews (user_id, company_id, rating, body, status, created_at, "
        "updated_at) values (%s, %s, 5, 'Хорошо', 'published', now(), now())",
        [люди["wrote"], buyer],
    )
    sql(
        "insert into user_notifications (user_id, company_id, type, title, tone, url, "
        "created_at, updated_at) values (%s, %s, 'platform_review_ask', 'Было', 'info', "
        "'/reviews/new', now(), now())",
        [люди["asked"], buyer],
    )

    # Раскрытия: (кто, у какой компании, дней назад, жалоба)
    for who, target, days, complaint in (
        ("uz-week", "t-ok", 5, None),
        ("uz-week", "t-gone", 5, None),
        ("uz-week", "t-blocked", 5, None),
        ("uz-week", "t-fresh", 1, None),
        ("uz-week", "t-old", 40, None),
        ("uz-week", "t-complaint", 5, "pending"),
        ("uz-week", "t-reviewed", 5, None),
        ("uz-week", "t-asked", 5, None),
        ("fresh", "t-ok", 4, None),
        ("gone", "t-ok", 4, None),
        ("blocked", "t-ok", 4, None),
    ):  # fmt: skip
        sql(
            "insert into contact_unlocks (company_id, target_company_id, user_id, credits_spent, "
            "complaint_status, created_at, updated_at) values (%s, %s, %s, 1, %s, "
            "now() - make_interval(days => %s), now())",
            [компании[своя.get(who, "buyer")], компании[target], люди[who], complaint, days],
        )

    sql(
        "insert into reviews (company_id, author_company_id, rating, body, status, created_at, "
        "updated_at) values (%s, %s, 4, 'Отзыв', 'published', now(), now())",
        [компании["t-reviewed"], buyer],
    )
    sql(
        "insert into user_notifications (user_id, company_id, type, title, tone, url, "
        "created_at, updated_at) values (%s, %s, 'review_ask', 'Было', 'info', "
        "'/company/t-asked#reviews', now(), now())",
        [люди["uz-week"], buyer],
    )
    sql("update companies set deleted_at = now() where slug = 't-gone'")
    sql("update companies set status = 'blocked' where slug = 't-blocked'")

    return люди


def снимок() -> list[tuple[Any, ...]]:
    return sorted(
        sql(
            "select u.email, n.company_id, n.type, n.title, n.body, n.tone, n.url, n.read_at "
            "from user_notifications n join users u on u.id = n.user_id"
        ),
        key=repr,
    )


def test_как_у_laravel(компании, tmp_path):
    подготовка(компании)
    php("Illuminate\\Support\\Facades\\Artisan::call('reviews:ask'); echo 'ok';", БЕЗ_ПЕРЕВОДА)
    л = снимок()

    подготовка(компании)
    out = subprocess.run(
        [sys.executable, "manage.py", "schedule", "--once", "reviews_ask"],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "PYTHONPATH": str(PYTHON),
            "SAVDEX_SCHEDULE_STATE": str(tmp_path / "state"),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    д = снимок()

    assert д == л, (д, л)
    assert "Просьб о площадке: 2, о компаниях: 2." in out.stdout
    новые = [row for row in д if row[3] != "Было"]
    assert {(row[0], row[2]) for row in новые} == {
        ("uz-week@example.uz", "platform_review_ask"),
        ("en-week@example.uz", "platform_review_ask"),
        ("uz-week@example.uz", "review_ask"),
        ("fresh@example.uz", "review_ask"),
    }
