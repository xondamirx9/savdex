"""
Уведомления компании — на языке каждого сотрудника (users.locale).

Фоновые задачи и модерация пишут компании без запроса посетителя: текст
собирается для каждого получателя на языке его профиля; лента компании —
на языке первого сотрудника.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from .factories import компания, пользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

#: Снятие истёкшего объявления: те же тексты, что у задачи expire_listings
СНЯТИЕ = """
import django
django.setup()
from functools import partial
from savdex.web import ui
from savdex.web.listing_actions import _notify_company
import sys

_notify_company(
    None,
    {"id": int(sys.argv[1])},
    "listing_expiring",
    partial(ui.t, "messages.listing.expired_title", title="Цемент М500"),
    "warning",
    "/cabinet/listings?status=expired",
    lambda locale: ui.t("messages.listing.expired_body", locale),
)
"""


@pytest.fixture(scope="module")
def компания_с_сотрудниками() -> int:
    свежая_база()
    c = компания(slug="multi")

    for locale in ("en", "uz", "ru"):
        пользователь(company_id=c, locale=locale)

    return c


def test_каждому_на_его_языке(компания_с_сотрудниками):
    c = компания_с_сотрудниками
    subprocess.run(
        [sys.executable, "-c", СНЯТИЕ, str(c)],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        check=True,
        capture_output=True,
    )

    получено = sql(
        "select u.locale, n.title, n.body from user_notifications n "
        "join users u on u.id = n.user_id where n.company_id = %s order by u.id",
        [c],
    )

    assert получено == [
        (
            "en",
            "The listing “Цемент М500” was taken down: its term has ended",
            "Renew it in your account — impressions resume right away.",
        ),
        (
            "uz",
            "«Цемент М500» e’loni olib tashlandi: joylashtirish muddati tugadi",
            "Uni kabinetda uzaytiring — ko‘rsatuvlar darhol tiklanadi.",
        ),
        (
            "ru",
            "Объявление «Цемент М500» снято: истёк срок размещения",
            "Продлите его в кабинете — показы возобновятся сразу.",
        ),
    ]
    # Лента компании — на языке первого сотрудника
    assert sql("select message from activity_events where company_id = %s", [c]) == [
        ("The listing “Цемент М500” was taken down: its term has ended",)
    ]
