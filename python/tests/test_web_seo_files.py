"""
robots.txt и карта сайта на Django неотличимы от Laravel: robots.txt
площадки (закрытые разделы, жадные роботы, адрес карты) и домена
мини-сайтов; список частей карты (объявления по 5000, новости, закупки и
IT-задачи — только если есть), части со всеми языковыми версиями адреса;
импортированное объявление — только на языках своего заголовка.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база
from .web_site import laravel, из_django, из_laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "$cat = App\\Models\\Category::factory()->create(['slug' => 'cement']);"
        "App\\Models\\Category::factory()->create(['slug' => 'empty']);"
        "$c = App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Company::factory()->create(['slug' => 'blocked', 'status' => 'blocked']);"
        "foreach (range(1, 4) as $i) { App\\Models\\Listing::factory()->create(["
        " 'company_id' => $c->id, 'category_id' => $cat->id, 'slug' => 'l-'.$i,"
        " 'status' => $i === 4 ? 'archived' : 'active',"
        " 'source' => $i === 2 ? 'import' : 'manual',"
        " 'title_i18n' => $i === 2 ? ['en' => 'Cement', 'uz' => ' '] : null]); }"
        "App\\Models\\ItTask::factory()->create(['company_id' => $c->id, 'slug' => 'task-1']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    sql("update companies set updated_at = '2026-09-01 10:00:00'")
    sql("update listings set updated_at = '2026-09-02 11:30:00'")

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def сверить_текст(сайт: str, path: str, *, без_времени: bool = False) -> str:
    д = из_django(сайт, path)
    л = из_laravel(сайт, path)

    for ответ in (д, л):
        if без_времени:
            ответ["body"] = re.sub(r"<lastmod>[^<]+</lastmod>", "<lastmod/>", ответ["body"])

    assert д["status"] == л["status"], (д["status"], л["status"], д["body"][:500])

    if д["status"] == 200:
        assert д["body"] == л["body"], (д["body"][:3000], л["body"][:3000])

        for header in ("content-type", "cache-control"):
            assert д["headers"].get(header) == л["headers"].get(header), header

    return str(д["body"])


@pytest.mark.parametrize("path", ["/robots.txt", "/uz/robots.txt"])
def test_robots(сайт, path):
    текст = сверить_текст(сайт, path)

    assert "AhrefsBot" in текст and "Sitemap: " in текст


def test_карта_список(сайт):
    текст = сверить_текст(сайт, "/sitemap.xml", без_времени=True)

    assert "sitemap-it-tasks.xml" in текст and "sitemap-news.xml" not in текст


@pytest.mark.parametrize(
    "part",
    ["static", "categories", "companies", "listings-1", "listings-2", "it-tasks", "news", "nope"],
)
def test_карта_часть(сайт, part):
    сверить_текст(сайт, f"/sitemap-{part}.xml")


def test_импортированное_объявление_на_своих_языках(сайт):
    текст = сверить_текст(сайт, "/sitemap-listings-1.xml")

    assert f"<loc>{сайт}/listing/l-2</loc>" in текст
    assert f"<loc>{сайт}/en/listing/l-2</loc>" in текст
    assert f"<loc>{сайт}/uz/listing/l-2</loc>" not in текст


# ── Превью объявления для og:image ──────────────────────────────────


@pytest.fixture(scope="module")
def картинки(сайт):
    """У l-1 — SVG, битый файл и PNG с прозрачностью; у l-3 — только SVG."""
    import io
    from pathlib import Path

    from PIL import Image

    from .pg_admin import КОРЕНЬ

    диск = Path(КОРЕНЬ) / "storage/app/public"
    (диск / "listings/og").mkdir(parents=True, exist_ok=True)
    буфер = io.BytesIO()
    Image.new("RGBA", (900, 1600), (200, 30, 30, 128)).save(буфер, "PNG")
    (диск / "listings/og/photo.png").write_bytes(буфер.getvalue())
    (диск / "listings/og/broken.jpg").write_bytes(b"not an image")
    (диск / "listings/og/logo.svg").write_bytes(b"<svg/>")

    for slug, files in (
        ("l-1", ["listings/og/logo.svg", "listings/og/photo.png"]),
        ("l-3", ["listings/og/logo.svg", "listings/og/missing.png"]),
        ("l-2", ["listings/og/broken.jpg"]),
    ):
        for sort, path in enumerate(files):
            sql(
                "insert into listing_images (listing_id, path, sort, created_at, updated_at) "
                "select id, %s, %s, now(), now() from listings where slug = %s",
                [path, sort, slug],
            )

    return диск


def _номер(slug: str) -> int:
    return int(sql("select id from listings where slug = %s", [slug])[0][0])


@pytest.mark.parametrize("slug", ["l-1", "l-2", "l-3", "l-4", None])
def test_превью_объявления(картинки, сайт, slug):
    import shutil

    номер = _номер(slug) if slug else 999999
    кэш = картинки / f"listings/{номер}"

    for сторона in (из_django, из_laravel):
        shutil.rmtree(кэш, ignore_errors=True)
        ответ = сторона(сайт, f"/og/listing/{номер}.jpg")
        сторона_итог = (ответ["status"], ответ["headers"].get("location"))

        if сторона is из_django:
            д = сторона_итог
            файлы_д = sorted(p.name for p in кэш.glob("*")) if кэш.exists() else []
        else:
            л = сторона_итог
            файлы_л = sorted(p.name for p in кэш.glob("*")) if кэш.exists() else []

    assert д == л and файлы_д == файлы_л

    if slug == "l-1":
        from PIL import Image

        assert f"/storage/listings/{номер}/og-" in д[1]
        with Image.open(next(кэш.glob("og-*.jpg"))) as картинка:
            assert картинка.size == (1200, 630) and картинка.format == "JPEG"


def test_превью_из_кэша(картинки, сайт):
    """Готовый файл не пересобирается: обе стороны просто ведут на него."""
    номер = _номер("l-1")
    из_laravel(сайт, f"/og/listing/{номер}.jpg")
    файл = next((картинки / f"listings/{номер}").glob("og-*.jpg"))
    файл.write_bytes(b"cached")

    assert из_django(сайт, f"/og/listing/{номер}.jpg")["headers"]["location"].endswith(
        f"/storage/listings/{номер}/{файл.name}"
    )
    assert файл.read_bytes() == b"cached"
