"""
Этап 5, шаг 22: машинный перевод на Python (manage.py translate) —
объявления, резюме, закупки, новости (как задачи TranslateListing,
TranslateResume, TranslateTender, TranslateNewsPost у Laravel) и тексты
страниц (translations:fill).

Переводчик — заглушка, HTTP-сервер (SAVDEX_TRANSLATE_URL). Перевод —
«<язык>:<текст>»; текст со словом FAIL — ошибка 500, RATE — отказ 429.
Проверяются json-столбцы текстом (json хранит текст как есть),
search_text и то, тронута ли строка (updated_at).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from .factories import объявление, пользователь, тендер
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

ВКЛЮЧЁН = {"MACHINE_TRANSLATION_ENABLED": "true"}


class _Заглушка(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        length = int(self.headers.get("Content-Length") or 0)
        text = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True).get("q", [""])[0]

        if "FAIL" in text or "RATE" in text:
            self.send_response(500 if "FAIL" in text else 429)
            self.end_headers()

            return

        body = json.dumps([[[f"{query['tl'][0]}:{text}", text]]]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def переводчик() -> Iterator[str]:
    свежая_база()
    сервер = ThreadingHTTPServer(("127.0.0.1", 0), _Заглушка)
    поток = threading.Thread(target=сервер.serve_forever, daemon=True)
    поток.start()

    try:
        yield f"http://127.0.0.1:{сервер.server_address[1]}/translate_a/single"
    finally:
        сервер.shutdown()


def _python(url: str, *args: str) -> None:
    вывод = subprocess.run(
        [sys.executable, "manage.py", "translate", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, **ВКЛЮЧЁН, "SAVDEX_TRANSLATE_URL": url},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]


def перевести(
    url: str,
    подготовить: Callable[[], None],
    снимок: Callable[[], Any],
    python_args: list[str],
) -> Any:
    """Подготовка, перевод manage.py translate, снимок базы после него."""
    подготовить()
    _python(url, *python_args)

    return снимок()


#: Язык сайта → код языка у переводчика
ЯЗЫКИ = (("en", "en"), ("uz", "uz"), ("tr", "tr"), ("zh", "zh-CN"))


def переводы(текст: Any, ручные: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Ожидаемые переводы: ручные остаются (пустые — прочь, но и не
    переводятся), недостающие языки — «<код>:<текст>» в порядке ЯЗЫКИ.
    """
    ручные = ручные or {}
    итог = {k: v for k, v in ручные.items() if v not in ("", None)}

    for язык, код in ЯЗЫКИ:
        if язык not in ручные:
            итог[язык] = текст(код) if callable(текст) else f"{код}:{текст}"

    return итог


def как_php(значение: Any) -> str:
    """json_encode у PHP: не ASCII — \\uXXXX, «/» — «\\/»: так json хранит текст."""
    return json.dumps(значение, separators=(",", ":")).replace("/", "\\/")


def json_столбец(текст: str, ждём: Any) -> None:
    """Столбец json: то же значение, в том же порядке ключей и в записи PHP."""
    assert json.loads(текст) == ждём
    assert текст == как_php(ждём)


# ── Объявления ──────────────────────────────────────────────────────

ПЕРВЫЙ = ("Абзац про цемент. " * 150).strip()
ДЛИННЫЙ = ("Длинное " * 700).strip()
ДЛИННОЕ = "\n\n".join([ПЕРВЫЙ, "Короткий абзац.", ДЛИННЫЙ])


def длинное(код: str) -> str:
    """
    Длинный текст — кусками до 4000 знаков: два первых абзаца вместе, а
    абзац длиннее куска — по границе слов (500 и 200 слов).
    """
    слова = ДЛИННЫЙ.split(" ")
    куски = [ПЕРВЫЙ + "\n\nКороткий абзац.", " ".join(слова[:500]), " ".join(слова[500:])]

    return "\n\n".join(f"{код}:{кусок}" for кусок in куски)


def _объявление() -> int:
    found = sql("select id from listings where slug = 'tr-listing'")

    if found:
        return int(found[0][0])

    return объявление(slug="tr-listing")


def _снимок_объявления(lid: int) -> Callable[[], Any]:
    return lambda: sql(
        "select title_i18n::text, description_i18n::text, search_text, "
        "updated_at > now() - interval '1 hour' from listings where id = %s",
        [lid],
    )


@pytest.mark.parametrize(
    ("title", "description", "titles", "descriptions", "ждём"),
    [
        (
            "Цемент М400 оптом", "Мешки по 50 кг / самовывоз", None, None,
            (переводы("Цемент М400 оптом"), переводы("Мешки по 50 кг / самовывоз")),
        ),
        # Ручной перевод остаётся; пустой и null — не переводятся и уходят
        (
            "Цемент", None, '{"en":"Manual","uz":"","zh":null}', '{"tr":"Elle"}',
            ({"en": "Manual", "tr": "tr:Цемент"}, {"tr": "Elle"}),
        ),
        # Ошибка переводчика (500) — без перевода, остальное переводится
        ("Цемент FAIL", "Описание", None, "[]", ([], переводы("Описание"))),
        ("Кирпич", ДЛИННОЕ, None, None, (переводы("Кирпич"), переводы(длинное))),
        # Всё переведено вручную; пустое описание — пустой список
        (
            "Песок", "   ", '{"en":"a","uz":"b","tr":"c","zh":"d"}', None,
            ({"en": "a", "uz": "b", "tr": "c", "zh": "d"}, []),
        ),
        # Отказ 429 на описании — описания нет, заголовок уже переведён
        (
            "Щебень «гранит» 5/20", "Описание RATE", '{"zh":"已有"}', None,
            (переводы("Щебень «гранит» 5/20", {"zh": "已有"}), []),
        ),
    ],
)  # fmt: skip
def test_объявление(переводчик, title, description, titles, descriptions, ждём):
    lid = _объявление()

    def подготовить() -> None:
        sql(
            "update listings set title = %s, description = %s, title_i18n = %s::json, "
            "description_i18n = %s::json, search_text = 'old', status = 'active', "
            "updated_at = now() - interval '1 day' where id = %s",
            [title, description, titles, descriptions, lid],
        )

    [(заголовки, описания, search_text, тронута)] = перевести(
        переводчик,
        подготовить,
        _снимок_объявления(lid),
        ["--kind", "listings", "--id", str(lid)],
    )

    json_столбец(заголовки, ждём[0])
    json_столбец(описания, ждём[1])
    assert тронута is True
    # Поиск — по заголовку, описанию и переводам заголовка (и транслитом)
    assert search_text.startswith(title.lower())
    assert all(str(v).lower() in search_text for v in (ждём[0] or {}).values())
    assert "old" not in search_text.split()


# ── Резюме ──────────────────────────────────────────────────────────


def _резюме() -> int:
    found = sql("select id from resumes where slug = 'tr-resume'")

    if found:
        return int(found[0][0])

    [(rid,)] = sql(
        "insert into resumes (user_id, slug, title, status, created_at, updated_at) "
        "values (%s, 'tr-resume', 'Бухгалтер', 'published', now(), now()) returning id",
        [пользователь()],
    )

    return int(rid)


ДЕСЯТЬ = [{"position": f"Должность {i}", "duties": "Учёт" if i % 2 else ""} for i in range(10)]


def места(код: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Места работы: переводятся первые восемь (их и читают), дальше —
    пустые строки на тех же местах; пустые обязанности — null.
    """
    return [
        {
            "position": f"{код}:{job['position']}" if i < 8 else None,
            "duties": f"{код}:{job['duties']}" if job["duties"] and i < 8 else None,
        }
        for i, job in enumerate(jobs)
    ]


@pytest.mark.parametrize(
    ("about", "jobs", "jobs_i18n", "ждём"),
    [
        (
            "Опыт 10 лет", ДЕСЯТЬ, None,
            (переводы("Опыт 10 лет"), переводы(lambda к: места(к, ДЕСЯТЬ))),
        ),
        (
            None, [{"position": "Бухгалтер", "duties": None}], '{"en":[{"position":"x"}]}',
            (
                [],
                переводы(
                    lambda к: места(к, [{"position": "Бухгалтер", "duties": None}]),
                    {"en": [{"position": "x"}]},
                ),
            ),
        ),
        ("О себе FAIL", [], None, ([], [])),
    ],
)  # fmt: skip
def test_резюме(переводчик, about, jobs, jobs_i18n, ждём):
    rid = _резюме()

    def подготовить() -> None:
        sql(
            "update resumes set about = %s, jobs = %s::json, title_i18n = null, about_i18n = null, "
            "jobs_i18n = %s::json, updated_at = now() - interval '1 day' where id = %s",
            [about, json.dumps(jobs, ensure_ascii=False), jobs_i18n, rid],
        )

    [(заголовки, о_себе, работа, тронута)] = перевести(
        переводчик,
        подготовить,
        lambda: sql(
            "select title_i18n::text, about_i18n::text, jobs_i18n::text, "
            "updated_at > now() - interval '1 hour' from resumes where id = %s",
            [rid],
        ),
        ["--kind", "resumes", "--id", str(rid)],
    )

    json_столбец(заголовки, переводы("Бухгалтер"))
    json_столбец(о_себе, ждём[0])
    json_столбец(работа, ждём[1])
    assert тронута is True


# ── Закупки и новости ───────────────────────────────────────────────


def _закупка() -> int:
    found = sql("select id from tenders where title = 'Закупка для перевода'")

    if found:
        return int(found[0][0])

    return тендер(title="Закупка для перевода")


@pytest.mark.parametrize(
    ("description", "customer", "titles", "ждём"),
    [
        (
            "Поставка труб", "Ташкентводоканал", None,
            (переводы("Закупка для перевода"), переводы("Поставка труб")),
        ),
        (None, None, '{"en":"Pipes"}', (переводы("Закупка для перевода", {"en": "Pipes"}), [])),
    ],
)  # fmt: skip
def test_закупка(переводчик, description, customer, titles, ждём):
    tid = _закупка()

    def подготовить() -> None:
        sql(
            "update tenders set description = %s, customer = %s, title_i18n = %s::json, "
            "description_i18n = null, search_text = 'old', "
            "updated_at = now() - interval '1 day' where id = %s",
            [description, customer, titles, tid],
        )

    [(заголовки, описания, search_text, тронута)] = перевести(
        переводчик,
        подготовить,
        lambda: sql(
            "select title_i18n::text, description_i18n::text, search_text, "
            "updated_at > now() - interval '1 hour' from tenders where id = %s",
            [tid],
        ),
        ["--kind", "tenders", "--id", str(tid)],
    )

    json_столбец(заголовки, ждём[0])
    json_столбец(описания, ждём[1])
    assert тронута is True
    # Поиск — заголовок, описание, заказчик и переводы заголовка
    assert search_text.startswith(
        " ".join(x.lower() for x in ("Закупка для перевода", description, customer) if x)
    )
    assert all(v.lower() in search_text for v in ждём[0].values())


def _новость() -> int:
    found = sql("select id from news_posts where slug = 'tr-news'")

    if found:
        return int(found[0][0])

    [(nid,)] = sql(
        "insert into news_posts (slug, title, category, excerpt, body, is_published, "
        "created_at, updated_at) values ('tr-news', 'Новость площадки', 'platform', '', '', "
        "true, now(), now()) returning id"
    )

    return int(nid)


@pytest.mark.parametrize(
    ("excerpt", "body", "titles", "ждём"),
    [
        (
            "Коротко", "Текст новости\n\nВторой абзац", None,
            (переводы("Новость площадки"), переводы("Коротко"),
             переводы("Текст новости\n\nВторой абзац")),
        ),
        ("", "  ", '{"uz":"Yangilik"}', (переводы("Новость площадки", {"uz": "Yangilik"}), [], [])),
    ],
)  # fmt: skip
def test_новость(переводчик, excerpt, body, titles, ждём):
    nid = _новость()

    def подготовить() -> None:
        sql(
            "update news_posts set excerpt = %s, body = %s, title_i18n = %s::json, "
            "excerpt_i18n = null, body_i18n = null, updated_at = now() - interval '1 day' "
            "where id = %s",
            [excerpt, body, titles, nid],
        )

    [(заголовки, анонсы, тексты, тронута)] = перевести(
        переводчик,
        подготовить,
        lambda: sql(
            "select title_i18n::text, excerpt_i18n::text, body_i18n::text, "
            "updated_at > now() - interval '1 hour' from news_posts where id = %s",
            [nid],
        ),
        ["--kind", "news", "--id", str(nid)],
    )

    json_столбец(заголовки, ждём[0])
    json_столбец(анонсы, ждём[1])
    json_столбец(тексты, ждём[2])
    assert тронута is True


# ── Тексты страниц ──────────────────────────────────────────────────


@pytest.mark.parametrize("rate", [False, True])
def test_тексты_страниц(переводчик, rate):
    def подготовить() -> None:
        sql("delete from content_translations")

        for i, (source, attempts) in enumerate(
            [
                ("Описание компании", 0),
                ("Сломанный FAIL", 2),
                ("Уже переведено", 0),
                ("Сдался FAIL", 5),
                ("Отказ RATE" if rate else "Ещё текст", 1),
                ("Последний", 0),
            ]
        ):
            sql(
                "insert into content_translations (hash, locale, source, translation, attempts, "
                "created_at, updated_at) values (%s, 'en', %s, %s, %s, now(), "
                "now() - interval '1 day')",
                [f"{i:040d}", source, "done" if i == 2 else None, attempts],
            )

    итог = перевести(
        переводчик,
        подготовить,
        lambda: sql(
            "select source, translation, attempts, updated_at > now() - interval '1 hour' "
            "from content_translations order by id"
        ),
        ["--once", "--limit", "20"],
    )

    # (текст, перевод, попытки, тронута): переведённое и сдавшееся
    # (5 попыток) не трогаются; ошибка 500 — +1 попытка
    if rate:
        # Отказ 429 прерывает проход: очередь — по числу попыток, текст
        # с двумя попытками до отказа не дошёл
        assert итог == [
            ("Описание компании", "en:Описание компании", 0, True),
            ("Сломанный FAIL", None, 2, False),
            ("Уже переведено", "done", 0, False),
            ("Сдался FAIL", None, 5, False),
            ("Отказ RATE", None, 1, False),
            ("Последний", "en:Последний", 0, True),
        ]
    else:
        assert итог == [
            ("Описание компании", "en:Описание компании", 0, True),
            ("Сломанный FAIL", None, 3, True),
            ("Уже переведено", "done", 0, False),
            ("Сдался FAIL", None, 5, False),
            ("Ещё текст", "en:Ещё текст", 1, True),
            ("Последний", "en:Последний", 0, True),
        ]


# ── Добор ────────────────────────────────────────────────────────────


def test_добор_переводит_недостающее(переводчик):
    """Проход --once находит объявления без переводов и переводит их."""
    lid = _объявление()
    # Отказ 429 прерывает проход целиком — очередь текстов пуста
    sql("delete from content_translations")
    sql(
        "update listings set title = 'Цемент для добора', description = null, title_i18n = null, "
        "description_i18n = null, status = 'active' where id = %s",
        [lid],
    )
    _python(переводчик, "--once")
    [(titles,)] = sql("select title_i18n::text from listings where id = %s", [lid])

    assert json.loads(titles) == переводы("Цемент для добора")
