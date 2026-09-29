"""
Загрузка компаний таблицей — перенос tests/Feature/Admin/CompanyImportTest.php.

Файл готовит заказчик, язык заголовков заранее не известен, ячейки набраны
руками: прочерк вместо пустоты, две почты через косую черту, «около 6500
(по публичным данным)» в численности. Строка из-за этого не теряется.

Сценарии PHP — одноимённые проверки ниже (каждый вызов import() у PHP —
отдельная таблица из одной строки, как очередь Filament). Сверх них:
отчёт по файлу (номера строк и причины, незнакомые столбцы, нет столбца
«Название»), поля новой компании и журнал — и сверка с настоящим
CompanyImporter: одни и те же строки через PHP и через Django дают одни
и те же компании и строки журнала.

Проверки с базой требуют PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from typing import Any

import pytest

from savdex.data import company_import
from savdex.data.company_import import column_map

from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база, сотрудник

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


@pytest.mark.skipif(
    shutil.which("php") is None or not (КОРЕНЬ / "vendor/autoload.php").exists(),
    reason="нет PHP с зависимостями",
)
def test_ячейки_как_у_php():
    """CompanyNameStyle и ImportCell::year/employees — те же ответы, что у PHP."""
    names = [
        "TOSHKENT MATRAS LYUKS", "ООО «СТРОЙБАЗА»", "O'ZBEK-TEST 3D AB.CD", "STRASSE ß",
        "Tashkent Matras", "12345", "  МЧЖ ХК QURILISH MCHJ ", "İSTANBUL ÇELİK", "X_Y É1A",
        "DŽEM OOO LLC JV", "",
    ]  # fmt: skip
    types = [
        "IT", "ИТ", "Айти", "IT-услуги", "IT services", "Логистика", "Üretim ve ihracat",
        "производство", "Import-export", "Дилер", " ", None,
    ]  # fmt: skip
    years = ["1827 / 2003", "осн. 1998 г.", "—", "1499", "2999", "3000 1990", "١٩٩٨ 2003"]
    staff = [
        "около 6500 (по публичным данным)", "50-100", "50 – 100", "1 000+", "не указано",
        "много", "12345678901234567", "очень много сотрудников в компании",
    ]  # fmt: skip
    вывод = subprocess.run(
        [
            "php",
            "-r",
            'require "vendor/autoload.php";'
            "use App\\Support\\CompanyNameStyle as S; use App\\Support\\ImportCell as C;"
            "$in = json_decode(stream_get_contents(STDIN), true);"
            "echo json_encode([array_map(fn ($s) => S::humanize($s), $in[0]),"
            " array_map(fn ($s) => S::typeKey($s), $in[1]),"
            " array_map(fn ($s) => C::year($s), $in[2]),"
            " array_map(fn ($s) => C::employees($s), $in[3])]);",
        ],
        cwd=КОРЕНЬ,
        input=json.dumps([names, types, years, staff]),
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(вывод.stdout) == [
        [company_import.humanize(s) for s in names],
        [company_import.type_key(s) for s in types],
        [company_import.year(s) for s in years],
        [company_import.employees(s) for s in staff],
    ]


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


# ── Сверка с настоящим CompanyImporter ──────────────────────────────

#: Строки всех сценариев PHP подряд, и сверх них — капс, пометки в заголовках
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
    """Компании и журнал без номеров и меток времени — у сторон они свои."""
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


@нужна_база
def test_как_у_php(админ):
    """Одни и те же строки через CompanyImporter и через Django — одно и то же."""
    _польша()
    задания = [[column_map(строка), строка] for строка in СВЕРКА]
    закодированные = base64.b64encode(json.dumps(задания).encode()).decode()

    php(
        f"$user = App\\Models\\User::find({админ}); auth()->setUser($user);"
        f"foreach (json_decode(base64_decode('{закодированные}'), true) as [$map, $row]) {{"
        " $import = Filament\\Actions\\Imports\\Models\\Import::create(['user_id' => $user->id,"
        " 'file_name' => 'companies.csv', 'file_path' => 'companies.csv',"
        " 'importer' => App\\Filament\\Imports\\CompanyImporter::class, 'total_rows' => 1]);"
        " try { (new App\\Filament\\Imports\\CompanyImporter($import, $map, []))($row); }"
        " catch (Illuminate\\Validation\\ValidationException $e) { } }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    у_php = _снимок()

    sql("delete from companies")
    sql("delete from admin_actions")
    отчёты = _импорт(админ, *СВЕРКА)
    у_django = _снимок()

    assert len(у_php["компании"]) == 14
    assert [з[0] for з in у_php["журнал"]].count("updated") == 2
    assert len(у_php["журнал"]) == 16
    assert у_django["компании"] == у_php["компании"]
    assert у_django["журнал"] == у_php["журнал"]
    # Две строки PHP отклонил проверкой — у Django они в отчёте с причиной
    assert [о["failed"] for о in отчёты if о["failed"]] == [
        [[2, "нет названия"]],
        [[2, "тип компании длиннее 32 знаков: очень длинный вид деятельности компании"]],
    ]
