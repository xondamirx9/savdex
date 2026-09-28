"""
Этап 5, шаг 22: машинный перевод на Python пишет в базу ровно то же,
что задачи Laravel (TranslateListing, TranslateResume, TranslateTender,
TranslateNewsPost) и translations:fill.

Переводчик — заглушка с одной логикой на обеих сторонах: у PHP —
Http::fake в tinker, у Python — HTTP-сервер (SAVDEX_TRANSLATE_URL).
Перевод — «<язык>:<текст>»; текст со словом FAIL — ошибка 500, RATE —
отказ 429. Каждая сторона начинает с одинаковых данных; сравниваются
json-столбцы текстом (json хранит текст как есть), search_text и то,
тронута ли строка (updated_at).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL).
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

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база

pytestmark = нужна_база

ВКЛЮЧЁН = {"MACHINE_TRANSLATION_ENABLED": "true"}

#: Та же заглушка у PHP: ответ по языку и тексту запроса
ПОДДЕЛКА = """
use Illuminate\\Support\\Facades\\Http;
Http::fake(function ($request) {
    parse_str((string) parse_url($request->url(), PHP_URL_QUERY), $query);
    $text = (string) ($request->data()['q'] ?? '');
    if (str_contains($text, 'FAIL')) { return Http::response('', 500); }
    if (str_contains($text, 'RATE')) { return Http::response('', 429); }
    return Http::response([[[$query['tl'].':'.$text, $text]]], 200);
});
"""


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


def _laravel(задача: str, номер: int) -> None:
    php(
        ПОДДЕЛКА + f"(new App\\Jobs\\{задача}({номер}))"
        "->handle(app(App\\Services\\MachineTranslator::class));"
        "echo 'ok';",
        ВКЛЮЧЁН,
    )


def _python(url: str, *args: str) -> None:
    вывод = subprocess.run(
        [sys.executable, "manage.py", "translate", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, **ВКЛЮЧЁН, "SAVDEX_TRANSLATE_URL": url},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]


def сверить(
    url: str,
    подготовить: Callable[[], None],
    снимок: Callable[[], Any],
    laravel: Callable[[], None],
    python_args: list[str],
) -> Any:
    подготовить()
    _python(url, *python_args)
    после_python = снимок()
    подготовить()
    laravel()
    после_laravel = снимок()

    assert после_python == после_laravel, json.dumps(
        [после_python, после_laravel], ensure_ascii=False, default=str, indent=1
    )

    return после_python


# ── Объявления ──────────────────────────────────────────────────────

ДЛИННОЕ = "\n\n".join(
    [("Абзац про цемент. " * 150).strip(), "Короткий абзац.", ("Длинное " * 700).strip()]
)


def _объявление() -> int:
    found = sql("select id from listings where slug = 'tr-listing'")

    if found:
        return int(found[0][0])

    php(
        "App\\Models\\Listing::factory()->create(['slug' => 'tr-listing']); echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    return int(sql("select id from listings where slug = 'tr-listing'")[0][0])


def _снимок_объявления(lid: int) -> Callable[[], Any]:
    return lambda: sql(
        "select title_i18n::text, description_i18n::text, search_text, "
        "updated_at > now() - interval '1 hour' from listings where id = %s",
        [lid],
    )


@pytest.mark.parametrize(
    ("title", "description", "titles", "descriptions"),
    [
        ("Цемент М400 оптом", "Мешки по 50 кг / самовывоз", None, None),
        ("Цемент", None, '{"en":"Manual","uz":"","zh":null}', '{"tr":"Elle"}'),
        ("Цемент FAIL", "Описание", None, "[]"),
        ("Кирпич", ДЛИННОЕ, None, None),
        ("Песок", "   ", '{"en":"a","uz":"b","tr":"c","zh":"d"}', None),
        ("Щебень «гранит» 5/20", "Описание RATE", '{"zh":"已有"}', None),
    ],
)
def test_объявление(переводчик, title, description, titles, descriptions):
    lid = _объявление()

    def подготовить() -> None:
        sql(
            "update listings set title = %s, description = %s, title_i18n = %s::json, "
            "description_i18n = %s::json, search_text = 'old', status = 'active', "
            "updated_at = now() - interval '1 day' where id = %s",
            [title, description, titles, descriptions, lid],
        )

    сверить(
        переводчик,
        подготовить,
        _снимок_объявления(lid),
        lambda: _laravel("TranslateListing", lid),
        ["--kind", "listings", "--id", str(lid)],
    )


# ── Резюме ──────────────────────────────────────────────────────────


def _резюме() -> int:
    found = sql("select id from resumes where slug = 'tr-resume'")

    if found:
        return int(found[0][0])

    php(
        "$u = App\\Models\\User::factory()->create();"
        "$r = new App\\Models\\Resume(); $r->forceFill(['user_id' => $u->id, 'slug' => 'tr-resume',"
        "'title' => 'Бухгалтер', 'status' => 'published'])->saveQuietly();"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    return int(sql("select id from resumes where slug = 'tr-resume'")[0][0])


@pytest.mark.parametrize(
    ("about", "jobs", "jobs_i18n"),
    [
        (
            "Опыт 10 лет",
            [{"position": f"Должность {i}", "duties": "Учёт" if i % 2 else ""} for i in range(10)],
            None,
        ),
        (None, [{"position": "Бухгалтер", "duties": None}], '{"en":[{"position":"x"}]}'),
        ("О себе FAIL", [], None),
    ],
)
def test_резюме(переводчик, about, jobs, jobs_i18n):
    rid = _резюме()

    def подготовить() -> None:
        sql(
            "update resumes set about = %s, jobs = %s::json, title_i18n = null, about_i18n = null, "
            "jobs_i18n = %s::json, updated_at = now() - interval '1 day' where id = %s",
            [about, json.dumps(jobs, ensure_ascii=False), jobs_i18n, rid],
        )

    сверить(
        переводчик,
        подготовить,
        lambda: sql(
            "select title_i18n::text, about_i18n::text, jobs_i18n::text, "
            "updated_at > now() - interval '1 hour' from resumes where id = %s",
            [rid],
        ),
        lambda: _laravel("TranslateResume", rid),
        ["--kind", "resumes", "--id", str(rid)],
    )


# ── Закупки и новости ───────────────────────────────────────────────


def _закупка() -> int:
    found = sql("select id from tenders where title = 'Закупка для перевода'")

    if found:
        return int(found[0][0])

    php(
        "App\\Models\\Tender::factory()->create(['title' => 'Закупка для перевода']); echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    return int(sql("select id from tenders where title = 'Закупка для перевода'")[0][0])


@pytest.mark.parametrize(
    ("description", "customer", "titles"),
    [("Поставка труб", "Ташкентводоканал", None), (None, None, '{"en":"Pipes"}')],
)
def test_закупка(переводчик, description, customer, titles):
    tid = _закупка()

    def подготовить() -> None:
        sql(
            "update tenders set description = %s, customer = %s, title_i18n = %s::json, "
            "description_i18n = null, search_text = 'old', "
            "updated_at = now() - interval '1 day' where id = %s",
            [description, customer, titles, tid],
        )

    сверить(
        переводчик,
        подготовить,
        lambda: sql(
            "select title_i18n::text, description_i18n::text, search_text, "
            "updated_at > now() - interval '1 hour' from tenders where id = %s",
            [tid],
        ),
        lambda: _laravel("TranslateTender", tid),
        ["--kind", "tenders", "--id", str(tid)],
    )


def _новость() -> int:
    found = sql("select id from news_posts where slug = 'tr-news'")

    if found:
        return int(found[0][0])

    php(
        "$p = new App\\Models\\NewsPost(); $p->forceFill(['slug' => 'tr-news',"
        "'title' => 'Новость площадки', 'category' => 'platform', 'excerpt' => '',"
        "'body' => '', 'is_published' => true])->saveQuietly(); echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    return int(sql("select id from news_posts where slug = 'tr-news'")[0][0])


@pytest.mark.parametrize(
    ("excerpt", "body", "titles"),
    [("Коротко", "Текст новости\n\nВторой абзац", None), ("", "  ", '{"uz":"Yangilik"}')],
)
def test_новость(переводчик, excerpt, body, titles):
    nid = _новость()

    def подготовить() -> None:
        sql(
            "update news_posts set excerpt = %s, body = %s, title_i18n = %s::json, "
            "excerpt_i18n = null, body_i18n = null, updated_at = now() - interval '1 day' "
            "where id = %s",
            [excerpt, body, titles, nid],
        )

    сверить(
        переводчик,
        подготовить,
        lambda: sql(
            "select title_i18n::text, excerpt_i18n::text, body_i18n::text, "
            "updated_at > now() - interval '1 hour' from news_posts where id = %s",
            [nid],
        ),
        lambda: _laravel("TranslateNewsPost", nid),
        ["--kind", "news", "--id", str(nid)],
    )


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

    сверить(
        переводчик,
        подготовить,
        lambda: sql(
            "select source, translation, attempts, updated_at > now() - interval '1 hour' "
            "from content_translations order by id"
        ),
        lambda: php(
            ПОДДЕЛКА + "Artisan::call('translations:fill', ['--limit' => 20]); echo 'ok';", ВКЛЮЧЁН
        ),
        ["--once", "--limit", "20"],
    )


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

    assert json.loads(titles) == {
        loc: f"{code}:Цемент для добора"
        for loc, code in (("en", "en"), ("uz", "uz"), ("tr", "tr"), ("zh", "zh-CN"))
    }
