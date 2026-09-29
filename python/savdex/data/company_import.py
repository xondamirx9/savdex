# ruff: noqa: E501 — словари заголовков перенесены из PHP как есть
"""
Загрузка компаний из таблицы — копия App\\Filament\\Imports\\CompanyImporter
(с MapsHeadersInAnyLanguage, ImportLanguage::COMPANY_HEADERS, ImportCell
и CompanyNameStyle). Общие части (normalize, matches, ячейки, страна,
чтение файла) — из savdex.tenders.importer.

Очереди у Django нет: загрузка идёт в запросе и возвращает отчёт —
новые, обновлённые, без изменений и причина по каждой незагруженной
строке с её номером, как в Excel.

Сопоставление — по ИНН, а не по названию: два разных ИНН — два юрлица
даже при одинаковом названии. Без ИНН компания находится по названию,
но только среди компаний без ИНН: повторная загрузка того же файла
не удваивает иностранных поставщиков и не подменяет компанию с ИНН.

Столбцы узнаются так, как их сопоставил бы Filament без правки в окне
импорта: сначала точное совпадение без учёта регистра с подписью,
именем столбца или синонимом (ImportAction), затем незанятое — по
словарю синонимов на пяти языках с пометками вроде «Название*»
(MapsHeadersInAnyLanguage). Одно отличие: синоним страны у PHP лежит под
ключом «country», а столбец называется country_id, и второй шаг страну
не находил; здесь находит.

Новая компания — активна, без проверки и с пометкой «данные из открытых
источников» (beforeSave); адрес из названия и search_text — как события
модели Company. Запись — как Eloquent: вставляются только заданные поля,
у найденной — только изменившиеся; у администратора — строки журнала
«создано» и «изменено» (AuditObserver).

Сверка с PHP — tests/test_company_import.py.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest

from savdex.data.emblem import staff_context
from savdex.guards import allowed_writes
from savdex.tenders.importer import country_id, email, first, matches, normalize, phone, text
from savdex.web import eloquent
from savdex.web.cabinet import _rows
from savdex.web.company_profile_actions import CASTS, _search_text, _slug
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context

# ── Словарь заголовков (ImportLanguage::COMPANY_HEADERS) ─────────────

COMPANY_HEADERS: dict[str, list[str]] = {
    "tin": ["инн", "налоговый номер", "стир", "tin", "inn", "stir", "tax id", "tax number",
        "vergi no", "vergi numarası", "税号"],
    "name": ["название", "наименование", "компания", "название компании", "организация", "фирма",
        "name", "company", "company name", "firm",
        "nomi", "kompaniya", "kompaniya nomi", "tashkilot", "şirket", "firma", "unvan", "公司", "名称"],
    "legal_name": ["юридическое название", "юр. название", "полное название", "официальное название",
        "legal name", "full name", "official name",
        "yuridik nomi", "rasmiy nomi", "toliq nomi", "resmi unvan", "ticaret unvanı", "法定名称"],
    "type": ["тип компании", "тип", "вид компании", "вид деятельности", "роль",
        "type", "company type", "kind", "role",
        "turi", "kompaniya turi", "faoliyat turi", "tür", "şirket türü", "类型"],
    "address": ["адрес", "юридический адрес", "фактический адрес", "address", "manzil", "adres", "地址"],
    "phone": ["телефон", "тел", "номер телефона", "контактный телефон",
        "phone", "telephone", "mobile", "telefon", "telefon raqami", "电话"],
    "email": ["почта", "эл. почта", "электронная почта", "мейл",
        "email", "e-mail", "mail", "pochta", "elektron pochta", "e-posta", "eposta", "邮箱", "电子邮件"],
    "website": ["сайт", "веб-сайт", "веб сайт", "вебсайт", "адрес сайта",
        "website", "web site", "site", "url", "web",
        "sayt", "veb-sayt", "web sitesi", "internet sitesi", "网站"],
    "description": ["описание", "о компании", "деятельность", "чем занимается",
        "description", "about", "activity", "tavsif", "faoliyat", "açıklama", "hakkında", "描述"],
    "founded_year": ["год основания", "основана", "основан", "год",
        "founded", "founded year", "year", "established",
        "tashkil etilgan yil", "tashkil topgan yil", "yil", "kuruluş yılı", "成立年份"],
    "employees_range": ["сотрудников", "количество сотрудников", "численность", "штат", "персонал",
        "employees", "staff", "headcount", "employees count",
        "xodimlar", "xodimlar soni", "çalışan sayısı", "personel", "员工"],
    "country": ["страна", "страна компании", "country", "davlat", "mamlakat", "ülke", "国家"],
}  # fmt: skip

#: Ключ словаря → столбец таблицы companies (у PHP страна — «country»)
_ALIAS_COLUMN = {"country": "country_id"}

#: CompanyImporter::beforeSave — пометка у карточки, которую завела площадка
SOURCE_NOTE = "Данные компании взяты из открытых источников."

# ── Название и тип (CompanyNameStyle) ────────────────────────────────

#: Юридические аббревиатуры, которым капс положен (кириллица и латиница вперемешку, как в PHP)
KEEP_UPPER = frozenset(
    {"ООО", "OOO", "СП", "ИП", "УП", "АЖ", "МЧЖ", "MCHJ", "QMJ", "XK", "ХК", "JV", "LLC"}
)

#: Корни типов компаний на пяти языках. Порядок важен: «производство
#: и экспорт» — производитель, поэтому производство раньше торговли
TYPE_STEMS: dict[str, list[str]] = {
    "manufacturer": ["производ", "изготов", "завод", "фабрик", "manufact", "factory", "producer",
        "ishlab chiqar", "üretim", "üretici", "imalat", "制造", "生产"],
    "distributor": ["дистриб", "distrib", "дилер", "dealer", "bayi", "经销"],
    "importer": ["импорт", "import", "ithalat", "进口"],
    "trader": ["торгов", "экспорт", "trade", "trading", "export", "savdo", "eksport",
        "ticaret", "ihracat", "贸易", "出口"],
    "service": ["услуг", "сервис", "service", "xizmat", "hizmet", "服务"],
}  # fmt: skip

#: Точные значения «it»: коротко и внутри слов встречается слишком часто
_IT = frozenset({"it", "ит", "айти", "it-услуги", "it services"})

#: trim() у PHP без второго аргумента
_PHP_TRIM = " \t\n\r\0\x0b"

#: Знаки, «прозрачные» для регистра (Word_Break MidLetter, MidNumLet,
#: Single_Quote): после «O'» у PHP идёт строчная — «O'zbek»
_CASE_IGNORABLE = frozenset(
    "'.:\u00b7\u0387\u055f\u05f4\u2018\u2019\u2024\u2027\ufe13\ufe52\ufe55\uff07\uff0e\uff1a"
)


def _ignorable(char: str) -> bool:
    return char in _CASE_IGNORABLE or unicodedata.category(char) in ("Mn", "Me", "Cf", "Lm", "Sk")


def _cased(char: str) -> bool:
    return char.islower() or char.isupper() or unicodedata.category(char) == "Lt"


def _title(value: str) -> str:
    """
    mb_convert_case(MB_CASE_TITLE) у PHP 8: заглавная — после любого знака,
    у которого нет регистра (пробел, цифра, дефис, «_»), кроме «прозрачных»
    (апостроф, точка, двоеточие). str.title() у Python делает «O'Zbek».
    """
    out = []
    title_mode = True

    for char in value:
        out.append(char.title() if title_mode else char.lower())

        if not _ignorable(char):
            title_mode = not _cased(char)

    return "".join(out)


def humanize(name: str) -> str:
    """
    CompanyNameStyle::humanize: название капсом — «Каждое Слово С Заглавной»,
    юридические аббревиатуры остаются заглавными; смешанный регистр не трогается.
    """
    trimmed = name.strip(_PHP_TRIM)

    if (
        trimmed == ""
        or trimmed != trimmed.upper()
        or not any(unicodedata.category(c).startswith("L") for c in trimmed)
    ):
        return trimmed

    words = _title(trimmed.lower()).split(" ")

    return " ".join(w.upper() if w.upper() in KEEP_UPPER else w for w in words)


def type_key(raw: str | None) -> str | None:
    """
    CompanyNameStyle::typeKey: тип по корню слова на любом языке; совсем
    незнакомое значение остаётся как есть (строчными).
    """
    value = (raw or "").strip(_PHP_TRIM).lower()

    if value == "":
        return None

    if value in _IT:
        return "service"

    for code, stems in TYPE_STEMS.items():
        if any(stem in value for stem in stems):
            return code

    return value


#: Справочник типов: нормализованный код, нормализованные названия, код
CompanyTypes = list[tuple[str, set[str], str]]


def company_types() -> CompanyTypes:
    """Типы компаний с названиями на всех языках — раз на загрузку."""
    names: dict[int, set[str]] = {}

    for row in _rows("select company_type_id, name from company_type_translations order by id"):
        names.setdefault(row["company_type_id"], set()).add(normalize(row["name"]))

    return [
        (normalize(t["code"]), names.get(t["id"], set()), str(t["code"]))
        for t in _rows("select id, code from company_types order by id")
    ]


def company_type(state: str | None, types: CompanyTypes) -> str | None:
    """
    CompanyImporter::type: код из справочника по коду или названию на любом
    языке («Производитель», «Ishlab chiqaruvchi»), иначе — по корню слова.
    """
    needle = normalize(state)

    if needle == "":
        return None

    for code_key, names, code in types:
        if code_key == needle or needle in names:
            return code

    return type_key(state)


# ── Ячейки (ImportCell::year, ::employees) ──────────────────────────


def year(value: Any) -> int | None:  # noqa: ANN401
    """«1827 / 2003» — 1827, «осн. 1998 г.» — 1998; от 1500 до нынешнего года."""
    cell = text(value)

    if cell is None:
        return None

    # Цифры не ASCII у PHP (int) превращает в 0 — такой год не проходит
    for candidate in re.findall(r"[0-9]{4}", cell):
        found = int(candidate)

        if 1500 <= found <= datetime.now(UTC).year:
            return found

    return None


def employees(value: Any, limit: int = 16) -> str | None:  # noqa: ANN401
    """«50-100», «1000+», «около 6500 (по публичным данным)» — «6500»."""
    cell = text(value)

    if cell is None:
        return None

    digits = cell.replace(" ", "").replace(" ", "")
    found = re.search(r"\d+\s*[-–—]\s*\d+\+?|\d+\+|\d+", digits)

    if found is not None:
        span = found.group(0).replace("–", "-").replace("—", "-")

        if len(span) <= limit:
            return span

    return text(cell, limit)


# ── Столбцы ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Column:
    #: Столбец companies (ImportColumn::make)
    name: str
    #: Подпись и заголовок образца (label, exampleHeader)
    label: str
    #: Подсказка на странице загрузки
    hint: str

    @property
    def aliases(self) -> list[str]:
        key = next((k for k, c in _ALIAS_COLUMN.items() if c == self.name), self.name)

        return COMPANY_HEADERS[key]


_COLUMNS = (
    _Column("tin", "ИНН", "по нему повторная загрузка находит компанию; прочерк — «ИНН нет»"),
    _Column(
        "name",
        "Название",
        "обязательно; без ИНН компания находится по названию среди компаний без ИНН; капс — «Каждое Слово С Заглавной»",
    ),
    _Column("legal_name", "Юридическое название", ""),
    _Column(
        "type",
        "Тип компании",
        "производитель, дистрибьютор, импортёр, торговая компания, услуги — на любом языке; незнакомое сохраняется как есть",
    ),
    _Column("address", "Адрес", ""),
    _Column("phone", "Телефон", "из нескольких через «/» или «;» берётся первый"),
    _Column("email", "Почта", "из нескольких берётся первая"),
    _Column("website", "Сайт", ""),
    _Column("description", "Описание", ""),
    _Column("founded_year", "Год основания", "от 1500 до нынешнего; «1827 / 2003» — первый"),
    _Column("employees_range", "Сотрудников", "50-100, 1000+; «около 6500 (…)» — 6500"),
    _Column("country_id", "Страна", "название на любом языке или код (uz); незнакомая — пусто"),
)

#: Столбцы для страницы загрузки: заголовок и подсказка
COLUMNS: list[tuple[str, str]] = [(c.label, c.hint) for c in _COLUMNS]

#: requiredMapping: без этого столбца Filament не начинал загрузку
REQUIRED = ("name",)


def column_map(headers: Iterable[str]) -> dict[str, str]:
    """
    Столбец площадки → заголовок файла.

    Сначала — как окно импорта Filament (ImportAction): первый заголовок,
    который без учёта регистра равен подписи, имени столбца или синониму.
    Затем то, что осталось пустым, — MapsHeadersInAnyLanguage: синонимы
    с нормализацией и без пометок, каждый заголовок — раз.
    """
    headers = [h for h in headers if h]
    # array_combine: из двух одинаковых без регистра побеждает последний
    by_lower = {h.lower(): h for h in headers}
    mapping: dict[str, str] = {}

    for column in _COLUMNS:
        guesses = {column.label.lower(), column.name.lower(), *(a.lower() for a in column.aliases)}
        found = next((h for h in headers if h.lower() in guesses), None)

        if found is not None:
            mapping[column.name] = by_lower[found.lower()]

    taken = set(mapping.values())

    for key, aliases in COMPANY_HEADERS.items():
        name = _ALIAS_COLUMN.get(key, key)

        if name in mapping:
            continue

        for header in headers:
            if header not in taken and matches(header, aliases):
                mapping[name] = header
                taken.add(header)
                break

    return mapping


def _state(value: Any) -> Any:  # noqa: ANN401
    """ImportColumn::castStateItem: строка без пробелов по краям, пустое — None."""
    if isinstance(value, str):
        value = value.strip(_PHP_TRIM)

    return None if value is None or value == "" else value


def _casts(types: CompanyTypes) -> dict[str, Callable[[Any], Any]]:
    """castStateUsing столбцов CompanyImporter."""
    return {
        # Прочерк в ИНН — «нет ИНН», а не общий номер, по которому
        # иностранные компании слиплись бы в одну
        "tin": lambda v: first(v, 20),
        # Госреестр пишет капсом — на витрине это выглядит криком
        "name": lambda v: humanize(text(v, 190) or ""),
        "legal_name": lambda v: text(v, 255),
        # «производство, экспорт, торговля» — первое: тип у компании один
        "type": lambda v: company_type(first(v), types),
        "address": lambda v: text(v, 255),
        "phone": lambda v: phone(v, 32),
        "email": lambda v: email(v, 190),
        "website": lambda v: first(v, 190),
        "description": lambda v: text(v, 5000),
        "founded_year": year,
        "employees_range": employees,
        "country_id": lambda v: country_id(first(v)),
    }


def _problems(data: dict[str, Any]) -> list[str]:
    """Правила столбцов, которые могут не сойтись после приведения ячеек."""
    problems = []

    if "name" in data:
        if not data["name"]:
            problems.append("нет названия")
        elif len(data["name"]) > 190:
            problems.append("название длиннее 190 знаков")

    if data.get("type") is not None and len(data["type"]) > 32:
        problems.append(f"тип компании длиннее 32 знаков: {data['type']}")

    return problems


# ── Загрузка ─────────────────────────────────────────────────────────


@dataclass
class Report:
    """Итог загрузки: номера компаний, причины по строкам (номер — как в Excel)."""

    created: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)
    unchanged: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)
    unknown_headers: list[str] = field(default_factory=list)
    #: Обязательные столбцы, которых в файле нет, — тогда не загружено ничего
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """CompanyImporter::getCompletedNotificationBody — для сообщения после загрузки."""
        if self.missing:
            return "В файле нет столбца " + ", ".join(f"«{m}»" for m in self.missing) + "."

        def number(n: int) -> str:
            return f"{n:,}".replace(",", " ")

        body = (
            "Импорт завершён. Обработано строк: "
            f"{number(len(self.created) + len(self.updated) + self.unchanged)}."
        )

        if self.failed:
            body += (
                f" Не удалось импортировать: {number(len(self.failed))}."
                " Причина по каждой строке — в отчёте ниже."
            )

        return body


def import_companies(
    table: list[dict[str, Any]],
    *,
    admin_id: int,
    request: HttpRequest | None = None,
) -> Report:
    """
    Загрузить строки таблицы (read_table из savdex.tenders.importer).

    admin_id — кто загружает: строки журнала «создано» и «изменено» от
    его имени; request — адрес в журнале (без него пусто). Каждая строка —
    своя транзакция: сбой одной не губит остальные.
    """
    report = Report()
    headers = list(table[0].keys()) if table else []
    mapping = column_map(headers)
    report.unknown_headers = [h for h in headers if h and h not in mapping.values()]
    report.missing = [c.label for c in _COLUMNS if c.name in REQUIRED and c.name not in mapping]

    if not table or report.missing:
        return report

    ctx = staff_context(admin_id, request)
    casts = _casts(company_types())

    for number, row in enumerate(table, start=2):
        data = {
            column.name: casts[column.name](_state(row.get(mapping[column.name])))
            for column in _COLUMNS
            if column.name in mapping
        }
        problems = _problems(data)

        if problems:
            report.failed.append((number, "; ".join(problems)))
            continue

        try:
            with transaction.atomic():
                _save_row(ctx, data, report)
        except Exception as error:
            report.failed.append((number, f"не сохранилась: {error}"))

    return report


def _resolve(data: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    CompanyImporter::resolveRecord: найденная строка компании или None и
    поля новой (firstOrNew по ИНН задаёт ИНН первым).
    """
    tin = str(data.get("tin") or "").strip(_PHP_TRIM)

    if tin:
        rows = _rows(
            "select * from companies where tin = %s and deleted_at is null order by id limit 1",
            [tin],
        )

        return (rows[0] if rows else None), {"tin": tin}

    # Без ИНН — по названию, но только среди компаний без ИНН: у
    # компании с ИНН опознание надёжнее, и подменять её нельзя
    name = str(data.get("name") or "").strip(_PHP_TRIM)

    if not name:
        return None, {}

    rows = _rows(
        "select * from companies where tin is null and name = %s and deleted_at is null "
        "order by id limit 1",
        [name],
    )

    return (rows[0] if rows else None), {}


def _save_row(ctx: Context, data: dict[str, Any], report: Report) -> None:
    company, preset = _resolve(data)

    if company is not None:
        changed = eloquent.save(
            ctx,
            "companies",
            company,
            data,
            section="companies",
            model="Company",
            saving=_search_text,
            casts=CASTS,
        )

        if changed:
            report.updated.append(int(company["id"]))
        else:
            report.unchanged += 1

        return

    report.created.append(_insert(ctx, {**preset, **data}))


def _insert(ctx: Context, fields: dict[str, Any]) -> int:
    """
    Новая компания, как Eloquent: заданные поля, beforeSave (активна, без
    проверки, пометка об источнике), saving (search_text), creating (адрес),
    метки времени; у администратора — строка журнала «создано».
    """
    row: dict[str, Any] = {
        **fields,
        "status": "active",
        "verification_level": 0,
        "source_note": SOURCE_NOTE,
    }
    row.update(_search_text(row))
    row["slug"] = _slug(str(row.get("name") or ""))
    now = _stamp(eloquent.now())
    row.update(updated_at=now, created_at=now)
    columns = list(row)

    with allowed_writes("companies"), connection.cursor() as cursor:
        cursor.execute(
            f"insert into companies ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [eloquent._written(CASTS.get(c), row[c]) for c in columns],
        )
        company_id = int(cursor.fetchone()[0])

    row["id"] = company_id
    after = {c: eloquent._written(CASTS.get(c), v) for c, v in row.items()}
    eloquent.journal(ctx, "created", "companies", "Company", row, {"after": after})

    return company_id
