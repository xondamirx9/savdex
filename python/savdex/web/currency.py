"""
Курсы валют ЦБ — чтение того, что запомнил Laravel (App\\Support\\CurrencyRate).

Таблицу курсов выгружает с cbu.uz Laravel: планировщик обновляет её
каждые четыре часа и кладёт в кэш на сутки, последнюю удачную — на
месяц про запас. На боевом кэш файловый (CACHE_STORE=file, render.yaml),
в той же службе, поэтому Django читает те же файлы и видит тот же курс.

С шага 71 таблицу обновляет расписание Django (refresh ниже, задача
cbu_rates каждые четыре часа) — в тот же кэш тем же форматом, поэтому
Laravel, пока жив, видит те же курсы. Страница к ЦБ не ходит: если
основной таблицы нет (ЦБ недоступен сутки, кэш не файловый), она берёт то
же, что Laravel взял бы при сбое ЦБ, — последнюю удачную таблицу, затем
курс доллара под старым ключом, затем запасной курс.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from pathlib import Path
from typing import Any

from django.conf import settings

#: CurrencyRate::URL
URL = "https://cbu.uz/oz/arkhiv-kursov-valyut/json/"

CACHE_KEY = "cbu.rates"
FALLBACK_KEY = "cbu.rates.last"
LEGACY_USD_KEY = "cbu.rate.usd.last"

#: CurrencyRate::DEFAULT_USD
DEFAULT_USD = 12_800.0


def _cache_path(key: str) -> Path:
    """FileStore::path: sha1 ключа, два уровня папок по два знака."""
    digest = hashlib.sha1(key.encode()).hexdigest()

    return (
        Path(settings.LARAVEL_ROOT)
        / "storage/framework/cache/data"
        / digest[:2]
        / digest[2:4]
        / digest
    )


def cached(key: str) -> object:
    """Cache::get() файлового кэша Laravel; нет, истёк или не файловый — None."""
    if os.environ.get("CACHE_STORE", "database") != "file":
        return None

    try:
        contents = _cache_path(key).read_bytes()
    except OSError:
        return None

    try:
        if time.time() >= int(contents[:10]):
            return None

        return unserialize(contents[10:])
    except ValueError:
        return None


def unserialize(data: bytes) -> object:
    """unserialize() PHP для скаляров и массивов — всего, что лежит в кэше курсов."""
    value, end = _parse(data, 0)

    if end != len(data):
        raise ValueError("лишние байты после значения")

    return value


def _until(data: bytes, pos: int, stop: bytes) -> tuple[bytes, int]:
    end = data.index(stop, pos)

    return data[pos:end], end + 1


def _parse(data: bytes, pos: int) -> tuple[object, int]:
    kind = data[pos : pos + 2]

    if data[pos : pos + 2] == b"N;":
        return None, pos + 2

    if kind == b"b:":
        raw, pos = _until(data, pos + 2, b";")

        return raw == b"1", pos

    if kind == b"i:":
        raw, pos = _until(data, pos + 2, b";")

        return int(raw), pos

    if kind == b"d:":
        raw, pos = _until(data, pos + 2, b";")
        text = raw.decode()

        return {"INF": math.inf, "-INF": -math.inf, "NAN": math.nan}.get(text) or float(text), pos

    if kind == b"s:":
        raw, pos = _until(data, pos + 2, b":")
        length = int(raw)
        start = pos + 1  # открывающая кавычка
        text = data[start : start + length].decode()

        if data[start + length : start + length + 2] != b'";':
            raise ValueError("строка не закрыта")

        return text, start + length + 2

    if kind == b"a:":
        raw, pos = _until(data, pos + 2, b":")
        count = int(raw)

        if data[pos : pos + 1] != b"{":
            raise ValueError("нет начала массива")

        pos += 1
        result: dict[object, object] = {}

        for _ in range(count):
            key, pos = _parse(data, pos)
            result[key], pos = _parse(data, pos)

        if data[pos : pos + 1] != b"}":
            raise ValueError("нет конца массива")

        return result, pos + 1

    raise ValueError(f"неизвестный тип {kind!r}")


class CurrencyRate:
    """Курсы на время запроса — как экземпляр CurrencyRate у Laravel."""

    def __init__(self) -> None:
        self._table: dict[str, float] | None = None

    def usd(self) -> float:
        """Курс доллара для кассы — известен всегда."""
        return self.rate("USD") or DEFAULT_USD

    def rate(self, code: str) -> float | None:
        if code == "UZS":
            return 1.0

        return self.rates().get(code)

    def rates(self) -> dict[str, float]:
        if self._table is None:
            self._table = _load()

        return self._table


def _table(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None

    return {str(k): float(v) for k, v in value.items() if isinstance(v, int | float)}


def _load() -> dict[str, float]:
    """CurrencyRate::load без похода в ЦБ."""
    fresh = _table(cached(CACHE_KEY))

    if fresh is not None:
        return fresh

    last = _table(cached(FALLBACK_KEY)) or {}
    legacy_usd = _number(cached(LEGACY_USD_KEY))

    if not last and legacy_usd > 0:
        last = {"USD": legacy_usd}

    return last


def _number(value: object) -> float:
    """(float) у PHP для того, что лежит в кэше: не число — ноль."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0

    try:
        return float(value)
    except ValueError:
        return 0.0


def php_round(value: float) -> float:
    """round() PHP: половина — от нуля, а не к чётному, как у Python."""
    return math.copysign(math.floor(abs(value) + 0.5), value)


def fetch(client: Any = None) -> dict[str, float] | None:  # noqa: ANN401
    """
    CurrencyRate::fetch: таблица ЦБ — код → сумов за единицу (курс
    некоторых валют ЦБ даёт за 10 или 100 единиц). Сбой — None.
    """
    import logging

    import httpx

    log = logging.getLogger("savdex.currency")

    try:
        own = client is None
        client = client or httpx.Client(timeout=5)

        try:
            response = client.get(URL)
        finally:
            if own:
                client.close()

        if response.is_success:
            rates: dict[str, float] = {}
            rows = response.json()

            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue

                code = str(row.get("Ccy") or "").strip().upper()
                nominal = _number(row.get("Nominal", 1)) or 1.0
                rate = _number(row.get("Rate", 0)) / nominal

                if code != "" and rate > 0:
                    rates[code] = rate

            if rates:
                return rates

        log.warning("Курс ЦБ: неожиданный ответ, код %s", response.status_code)
    except Exception as error:
        log.warning("Курс ЦБ недоступен: %s", error)

    return None


def refresh(client: Any = None) -> bool:  # noqa: ANN401
    """
    CurrencyRate::refresh: свежая таблица — в кэш на сутки и последней
    удачной на месяц (now()->addMonth()). ЦБ недоступен — кэш не трогаем.
    """
    from datetime import UTC, datetime

    from savdex import laravel_cache

    fresh = fetch(client)

    if fresh is None:
        return False

    now = datetime.now(UTC)
    month = _add_month(now)
    table: dict[str | int, laravel_cache.Value] = {k: v for k, v in fresh.items()}
    laravel_cache.put(CACHE_KEY, table, 86400)
    laravel_cache.put(FALLBACK_KEY, table, int((month - now).total_seconds()))

    return True


def _add_month(moment: Any) -> Any:  # noqa: ANN401
    """Carbon::addMonth с переполнением: 31 января + месяц — 3 марта."""
    from datetime import timedelta

    year, month = (moment.year, moment.month + 1) if moment.month < 12 else (moment.year + 1, 1)
    first = moment.replace(year=year, month=month, day=1)

    return first + timedelta(days=moment.day - 1)
