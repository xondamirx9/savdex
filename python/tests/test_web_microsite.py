"""
Мини-сайт компании на Django: страница /s/<адрес>
(оформление — переменные SiteTheme с подбором читаемых цветов, шрифты,
свой корневой шаблон с вывеской компании; контакты целиком, товары сайта
и объявления, файлы, отзывы), 404 для черновика, заблокированной
компании и тарифа без мини-сайта; предпросмотр в кабинете (оформление из
редактора или черновик); с MICROSITE_DOMAIN — сайт на поддомене,
301 с /s/<адрес>, сам домен — в каталог компаний, прочее там — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from .factories import Выражение, компания, объявление, отзыв, пользователь
from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .test_web_forms import учётка
from .web_site import адрес, вход, открыть, страница

pytestmark = нужна_база

ДОМЕН = {"MICROSITE_DOMAIN": "savdex.site"}
ТЕМА = {
    "template": "bold",
    "primary": "#FACC15",
    "accent": "#f5d020",
    "mode": "light",
    "heading_font": "lora",
    "body_font": "pt-sans",
    "radius": "round",
    "hero_image": "sites/1/hero.webp",
}


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (PlanSeeder).
    """
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"seeds.seed(data={{k: v if k in {list(таблицы)!r} else [] for k, v in data.items()}})"
    )
    subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            # Справочники заводит владелец базы, как миграции
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        check=True,
    )


@pytest.fixture(scope="module")
def база() -> None:
    свежая_база()
    справочники("plans")
    c = компания(
        slug="mine",
        name="ООО «Цемент»",
        description="  Цемент   М400\n и арматура " + "оптом " * 40,
    )
    o = компания(slug="buyer", name="Покупатель")

    for i, (type_, value, public) in enumerate(
        [("phone", "+998 90 123-45-67", True), ("telegram", "@cement", True),
         ("email", "hidden@cement.uz", False)]
    ):  # fmt: skip
        sql(
            "insert into company_contacts (company_id, type, value, is_public, sort_order, "
            "created_at, updated_at) values (%s, %s, %s, %s, %s, now(), now())",
            [c, type_, value, public, 3 - i],
        )

    for i in range(1, 4):
        объявление(
            company_id=c,
            status="archived" if i == 3 else "active",
            title=f"Цемент {i}",
            published_at=Выражение(f"now() - interval '{i} days'"),
        )

    отзыв(company_id=c, author_company_id=o, status="published", rating=5, body="Отличный цемент")
    отзыв(company_id=c, author_company_id=компания(), status="moderation", rating=1)
    sql(
        "insert into company_site_products (company_id, title, description, price, currency, "
        "unit, sort, created_at, updated_at) select id, 'Свой товар', '  Мешок  50 кг ', "
        "120000, 'UZS', 'шт', 1, now(), now() from companies where slug = 'mine'"
    )
    sql(
        "insert into company_site_products (company_id, title, sort, created_at, updated_at) "
        "select id, 'Под заказ', 0, now(), now() from companies where slug = 'mine'"
    )
    фон = Path(КОРЕНЬ) / "storage/app/public/sites/1/hero.webp"
    фон.parent.mkdir(parents=True, exist_ok=True)
    фон.write_bytes(b"hero")


@pytest.fixture(scope="module")
def сайт(база) -> Iterator[str]:
    with адрес() as root:
        yield root


def сброс(
    *,
    статус: str = "published",
    тариф: bool = True,
    блок: bool = False,
    тема: dict[str, object] | None = None,
    черновик: dict[str, object] | None = None,
) -> Callable[[], None]:
    def run() -> None:
        sql("update plans set has_microsite = %s where code = 'free'", [тариф])
        статус_компании = "blocked" if блок else "active"
        sql("update companies set status = %s where slug = 'mine'", [статус_компании])
        sql("delete from company_sites")
        sql(
            "insert into company_sites (company_id, subdomain, status, theme, published_theme, "
            "published_at, created_at, updated_at) select id, 'mine', %s, %s, %s, now(), now(), "
            "now() from companies where slug = 'mine'",
            [статус, json.dumps(черновик or {}), json.dumps(тема or ТЕМА)],
        )

    return run


def мини_сайт(ответ: dict[str, Any]) -> dict[str, Any]:
    """Пропсы мини-сайта: страница site/Show."""
    стр = страница(ответ["body"])

    assert ответ["status"] == 200 and стр["component"] == "site/Show", ответ["status"]

    return dict(стр["props"])


@pytest.mark.parametrize(
    ("path", "настройка", "ожидание"),
    [
        (
            "/s/mine",
            {},
            {"template": "bold", "--ms-radius": "22px", "--ms-primary-text": "#857220"},
        ),
        ("/en/s/mine", {}, {"template": "bold", "marketplace": "/en/company/mine"}),
        # Тёмная тема и тёмный основной цвет — текст основного цвета светлее
        (
            "/s/mine",
            {"тема": {"mode": "dark", "primary": "#0f172a", "accent": "#0f172a"}},
            {"template": "classic", "--ms-bg": "#0b1120", "--ms-primary-text": "#7c828f"},
        ),
        # Белый основной на светлом — читаемый серый; неизвестное скругление — обычное
        (
            "/s/mine",
            {"тема": {"primary": "#ffffff", "heading_font": "oswald", "radius": "x"}},
            {
                "template": "classic",
                "--ms-primary-text": "#6f747f",
                "--ms-radius": "10px",
                "--ms-font-heading": "'Oswald', sans-serif",
            },
        ),
        (
            "/s/mine",
            {"тема": {"primary": "#5b3cc4", "accent": "#e11d74", "template": "minimal"}},
            {"template": "minimal", "--ms-primary-text": "#5b3cc4", "--ms-on-accent": "#ffffff"},
        ),
        # Черновик, тариф без мини-сайта, заблокированная компания, нет сайта — 404
        ("/s/mine", {"статус": "draft"}, None),
        ("/s/mine", {"тариф": False}, None),
        ("/s/mine", {"блок": True}, None),
        ("/s/nothing", {}, None),
    ],
)
def test_страница(сайт, path, настройка, ожидание):
    сброс(**настройка)()
    д = открыть(сайт, path)

    if ожидание is None:
        assert д["status"] == 404
        assert страница(д["body"])["component"] == "Error"
        return

    props = мини_сайт(д)
    найдено = {"template": props["theme"]["template"], **props["vars"]}
    найдено["marketplace"] = props["site"]["marketplace"].removeprefix(сайт)

    assert {k: найдено[k] for k in ожидание} == ожидание
    assert props["preview"] is False
    assert props["site"]["url"] == f"{сайт}/s/mine"
    # Свой корневой шаблон: вывеска компании, шрифты темы
    assert "<title inertia>ООО «Цемент»</title>" in д["body"]
    assert 'id="ms-fonts"' in д["body"]


def test_оформление_читаемо(сайт):
    сброс()()
    props = мини_сайт(открыть(сайт, "/s/mine"))

    assert props["vars"]["--ms-primary-text"] != "#facc15"
    assert props["hero"] == f"{сайт}/storage/sites/1/hero.webp"
    # Только открытые контакты — по порядку
    assert [c["value"] for c in props["contacts"]] == ["@cement", "+998 90 123-45-67"]
    # Товары сайта по порядку, затем объявления (без архивного)
    assert [(p["key"], p["title"]) for p in props["products"]] == [
        ("p2", "Под заказ"),
        ("p1", "Свой товар"),
        ("l1", "Цемент 1"),
        ("l2", "Цемент 2"),
    ]
    assert props["products"][1]["excerpt"] == "Мешок 50 кг"
    # Только опубликованные отзывы
    assert (props["reviews"]["count"], props["reviews"]["rating"]) == (1, 5)
    assert [r["body"] for r in props["reviews"]["latest"]] == ["Отличный цемент"]


def владелец() -> dict[str, str]:
    uid = учётка("owner@savdex.uz")
    sql(
        "update users set company_id = (select id from companies where slug = 'mine') "
        "where id = %s",
        [uid],
    )

    return вход(uid)


@pytest.mark.parametrize(
    ("query", "оформление"),
    [
        # Без оформления в адресе — черновик из редактора
        ("", ("minimal", "#0f6e56", "light")),
        (
            "?theme=" + quote(json.dumps({"mode": "dark", "primary": "#112233"})),
            ("classic", "#112233", "dark"),
        ),
        # Массив вместо оформления — оформление по умолчанию
        ("?theme=" + quote("[1,2]"), ("classic", "#1a56db", "light")),
        # Не JSON и не объект — черновик
        ("?theme=oops", ("minimal", "#0f6e56", "light")),
        ("?theme=5", ("minimal", "#0f6e56", "light")),
    ],
)
def test_предпросмотр(сайт, query, оформление):
    куки = владелец()
    сброс(черновик={"template": "minimal", "primary": "#0f6e56"})()
    д = открыть(сайт, "/cabinet/site/preview" + query, куки)
    props = мини_сайт(д)

    assert props["preview"] is True
    assert (props["theme"]["template"], props["theme"]["primary"], props["theme"]["mode"]) == (
        оформление
    )
    assert props["vars"]["--ms-primary"] == оформление[1]
    # Предпросмотр поисковикам не показывается
    assert '<meta name="robots" content="noindex, nofollow">' in д["body"]


def test_предпросмотр_без_сайта_и_без_компании(сайт):
    д = открыть(сайт, "/cabinet/site/preview", вход(учётка("nocompany@savdex.uz")))
    assert (д["status"], д["headers"]["location"]) == (302, f"{сайт}/cabinet/company")

    куки = владелец()
    sql("delete from company_sites")
    props = мини_сайт(открыть(сайт, "/cabinet/site/preview", куки))
    assert props["preview"] is True
    assert props["theme"]["template"] == "classic"


@pytest.fixture(scope="module")
def поддомены(база) -> Iterator[str]:
    with адрес() as root:
        yield root


@pytest.mark.parametrize(
    ("host", "path", "ожидание"),
    [
        ("mine.savdex.site", "/", "ru"),
        ("mine.savdex.site", "/uz", "uz"),
        ("nothing.savdex.site", "/", 404),
        # Сам домен мини-сайтов — в каталог компаний площадки
        ("savdex.site", "/", "/companies"),
        # Прочее на поддомене — 404
        ("mine.savdex.site", "/catalog", 404),
        # Старый адрес — навсегда на поддомен
        (None, "/s/mine", "mine.savdex.site"),
    ],
)
def test_поддомены(поддомены, host, path, ожидание):
    port = поддомены.rsplit(":", 1)[1]
    headers = {"Host": f"{host}:{port}"} if host else None
    сброс()()
    д = открыть(поддомены, path, headers=headers, env=ДОМЕН)

    if ожидание == 404:
        assert д["status"] == 404
    elif ожидание == "/companies":
        assert (д["status"], д["headers"]["location"]) == (302, f"{поддомены}/companies")
    elif ожидание == "mine.savdex.site":
        assert (д["status"], д["headers"]["location"]) == (301, f"http://mine.savdex.site:{port}")
    else:
        props = мини_сайт(д)
        assert props["locale"] == ожидание
        assert props["site"]["url"] == f"http://mine.savdex.site:{port}"
        prefix = "" if ожидание == "ru" else f"/{ожидание}"
        assert props["site"]["marketplace"] == f"{поддомены}{prefix}/company/mine"


def test_контакты_из_регистрации(сайт):
    """
    Нет телефона и почты в «Моих контактах» — мини-сайт берёт их из
    профиля компании и учётной записи владельца; скрытый вид контакта сам
    не подставляется.
    """
    сброс()()
    [(cid,)] = sql("select id from companies where slug = 'mine'")
    пользователь(
        company_id=cid,
        email="owner@cement.uz",
        phone="+998 91 000-00-00",
        company_role="owner",
    )
    sql("delete from company_contacts where company_id = %s and type = 'phone'", [cid])
    sql("update companies set whatsapp = '+998 93 111-11-11' where id = %s", [cid])

    try:
        props = мини_сайт(открыть(сайт, "/s/mine"))
    finally:
        sql("delete from users where email = 'owner@cement.uz'")
        sql("update companies set whatsapp = null where id = %s", [cid])
        sql(
            "insert into company_contacts (company_id, type, value, is_public, sort_order, "
            "created_at, updated_at) "
            "values (%s, 'phone', '+998 90 123-45-67', true, 3, now(), now())",
            [cid],
        )

    assert [(c["type"], c["value"], c["href"]) for c in props["contacts"]] == [
        ("telegram", "@cement", "https://t.me/cement"),
        # Телефона в «Моих контактах» нет — из регистрации владельца
        ("phone", "+998 91 000-00-00", "tel:+998910000000"),
        # Почта в «Моих контактах» скрыта — не подставляется
        ("whatsapp", "+998 93 111-11-11", "https://wa.me/998931111111"),
    ]
