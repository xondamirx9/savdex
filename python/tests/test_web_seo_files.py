"""
robots.txt, карта сайта и превью объявления на Django: robots.txt
площадки (закрытые разделы, жадные роботы, адрес карты) и домена
мини-сайтов; список частей карты (объявления по 5000, новости, закупки и
IT-задачи — только если есть), части со всеми языковыми версиями адреса;
импортированное объявление — только на языках своего заголовка.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest

from .factories import it_задача, категория, компания, объявление
from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть, шапка

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    cat = категория(slug="cement")
    категория(slug="empty")
    c = компания(slug="mine")
    компания(slug="blocked", status="blocked")

    for i in range(1, 5):
        объявление(
            company_id=c,
            category_id=cat,
            slug=f"l-{i}",
            status="archived" if i == 4 else "active",
            source="import" if i == 2 else "manual",
            title_i18n={"en": "Cement", "uz": " "} if i == 2 else None,
        )

    it_задача(company_id=c, slug="task-1")
    sql("update companies set updated_at = '2026-09-01 10:00:00'")
    sql("update listings set updated_at = '2026-09-02 11:30:00'")

    with адрес() as root:
        yield root


ЯЗЫКИ = ("", "/uz", "/en", "/zh", "/tr")


def текст(сайт: str, path: str, тип: str = "application/xml; charset=utf-8") -> str:
    """Ответ 200 с текстом; у карты — кэш на час."""
    д = открыть(сайт, path)

    assert д["status"] == 200, (д["status"], д["body"][:500])
    assert д["headers"].get("content-type") == тип

    if тип.startswith("application/xml"):
        assert д["headers"].get("cache-control") == "max-age=3600, public"

    return str(д["body"])


def адреса(сайт: str, текст_: str) -> list[str]:
    """<loc> части карты — без адреса сайта."""
    return [loc.removeprefix(сайт) for loc in re.findall(r"<loc>([^<]*)</loc>", текст_)]


def на_всех_языках(*paths: str) -> list[str]:
    return [f"{язык}{path}" for path in paths for язык in ЯЗЫКИ]


@pytest.mark.parametrize("path", ["/robots.txt", "/uz/robots.txt"])
def test_robots(сайт, path):
    текст_ = текст(сайт, path, "text/plain; charset=utf-8")

    assert "AhrefsBot" in текст_ and "Disallow: /cabinet" in текст_
    assert f"Sitemap: {сайт}/sitemap.xml" in текст_
    # Служебные адреса закрыты и под префиксом языка
    assert "Disallow: /en/cabinet" in текст_ and "Disallow: /uz/login" in текст_


def test_карта_список(сайт):
    текст_ = текст(сайт, "/sitemap.xml")

    # Новостей и закупок нет — их частей нет; объявлений меньше 5000 — одна часть
    assert адреса(сайт, текст_) == [
        "/sitemap-static.xml",
        "/sitemap-categories.xml",
        "/sitemap-companies.xml",
        "/sitemap-listings-1.xml",
        "/sitemap-it-tasks.xml",
    ]


@pytest.mark.parametrize(
    ("part", "ожидание"),
    [
        # Категория без объявлений, заблокированная компания и архивное
        # объявление в карту не попадают
        ("categories", на_всех_языках("/catalog?category=1")),
        ("companies", на_всех_языках("/company/mine")),
        ("listings-1", на_всех_языках("/listing/l-1", "/listing/l-2", "/listing/l-3")),
        ("it-tasks", на_всех_языках("/it-services/task-1")),
        ("news", []),
    ],
)
def test_карта_часть(сайт, part, ожидание):
    текст_ = текст(сайт, f"/sitemap-{part}.xml")

    assert адреса(сайт, текст_) == ожидание
    # У каждого адреса — все языковые версии и x-default
    assert текст_.count("<xhtml:link") == len(ожидание) * 6


def test_карта_статичные_страницы(сайт):
    found = адреса(сайт, текст(сайт, "/sitemap-static.xml"))

    assert found[:5] == ["", "/uz", "/en", "/zh", "/tr"]
    for path in ("/catalog", "/companies", "/about", "/it-services"):
        assert set(на_всех_языках(path)) <= set(found), path
    # Документы только на русском — без чужих языковых версий
    assert "/terms" in found and "/en/terms" not in found


def test_документ_на_русском_канонический(сайт):
    assert f'<link rel="canonical" href="{сайт}/terms">' in _мета(сайт, "/en/terms")


def test_карта_время_изменения(сайт):
    """lastmod — время правки записи (updated_at), в UTC."""
    assert "<lastmod>2026-09-01T10:00:00+00:00</lastmod>" in текст(сайт, "/sitemap-companies.xml")
    assert "<lastmod>2026-09-02T11:30:00+00:00</lastmod>" in текст(сайт, "/sitemap-listings-1.xml")


def test_нет_такой_части(сайт):
    assert открыть(сайт, "/sitemap-nope.xml")["status"] == 404
    # Часть объявлений дальше последней — тоже нет, а не пустая карта
    assert открыть(сайт, "/sitemap-listings-2.xml")["status"] == 404


def test_импортированное_объявление_на_всех_языках(сайт):
    """Загруженное из книги — на всех языках, и без перевода тоже."""
    текст_ = текст(сайт, "/sitemap-listings-1.xml")

    assert f"<loc>{сайт}/listing/l-2</loc>" in текст_
    assert f"<loc>{сайт}/en/listing/l-2</loc>" in текст_
    assert f"<loc>{сайт}/uz/listing/l-2</loc>" in текст_


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


@pytest.mark.parametrize(
    ("slug", "итог"),
    [
        # SVG пропускается — превью из PNG, файл назван по номеру картинки
        ("l-1", "og"),
        # Битый файл, только SVG и пропавший файл, без картинок — общая обложка
        ("l-2", "cover"),
        ("l-3", "cover"),
        ("l-4", "cover"),
        (None, 404),
    ],
)
def test_превью_объявления(картинки, сайт, slug, итог):
    import shutil

    номер = _номер(slug) if slug else 999999
    кэш = картинки / f"listings/{номер}"
    shutil.rmtree(кэш, ignore_errors=True)
    ответ = открыть(сайт, f"/og/listing/{номер}.jpg")
    файлы = sorted(p.name for p in кэш.glob("*")) if кэш.exists() else []

    if итог == 404:
        assert ответ["status"] == 404 and файлы == []
    elif итог == "cover":
        assert (ответ["status"], ответ["headers"].get("location")) == (302, f"{сайт}/og-cover.png")
        assert файлы == []
    else:
        [(png,)] = sql(
            "select id from listing_images where listing_id = %s and path like '%%.png'", [номер]
        )
        assert ответ["status"] == 302
        assert ответ["headers"]["location"] == f"{сайт}/storage/listings/{номер}/og-{png}.jpg"
        assert файлы == [f"og-{png}.jpg"]

        from PIL import Image

        with Image.open(кэш / файлы[0]) as картинка:
            assert картинка.size == (1200, 630) and картинка.format == "JPEG"


def test_превью_из_кэша(картинки, сайт):
    """Готовый файл не пересобирается: сайт просто ведёт на него."""
    номер = _номер("l-1")
    открыть(сайт, f"/og/listing/{номер}.jpg")
    файл = next((картинки / f"listings/{номер}").glob("og-*.jpg"))
    файл.write_bytes(b"cached")

    assert открыть(сайт, f"/og/listing/{номер}.jpg")["headers"]["location"].endswith(
        f"/storage/listings/{номер}/{файл.name}"
    )
    assert файл.read_bytes() == b"cached"


# ── Шапка страниц ───────────────────────────────────────────────────


def _мета(сайт: str, path: str) -> list[str]:
    ответ = открыть(сайт, path)
    assert ответ["status"] == 200, path

    return шапка(ответ["body"])


def test_рубрика_индексируется_под_своим_адресом(сайт):
    """Страница рубрики из карты сайта — с собственным canonical и без noindex."""
    cat = sql("select id from categories where slug = 'cement'")[0][0]
    теги = _мета(сайт, f"/en/catalog?category={cat}")

    assert f'<link rel="canonical" href="{сайт}/en/catalog?category={cat}">' in теги
    assert not any('name="robots"' in t for t in теги)
    # С другим фильтром — по-прежнему служебная выборка
    assert '<meta name="robots" content="noindex, follow">' in _мета(
        сайт, f"/en/catalog?category={cat}&verified=1"
    )


def test_вход_не_индексируется(сайт):
    for path in ("/login", "/en/register", "/uz/forgot-password"):
        assert '<meta name="robots" content="noindex, follow">' in _мета(сайт, path), path


def test_og_locale_с_регионом(сайт):
    assert '<meta property="og:locale" content="en_US">' in _мета(сайт, "/en/about")
    assert '<meta property="og:locale" content="ru_RU">' in _мета(сайт, "/about")


def test_заголовок_без_второго_savdex(сайт):
    [заголовок] = [t for t in _мета(сайт, "/about") if t.startswith("<title")]

    assert заголовок.count("SAVDEX") == 1, заголовок


def test_разметка_объявления_на_языке_страницы(сайт):
    """Ссылки JSON-LD — с префиксом языка; пустого списка картинок нет."""
    sql("update listings set title_i18n = '{\"en\": \"Cement M500 wholesale\"}' where slug = 'l-1'")
    ответ = открыть(сайт, "/en/listing/l-1")
    [разметка] = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', ответ["body"], re.S
    )

    assert f"{сайт}/en/listing/l-1" in разметка.replace("\\/", "/")
    assert f'{сайт}/listing/l-1"' not in разметка.replace("\\/", "/")
    assert "Cement M500 wholesale" in разметка
    assert '"image":[]' not in разметка


def test_просмотр_не_меняет_дату_изменения(сайт):
    before = sql("select updated_at from listings where slug = 'l-3'")
    открыть(сайт, "/listing/l-3")

    assert sql("select updated_at from listings where slug = 'l-3'") == before
