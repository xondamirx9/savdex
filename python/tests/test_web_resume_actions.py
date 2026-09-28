"""
Своё резюме на Django неотличимо от Laravel: опубликовать (дата — если
не было, заблокированное — ошибка поля status), скрыть (только
опубликованное), удалить (мягко, фото — с диска, DELETE от Inertia —
303). Без резюме — 404.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

ФОТО = "resumes/parity.webp"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def соискатель() -> int:
    return учётка("seeker@savdex.uz")


def резюме(status: str | None, *, опубликовано: bool = True) -> Callable[[], None]:
    def run() -> None:
        sql("delete from resumes")

        if status is None:
            return

        sql(
            "insert into resumes (user_id, title, status, photo_path, published_at, created_at, "
            "updated_at) values (%s, 'Прораб', %s, %s, %s, now() - interval '1 day', "
            "now() - interval '1 day')",
            [
                соискатель(),
                status,
                ФОТО,
                "2026-09-01 10:00:00" if опубликовано else None,
            ],
        )
        путь = Path(КОРЕНЬ) / "storage/app/public" / ФОТО
        путь.parent.mkdir(parents=True, exist_ok=True)
        путь.write_bytes(b"webp")

    return run


def снимок() -> Any:
    return {
        "resumes": sql(
            "select status, published_at::text, published_at > now() - interval '1 hour', "
            "deleted_at is not null, updated_at > now() - interval '1 hour' from resumes"
        ),
        "photo": (Path(КОРЕНЬ) / "storage/app/public" / ФОТО).exists(),
    }


@pytest.mark.parametrize("verb", ["publish", "hide"])
@pytest.mark.parametrize(
    ("status", "опубликовано"),
    [
        ("draft", False),
        ("published", True),
        ("hidden", True),
        ("hidden", False),
        ("blocked", True),
        (None, False),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_опубликовать_и_скрыть(сайт, verb, status, опубликовано, prefix):
    отправить(
        сайт,
        f"{prefix}/cabinet/resume/{verb}",
        резюме(status, опубликовано=опубликовано),
        снимок,
        uid=соискатель(),
        headers=inertia(),
    )


@pytest.mark.parametrize("status", ["published", None])
def test_удалить(сайт, status):
    итог = отправить(
        сайт,
        "/cabinet/resume",
        резюме(status),
        снимок,
        uid=соискатель(),
        method="DELETE",
        headers=inertia(),
    )

    if status is not None:
        assert итог["ответ"]["status"] == 303
        assert итог["база"]["resumes"][0][3] is True and not итог["база"]["photo"]


# ── Правка ──────────────────────────────────────────────────────────


def снимок_правки() -> Any:
    return sql(
        "select slug, title, field, country_id, city_id, salary, currency, employment::text, "
        "schedule::text, experience_months, about, skills::text, jobs::text, education::text, "
        "languages::text, contact_name, contact_phone, contact_email, show_phone, show_email, "
        "title_i18n::text, about_i18n::text, jobs_i18n::text, "
        "updated_at > now() - interval '1 hour' from resumes order by id"
    )


def есть_резюме(slug: str | None = "prorab-1") -> Callable[[], None]:
    def run() -> None:
        sql("delete from resumes")
        sql("select setval('resumes_id_seq', 1, false)")
        sql(
            "insert into resumes (user_id, slug, title, about, employment, jobs, skills, "
            "title_i18n, about_i18n, jobs_i18n, status, created_at, updated_at) "
            "values (%s, %s, 'Прораб', 'Стройка', '[\"full\"]', '[]', '[\"Excel\"]', "
            '\'{"en":"Foreman"}\', \'{"en":"Construction"}\', \'{"en":[]}\', \'published\', '
            "now() - interval '1 day', now() - interval '1 day')",
            [соискатель(), slug],
        )

    return run


def нет_резюме() -> None:
    sql("delete from resumes")
    sql("select setval('resumes_id_seq', 1, false)")


ПОЛНОЕ = {
    "title": "Прораб / мастер участка",
    "field": "construction",
    "salary": "15000000",
    "currency": "UZS",
    "employment": ["full", "project"],
    "schedule": ["shift"],
    "about": 'Стройка 10 лет, "под ключ" — https://savdex.uz',
    "skills": ["  AutoCAD ", "", "Сметы", None],
    "jobs": [
        {"company": "ООО Цемент", "position": "Прораб", "start": "2018-03", "end": "2021-06"},
        {"company": "Бетон", "position": "Мастер", "start": "2020-01", "end": "", "hack": 1},
        {"company": "", "position": "", "start": "", "end": ""},
    ],
    "education": [{"institution": "ТАСИ", "level": "bachelor", "year": "2012"}, {"faculty": "x"}],
    "languages": [{"name": "Русский", "level": "native"}, {"name": "", "level": "basic"}],
    "contact_name": "Азиз",
    "contact_phone": "+998 90 111-22-33",
    "contact_email": "aziz@savdex.uz",
    "show_phone": "0",
    "show_email": True,
}


@pytest.mark.parametrize(
    "body",
    [
        ПОЛНОЕ,
        {"title": "Прораб"},
        {"title": "Прораб", "about": "Новое о себе", "employment": []},
        {"title": "Инженер ПТО", "jobs": [{"company": "A", "position": "B", "start": "2019"}]},
        {"title": "ab"},
        {**ПОЛНОЕ, "jobs": [{"company": "Без должности"}]},
        {**ПОЛНОЕ, "education": [{"institution": "ТАСИ", "year": "1900"}]},
        {**ПОЛНОЕ, "country_id": 999999, "city_id": "abc"},
        {**ПОЛНОЕ, "contact_email": "не почта"},
        {**ПОЛНОЕ, "skills": [f"навык {i}" for i in range(31)]},
        {**ПОЛНОЕ, "employment": ["full", "boss"], "salary": -5, "show_phone": "yes"},
        {**ПОЛНОЕ, "field": "space", "currency": "BTC"},
        {},
    ],
)
@pytest.mark.parametrize("было", ["есть", "нет", "без адреса"])
def test_правка(сайт, body, было):
    подготовка = {"есть": есть_резюме(), "нет": нет_резюме, "без адреса": есть_резюме(None)}[было]
    отправить(
        сайт,
        "/cabinet/resume",
        подготовка,
        снимок_правки,
        uid=соискатель(),
        body=body,
        method="PATCH",
        headers=inertia(),
    )


@pytest.mark.parametrize("prefix", ["/en", "/uz"])
def test_правка_на_языке(сайт, prefix):
    отправить(
        сайт,
        f"{prefix}/cabinet/resume",
        нет_резюме,
        снимок_правки,
        uid=соискатель(),
        body={**ПОЛНОЕ, "jobs": [{"company": "Без должности"}], "title": "ab"},
        method="PATCH",
        headers=inertia(),
    )
