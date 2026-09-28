# ruff: noqa: E501 — словари заголовков перенесены из PHP как есть
"""
Загрузка закупок из таблицы — копия App\\Filament\\Imports\\TenderImporter
(с App\\Support\\ImportLanguage, ImportCell и CatalogLookup), плюс
госзакупки.

Файл — Excel (.xlsx) или CSV, язык любой: заголовки столбцов, валюта,
«да» в публикации, месяц в дате узнаются на пяти языках площадки.
Категория и страна — названием или кодом. Повторная загрузка не плодит
дублей: закупка со ссылкой на источник находится по ней, без ссылки —
по заголовку и заказчику. Ячейка, которую загрузка не понимает,
пропускается, а строка загружается; строка без заголовка или с
неверной датой не загружается — в отчёте причина по каждой.

Госзакупка: галочка «все закупки в файле — госзакупки» или столбец
«Госзакупка» с «да»/«нет» в каждой строке. Без того и другого у новой
закупки признака нет, у найденной — остаётся прежним.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from django.db import connection, transaction
from django.utils import timezone

from savdex.tenders.models import CURRENCIES, Tender

# ── Словари (ImportLanguage) ─────────────────────────────────────────

HEADERS: dict[str, list[str]] = {
    "title": ["заголовок", "название", "наименование", "предмет закупки", "предмет контракта", "предмет",
        "наименование закупки", "название закупки", "тема", "лот", "тендер",
        "title", "tender", "tender title", "tender name", "name", "subject", "lot",
        "nomi", "sarlavha", "mavzu", "başlık", "konu", "标题", "名称"],
    "description": ["описание", "подробности", "детали", "текст", "условия",
        "description", "details", "text", "tavsif", "izoh", "batafsil", "açıklama", "detay", "描述", "说明"],
    "customer": ["заказчик", "заказчик закупки", "организатор", "организатор закупки", "организация",
        "покупатель", "клиент",
        "customer", "client", "buyer", "procuring entity", "issuer", "organization", "organisation",
        "buyurtmachi", "tashkilot", "mijoz", "müşteri", "kurum", "客户", "采购方"],
    "category_id": ["категория", "категории", "категория товара", "товарная группа", "раздел", "рубрика",
        "отрасль", "сфера", "группа", "товар", "продукция",
        "category", "categories", "section", "industry", "sector", "group", "product",
        "kategoriya", "turkum", "bo'lim", "soha", "yonalish", "kategori", "bölüm", "sektör", "类别", "分类"],
    "country_id": ["страна", "государство", "country", "state", "mamlakat", "davlat", "ülke", "国家"],
    "location": ["город", "регион", "область", "место", "адрес", "местоположение",
        "city", "region", "location", "address", "place",
        "shahar", "viloyat", "manzil", "joy", "şehir", "bölge", "adres", "城市", "地区"],
    "budget": ["бюджет", "сумма", "сумма контракта", "стоимость", "стоимость контракта", "цена",
        "начальная цена", "начальная (максимальная) цена", "нмцк",
        "budget", "amount", "price", "cost", "sum", "value", "estimated value", "contract value",
        "tender value", "byudjet", "summa", "narx", "qiymat", "bütçe", "tutar", "fiyat", "预算", "金额"],
    "currency": ["валюта", "currency", "valyuta", "pul birligi", "para birimi", "货币"],
    "deadline_at": ["прием заявок до", "срок подачи", "срок", "дедлайн", "дата окончания",
        "окончание приема", "дата окончания подачи", "окончание подачи заявок",
        "дата окончания приема заявок", "дата закрытия", "до",
        "deadline", "submission deadline", "bid deadline", "due date", "due", "end date",
        "closing date", "closing", "last date", "last date of submission",
        "muddat", "oxirgi muddat", "tugash sanasi", "son muddat", "bitiş tarihi", "son tarih", "截止日期"],
    "source_url": ["ссылка на источник", "ссылка на тендер", "ссылка", "источник",
        "url", "tender url", "tender link", "link", "source",
        "havola", "manba", "bağlantı", "kaynak", "链接", "来源"],
    "contact_name": ["контактное лицо", "контакт", "фио", "ответственный",
        "contact", "contact person", "aloqa shaxsi", "masul shaxs", "ilgili kişi", "yetkili", "联系人"],
    "contact_phone": ["телефон", "тел", "номер телефона",
        "phone", "telephone", "mobile", "telefon", "telefon raqami", "raqam", "电话"],
    "contact_email": ["почта", "эл. почта", "электронная почта", "мейл",
        "email", "e-mail", "mail", "pochta", "elektron pochta", "e-posta", "eposta", "邮箱", "电子邮件"],
    "status": ["опубликовать", "публиковать", "публикация", "статус",
        "publish", "published", "status", "nashr etish", "holat", "yayınla", "durum", "状态", "发布"],
    # Госзакупки (этап 5): в Filament такого столбца не было
    "is_government": ["госзакупка", "гос закупка", "гостендер", "гос тендер", "государственная закупка",
        "государственный тендер", "гос", "government", "government tender", "public procurement",
        "gov", "davlat xaridi", "davlat tenderi", "kamu ihalesi", "政府采购"],
}  # fmt: skip

_CURRENCIES = {
    "UZS": ["uzs", "сум", "сумы", "сумов", "сумм", "сўм", "so'm", "som", "soum"],
    "USD": ["usd", "$", "доллар", "доллары", "долларов", "долл", "дол", "dollar", "dollars",
        "dolar", "美元"],
    "EUR": ["eur", "€", "евро", "euro", "avro", "欧元"],
    "RUB": ["rub", "₽", "руб", "рубль", "рубли", "рублей", "ruble", "rubl", "卢布"],
    "CNY": ["cny", "¥", "юань", "юани", "юаней", "yuan", "rmb", "元", "人民币"],
    "TRY": ["try", "₺", "лира", "лиры", "лир", "lira", "tl", "türk lirası", "turk lirasi", "里拉",
        "土耳其里拉"],
    "KZT": ["kzt", "₸", "тенге", "tenge"],
}  # fmt: skip

_YES = ["да", "д", "yes", "y", "true", "1", "+", "ok", "on",
    "ha", "xa", "bor", "опубликовать", "публиковать", "опубликован",
    "publish", "published", "active", "evet", "var", "是", "发布"]  # fmt: skip

_MONTHS = {
    1: ["январ", "yanvar", "january", "jan", "ocak"],
    2: ["феврал", "fevral", "february", "feb", "şubat", "subat"],
    3: ["март", "mart", "march", "mar"],
    4: ["апрел", "aprel", "april", "apr", "nisan"],
    5: ["май", "мая", "мае", "may", "mayıs"],
    6: ["июн", "iyun", "june", "jun", "haziran"],
    7: ["июл", "iyul", "july", "jul", "temmuz"],
    8: ["август", "avgust", "august", "aug", "ağustos", "agustos"],
    9: ["сентябр", "sentabr", "sentyabr", "september", "sept", "sep", "eylül"],
    10: ["октябр", "oktabr", "oktyabr", "october", "oct", "ekim"],
    11: ["ноябр", "noyabr", "november", "nov", "kasım", "kasim"],
    12: ["декабр", "dekabr", "december", "dec", "aralık", "aralik"],
}

_MULTIPLIERS = [
    (1_000_000_000, ["млрд", "миллиард", "mlrd", "milliard", "billion"]),
    (1_000_000, ["млн", "миллион", "mln", "million"]),
    (1_000, ["тыс", "тысяч", "ming", "thousand"]),
]

_BLANKS = {
    "-", "--", "---", "—", "–", "−", ".", "?", "n/a", "na", "n.a.", "none", "null", "unknown",
    "нет", "нет данных", "не указан", "не указано", "неизвестно", "отсутствует",
    "yo'q", "yoq", "malumot yoq", "bilinmiyor", "yok", "无", "没有",
}  # fmt: skip

_NORMALIZE = str.maketrans(
    {
        "﻿": "", " ": " ", " ": " ", " ": " ", "​": "", "ё": "е",
        "«": "", "»": "", '"': "", "’": "'", "‘": "'", "ʼ": "'", "ʻ": "'", "`": "'", "´": "'",
    }
)  # fmt: skip


def normalize(value: Any) -> str:  # noqa: ANN401
    """ImportLanguage::normalize: нижний регистр, одни кавычки, одиночные пробелы."""
    text = str(value if value is not None else "").lower().translate(_NORMALIZE)

    return re.sub(r"\s+", " ", text).strip()


def currency(state: str | None) -> str:
    needle = normalize(state)

    if needle == "":
        return "UZS"

    for code, aliases in _CURRENCIES.items():
        if needle in aliases:
            return code

    return needle.upper()


def is_yes(state: str | None) -> bool:
    return normalize(state) in _YES


def amount(state: str | None) -> Decimal | None:
    """ImportLanguage::amount: «от 100 до 200 млн» — нижняя граница с множителем."""
    raw = normalize(state)
    multiplier = 1

    for value, words in _MULTIPLIERS:
        if any(word in raw for word in words):
            multiplier = value
            break

    digits = _digits(_lower_bound(raw))

    return None if digits is None else digits * multiplier


def _lower_bound(value: str) -> str:
    for part in re.split(r"\s*(?:—|–|-|\.{2,}|…|(?<![^\W\d_])(?:до|to)(?![^\W\d_]))\s*", value):
        if re.search(r"\d", part):
            return part

    return value


def _digits(value: str) -> Decimal | None:
    digits = re.sub(r"[^\d,.]", "", value)

    if digits == "" or not re.search(r"\d", digits):
        return None

    separator = max(digits.rfind(","), digits.rfind("."))
    tail = digits[separator + 1 :] if separator > 0 else ""

    if tail != "" and len(tail) != 3:
        digits = re.sub(r"[,.](?=[^,.]*[,.])", "", digits).replace(",", ".")
    else:
        digits = digits.replace(",", "").replace(".", "")

    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


_DATE_FORMATS = [
    ("%d.%m.%Y %H:%M", True),
    ("%d.%m.%Y", False),
    ("%Y-%m-%d %H:%M", True),
    ("%Y-%m-%d", False),
    ("%d/%m/%Y", False),
    ("%d-%m-%Y", False),
    ("%m/%d/%Y", False),
]


def parse_date(state: Any) -> datetime | str | None:  # noqa: ANN401
    """
    ImportLanguage::date: разобранная дата (без времени — конец дня) или
    строка как есть — её не пропустит проверка «date».
    """
    if isinstance(state, datetime):
        return state.replace(tzinfo=None)

    if isinstance(state, date):
        return datetime.combine(state, time(23, 59, 59))

    raw = str(state or "").strip()

    if raw == "":
        return None

    raw = _spell_out_date(raw) or raw

    for fmt, with_time in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue

        return parsed if with_time else parsed.replace(hour=23, minute=59, second=59)

    return raw


def _spell_out_date(value: str) -> str | None:
    needle = normalize(value)
    month = next(
        (
            number
            for number, names in _MONTHS.items()
            for word in needle.split(" ")
            for name in names
            if word.startswith(name)
        ),
        None,
    )

    if month is None:
        return None

    day = year = None

    for number in (int(n) for n in re.findall(r"\d+", needle)):
        if number > 31:
            year = year if year is not None else number
        else:
            day = day if day is not None else number

    if day is None or year is None:
        return None

    return f"{day:02d}.{month:02d}.{year:04d}"


# ── Ячейки (ImportCell) ─────────────────────────────────────────────

_SEPARATOR = re.compile(r"\s*[;|,]\s*|\s+/\s+|\r\n|[\n\r\x0b\x0c\x85  ]")


def text(value: Any, limit: int | None = None) -> str | None:  # noqa: ANN401
    raw = re.sub(r"\s+", " ", str(value if value is not None else "").replace(" ", " "))
    cell = raw.strip()

    if cell == "" or normalize(cell) in _BLANKS:
        return None

    if limit is not None and len(cell) > limit:
        cut = cell[:limit]
        space = cut.rfind(" ")
        cell = cut[:space] if space > limit / 2 else cut
        cell = cell.rstrip(" ,.;/-")

    return cell or None


def first(value: Any, limit: int | None = None) -> str | None:  # noqa: ANN401
    cell = text(value)

    if cell is None:
        return None

    for part in _SEPARATOR.split(cell):
        found = text(part, limit)

        if found is not None:
            return found

    return None


def email(value: Any, limit: int = 190) -> str | None:  # noqa: ANN401
    cell = text(value)

    if cell is None:
        return None

    for part in re.split(r"[\s/;|,]+", cell):
        part = part.strip(" <>()[]\"'")

        try:
            EmailValidator()(part)
        except ValidationError:
            continue

        if len(part) <= limit:
            return part.lower()

    return None


def phone(value: Any, limit: int = 40) -> str | None:  # noqa: ANN401
    found = first(value)

    return found if found is not None and len(found) <= limit else None


def url(value: Any) -> str | None:  # noqa: ANN401
    found = first(value, 255)

    try:
        URLValidator(schemes=["http", "https", "ftp", "ftps"])(found)
    except ValidationError:
        return None

    return found


# ── Справочники (CatalogLookup) ─────────────────────────────────────


def _rows(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])

        return list(cursor.fetchall())


def category_id(value: str | None) -> int | None:
    """Категория по названию на любом языке или slug; «Раздел → Подраздел» уточняет."""
    path = [
        p for p in (normalize(x) for x in re.split(r"\s*(?:→|->|>|/|\\|\|)\s*", value or "")) if p
    ]

    if not path:
        return None

    name, parent_name = path[-1], (path[-2] if len(path) > 1 else None)
    categories = _rows("select id, parent_id, slug from categories order by id")
    names: dict[int, set[str]] = {}

    for cid, label in _rows("select category_id, name from category_translations"):
        names.setdefault(cid, set()).add(normalize(label))

    def named(cid: int, slug: str, needle: str) -> bool:
        return normalize(slug) == needle or needle in names.get(cid, set())

    matches = [c for c in categories if named(c[0], c[2], name)]

    if len(matches) > 1 and parent_name is not None:
        by_id = {c[0]: c for c in categories}
        narrowed = [
            c
            for c in matches
            if c[1] in by_id and named(by_id[c[1]][0], by_id[c[1]][2], parent_name)
        ]
        matches = narrowed or matches

    return int(matches[0][0]) if matches else None


def country_id(value: str | None) -> int | None:
    """Страна по коду ISO («uz») или названию на любом языке."""
    needle = normalize(value)

    if needle == "":
        return None

    by_code = _rows("select id from countries where code = %s limit 1", [needle])

    if by_code:
        return int(by_code[0][0])

    for cid, label in _rows("select country_id, name from country_translations order by id"):
        if normalize(label) == needle:
            return int(cid)

    return None


# ── Файл ─────────────────────────────────────────────────────────────


def _cell(value: Any) -> Any:  # noqa: ANN401
    """Значение ячейки Excel: даты — как есть, целые числа — без «.0»."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        return str(value)

    return value


def read_table(name: str, content: bytes) -> list[dict[str, Any]]:
    """Строки таблицы: заголовок столбца → значение. Excel — первый лист."""
    if name.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = list(book.worksheets[0].iter_rows(values_only=True))
    else:
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = content.decode("cp1251")

        sample = decoded[:4096]

        try:
            dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        rows = [tuple(r) for r in csv.reader(io.StringIO(decoded), dialect)]

    if not rows:
        return []

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    table = []

    for row in rows[1:]:
        if all(v in (None, "") for v in row):
            continue

        table.append({headers[i]: _cell(v) for i, v in enumerate(row) if i < len(headers)})

    return table


def column_map(headers: Iterable[str]) -> dict[str, str]:
    """MapsHeadersInAnyLanguage: столбец площадки → заголовок файла, каждый заголовок — раз."""
    taken: set[str] = set()
    mapping: dict[str, str] = {}
    headers = list(headers)

    for column, aliases in HEADERS.items():
        for header in headers:
            if header not in taken and normalize(header) in aliases:
                mapping[column] = header
                taken.add(header)
                break

    return mapping


# ── Загрузка ─────────────────────────────────────────────────────────

_CASTS: dict[str, Callable[[Any], Any]] = {
    "title": lambda v: text(v, 190),
    "description": lambda v: text(v, 10000),
    "customer": lambda v: text(v, 190),
    "category_id": lambda v: category_id(first(v)),
    "country_id": lambda v: country_id(first(v)),
    "location": lambda v: text(v, 190),
    "budget": lambda v: amount(None if v is None else str(v)),
    "currency": lambda v: currency(None if v is None else str(v)),
    "deadline_at": parse_date,
    "source_url": url,
    "contact_name": lambda v: text(v, 190),
    "contact_phone": lambda v: phone(v, 40),
    "contact_email": email,
    "status": lambda v: "published" if is_yes(None if v is None else str(v)) else "draft",
    "is_government": lambda v: is_yes(None if v is None else str(v)),
}


def _problems(data: dict[str, Any]) -> list[str]:
    """Правила столбцов TenderImporter, которые могут не сойтись после приведения."""
    problems = []

    if "title" in data and not data["title"]:
        problems.append("нет заголовка")

    if isinstance(data.get("deadline_at"), str):
        problems.append(f"не дата в «Приём заявок до»: {data['deadline_at']}")

    if data.get("currency") and data["currency"] not in CURRENCIES:
        problems.append(f"неизвестная валюта: {data['currency']}")

    if data.get("budget") is not None and data["budget"] < 0:
        problems.append("бюджет меньше нуля")

    return problems


@dataclass
class Report:
    created: list[Tender] = field(default_factory=list)
    updated: list[Tender] = field(default_factory=list)
    unchanged: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)
    unknown_headers: list[str] = field(default_factory=list)


def _resolve(data: dict[str, Any]) -> Tender:
    """TenderImporter::resolveRecord: по ссылке, иначе по заголовку и заказчику."""
    source = (data.get("source_url") or "").strip()

    if source:
        return Tender.objects.filter(source_url=source).order_by("id").first() or Tender(
            source_url=source
        )

    title = (data.get("title") or "").strip()
    customer = (data.get("customer") or "").strip() or None

    if not title:
        return Tender()

    return Tender.objects.filter(title=title, customer=customer).order_by("id").first() or Tender(
        title=title, customer=customer
    )


def import_tenders(
    table: list[dict[str, Any]],
    *,
    author_id: int | None,
    all_government: bool,
    on_saved: Callable[[Tender, bool, dict[str, Any]], None],
) -> Report:
    """
    Загрузить строки. on_saved(закупка, создана ли, снимок до правки) —
    для журнала. Каждая строка — своя транзакция: сбой одной не губит
    остальные.
    """
    report = Report()
    mapping = column_map(table[0].keys() if table else [])
    report.unknown_headers = [
        h for h in (table[0].keys() if table else []) if h and h not in mapping.values()
    ]

    if all_government:
        mapping.pop("is_government", None)

    for number, row in enumerate(table, start=2):
        data = {column: _CASTS[column](row.get(header)) for column, header in mapping.items()}
        problems = _problems(data)

        if problems:
            report.failed.append((number, "; ".join(problems)))
            continue

        try:
            with transaction.atomic():
                _save_row(data, author_id, all_government, report, on_saved)
        except Exception as error:
            report.failed.append((number, f"не сохранилась: {error}"))

    return report


def _save_row(
    data: dict[str, Any],
    author_id: int | None,
    all_government: bool,
    report: Report,
    on_saved: Callable[[Tender, bool, dict[str, Any]], None],
) -> None:
    tender = _resolve(data)
    adding = tender.pk is None
    before = _snapshot(tender) if not adding else {}

    for column, value in data.items():
        if column == "deadline_at" and isinstance(value, datetime):
            value = value.replace(tzinfo=UTC)

        setattr(tender, column, value)

    if all_government:
        tender.is_government = True

    # beforeSave: автор, валюта и статус по умолчанию, дата публикации
    if adding:
        tender.author_id = author_id

    tender.currency = tender.currency or "UZS"
    tender.status = tender.status or "draft"

    if tender.status == "published" and tender.published_at is None:
        tender.published_at = timezone.now().replace(microsecond=0)

    if not adding and _snapshot(tender) == before:
        report.unchanged += 1

        return

    tender.save()
    (report.created if adding else report.updated).append(tender)
    on_saved(tender, adding, before)


def _snapshot(tender: Tender) -> dict[str, Any]:
    return {
        f.attname: getattr(tender, f.attname)
        for f in tender._meta.concrete_fields
        if f.attname not in ("updated_at", "search_text", "views_count")
    }
