"""
Раздел «Настройки площадки» админки на Django — сквозь настоящую базу.

Настройки заводит manage.py seed (как SettingSeeder). Проверяется то,
ради чего раздел устроен именно так:

- поле значения под тип: координаты, валюта из списка, число, флаг
  (в том числе «boolean», который Filament не показывал);
- картинка ложится на публичный диск, и витрина её видит;
- после правки сайт сразу показывает новое значение;
- настройки, которые читает код, не удаляются.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from typing import Any

import pytest

from savdex.site.models import SYSTEM_KEYS

from .pg_admin import (
    PYTHON,
    КОРЕНЬ,
    ОКРУЖЕНИЕ,
    django,
    sql,
    журнал,
    нужна_база,
    свежая_база,
    сотрудник,
    файл,
)
from .web_site import адрес, открыть, страница

pytestmark = нужна_база

LIST = "/py/admin/site/setting/"
ADD = "/py/admin/site/setting/add/"
PUBLIC = КОРЕНЬ / "storage/app/public"

#: Самый маленький настоящий PNG: 1×1, прозрачный
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'
)


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    # Справочники, как при деплое (вместо SettingSeeder) — под владельцем базы
    subprocess.run(
        [sys.executable, "manage.py", "seed"],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        check=True,
    )

    return {role: сотрудник(role) for role in ("superadmin", "admin")}


@pytest.fixture
def картинки():
    """Файлы, которые тест положил на публичный диск, — убрать после."""
    before = set(PUBLIC.glob("appearance/*"))

    yield

    for path in set(PUBLIC.glob("appearance/*")) - before:
        path.unlink()


def _витрина() -> dict[str, Any]:
    """Пропсы главной страницы сайта (Django) — что видит посетитель."""
    with адрес() as root:
        ответ = открыть(root, "/")

    return dict(страница(ответ["body"])["props"])


def _id(key: str) -> int:
    [(pk,)] = sql("select id from settings where key = %s", [key])

    return int(pk)


def _value(key: str) -> Any:
    [(value,)] = sql("select value from settings where key = %s", [key])

    return value


def _правка(key: str, value: Any, **extra: Any) -> tuple[str, str, dict[str, Any]]:
    [(label, group, sort)] = sql('select label, "group", sort from settings where key = %s', [key])
    data = {"label": label, "group": group, "sort": str(sort), "description": "", **extra}

    if value is not None:
        data["value_input"] = value

    return ("post", f"{LIST}{_id(key)}/change/", data)


def test_системные_настройки_совпадают_с_сидером(люди):
    """SYSTEM_KEYS — ровно то, что заводит manage.py seed: их читает код."""
    assert {key for (key,) in sql("select key from settings")} == set(SYSTEM_KEYS)


def test_список_и_права(люди):
    вход, список = django(люди["superadmin"], ("get", LIST, None))

    assert вход == 302
    assert "Название площадки · site_name" in список["body"]
    # Кнопка над списком ведёт прямо к логотипу
    assert f"{LIST}{_id('logo_image')}/change/" in список["body"]
    assert "Логотип площадки" in список["body"]

    # Настройки — только суперадмину
    _, чужой = django(люди["admin"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_координаты_проверяются(люди):
    _, плохие, хорошие = django(
        люди["superadmin"],
        _правка("office_coords", "41,31 69,24"),
        _правка("office_coords", "39.654620, 66.959720"),
    )

    assert плохие["status"] == 200
    assert "Ожидается широта и долгота через запятую" in плохие["body"]
    assert хорошие["status"] == 302, хорошие["body"][:3000]
    assert _value("office_coords") == "39.654620, 66.959720"


def test_прочие_строки_свободным_текстом(люди):
    _, ответ = django(люди["superadmin"], _правка("support_phone", "+998 71 300-00-00"))

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert _value("support_phone") == "+998 71 300-00-00"

    запись = журнал("updated")
    assert запись["section"] == "settings"
    assert запись["subject_type"] == "App\\Models\\Setting"
    assert запись["changes"]["after"] == {"value": "+998 71 300-00-00"}


def test_валюта_из_списка(люди):
    _, мимо, ок = django(
        люди["superadmin"],
        _правка("display_currency_en", "XXX"),
        _правка("display_currency_en", "EUR"),
    )

    assert мимо["status"] == 200
    assert "Выберите корректный вариант" in мимо["body"]
    assert ок["status"] == 302
    assert _value("display_currency_en") == "EUR"
    # Витрина видит новую валюту
    from savdex.web.home import PriceDisplay

    assert (
        PriceDisplay("en", {"display_currency_en": _value("display_currency_en")}, None).currency
        == "EUR"
    )


def test_валюта_при_создании_тоже_из_списка(люди):
    sql("delete from settings where key = 'display_currency_tr'")
    данные = {
        "label": "Валюта на турецкой",
        "key": "display_currency_tr",
        "group": "currency",
        "type": "string",
        "sort": "0",
        "description": "",
    }

    _, мимо, ок = django(
        люди["superadmin"],
        ("post", ADD, {**данные, "value_input": "XXX"}),
        ("post", ADD, {**данные, "value_input": "TRY"}),
    )

    assert мимо["status"] == 200
    assert "Выберите корректный вариант" in мимо["body"]
    assert ок["status"] == 302, ок["body"][:3000]
    assert _value("display_currency_tr") == "TRY"


def test_число_и_флаг(люди):
    """Флаг премодерации отзывов — тип «boolean», в Filament поля для него не было."""
    _, число, флаг = django(
        люди["superadmin"],
        _правка("office_map_zoom", "17"),
        # Выключенный переключатель браузер не присылает вовсе
        _правка("reviews_premoderation", None),
    )

    assert число["status"] == 302, число["body"][:3000]
    assert флаг["status"] == 302, флаг["body"][:3000]
    assert _value("office_map_zoom") == 17
    assert _value("reviews_premoderation") is False

    _, форма = django(
        люди["superadmin"], ("get", f"{LIST}{_id('reviews_premoderation')}/change/", None)
    )
    assert 'type="checkbox" name="value_input"' in форма["body"]


def test_картинка_на_публичный_диск(люди, картинки):
    _, ответ = django(люди["superadmin"], _правка("hero_image", файл("fon.png", PNG)))

    assert ответ["status"] == 302, ответ["body"][:3000]
    path = _value("hero_image")
    assert path.startswith("appearance/") and path.endswith(".png")
    assert (PUBLIC / path).read_bytes() == PNG
    # Витрина строит адрес через публичный диск
    assert _витрина()["heroImage"].endswith(f"/storage/{path}")


@pytest.mark.parametrize(
    ("key", "name", "content", "принят"),
    [
        ("hero_image", "fon.svg", SVG, False),
        ("logo_image", "znak.svg", SVG, True),
        ("logo_image", "znak.png", b"not an image at all", False),
    ],
)
def test_какие_картинки_принимаются(люди, картинки, key, name, content, принят):
    """Вектор — только для логотипа, как в Filament; не картинка — нигде."""
    before = _value(key)
    _, ответ = django(люди["superadmin"], _правка(key, файл(name, content)))

    if принят:
        assert ответ["status"] == 302, ответ["body"][:3000]
        assert _value(key).endswith(".svg")
    else:
        assert ответ["status"] == 200
        assert "Нужна картинка PNG, JPEG или WebP" in ответ["body"]
        assert _value(key) == before


def test_картинку_можно_убрать(люди, картинки):
    django(люди["superadmin"], _правка("hero_image", файл("fon.png", PNG)))
    _, ответ = django(люди["superadmin"], _правка("hero_image", None, value_clear="on"))

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert _value("hero_image") == ""
    assert _витрина()["heroImage"] == "/images/hero-port.svg"


def test_сайт_сразу_видит_правку(люди):
    """Сайт читает настройки из базы на каждый запрос — правка видна сразу."""
    assert _витрина()["support"]["phone"] == _value("support_phone")

    _, ответ = django(люди["superadmin"], _правка("support_phone", "+998 77 000 00 00"))

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert _витрина()["support"]["phone"] == "+998 77 000 00 00"


def test_системные_не_удаляются_свои_удаляются(люди):
    pk = _id("site_name")

    _, форма, удаление = django(
        люди["superadmin"],
        ("get", f"{LIST}{pk}/change/", None),
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
    )
    assert "Нельзя: настройку читает код площадки." in форма["body"]
    assert удаление["status"] == 403

    _, создание = django(
        люди["superadmin"],
        (
            "post",
            ADD,
            {
                "label": "Промо-баннер",
                "key": "promo_text",
                "group": "general",
                "type": "string",
                "sort": "0",
                "description": "",
                "value_input": "Скидки",
            },
        ),
    )
    assert создание["status"] == 302, создание["body"][:3000]

    _, удалена = django(
        люди["superadmin"], ("post", f"{LIST}{_id('promo_text')}/delete/", {"post": "yes"})
    )
    assert удалена["status"] == 302
    assert sql("select count(*) from settings where key = 'promo_text'") == [(0,)]


@pytest.mark.parametrize("key", ["Promo", "promo-text", "1promo", "промо"])
def test_ключ_новой_настройки(люди, key):
    данные = {
        "label": "Тест",
        "key": key,
        "group": "general",
        "type": "string",
        "sort": "0",
        "description": "",
        "value_input": "x",
    }
    _, ответ = django(люди["superadmin"], ("post", ADD, данные))

    assert ответ["status"] == 200
    assert "Латиница в нижнем регистре, цифры и подчёркивание" in ответ["body"]


def test_публичный_диск_тот_же(люди):
    """Django пишет туда же, откуда сайт отдаёт /storage, — storage/app/public."""
    from savdex import laravel_storage

    assert laravel_storage.public_root().resolve() == PUBLIC.resolve()
