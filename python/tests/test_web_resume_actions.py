"""
Своё резюме на Django: опубликовать (дата — если не было,
заблокированное — ошибка поля status), скрыть (только опубликованное),
удалить (мягко, фото — с диска, DELETE от Inertia — 303), править
(проверка полей, пустые пункты отбрасываются, адрес — один раз),
фото. Без резюме — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

ФОТО = "resumes/parity.webp"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
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
            "select status, case when published_at > now() - interval '1 hour' then 'сейчас' "
            "else published_at::text end, "
            "deleted_at is not null, updated_at > now() - interval '1 hour' from resumes"
        ),
        "photo": (Path(КОРЕНЬ) / "storage/app/public" / ФОТО).exists(),
    }


#: (действие, статус, опубликовано ли раньше) → статус и дата публикации
#: после; дата «сейчас» — публикуется впервые; строка — ошибка поля status
ПУБЛИКАЦИЯ = {
    ("publish", "draft", False): ("published", "сейчас"),
    ("publish", "published", True): ("published", "2026-09-01 10:00:00"),
    ("publish", "hidden", True): ("published", "2026-09-01 10:00:00"),
    ("publish", "hidden", False): ("published", "сейчас"),
    ("publish", "blocked", True): "blocked",
    # Скрыть можно только опубликованное, прочее — без изменений
    ("hide", "draft", False): ("draft", None),
    ("hide", "published", True): ("hidden", "2026-09-01 10:00:00"),
    ("hide", "hidden", True): ("hidden", "2026-09-01 10:00:00"),
    ("hide", "hidden", False): ("hidden", None),
    ("hide", "blocked", True): ("blocked", "2026-09-01 10:00:00"),
}

СООБЩЕНИЯ = {
    ("", "publish"): "Резюме опубликовано — теперь его видят компании.",
    ("", "hide"): "Резюме снято с публикации.",
    ("", "blocked"): "Резюме снято модерацией. Напишите в поддержку, если это ошибка.",
    ("/en", "publish"): "Resume published — companies can see it now.",
    ("/en", "hide"): "Resume unpublished.",
    (
        "/en",
        "blocked",
    ): "The resume was removed by moderation. Contact support if this is a mistake.",
}


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


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
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/resume/{verb}",
        резюме(status, опубликовано=опубликовано),
        снимок,
        uid=соискатель(),
        headers=inertia(),
    )
    ответ, база = итог["ответ"], итог["база"]

    if status is None:
        assert ответ["status"] == 404
        assert база["resumes"] == []

        return

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == f"{сайт}{prefix}/cabinet/settings"
    ждём = ПУБЛИКАЦИЯ[(verb, status, опубликовано)]
    [(после, дата, удалено, тронуто)] = база["resumes"]
    assert удалено is False and база["photo"] is True

    if ждём == "blocked":
        assert (после, тронуто) == ("blocked", False)
        assert json_errors(_сессия(итог)) == {"status": [СООБЩЕНИЯ[(prefix, "blocked")]]}

        return

    assert (после, дата) == ждём
    # Строка правится, только если статус или дата меняются
    assert тронуто is ((после, дата) != (status, "2026-09-01 10:00:00" if опубликовано else None))
    assert _сессия(итог)["status"] == СООБЩЕНИЯ[(prefix, verb)]


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

    if status is None:
        assert итог["ответ"]["status"] == 404
        assert итог["база"]["photo"] is False

        return

    assert итог["ответ"]["status"] == 303
    assert итог["база"]["resumes"][0][2] is True and not итог["база"]["photo"]


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


#: Столбцы снимок_правки()
СТОЛБЦЫ = (
    "slug", "title", "field", "country_id", "city_id", "salary", "currency", "employment",
    "schedule", "experience_months", "about", "skills", "jobs", "education", "languages",
    "contact_name", "contact_phone", "contact_email", "show_phone", "show_email", "title_i18n",
    "about_i18n", "jobs_i18n", "свежее",
)  # fmt: skip
JSON = {"employment", "schedule", "skills", "jobs", "education", "languages"} | {
    "title_i18n", "about_i18n", "jobs_i18n"
}  # fmt: skip


def _строка(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        k: json.loads(v) if k in JSON and v is not None else v
        for k, v in zip(СТОЛБЦЫ, row, strict=True)
    }


#: Опыт: 2018-03 … сейчас (вторая работа без конца перекрывает первую)
ОПЫТ_ПОЛНОГО = 103

ПРАВКИ = [
    # (тело, ждём): ждём — поля сохранённого резюме или ошибки проверки
    (
        ПОЛНОЕ,
        {
            "title": "Прораб / мастер участка",
            "field": "construction",
            "salary": 15000000,
            "employment": ["full", "project"],
            "experience_months": ОПЫТ_ПОЛНОГО,
            # Пустые навыки, работы, учёба и языки отброшены, лишние ключи — тоже
            "skills": ["AutoCAD", "Сметы"],
            "jobs": [
                {
                    "company": "ООО Цемент",
                    "position": "Прораб",
                    "start": "2018-03",
                    "end": "2021-06",
                },
                # Пустой конец — null: работает до сих пор
                {"company": "Бетон", "position": "Мастер", "start": "2020-01", "end": None},
            ],
            "education": [{"institution": "ТАСИ", "level": "bachelor", "year": "2012"}],
            "languages": [{"name": "Русский", "level": "native"}],
            "show_phone": False,
            "show_email": True,
            # Заголовок и «о себе» сменились — прежний перевод не годится
            "title_i18n": None,
            "about_i18n": None,
        },
    ),
    (
        {"title": "Прораб"},
        # Заголовок прежний — перевод остаётся (если резюме было)
        {"title": "Прораб", "skills": [], "jobs": [], "experience_months": 0},
    ),
    (
        {"title": "Прораб", "about": "Новое о себе", "employment": []},
        {"title": "Прораб", "employment": [], "about_i18n": None},
    ),
    (
        {"title": "Инженер ПТО", "jobs": [{"company": "A", "position": "B", "start": "2019"}]},
        {
            "title": "Инженер ПТО",
            "jobs": [{"company": "A", "position": "B", "start": "2019"}],
            "experience_months": 93,
            "title_i18n": None,
        },
    ),
    ({"title": "ab"}, ["title"]),
    ({**ПОЛНОЕ, "jobs": [{"company": "Без должности"}]}, ["jobs.0.position"]),
    ({**ПОЛНОЕ, "education": [{"institution": "ТАСИ", "year": "1900"}]}, ["education.0.year"]),
    ({**ПОЛНОЕ, "country_id": 999999, "city_id": "abc"}, ["city_id", "country_id"]),
    ({**ПОЛНОЕ, "contact_email": "не почта"}, ["contact_email"]),
    ({**ПОЛНОЕ, "skills": [f"навык {i}" for i in range(31)]}, ["skills"]),
    (
        {**ПОЛНОЕ, "employment": ["full", "boss"], "salary": -5, "show_phone": "yes"},
        ["employment.1", "salary", "show_phone"],
    ),
    ({**ПОЛНОЕ, "field": "space", "currency": "BTC"}, ["currency", "field"]),
    ({}, ["title"]),
]


@pytest.mark.parametrize(("body", "ждём"), ПРАВКИ)
@pytest.mark.parametrize("было", ["есть", "нет", "без адреса"])
def test_правка(сайт, body, ждём, было):
    подготовка = {"есть": есть_резюме(), "нет": нет_резюме, "без адреса": есть_резюме(None)}[было]
    итог = отправить(
        сайт,
        "/cabinet/resume",
        подготовка,
        снимок_правки,
        uid=соискатель(),
        body=body,
        method="PATCH",
        headers=inertia(),
    )
    ответ = итог["ответ"]
    строки = [_строка(row) for row in итог["база"]]

    # Inertia: PATCH, ответивший переходом, — 303, назад
    assert ответ["status"] == 303
    assert ответ["headers"]["location"] == сайт + "/cabinet/settings"

    if isinstance(ждём, list):
        assert sorted(json_errors(_сессия(итог))) == ждём

        if было == "нет":
            assert строки == []
        else:
            # Ничего не записано
            [строка] = строки
            assert (строка["title"], строка["свежее"]) == ("Прораб", False)

        return

    assert _сессия(итог)["status"] == "Резюме сохранено."
    [строка] = строки
    assert строка["свежее"] is True
    # Адрес — один раз: есть — прежний, нет — из заголовка и номера
    адрес_ = "prorab-1" if было == "есть" else _адрес_нового(строка["title"])
    assert строка["slug"] == адрес_

    for поле, значение in ждём.items():
        if было == "нет" and поле.endswith("_i18n"):
            continue

        assert строка[поле] == значение, поле

    if было != "нет" and body.get("title") == "Прораб" and "about" not in body:
        assert строка["title_i18n"] == {"en": "Foreman"}


def _адрес_нового(title: str) -> str:
    """Адрес нового резюме: заголовок латиницей и номер строки (1)."""
    return {
        "Прораб / мастер участка": "prorab-master-uchastka-1",
        "Прораб": "prorab-1",
        "Инженер ПТО": "inzhener-pto-1",
    }[title]


@pytest.mark.parametrize(
    ("prefix", "ждём"),
    [
        (
            "/en",
            {
                "title": ["This field must be at least 3 characters."],
                "jobs.0.position": ["This field is required when jobs.0.company is present."],
            },
        ),
        # На узбекском — свои короткие тексты, без имени поля
        (
            "/uz",
            {"title": ["Kamida 3 belgi kiriting."], "jobs.0.position": ["Bu maydonni to‘ldiring."]},
        ),
    ],
)
def test_правка_на_языке(сайт, prefix, ждём):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/resume",
        нет_резюме,
        снимок_правки,
        uid=соискатель(),
        body={**ПОЛНОЕ, "jobs": [{"company": "Без должности"}], "title": "ab"},
        method="PATCH",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303
    assert итог["ответ"]["headers"]["location"] == f"{сайт}{prefix}/cabinet/settings"
    assert json_errors(_сессия(итог)) == ждём
    assert итог["база"] == []


# ── Фото резюме ─────────────────────────────────────────────────────
#
# У Laravel загрузка фото всегда кончалась ошибкой 500 (ImageStore::store
# получал [400, 400] вместо ['w' => 400, 'h' => 400]); форма переехала
# на Django сразу рабочей.


def _фото(
    сайт: str, файл: tuple[str, bytes] | None, env: dict[str, str] | None = None
) -> tuple[dict[str, Any], Any]:
    from savdex import laravel_session

    from .test_web_company_profile_actions import multipart
    from .test_web_forms import SID, ТОКЕН
    from .web_site import СЕССИЯ, завести, из_django, кука

    завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: соискатель()})
    тело, тип = multipart({"photo": файл} if файл else {"note": "x"})
    ответ = из_django(
        сайт,
        "/cabinet/resume/photo",
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        {**inertia(), "Referer": сайт + "/cabinet/resume"},
        env,
        method="POST",
        body=тело,
        content_type=тип,
    )
    сессия = sql("select payload from sessions where id = %s", [SID])[0][0]

    return ответ, json.loads(base64.b64decode(сессия).decode()) if сессия else {}


@pytest.mark.parametrize("было", [True, False])
def test_фото(сайт, было):
    from .test_web_company_profile_actions import картинка

    резюме("draft")()

    if not было:
        sql("update resumes set photo_path = null")

    ответ, сессия = _фото(сайт, ("face.png", картинка(900, 600)))
    путь = sql("select photo_path from resumes")[0][0]

    assert ответ["status"] == 302
    assert re.fullmatch(r"resumes/[A-Za-z0-9]{40}\.webp", путь)
    assert (Path(КОРЕНЬ) / "storage/app/public" / путь).exists()
    # Прежнее фото с диска уходит; не было прежнего — чужой файл не трогаем
    assert (Path(КОРЕНЬ) / "storage/app/public" / ФОТО).exists() is not было
    assert сессия.get("status") == "Фотография сохранена."


@pytest.mark.parametrize("файл", [("fake.png", b"nope"), None])
def test_фото_отказ(сайт, файл):
    резюме("draft")()
    ответ, сессия = _фото(сайт, файл)

    assert ответ["status"] == 302
    assert sql("select photo_path from resumes")[0][0] == ФОТО
    assert "photo" in json_errors(сессия)


def test_фото_без_резюме(сайт):
    from .test_web_company_profile_actions import картинка

    резюме(None)()
    ответ, _ = _фото(сайт, ("face.png", картинка(10, 10)))

    assert ответ["status"] == 404


def json_errors(сессия: dict[str, Any]) -> dict[str, Any]:
    return (сессия.get("errors") or {}).get("default", {}).get("messages", {})


def test_фото_частота(сайт, monkeypatch):
    """
    throttle:30,60,resume-photo, как у Laravel: на файловом кэше
    тридцать первая загрузка за час — отказ, фото не меняется.
    """
    import hashlib

    from savdex import laravel_cache

    from .test_web_company_profile_actions import картинка

    резюме("draft")()
    monkeypatch.setenv("CACHE_STORE", "file")
    ключ = "resume-photo" + hashlib.sha1(str(соискатель()).encode()).hexdigest()
    laravel_cache.put(ключ, 30, 3600)
    laravel_cache.put(f"{ключ}:timer", int(time.time()) + 3600, 3600)

    try:
        ответ, сессия = _фото(сайт, ("face.png", картинка(900, 600)), {"CACHE_STORE": "file"})
    finally:
        laravel_cache.forget(ключ)
        laravel_cache.forget(f"{ключ}:timer")

    assert ответ["status"] == 302
    assert sql("select photo_path from resumes")[0][0] == ФОТО
    assert сессия["error"].startswith("Слишком много действий подряд")
