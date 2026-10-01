"""
Загрузка компаний таблицей — перенос tests/Feature/Admin/CompanyImportTest.php.

Файл готовит заказчик, язык заголовков заранее не известен, ячейки набраны
руками: прочерк вместо пустоты, две почты через косую черту, «около 6500
(по публичным данным)» в численности. Строка из-за этого не теряется.

Сценарии PHP — одноимённые проверки ниже (каждый вызов import() у PHP —
отдельная таблица из одной строки, как очередь Filament). Сверх них:
отчёт по файлу (номера строк и причины, незнакомые столбцы, нет столбца
«Название»), поля новой компании и журнал — и все сценарии подряд
одной очередью: какие компании и строки журнала получаются в итоге.

Проверки с базой требуют PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from savdex.data import company_import
from savdex.data.company_import import column_map

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база, сотрудник

#: import_companies() в отдельном процессе Django: по таблице на вызов
ПРОБА = """
import dataclasses, json, sys
import django
django.setup()
from savdex.data.company_import import import_companies
from savdex.tenders.importer import read_table

tables, admin = json.loads(sys.argv[1]), int(sys.argv[2])
out = []
for table in tables:
    if isinstance(table, dict):
        table = read_table(table["name"], table["csv"].encode("utf-8-sig"))
    out.append(dataclasses.asdict(import_companies(table, admin_id=admin)))
print(json.dumps(out, ensure_ascii=False))
"""

СТОЛБЦЫ = (
    "tin", "name", "legal_name", "type", "address", "phone", "email", "website",
    "description", "founded_year", "employees_range", "country_id", "status",
    "verification_level", "source_note", "search_text", "slug", "logo_path", "deleted_at",
)  # fmt: skip


# ── Без базы: заголовки и ячейки ─────────────────────────────────────


def test_заголовки_узнаются_как_в_окне_импорта_и_по_синонимам():
    # Точное совпадение без учёта регистра — как угадывает Filament,
    # в том числе по имени столбца
    assert column_map(["ИНН", "legal_name", "EMPLOYEES_RANGE"]) == {
        "tin": "ИНН",
        "legal_name": "legal_name",
        "employees_range": "EMPLOYEES_RANGE",
    }
    # Пометки, «ё» и лишние пробелы — вторым шагом, по словарю синонимов
    assert column_map(["Название*", "Год  основания:", "Сайт (адрес)", "Страна, код"]) == {
        "name": "Название*",
        "founded_year": "Год  основания:",
        "website": "Сайт (адрес)",
        # У PHP синоним страны лежит под ключом «country» и второй шаг
        # страну не находил; здесь находит
        "country_id": "Страна, код",
    }
    # Заголовок занимает один столбец: «Адрес» — адрес, а не сайт
    assert column_map(["Адрес", "Адрес сайта"]) == {"address": "Адрес", "website": "Адрес сайта"}


def test_ячейки_набранные_руками():
    assert company_import.year("1827 / 2003") == 1827
    assert company_import.year("осн. 1998 г.") == 1998
    assert company_import.year("—") is None
    assert company_import.year("1499") is None
    assert company_import.employees("около 6500 (по публичным данным)") == "6500"
    assert company_import.employees("50 – 100") == "50-100"
    assert company_import.employees("не указано") is None
    assert company_import.humanize("TOSHKENT MATRAS LYUKS MCHJ") == "Toshkent Matras Lyuks MCHJ"
    assert company_import.humanize("ООО «СТРОЙБАЗА»") == "ООО «Стройбаза»"
    assert company_import.humanize("O'ZBEK-TEST") == "O'zbek-Test"
    assert company_import.humanize("Tashkent Matras") == "Tashkent Matras"
    assert company_import.type_key("IT") == "service"
    assert company_import.type_key("Üretim ve ihracat") == "manufacturer"
    assert company_import.type_key("Логистика") == "логистика"


@pytest.mark.parametrize(
    ("название", "итог"),
    [
        # Капсом — с заглавной каждое слово; формы собственности — как есть
        ("TOSHKENT MATRAS LYUKS", "Toshkent Matras Lyuks"),
        ("ООО «СТРОЙБАЗА»", "ООО «Стройбаза»"),
        ("O'ZBEK-TEST 3D AB.CD", "O'zbek-Test 3D Ab.cd"),
        # Есть строчные (ß) — не капс, не трогаем
        ("STRASSE ß", "STRASSE ß"),
        ("Tashkent Matras", "Tashkent Matras"),
        ("12345", "12345"),
        ("  МЧЖ ХК QURILISH MCHJ ", "МЧЖ ХК Qurilish MCHJ"),
        # mb_strtolower делает из «İ» «i» и точку сверху отдельным знаком
        ("İSTANBUL ÇELİK", "I\u0307stanbul Çeli\u0307k"),
        ("X_Y É1A", "X_Y É1A"),
        ("DŽEM OOO LLC JV", "Džem OOO LLC JV"),
        ("", ""),
    ],
)
def test_название_капсом(название, итог):
    """CompanyNameStyle::humanize."""
    assert company_import.humanize(название) == итог


@pytest.mark.parametrize(
    ("тип", "ключ"),
    [
        ("IT", "service"),
        ("ИТ", "service"),
        ("Айти", "service"),
        ("IT-услуги", "service"),
        ("IT services", "service"),
        # Вне справочника — как есть, строчными
        ("Логистика", "логистика"),
        ("Üretim ve ihracat", "manufacturer"),
        ("производство", "manufacturer"),
        ("Import-export", "importer"),
        ("Дилер", "distributor"),
        (" ", None),
        (None, None),
    ],
)
def test_тип_компании(тип, ключ):
    """CompanyNameStyle::typeKey."""
    assert company_import.type_key(тип) == ключ


@pytest.mark.parametrize(
    ("ячейка", "год"),
    [
        ("1827 / 2003", 1827),
        ("осн. 1998 г.", 1998),
        ("—", None),
        # Вне 1500…текущего года — не год
        ("1499", None),
        ("2999", None),
        ("3000 1990", 1990),
        # Цифры другой письменности не считаются
        ("١٩٩٨ 2003", 2003),
    ],
)
def test_год_основания(ячейка, год):
    """ImportCell::year: первое правдоподобное четырёхзначное число."""
    assert company_import.year(ячейка) == год


@pytest.mark.parametrize(
    ("ячейка", "численность"),
    [
        ("около 6500 (по публичным данным)", "6500"),
        ("50-100", "50-100"),
        ("50 – 100", "50-100"),
        ("1 000+", "1000+"),
        ("не указано", None),
        ("много", "много"),
        # Длинное — обрезается до 16 знаков
        ("12345678901234567", "1234567890123456"),
        ("очень много сотрудников в компании", "очень много"),
    ],
)
def test_численность(ячейка, численность):
    """ImportCell::employees."""
    assert company_import.employees(ячейка) == численность


# ── С базой ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def база() -> dict[str, int]:
    свежая_база()

    return {"админ": сотрудник("superadmin")}


@pytest.fixture
def админ(база) -> int:
    """Каждая проверка — с пустым списком компаний, как RefreshDatabase у PHP."""
    sql("delete from companies")
    sql("delete from admin_actions")

    return база["админ"]


def _загрузить(admin: int, *таблицы: list[dict[str, Any]] | dict[str, str]) -> list[dict[str, Any]]:
    """Таблицы по очереди; таблица — строки или {"name", "csv"} — файл для read_table."""
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, json.dumps(таблицы), str(admin)],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return list(json.loads(вывод.stdout))


def _импорт(admin: int, *строки: dict[str, str]) -> list[dict[str, Any]]:
    """Как import() у PHP: каждая строка — отдельная загрузка."""
    return _загрузить(admin, *([строка] for строка in строки))


def _компании() -> list[dict[str, Any]]:
    rows = sql(f"select {', '.join(СТОЛБЦЫ)} from companies order by id")

    return [dict(zip(СТОЛБЦЫ, row, strict=True)) for row in rows]


def _компания(name: str) -> dict[str, Any]:
    [компания] = [c for c in _компании() if c["name"] == name]

    return компания


@нужна_база
def test_синонимы_русских_заголовков_разбираются(админ):
    _импорт(
        админ,
        {
            "ИНН": "304561278",
            "Компания": "ООО «Стройбаза»",
            "Тип": "Производитель",
            "Год основания": "1998",
            "Контактный телефон": "+998 71 200-00-00",
            "Адрес сайта": "stroybaza.uz",
        },
    )

    [компания] = _компании()

    assert компания["tin"] == "304561278"
    assert компания["name"] == "ООО «Стройбаза»"
    assert компания["type"] == "manufacturer"
    assert компания["founded_year"] == 1998
    assert компания["phone"] == "+998 71 200-00-00"
    assert компания["website"] == "stroybaza.uz"


@нужна_база
def test_заголовки_и_тип_компании_на_чужом_языке_разбираются(админ):
    _импорт(
        админ,
        {
            "Tax ID": "305000111",
            "Company name": "Tashkent Matras",
            "Company type": "Ishlab chiqaruvchi",
            "Employees": "50-100",
            "Web site": "matras.uz",
            "Kuruluş yılı": "2005",
        },
    )

    [компания] = _компании()

    assert компания["tin"] == "305000111"
    assert компания["name"] == "Tashkent Matras"
    assert компания["type"] == "manufacturer"
    assert компания["employees_range"] == "50-100"
    assert компания["website"] == "matras.uz"
    assert компания["founded_year"] == 2005


@нужна_база
def test_тип_вне_справочника_сохраняется_как_есть(админ):
    _импорт(
        админ, {"ИНН": "300111222", "Название": "Быстрая логистика", "Тип компании": "Логистика"}
    )

    assert _компании()[0]["type"] == "логистика"


@нужна_база
def test_прочерк_вместо_значения_не_ломает_строку(админ):
    """
    Прочерк — «данных нет», а не значение: раньше «—» в ИНН делал всех
    иностранных поставщиков одной компанией.
    """
    _импорт(
        админ,
        {"ИНН": "—", "Название": "Awal Dairy", "Почта": "—", "Год основания": "—", "Телефон": "-"},
        {"ИНН": "—", "Название": "Alba", "Почта": "н/д", "Сотрудников": "не указано"},
    )

    assert len(_компании()) == 2

    компания = _компания("Awal Dairy")

    assert компания["tin"] is None
    assert компания["email"] is None
    assert компания["founded_year"] is None
    assert компания["phone"] is None
    assert _компания("Alba")["employees_range"] is None


@нужна_база
def test_несколько_значений_в_ячейке_берут_первое(админ):
    _импорт(
        админ,
        {
            "Название": "Arabian Pipes",
            "Почта": "info@arabian-pipes.com / export_sales@arabian-pipes.com",
            "Телефон": "+966 11 8133333 / +966 12 6104000 / +966 13 8495000",
            "Год основания": "1827 / 2003",
            "Сайт": "https://arabian-pipes.com / https://shop.arabian-pipes.com",
        },
    )

    [компания] = _компании()

    assert компания["email"] == "info@arabian-pipes.com"
    assert компания["phone"] == "+966 11 8133333"
    assert компания["founded_year"] == 1827
    assert компания["website"] == "https://arabian-pipes.com"


@нужна_база
def test_старая_компания_и_численность_словами(админ):
    _импорт(
        админ,
        {
            "Название": "Villeroy & Boch",
            "Год основания": "1790",
            "Сотрудников": "около 6500 (по публичным данным)",
        },
    )

    [компания] = _компании()

    assert компания["founded_year"] == 1790
    assert компания["employees_range"] == "6500"


@нужна_база
def test_тип_узнаётся_по_корню_слова(админ):
    _импорт(
        админ,
        {"Название": "Hateks", "Тип компании": "производство, экспорт, торговля"},
        {"Название": "ITWorx", "Тип компании": "IT"},
        {"Название": "Ekol", "Тип компании": "Üretim ve ihracat"},
    )

    assert _компания("Hateks")["type"] == "manufacturer"
    assert _компания("ITWorx")["type"] == "service"
    assert _компания("Ekol")["type"] == "manufacturer"


def _польша() -> int:
    найдена = sql("select id from countries where code = 'pl'")

    if найдена:
        return int(найдена[0][0])

    [(pk,)] = sql(
        "insert into countries (code, phone_code, currency_code, is_active, created_at, "
        "updated_at) values ('pl', '+48', 'PLN', true, now(), now()) returning id"
    )
    sql(
        "insert into country_translations (country_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', 'Польша', now(), now())",
        [pk],
    )

    return int(pk)


@нужна_база
def test_страна_из_таблицы_проставляется(админ):
    польша = _польша()

    _импорт(
        админ,
        {"Название": "Forte", "Страна": "Польша"},
        {"Название": "Szynaka", "Страна": "Мордор"},
    )

    assert _компания("Forte")["country_id"] == польша
    assert _компания("Szynaka")["country_id"] is None


@нужна_база
def test_повторная_загрузка_без_инн_не_плодит_дублей(админ):
    отчёты = _импорт(
        админ,
        {"Название": "Comforty", "Почта": "comforty@comforty.pl"},
        {"Название": "Comforty", "Почта": "info@comforty.pl", "Год основания": "1995"},
    )

    [компания] = _компании()

    assert компания["email"] == "info@comforty.pl"
    assert компания["founded_year"] == 1995
    assert [len(о["created"]) for о in отчёты] == [1, 0]
    assert [len(о["updated"]) for о in отчёты] == [0, 1]


@нужна_база
def test_компанию_с_инн_безымянная_строка_не_трогает(админ):
    _импорт(
        админ,
        {"ИНН": "304561278", "Название": "Стройбаза", "Почта": "info@stroybaza.uz"},
        {"ИНН": "—", "Название": "Стройбаза", "Почта": "other@example.com"},
    )

    assert len(_компании()) == 2
    assert [c["email"] for c in _компании() if c["tin"] == "304561278"] == ["info@stroybaza.uz"]


@нужна_база
def test_новая_компания_и_журнал(админ):
    """beforeSave, события Company и AuditObserver: как у Eloquent."""
    [отчёт] = _импорт(админ, {"ИНН": "301234567", "Название": "TOSHKENT MATRAS LYUKS"})
    [компания] = _компании()

    assert компания["name"] == "Toshkent Matras Lyuks"
    assert компания["status"] == "active"
    assert компания["verification_level"] == 0
    assert компания["source_note"] == "Данные компании взяты из открытых источников."
    assert компания["slug"] == "toshkent-matras-lyuks"
    assert компания["search_text"]
    assert len(отчёт["created"]) == 1

    [(действие, раздел, подпись, изменения)] = sql(
        "select action, section, subject_label, changes from admin_actions"
    )
    assert (действие, раздел, подпись) == ("created", "companies", "Toshkent Matras Lyuks")
    assert list(изменения["after"]) == [
        "tin", "name", "status", "verification_level", "source_note", "slug", "id",
    ]  # fmt: skip

    # Та же строка ещё раз — ничего не меняется, журнал молчит
    [отчёт] = _импорт(админ, {"ИНН": "301234567", "Название": "TOSHKENT MATRAS LYUKS"})

    assert отчёт["unchanged"] == 1
    assert len(sql("select id from admin_actions")) == 1

    # Правка — «изменено» с тем, что было и что стало
    _импорт(админ, {"ИНН": "301234567", "Название": "Toshkent Matras", "Почта": "a@b.uz"})

    [(изменения,)] = sql("select changes from admin_actions where action = 'updated'")
    assert изменения == {
        "before": {"name": "Toshkent Matras Lyuks", "email": None},
        "after": {"name": "Toshkent Matras", "email": "a@b.uz"},
    }


@нужна_база
def test_отчёт_по_файлу(админ):
    файл = {
        "name": "companies.csv",
        "csv": "Название;Тип компании;Почта;Непонятный столбец\n"
        "Forte;Производитель;info@forte.pl;x\n"
        "—;Производитель;a@b.pl;x\n"
        "Szynaka;Очень длинный вид деятельности компании;;x\n",
    }

    [первый, второй] = _загрузить(админ, файл, файл)

    assert len(первый["created"]) == 1
    assert первый["failed"] == [
        [3, "нет названия"],
        [4, "тип компании длиннее 32 знаков: очень длинный вид деятельности компании"],
    ]
    assert первый["unknown_headers"] == ["Непонятный столбец"]
    assert (len(второй["created"]), второй["unchanged"]) == (0, 1)
    assert [c["name"] for c in _компании()] == ["Forte"]


@нужна_база
def test_без_столбца_названия_не_загружается_ничего(админ):
    [отчёт] = _загрузить(админ, [{"ИНН": "304561278", "Почта": "info@stroybaza.uz"}])

    assert отчёт["missing"] == ["Название"]
    assert _компании() == []


# ── Все сценарии подряд ─────────────────────────────────────────────

#: Строки всех сценариев подряд, и сверх них — капс, пометки в заголовках
СВЕРКА = [
    {"ИНН": "304561278", "Компания": "ООО «Стройбаза»", "Тип": "Производитель",
     "Год основания": "1998", "Контактный телефон": "+998 71 200-00-00",
     "Адрес сайта": "stroybaza.uz"},
    {"Tax ID": "305000111", "Company name": "Tashkent Matras", "Company type": "Ishlab chiqaruvchi",
     "Employees": "50-100", "Web site": "matras.uz", "Kuruluş yılı": "2005"},
    {"ИНН": "300111222", "Название": "Быстрая логистика", "Тип компании": "Логистика"},
    {"ИНН": "—", "Название": "Awal Dairy", "Почта": "—", "Год основания": "—", "Телефон": "-"},
    {"ИНН": "—", "Название": "Alba", "Почта": "н/д", "Сотрудников": "не указано"},
    {"Название": "Arabian Pipes",
     "Почта": "info@arabian-pipes.com / export_sales@arabian-pipes.com",
     "Телефон": "+966 11 8133333 / +966 12 6104000", "Год основания": "1827 / 2003",
     "Сайт": "https://arabian-pipes.com / https://shop.arabian-pipes.com"},
    {"Название": "Villeroy & Boch", "Год основания": "1790",
     "Сотрудников": "около 6500 (по публичным данным)"},
    {"Название": "Hateks", "Тип компании": "производство, экспорт, торговля"},
    {"Название": "ITWorx", "Тип компании": "IT"},
    {"Название": "Forte", "Страна": "Польша"},
    {"Название": "Szynaka", "Страна": "Мордор"},
    {"Название": "Comforty", "Почта": "comforty@comforty.pl"},
    {"Название": "Comforty", "Почта": "info@comforty.pl", "Год основания": "1995"},
    {"ИНН": "304561278", "Название": "СТРОЙБАЗА ГРУПП MCHJ", "Почта": "info@stroybaza.uz",
     "Юридическое название": "ООО «Стройбаза Групп»", "Описание": "Цемент  и  бетон"},
    {"ИНН": "—", "Название": "Стройбаза Групп MCHJ", "Почта": "other@example.com"},
    {"Название*": "Ekol", "Тип компании:": "Üretim ve ihracat", "Адрес (юр.)": "İstanbul"},
    {"Название": "—", "Почта": "x@y.z"},
    {"Название": "Long Type", "Тип": "Очень длинный вид деятельности компании"},
]  # fmt: skip


def _снимок() -> dict[str, Any]:
    """Компании и журнал без номеров записей и меток времени."""
    журнал = []

    for действие, раздел, подпись, изменения, роль in sql(
        "select action, section, subject_label, changes::text, user_role "
        "from admin_actions order by id"
    ):
        разобранные = json.loads(изменения) if изменения else None

        if разобранные and "after" in разобранные:
            разобранные["after"].pop("id", None)

        # Порядок полей — часть строки журнала: список пар, а не словарь
        журнал.append(
            (
                действие,
                раздел,
                подпись,
                {k: list(v.items()) for k, v in разобранные.items()} if разобранные else None,
                роль,
            )
        )

    return {"компании": _компании(), "журнал": журнал}


ИСТОЧНИК = "Данные компании взяты из открытых источников."


@нужна_база
def test_все_сценарии_подряд(админ):
    """Строки всех сценариев одной очередью: итоговые компании и журнал."""
    польша = _польша()
    отчёты = _импорт(админ, *СВЕРКА)
    снимок = _снимок()
    поля = ("name", "tin", "type", "email", "phone", "website", "founded_year",
            "employees_range", "country_id", "address")  # fmt: skip

    # (название, ИНН, тип, почта, телефон, сайт, год, численность, страна, адрес)
    assert [tuple(c[k] for k in поля) for c in снимок["компании"]] == [
        # ИНН совпал со строкой «СТРОЙБАЗА ГРУПП MCHJ» — та же компания, обновлена
        ("Стройбаза Групп MCHJ", "304561278", "manufacturer", "info@stroybaza.uz",
         "+998 71 200-00-00", "stroybaza.uz", 1998, None, None, None),
        ("Tashkent Matras", "305000111", "manufacturer", None, None, "matras.uz", 2005, "50-100",
         None, None),
        ("Быстрая логистика", "300111222", "логистика", None, None, None, None, None, None, None),
        # Прочерки и «н/д» — пусто
        ("Awal Dairy", None, None, None, None, None, None, None, None, None),
        ("Alba", None, None, None, None, None, None, None, None, None),
        # Несколько значений через «/» — первое
        ("Arabian Pipes", None, None, "info@arabian-pipes.com", "+966 11 8133333",
         "https://arabian-pipes.com", 1827, None, None, None),
        ("Villeroy & Boch", None, None, None, None, None, 1790, "6500", None, None),
        ("Hateks", None, "manufacturer", None, None, None, None, None, None, None),
        ("ITWorx", None, "service", None, None, None, None, None, None, None),
        ("Forte", None, None, None, None, None, None, None, польша, None),
        ("Szynaka", None, None, None, None, None, None, None, None, None),
        # Повтор без ИНН — та же компания, обновлена
        ("Comforty", None, None, "info@comforty.pl", None, None, 1995, None, None, None),
        # Без ИНН компанию с ИНН не трогает — новая
        ("Стройбаза Групп MCHJ", None, None, "other@example.com", None, None, None, None, None,
         None),
        # Пометки в заголовках («Название*», «Тип компании:») узнаются
        ("Ekol", None, "manufacturer", None, None, None, None, None, None, "İstanbul"),
    ]  # fmt: skip
    первая = снимок["компании"][0]

    assert первая["legal_name"] == "ООО «Стройбаза Групп»"
    # Двойные пробелы в описании схлопываются; slug — от первого названия
    assert первая["description"] == "Цемент и бетон"
    assert первая["slug"] == "ooo-stroibaza"
    assert all(
        (c["status"], c["verification_level"], c["source_note"]) == ("active", 0, ИСТОЧНИК)
        for c in снимок["компании"]
    )

    # Журнал: 14 созданий и 2 правки — от имени суперадмина
    assert [(з[0], з[2]) for з in снимок["журнал"]] == [
        # Подпись — название на момент записи
        ("created", "ООО «Стройбаза»"),
        *[("created", c["name"]) for c in снимок["компании"][1:12]],
        ("updated", "Comforty"),
        ("updated", "Стройбаза Групп MCHJ"),
        ("created", "Стройбаза Групп MCHJ"),
        ("created", "Ekol"),
    ]
    assert {(з[1], з[4]) for з in снимок["журнал"]} == {("companies", "superadmin")}
    # Поля правки в журнале — по порядку
    assert снимок["журнал"][13][3] == {
        "after": [
            ("name", "Стройбаза Групп MCHJ"),
            ("legal_name", "ООО «Стройбаза Групп»"),
            ("description", "Цемент и бетон"),
            ("email", "info@stroybaza.uz"),
        ],
        "before": [
            ("name", "ООО «Стройбаза»"),
            ("legal_name", None),
            ("description", None),
            ("email", None),
        ],
    }
    assert снимок["журнал"][12][3] == {
        "after": [("email", "info@comforty.pl"), ("founded_year", 1995)],
        "before": [("email", "comforty@comforty.pl"), ("founded_year", None)],
    }
    # Две строки отклонены проверкой — в отчёте с причиной
    assert [о["failed"] for о in отчёты if о["failed"]] == [
        [[2, "нет названия"]],
        [[2, "тип компании длиннее 32 знаков: очень длинный вид деятельности компании"]],
    ]
