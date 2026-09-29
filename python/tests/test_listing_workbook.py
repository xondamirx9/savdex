"""
Загрузка каталога книгой Excel вместе с фотографиями на Django
(savdex/data/workbook.py) — все случаи теста Laravel
tests/Feature/Admin/ListingWorkbookImportTest.php, тем же порядком.

Книга собирается здесь же, а не лежит файлом: тест должен ломаться при
изменении разбора, а не при пересохранении фикстуры. Значения пишет
openpyxl, фотографии — openpyxl.drawing.image с настоящим PNG от Pillow
(загрузка проверяет файлы). Данные заводят фабрики Laravel (tinker),
загрузка идёт в отдельном процессе Django — под ролью savdex_django,
если задан SAVDEX_PARITY_DJANGO_URL, как на сервере. Публичный диск —
во временном каталоге (Storage::fake у Laravel).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
Разбор рисунков по-PHP-шному (относительные ссылки, twoCellAnchor) и
образец книги проверяются и без базы.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import PYTHON, АДРЕС, ОКРУЖЕНИЕ, php, sql, свежая_база

HEADERS = ["Номер", "Название", "Компания", "Категория", "Цена", "Валюта", "Город", "Фото"]

#: Шапка языкового листа: только переводимые поля
TEXT_HEADERS = ["Заголовок", "Описание", "Условия поставки", "Условия оплаты"]

КИРПИЧ = ["", "Кирпич керамический М150", "ООО «Стройбаза»", "", "", "", "", ""]
ПРЯЖА = ["", "Пряжа хлопковая 30/1", "ООО «Стройбаза»", "", "", "", "", ""]

#: Django в отдельном процессе: загрузка книг, итог — JSON-ом
ПРОБА = """
import base64, json, sys
import django
django.setup()
from savdex.data import workbook

a = json.loads(sys.stdin.read())
files = [(name, base64.b64decode(body)) for name, body in a["files"]]

if a["action"]:
    # Кнопка «Загрузить» в списке объявлений: от имени администратора
    out = workbook.import_workbooks(
        files, admin_id=a["admin"], replace=a["replace"], ip="203.0.113.7"
    )
else:
    # ListingWorkbookImport::run, как его зовёт тест Laravel: без входа
    out = workbook.import_workbook(files[0][1], author_id=a["admin"], replace=a["replace"])

print(json.dumps(out, ensure_ascii=False))
"""


@pytest.fixture(scope="module")
def база() -> None:
    if not АДРЕС:
        pytest.skip("нет SAVDEX_PARITY_PG_URL — проверка требует PHP и PostgreSQL")

    свежая_база()


@pytest.fixture
def диск(база: None, tmp_path: Path) -> Path:
    """Чистые таблицы, администратор и пустой публичный диск."""
    sql(
        "truncate listings, listing_images, companies, categories, category_translations, "
        "cities, city_translations, countries, users, admin_actions restart identity cascade"
    )
    sql(
        "insert into users (name, email, password, is_admin, admin_role, status, created_at, "
        "updated_at) values ('Администратор', 'admin@savdex.uz', 'x', true, 'superadmin', "
        "'active', now(), now())"
    )

    return tmp_path


def _админ() -> int:
    return int(sql("select id from users where email = 'admin@savdex.uz'")[0][0])


def загрузить(
    диск: Path,
    *книги: bytes | tuple[str, bytes],
    replace: bool = False,
    кнопкой: bool = False,
) -> dict[str, Any]:
    """Загрузить книги в Django; кнопкой — как действие админки (с журналом)."""
    files = [к if isinstance(к, tuple) else ("catalog.xlsx", к) for к in книги]
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
            "LARAVEL_ROOT": str(диск),
        },
        input=json.dumps(
            {
                "files": [(name, base64.b64encode(body).decode()) for name, body in files],
                "admin": _админ(),
                "replace": replace,
                "action": кнопкой,
            }
        ),
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return dict(json.loads(вывод.stdout))


def фабрика(code: str) -> Any:
    """Данные фабриками Laravel; код печатает JSON последней строкой."""
    return json.loads(php(code, {"MACHINE_TRANSLATION_ENABLED": "false"}).splitlines()[-1])


def компания(name: str = "ООО «Стройбаза»") -> int:
    return int(
        фабрика(
            f"echo json_encode(App\\Models\\Company::factory()->create(['name' => '{name}'])->id);"
        )
    )


def товар(company: int | None, title: str, extra: str = "") -> int:
    """Listing::factory()->for($company)->create([...]); без компании — своя у каждого."""
    owner = (
        f"App\\Models\\Company::query()->findOrFail({company})"
        if company is not None
        else "App\\Models\\Company::factory()->create()"
    )

    return int(
        фабрика(
            f"echo json_encode(App\\Models\\Listing::factory()->for({owner})->create("
            f"['title' => '{title}'{extra}])->id);"
        )
    )


def категория(name: str, parent: int | None = None) -> int:
    child = f"->child(App\\Models\\Category::query()->findOrFail({parent}))" if parent else ""

    return int(
        фабрика(
            f"echo json_encode(App\\Models\\Category::factory()->named('{name}'){child}"
            "->create()->id);"
        )
    )


def город(name: str) -> int:
    """Город с русским названием — как city() в тесте Laravel."""
    return int(
        фабрика(
            "$country = App\\Models\\Country::query()->firstOrCreate(['code' => 'uz'], "
            "['sort' => 0, 'is_active' => true]);"
            "$city = App\\Models\\City::query()->create(['country_id' => $country->id, "
            "'slug' => 'tashkent', 'sort' => 0, 'is_active' => true]);"
            f"$city->translations()->create(['locale' => 'ru', 'name' => '{name}']);"
            "echo json_encode($city->id);"
        )
    )


def строки(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(АДРЕС, autocommit=True, row_factory=dict_row) as соединение:
        return list(соединение.execute(query, params or []).fetchall())


def объявление(title: str) -> dict[str, Any]:
    [found] = строки("select * from listings where title = %s", [title])

    return found


def по_номеру(listing_id: int) -> dict[str, Any]:
    [found] = строки("select * from listings where id = %s", [listing_id])

    return found


def фото(listing_id: int) -> list[dict[str, Any]]:
    return строки(
        "select * from listing_images where listing_id = %s order by sort, id", [listing_id]
    )


def перевод(listing: dict[str, Any], field: str, locale: str) -> str | None:
    """Listing::hasTranslation / localized*: перевод поля, если он не пустой."""
    text = (listing[f"{field}_i18n"] or {}).get(locale)

    return text if text is not None and str(text).strip() != "" else None


# ── Сборка книги ─────────────────────────────────────────────────────


def png(seed: int) -> bytes:
    """Настоящий PNG: загрузка проверяет файлы."""
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (40, 30), ((seed * 40) % 255, 120, 200)).save(out, "PNG")

    return out.getvalue()


def книга(
    rows: dict[int, list[str]],
    pictures: dict[int, int],
    translations: dict[str, dict[int, list[str]]] | None = None,
    *,
    russian_last: bool = False,
    hidden: tuple[str, ...] = (),
) -> bytes:
    """
    Русский лист с товарами и, если нужно, языковые листы. Русский без
    языковых остаётся безымянным, как книга из одного листа; с ними —
    «Русский», первым или последним. Фотографии — на русский лист, в
    столбец «Фото» и правее, по одной на колонку.
    """
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image
    from openpyxl.utils import get_column_letter

    translations = translations or {}
    book = Workbook()
    first = True

    def sheet(name: str | None, headers: list[str], body: dict[int, list[str]]) -> Any:
        nonlocal first
        page: Any = book.active if first else book.create_sheet()
        first = False

        if name is not None:
            page.title = name

            if name in hidden:
                page.sheet_state = "hidden"

        page.append(headers)

        for number in range(2, (max(body) if body else 1) + 1):
            page.append(body.get(number, [""]))

        return page

    def russian() -> Any:
        return sheet("Русский" if translations else None, HEADERS, rows)

    page = None if russian_last else russian()

    for name, body in translations.items():
        sheet(name, TEXT_HEADERS, body)

    if russian_last:
        page = russian()

    number = 0

    for row, count in pictures.items():
        for i in range(count):
            number += 1
            page.add_image(Image(io.BytesIO(png(number))), f"{get_column_letter(8 + i)}{row}")

    out = io.BytesIO()
    book.save(out)

    return out.getvalue()


def лист(name: str, rows: list[list[Any]]) -> bytes:
    """Книга из одного листа — со строками как есть, без готовой шапки."""
    from openpyxl import Workbook

    book = Workbook()
    page: Any = book.active
    page.title = name

    for row in rows:
        page.append(row or [""])

    out = io.BytesIO()
    book.save(out)

    return out.getvalue()


def рисунки_как_в_php(content: bytes, pictures: dict[int, int], sheet: int = 1) -> bytes:
    """
    addPictures() теста Laravel: рисунки дописываются в готовую книгу так,
    как это делает Excel, — twoCellAnchor и ссылки относительно части.
    """
    anchors = relations = ""
    media: dict[str, bytes] = {}
    number = 0

    for row, count in pictures.items():
        for i in range(count):
            number += 1
            media[f"xl/media/image{number}.png"] = png(number)
            anchors += (
                '<xdr:twoCellAnchor editAs="oneCell">'
                f"<xdr:from><xdr:col>{7 + i}</xdr:col><xdr:colOff>0</xdr:colOff>"
                f"<xdr:row>{row - 1}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
                f"<xdr:to><xdr:col>{8 + i}</xdr:col><xdr:colOff>0</xdr:colOff>"
                f"<xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>"
                f'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{number}" name="Picture {number}"/>'
                "<xdr:cNvPicPr/></xdr:nvPicPr>"
                '<xdr:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/'
                f'officeDocument/2006/relationships" r:embed="rId{number}"/>'
                "<a:stretch><a:fillRect/></a:stretch></xdr:blipFill>"
                '<xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
                "</xdr:pic><xdr:clientData/></xdr:twoCellAnchor>"
            )
            relations += (
                f'<Relationship Id="rId{number}" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/image" '
                f'Target="../media/image{number}.png"/>'
            )

    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    parts = {
        **media,
        "xl/drawings/drawing1.xml": head
        + '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/'
        'spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        + anchors
        + "</xdr:wsDr>",
        "xl/drawings/_rels/drawing1.xml.rels": head
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + relations
        + "</Relationships>",
        f"xl/worksheets/_rels/sheet{sheet}.xml.rels": head
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>',
    }

    return _дописать(content, parts)


def _дописать(content: bytes, parts: dict[str, str | bytes]) -> bytes:
    """ZipArchive::addFromString: части заменяются или добавляются."""
    out = io.BytesIO()

    with (
        zipfile.ZipFile(io.BytesIO(content)) as source,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            if item.filename not in parts:
                target.writestr(item, source.read(item.filename))

        for name, data in parts.items():
            target.writestr(name, data)

    return out.getvalue()


# ── Фотографии ───────────────────────────────────────────────────────


def test_фотографии_достаются_объявлениям_своих_строк(диск):
    c = компания()
    brick = товар(c, "Кирпич керамический М150")
    yarn = товар(c, "Пряжа хлопковая 30/1")

    # Между товарами пустая строка: номера строк не должны сползти
    result = загрузить(диск, книга({2: КИРПИЧ, 3: [], 4: ПРЯЖА}, {2: 1, 4: 1}))

    assert result["photos"] == 2
    assert len(фото(brick)) == 1 and len(фото(yarn)) == 1

    [image] = фото(brick)
    assert (диск / "storage/app/public" / image["path"]).is_file()
    assert (диск / "storage/app/public" / image["thumb_path"]).is_file()
    assert image["path"].startswith(f"listings/{brick}/")
    assert image["thumb_path"].startswith(f"listings/{brick}/thumb/")


def test_несколько_фотографий_строки_идут_по_порядку_колонок(диск):
    listing = товар(компания(), "Кирпич керамический М150")

    загрузить(диск, книга({2: КИРПИЧ}, {2: 3}))

    assert [image["sort"] for image in фото(listing)] == [0, 1, 2]


def test_новый_товар_создаётся_с_компанией_категорией_и_ценой(диск):
    c = компания()
    section = категория("Стройматериалы")

    result = загрузить(
        диск,
        книга(
            {
                2: [
                    "",
                    "Профнастил С8",
                    "ООО «Стройбаза»",
                    "Стройматериалы",
                    "1 200 000",
                    "сум",
                    "",
                    "",
                ]
            },
            {2: 1},
        ),
    )
    listing = объявление("Профнастил С8")

    assert result["created"] == 1
    assert listing["category_id"] == section and listing["company_id"] == c
    assert float(listing["price"]) == 1_200_000.0 and listing["currency"] == "UZS"
    assert listing["slug"] == f"profnastil-s8-{listing['id']}"
    assert len(фото(listing["id"])) == 1

    # Новое ждёт проверки: публикует администратор, посмотрев, что получилось
    assert listing["status"] == "moderation" and listing["published_at"] is None
    assert listing["source"] == "import" and listing["type"] == "supply"
    assert listing["user_id"] == _админ() and listing["price_negotiable"] is False
    assert "profnastil" in listing["search_text"]


def test_повторная_загрузка_не_плодит_фотографии(диск):
    listing = товар(компания(), "Кирпич керамический М150")

    загрузить(диск, книга({2: КИРПИЧ}, {2: 1}))
    second = загрузить(диск, книга({2: КИРПИЧ}, {2: 1}))

    assert second["photos"] == 0
    assert len(фото(listing)) == 1


def test_галочка_замены_меняет_фотографии(диск):
    listing = товар(компания(), "Кирпич керамический М150")

    загрузить(диск, книга({2: КИРПИЧ}, {2: 1}))
    [old] = фото(listing)

    загрузить(диск, книга({2: КИРПИЧ}, {2: 2}), replace=True)

    assert len(фото(listing)) == 2
    assert old["path"] not in [image["path"] for image in фото(listing)]
    assert not (диск / "storage/app/public" / old["path"]).exists()
    assert not (диск / "storage/app/public" / old["thumb_path"]).exists()


# ── Строка ───────────────────────────────────────────────────────────


def test_незнакомая_категория_пропускается_а_товар_загружается(диск):
    """
    Непонятная ячейка пропускается, а товар загружается: модератор
    дочинит категорию; пропуск записан в отчёт.
    """
    компания()

    result = загрузить(
        диск,
        книга({2: ["", "Профнастил С8", "ООО «Стройбаза»", "Строительство", "", "", "", ""]}, {}),
    )

    assert result["created"] == 1 and result["errors"] == []
    assert result["notes"] == [
        "Строка 2: категория «Строительство» не найдена в каталоге — ячейка пропущена"
    ]

    [listing] = строки("select * from listings")
    assert listing["title"] == "Профнастил С8" and listing["category_id"] is None


def test_строка_с_номером_правит_существующее_объявление(диск):
    listing = товар(компания(), "Старое название", ", 'price' => 100")

    result = загрузить(
        диск,
        книга({2: [str(listing), "Кирпич керамический М150", "", "", "250000", "", "", ""]}, {}),
    )
    fresh = по_номеру(listing)

    assert result["updated"] == 1
    assert fresh["title"] == "Кирпич керамический М150" and float(fresh["price"]) == 250_000.0

    # Опубликованное повторная загрузка не снимает с витрины
    assert fresh["status"] == "active" and fresh["source"] == "import"
    assert "kirpich" in fresh["search_text"]


def test_номер_числом_и_номер_которого_нет(диск):
    """«Номер» из Excel приходит дробным (12.0) — это всё равно номер 12."""
    listing = товар(компания(), "Кирпич керамический М150")
    book = книга(
        {2: [float(listing), "Кирпич новый", "", "", "", "", "", ""], 3: [99999, "Нет такого"]}, {}
    )

    result = загрузить(диск, book)

    assert result["updated"] == 1
    assert result["errors"] == ["Строка 3: объявление № 99999 не найдено"]
    assert по_номеру(listing)["title"] == "Кирпич новый"


# ── Кнопка в админке ─────────────────────────────────────────────────


def test_кнопка_в_админке_принимает_книгу_и_раскладывает_фотографии(диск):
    listing = товар(компания(), "Кирпич керамический М150")

    result = загрузить(диск, книга({2: КИРПИЧ}, {2: 1}), кнопкой=True)

    assert (result["updated"], result["photos"], result["errors"]) == (1, 1, [])
    assert len(фото(listing)) == 1

    # Журнал: правка объявления (AuditObserver) и след загрузки пачкой
    [(subject, changes, ip)] = sql(
        "select subject_id, changes::text, ip from admin_actions "
        "where section = 'listings' and action = 'updated'"
    )
    assert (subject, ip) == (listing, "203.0.113.7")
    assert json.loads(changes)["after"] == {"source": "import"}
    assert sql(
        "select user_name, note, subject_id from admin_actions where action = 'imported'"
    ) == [("Администратор", "Книг: 1, создано: 0, обновлено: 1, фотографий: 1", None)]


def test_за_раз_принимается_несколько_книг(диск):
    c = компания()
    brick = товар(c, "Кирпич керамический М150")
    yarn = товар(c, "Пряжа хлопковая 30/1")

    # Каталог разрезан по разделам: в каждой книге свой товар
    result = загрузить(
        диск,
        ("stroy.xlsx", книга({2: КИРПИЧ}, {2: 1})),
        ("tekstil.xlsx", книга({2: ПРЯЖА}, {2: 1})),
        кнопкой=True,
    )

    assert (result["updated"], result["photos"]) == (2, 2)
    assert len(фото(brick)) == 1 and len(фото(yarn)) == 1
    assert sql("select note from admin_actions where action = 'imported'") == [
        ("Книг: 2, создано: 0, обновлено: 2, фотографий: 2",)
    ]


def test_имя_книги_в_отчёте_когда_книг_несколько(диск):
    """Из какой книги строка отчёта — понятно только когда их несколько."""
    компания()
    ошибка = книга({2: ["", "Без компании", "", "", "", "", "", ""]}, {})

    одна = загрузить(диск, ("one.xlsx", ошибка), кнопкой=True)
    две = загрузить(диск, ("one.xlsx", ошибка), ("two.xlsx", лист("Лист1", [])), кнопкой=True)

    assert одна["errors"] == [
        "Строка 2: не указана компания, а без неё новое объявление не создать"
    ]
    assert две["errors"] == [
        "one.xlsx, Строка 2: не указана компания, а без неё новое объявление не создать",
        "two.xlsx, Лист «Лист1»: не найдено ни одной заполненной ячейки — лист пуст. "
        "Скачайте образец книги — в нём столбцы названы так, как их ждёт загрузка.",
    ]


# ── Образец и языки столбцов ─────────────────────────────────────────


def test_образец_книги_загружается_без_правок(диск):
    """Образец отдаём заказчику: если его же загрузка не читает — читать нечего."""
    from savdex.data.workbook import template_bytes

    компания()
    section = категория("Стройматериалы")
    bricks = категория("Кирпич и блоки", section)
    city = город("Ташкент")

    result = загрузить(диск, template_bytes())
    listing = объявление("Кирпич керамический М150")

    assert (result["errors"], result["notes"], result["created"]) == ([], [], 1)
    assert listing["category_id"] == bricks and listing["city_id"] == city
    assert listing["currency"] == "UZS" and float(listing["price"]) == 1_200.0
    assert listing["status"] == "moderation" and listing["unit"] == "шт"
    assert listing["min_order"] == 5000
    assert listing["delivery_terms"] == "Самовывоз со склада, доставка по Ташкентской области."
    assert listing["payment_terms"] == "Предоплата 50 %, остаток по факту отгрузки."

    # Четыре языковых листа образца дают четыре перевода каждого поля
    for locale in ("en", "uz", "zh", "tr"):
        for field in ("title", "description", "delivery_terms", "payment_terms"):
            assert перевод(listing, field, locale) is not None, (field, locale)

    assert перевод(listing, "title", "en") == "Ceramic brick M150"


def test_столбцы_на_любом_языке_узнаются(диск):
    # Каждый столбец назван на своём языке, значения — тоже
    компания("Uyut Gulistan Mebel")
    furniture = категория("Мебель")
    фабрика(
        f"App\\Models\\Category::query()->findOrFail({furniture})->translations()"
        "->create(['locale' => 'zh', 'name' => '家具']); echo json_encode(1);"
    )
    city = город("Ташкент")
    фабрика(
        f"App\\Models\\City::query()->findOrFail({city})->translations()"
        "->create(['locale' => 'uz', 'name' => 'Toshkent']); echo json_encode(1);"
    )

    result = загрузить(
        диск,
        лист(
            "Sheet1",
            [
                ["Nomi", "Şirket", "类别", "Price", "Валюта", "Shahar", "Yayınla"],
                [
                    "Ofis stoli",
                    "Uyut Gulistan Mebel",
                    "家具",
                    "1 200 000",
                    "so'm",
                    "Toshkent",
                    "evet",
                ],
            ],
        ),
    )
    listing = объявление("Ofis stoli")

    assert result["errors"] == [] and result["created"] == 1
    assert listing["category_id"] == furniture and listing["city_id"] == city
    assert float(listing["price"]) == 1_200_000.0 and listing["currency"] == "UZS"
    assert listing["status"] == "moderation"


# ── Языковые листы ───────────────────────────────────────────────────


def test_языковые_листы_дают_переводы_строка_к_строке(диск):
    компания()

    # Два товара через пустую строку: смещение от шапки должно сходиться
    # на всех листах, включая пустые строки
    result = загрузить(
        диск,
        книга(
            {2: КИРПИЧ, 3: [], 4: ПРЯЖА},
            {2: 1},
            {
                "English": {
                    2: [
                        "Ceramic brick M150",
                        "Solid brick.",
                        "Pick-up from the warehouse",
                        "50 % prepayment",
                    ],
                    3: [],
                    4: ["Cotton yarn 30/1", "Combed yarn.", "", ""],
                },
                "中文": {
                    2: ["M150 陶瓷砖", "实心砖。", "仓库自提", "预付 50 %"],
                    3: [],
                    4: ["棉纱 30/1", "", "", ""],
                },
            },
        ),
    )
    brick = объявление("Кирпич керамический М150")
    yarn = объявление("Пряжа хлопковая 30/1")

    assert result["errors"] == [] and result["created"] == 2
    assert перевод(brick, "title", "en") == "Ceramic brick M150"
    assert перевод(brick, "description", "en") == "Solid brick."
    assert перевод(brick, "delivery_terms", "en") == "Pick-up from the warehouse"
    assert перевод(brick, "payment_terms", "en") == "50 % prepayment"
    assert перевод(brick, "title", "zh") == "M150 陶瓷砖"
    assert len(фото(brick["id"])) == 1

    assert перевод(yarn, "title", "en") == "Cotton yarn 30/1"
    assert перевод(yarn, "title", "zh") == "棉纱 30/1"

    # Чего на листе не было, того и в переводах нет
    assert перевод(yarn, "description", "zh") is None
    assert перевод(yarn, "delivery_terms", "en") is None
    assert перевод(brick, "title", "uz") is None

    # Переводы заголовка — в поисковом тексте
    assert "ceramic brick" in brick["search_text"]


def test_русский_лист_узнаётся_по_имени_а_не_по_порядку(диск):
    listing = товар(компания(), "Кирпич керамический М150")

    # Английский лист первый: цены и фото всё равно — с русского
    result = загрузить(
        диск,
        книга(
            {2: ["", "Кирпич керамический М150", "ООО «Стройбаза»", "", "9 900", "сум", "", ""]},
            {2: 1},
            {"English": {2: ["Ceramic brick M150", "", "", ""]}},
            russian_last=True,
        ),
    )
    fresh = по_номеру(listing)

    assert result["errors"] == [] and result["updated"] == 1
    assert len(фото(listing)) == 1
    assert float(fresh["price"]) == 9_900.0
    assert перевод(fresh, "title", "en") == "Ceramic brick M150"


def test_лист_с_другим_числом_строк_отклоняет_книгу(диск):
    компания()

    # На английском листе строка удалена: переводы съехали бы на соседний товар
    result = загрузить(
        диск,
        книга({2: КИРПИЧ, 3: ПРЯЖА}, {}, {"English": {2: ["Cotton yarn 30/1", "", "", ""]}}),
    )

    assert (result["created"], result["rows"]) == (0, 0)
    [error] = result["errors"]
    assert "English" in error and "не загружена" in error
    assert error.startswith("Лист «English»: строк с данными 1, на русском листе 2.")
    assert sql("select count(*) from listings") == [(0,)]


def test_пустой_языковой_лист_не_мешает_загрузке(диск):
    компания()

    result = загрузить(диск, книга({2: КИРПИЧ}, {}, {"English": {}}))

    assert result["errors"] == [] and result["created"] == 1
    assert result["notes"] == ["Лист «English» пуст — переводов на этот язык нет."]

    [listing] = строки("select * from listings")
    assert перевод(listing, "title", "en") is None


def test_пустая_ячейка_перевода_не_стирает_старый(диск):
    listing = товар(
        компания(),
        "Кирпич керамический М150",
        ", 'title_i18n' => ['en' => 'Ceramic brick M150', 'tr' => 'Seramik tuğla M150']",
    )

    # Переводчик дошёл только до описания: заголовок в книге пуст
    загрузить(диск, книга({2: КИРПИЧ}, {}, {"English": {2: ["", "Solid brick.", "", ""]}}))
    fresh = по_номеру(listing)

    assert перевод(fresh, "title", "en") == "Ceramic brick M150"
    assert перевод(fresh, "title", "tr") == "Seramik tuğla M150"
    assert перевод(fresh, "description", "en") == "Solid brick."


def test_два_листа_на_одном_языке_отклоняют_книгу(диск):
    компания()

    result = загрузить(
        диск,
        книга(
            {2: КИРПИЧ},
            {},
            {"English": {2: ["Ceramic brick", "", "", ""]}, "en": {2: ["Brick", "", "", ""]}},
        ),
    )

    assert result["created"] == 0
    assert result["errors"] == [
        "Два листа на одном языке: «English» и «en». Оставьте один — книга не загружена."
    ]


def test_книга_без_русского_листа_отклоняется(диск):
    компания()

    result = загрузить(
        диск,
        лист("English", [HEADERS, ["", "Ceramic brick", "ООО «Стройбаза»", "", "", "", "", ""]]),
    )

    assert result["created"] == 0
    [error] = result["errors"]
    assert "нет русского листа" in error


# ── Шапка ────────────────────────────────────────────────────────────


def test_шапка_с_пометками_узнаётся(диск):
    компания()

    # Звёздочки, пояснения в скобках и единица через запятую
    result = загрузить(
        диск,
        лист(
            "Лист XLSX",
            [
                ["Название*", "Компания:", "Цена (за штуку)", "Валюта, код"],
                ["Профнастил С8", "ООО «Стройбаза»", "1 200 000", "сум"],
            ],
        ),
    )
    listing = объявление("Профнастил С8")

    assert result["errors"] == []
    assert float(listing["price"]) == 1_200_000.0 and listing["currency"] == "UZS"


def test_без_шапки_отчёт_показывает_что_стоит_в_строке(диск):
    result = загрузить(
        диск,
        лист(
            "Лист XLSX",
            [
                ["Каталог продукции"],
                [],
                ["Наименование позиции", "Производитель", "Сколько стоит"],
                ["Профнастил С8", "ООО «Стройбаза»", "1 200 000"],
            ],
        ),
    )

    assert result["created"] == 0
    [error] = result["errors"]

    # Показана строка с несколькими ячейками, а не заголовок отчёта над ней
    assert "В строке 3 записано «Наименование позиции», «Производитель»" in error
    assert "Загрузка ждёт: Номер, Название, Компания" in error
    assert "Фото" not in error
    assert error == (
        "Лист «Лист XLSX»: не найдена строка с названиями столбцов. В строке 3 записано "
        "«Наименование позиции», «Производитель», «Сколько стоит» — ни одно не совпало с "
        "названием столбца. Загрузка ждёт: Номер, Название, Компания, Категория, Тип, Цена, "
        "Валюта, Единица, Минимальный заказ, Город, Описание, Условия поставки, Условия "
        "оплаты. Скачайте образец книги — в нём столбцы названы так, как их ждёт загрузка."
    )


def test_шапка_в_одной_ячейке_просит_разбить_по_столбцам(диск):
    result = загрузить(
        диск,
        лист(
            "Лист XLSX",
            [["Номер;Название;Компания;Цена"], [";Профнастил С8;ООО «Стройбаза»;1200000"]],
        ),
    )

    [error] = result["errors"]
    assert "в одной ячейке через «;»" in error


def test_пустой_лист_называется_пустым(диск):
    result = загрузить(диск, лист("Лист XLSX", []))

    [error] = result["errors"]
    assert "лист пуст" in error


def test_условия_поставки_и_оплаты_читаются_с_русского_листа(диск):
    компания()

    result = загрузить(
        диск,
        лист(
            "Sheet1",
            [
                ["Название", "Компания", "Условия доставки", "Оплата"],
                [
                    "Кирпич керамический М150",
                    "ООО «Стройбаза»",
                    "Самовывоз со склада",
                    "Предоплата 50 %",
                ],
            ],
        ),
    )
    [listing] = строки("select * from listings")

    assert result["errors"] == []
    assert listing["delivery_terms"] == "Самовывоз со склада"
    assert listing["payment_terms"] == "Предоплата 50 %"


def test_незнакомая_валюта_пропускается(диск):
    """Валюта не из списка — цена остаётся в сумах, товар загружается."""
    компания()

    result = загрузить(
        диск,
        книга(
            {2: ["", "Кирпич керамический М150", "ООО «Стройбаза»", "", "100", "XYZ", "", ""]}, {}
        ),
    )

    assert result["created"] == 1 and result["errors"] == []
    assert "XYZ" in result["notes"][0]
    assert result["notes"] == [
        "Строка 2: валюта «XYZ» не поддерживается (можно: UZS, USD, EUR, CNY, TRY, RUB, KZT) "
        "— оставлена прежняя"
    ]

    [listing] = строки("select price::text, currency from listings")
    assert (listing["price"], listing["currency"]) == ("100.00", "UZS")


def test_скрытый_лист_не_читается(диск):
    компания()

    # «English» из образца спрятали вместо удаления: в нём остался пример,
    # и он не должен стать переводом чужого товара
    result = загрузить(
        диск,
        книга(
            {2: КИРПИЧ, 3: ПРЯЖА},
            {},
            {"English": {2: ["Ceramic brick M150", "Sample.", "", ""]}},
            hidden=("English",),
        ),
    )

    assert result["errors"] == [] and result["created"] == 2
    assert result["notes"] == ["Скрытый лист «English» пропущен."]
    assert перевод(объявление("Кирпич керамический М150"), "title", "en") is None


def test_лист_с_неузнанным_именем_пропускается_с_заметкой(диск):
    компания()

    result = загрузить(
        диск, книга({2: КИРПИЧ}, {}, {"Eng.": {2: ["Ceramic brick M150", "", "", ""]}})
    )

    assert result["errors"] == [] and result["created"] == 1
    [note] = result["notes"]
    assert "«Eng.»" in note
    [listing] = строки("select * from listings")
    assert перевод(listing, "title", "en") is None


def test_перевод_напротив_пустой_русской_строки_отклоняет_книгу(диск):
    компания()

    # Число строк сходится, но в русском листе строку стёрли, а внизу
    # дописали: переводы съехали на соседний товар
    result = загрузить(
        диск,
        книга(
            {2: КИРПИЧ, 3: [], 4: ПРЯЖА},
            {},
            {
                "English": {
                    2: ["Ceramic brick M150", "", "", ""],
                    3: ["Orphan translation", "", "", ""],
                    4: ["Cotton yarn 30/1", "", "", ""],
                }
            },
        ),
    )

    assert result["created"] == 0
    assert result["errors"] == [
        "Лист «English», строка 3: заполнена, а на русском листе строка 3 пуста — строки "
        "разъехались. Книга не загружена."
    ]


def test_одинаковый_заголовок_у_разных_компаний_требует_компанию(диск):
    first = товар(None, "Кирпич керамический М150", ", 'price' => 100")
    second = товар(None, "Кирпич керамический М150", ", 'price' => 200")

    # Ни номера, ни компании: править первое попавшееся — значит менять
    # цену чужого товара
    result = загрузить(
        диск, книга({2: ["", "Кирпич керамический М150", "", "", "777", "", "", ""]}, {})
    )

    assert result["updated"] == 0
    [error] = result["errors"]
    assert "нескольких объявлений" in error
    assert float(по_номеру(first)["price"]) == 100.0
    assert float(по_номеру(second)["price"]) == 200.0


def test_слишком_длинный_текст_обрезается_с_заметкой(диск):
    """Длинный текст обрезается по границе слова, а не отменяет строку."""
    компания()

    result = загрузить(диск, книга({2: КИРПИЧ}, {}, {"English": {2: ["Brick " * 20, "", "", ""]}}))

    assert result["created"] == 1 and result["errors"] == []
    assert "«en»" in result["notes"][0] and "90" in result["notes"][0]

    [listing] = строки("select * from listings")
    english = listing["title_i18n"]["en"]

    assert len(english) <= 90 and english.startswith("Brick Brick")
    assert english == ("Brick " * 15).strip()


# ── Сверх теста Laravel ──────────────────────────────────────────────


def test_пропуски_копятся_между_строками_как_у_laravel(диск):
    """
    Ошибка Laravel, повторённая до его отключения: список пропущенных
    ячеек не сбрасывается между строками одной книги.
    """
    компания()

    result = загрузить(
        диск,
        книга(
            {
                2: ["", "Профнастил С8", "ООО «Стройбаза»", "Строительство", "", "", "", ""],
                3: ["", "Профнастил С10", "ООО «Стройбаза»", "", "", "", "", ""],
            },
            {},
        ),
    )

    assert result["created"] == 2
    assert result["notes"] == [
        "Строка 2: категория «Строительство» не найдена в каталоге — ячейка пропущена",
        "Строка 3: категория «Строительство» не найдена в каталоге — ячейка пропущена",
    ]


def test_рисунки_как_их_вставляет_excel(диск):
    """Относительные ссылки и twoCellAnchor, как в addPictures() теста Laravel."""
    listing = товар(компания(), "Кирпич керамический М150")

    result = загрузить(диск, рисунки_как_в_php(книга({2: КИРПИЧ}, {}), {2: 2}))

    assert result["photos"] == 2
    assert [image["sort"] for image in фото(listing)] == [0, 1]


# ── Без базы ─────────────────────────────────────────────────────────


def test_фотографии_по_строкам_и_колонкам(tmp_path):
    """
    WorkbookImages: строка — по верхнему левому углу, в строке — по
    колонкам; absoluteAnchor, внешняя картинка и пустой файл — мимо.
    """
    from savdex.data.workbook import extract_photos

    book = рисунки_как_в_php(книга({2: КИРПИЧ, 3: ПРЯЖА}, {}), {3: 2, 2: 1})

    with zipfile.ZipFile(io.BytesIO(book)) as source:
        drawing = source.read("xl/drawings/drawing1.xml").decode()
        rels = source.read("xl/drawings/_rels/drawing1.xml.rels").decode()

    # Колонки второй строки — в обратном порядке: порядок берётся из колонок
    drawing = drawing.replace("<xdr:col>7</xdr:col>", "<xdr:col>9</xdr:col>", 1)
    extra = (
        '<xdr:absoluteAnchor><xdr:pos x="0" y="0"/><xdr:pic><xdr:blipFill>'
        '<a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'r:embed="rId1"/></xdr:blipFill></xdr:pic></xdr:absoluteAnchor>'
        "<xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:row>3</xdr:row></xdr:from>"
        '<xdr:pic><xdr:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships" r:embed="rId9"/></xdr:blipFill></xdr:pic>'
        "</xdr:oneCellAnchor>"
        "<xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:row>4</xdr:row></xdr:from>"
        '<xdr:pic><xdr:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships" r:embed="rId8"/></xdr:blipFill></xdr:pic>'
        "</xdr:oneCellAnchor>"
    )
    drawing = drawing.replace("</xdr:wsDr>", extra + "</xdr:wsDr>")
    rels = rels.replace(
        "</Relationships>",
        '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/image" Target="http://example.com/a.png" TargetMode="External"/>'
        '<Relationship Id="rId8" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/image" Target="../media/empty.png"/></Relationships>',
    )
    book = _дописать(
        book,
        {
            "xl/drawings/drawing1.xml": drawing,
            "xl/drawings/_rels/drawing1.xml.rels": rels,
            "xl/media/empty.png": b"",
        },
    )

    photos = extract_photos(book, tmp_path, "Sheet")

    assert sorted(photos) == [2, 3]
    assert [p.name for p in photos[2]] == ["1-image3.png"]
    # Рисунок из колонки H перенесён в J: теперь он второй
    assert [p.name for p in photos[3]] == ["2-image2.png", "3-image1.png"]
    assert photos[3][1].read_bytes() == png(1)

    # Лист без рисунков и чужое имя — пусто; не книга — пусто
    assert extract_photos(book, tmp_path / "x", "Нет такого") == {}
    assert extract_photos(b"not a zip", tmp_path / "y") == {}


def test_рисунки_openpyxl_с_абсолютными_ссылками(tmp_path):
    from savdex.data.workbook import extract_photos

    photos = extract_photos(книга({2: КИРПИЧ, 3: [], 4: ПРЯЖА}, {4: 2, 2: 1}), tmp_path)

    assert {row: [p.name for p in paths] for row, paths in photos.items()} == {
        2: ["1-image3.png"],
        4: ["2-image1.png", "3-image2.png"],
    }


def test_образец_книги():
    """Пять листов, по одному на язык, с именами как в переключателе языка."""
    from openpyxl import load_workbook

    from savdex.data.workbook import HEADERS as ОБРАЗЕЦ
    from savdex.data.workbook import sheet_locale, template_bytes

    book = load_workbook(io.BytesIO(template_bytes()))
    names = book.sheetnames

    assert names == ["Русский", "English", "O‘zbekcha", "中文", "Türkçe"]
    assert [sheet_locale(name) for name in names] == ["ru", "en", "uz", "zh", "tr"]

    ru = [list(row) for row in book["Русский"].iter_rows(values_only=True)]
    assert ru[0] == ОБРАЗЕЦ and ru[1][0] is None and ru[1][5] == "1200"
    english = [list(row) for row in book["English"].iter_rows(values_only=True)]
    assert english[0] == ["Title", "Description", "Delivery terms", "Payment terms"]


def test_не_книга():
    from savdex.data.workbook import UnreadableWorkbookError, import_workbook

    with pytest.raises(UnreadableWorkbookError):
        import_workbook(b"not a workbook", author_id=1)


def test_значения_ячеек_как_у_openspout():
    from datetime import datetime, time

    from savdex.data.workbook import _strimwidth, _text

    epoch = datetime(1899, 12, 30)

    assert _text(12.0, epoch) == "12" and _text(12.5, epoch) == "12.5"
    assert _text(0.00001, epoch) == "1.0E-5"
    assert _text(True, epoch) == "да" and _text(False, epoch) == "нет"
    assert _text(datetime(2026, 10, 30, 12), epoch) == "30.10.2026"
    assert _text(time(12), epoch) == "30.12.1899"
    assert _text("  Кирпич \t", epoch) == "Кирпич" and _text(None, epoch) == ""
    # Неразрывный пробел trim() у PHP не трогает
    assert _text(" x ", epoch) == " x "

    assert _strimwidth("а" * 40, 40) == "а" * 40
    assert _strimwidth("а" * 41, 40) == "а" * 39 + "…"
    assert _strimwidth("中" * 25, 40) == "中" * 19 + "…"
