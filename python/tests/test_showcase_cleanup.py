"""
ТЗ-01: чистка витрины — manage.py showcase_cleanup (savdex/data/showcase_cleanup.py).

Отчёт находит заявки площадки и «Куплю…» среди предложений, описания
заявок площадки с источником («Оригинальное объявление», «платному
доступу», «Агрору») и тестовые компании; apply применяет только номера,
оставшиеся в файлах после просмотра командой, и повтор ничего не портит.
Помощники разбора текста проверяются без базы.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from savdex.data import showcase_cleanup as sc

from .factories import компания, объявление
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

ПЕЧЬ = (
    "Куплю ротационную хлебопекарную печь Panemor. Требуемый объём: 1 шт. "
    "Контакты покупателя закрыты платформой и открываются продавцам по платному доступу. "
    "Оригинальное объявление: «Куплю печь. Срочно.»"
)


# ── Без базы ────────────────────────────────────────────────────────


def test_вырезает_предложения_с_источником():
    assert sc.clean(ПЕЧЬ) == "Куплю ротационную хлебопекарную печь Panemor. Требуемый объём: 1 шт."
    assert sc.clean("Нужна арматура.\nИз раздела «Спрос» площадки Агрору.ком.\nОбъём 5 т.") == (
        "Нужна арматура.\nОбъём 5 т."
    )
    assert sc.clean("求购钢筋。原始信息：某某。数量5吨。") == "求购钢筋。数量5吨。"
    assert sc.clean("Цемент М500. Дата публикации: 01.10.2026.") == "Цемент М500."
    # Обычный текст не меняется ни на знак
    assert (
        sc.clean("Цемент. Доставка по городу!  Звоните.") == "Цемент. Доставка по городу!  Звоните."
    )


def test_предложения_собираются_обратно():
    assert "".join(sc.sentences(ПЕЧЬ)) == ПЕЧЬ
    assert len(sc.sentences(ПЕЧЬ)) == 4


@pytest.mark.parametrize(
    ("title", "word"),
    [
        ("Куплю цемент", "куплю"),
        ("«Требуется» арматура", "требуется"),
        ("Buy cement", "buy"),
        ("WTB steel pipes", "wtb"),
        ("求购钢筋", "求购"),
        ("Sotib olaman un", "sotib olaman"),
        ("Buyer guide", None),
        ("Продаю цемент", None),
        ("Нужность", None),
    ],
)
def test_заголовок_заявки(title, word):
    assert sc.demand_title(title) == word


def test_случайные_буквы():
    assert sc.random_letters("rirjgijg")
    assert not sc.random_letters("OOO turk")
    assert not sc.random_letters("Oscar")
    assert not sc.random_letters("ООО «Ромашка»")


# ── С базой ─────────────────────────────────────────────────────────


def _команда(*args: str) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "showcase_cleanup", *args],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    )

    return out.stdout


def _строки(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@нужна_база
def test_отчёт_и_применение(tmp_path):
    свежая_база()
    служебная = компания(name="Anjir Group")
    настоящая = компания(name="ООО «Цемент-Сервис»")
    заявка = объявление(
        company_id=служебная,
        source="import",
        title="Куплю печь",
        description=ПЕЧЬ,
        description_i18n={"en": "Buying an oven. Original listing: «Oven». Volume: 1 pc."},
    )
    заявка_без_хвоста = объявление(company_id=служебная, source="import", title="Цемент оптом")
    куплю = объявление(company_id=настоящая, title="Куплю арматуру А500С")
    предложение = объявление(company_id=настоящая, title="Продаю арматуру")
    своё_служебной = объявление(company_id=служебная, title="Аренда склада")
    ромашка = компания(name="ооо ромашка")
    буквы = компания(name="rirjgijg")
    живая = компания(name="Kvrtz")
    объявление(company_id=живая, title="Кварц")

    отчёт = tmp_path / "cleanup"
    _команда("report", "--dir", str(отчёт))

    demand = {int(r["id"]) for r in _строки(отчёт / sc.DEMAND_FILE)}
    assert demand == {заявка, заявка_без_хвоста, куплю}
    assert предложение not in demand and своё_служебной not in demand

    тексты = _строки(отчёт / sc.DESCRIPTIONS_FILE)
    assert {(int(r["id"]), r["field"]) for r in тексты} == {
        (заявка, "description"),
        (заявка, "description.en"),
    }

    компании = {int(r["id"]): r["reason"] for r in _строки(отчёт / sc.COMPANIES_FILE)}
    assert set(компании) == {ромашка, буквы}  # у «Kvrtz» есть объявление — не трогаем

    # Команда вычеркнула «Куплю арматуру» — его apply не тронет
    строки = [r for r in _строки(отчёт / sc.DEMAND_FILE) if int(r["id"]) != куплю]
    with (отчёт / sc.DEMAND_FILE).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(строки[0]))
        writer.writeheader()
        writer.writerows(строки)

    assert "в запросы — 2" in _команда("apply", "--dir", str(отчёт), "--dry-run")
    assert sql("select count(*) from listings where type = 'demand'") == [(0,)]

    вывод = _команда("apply", "--dir", str(отчёт))
    assert "в запросы — 2, описаний — 1, скрыто компаний — 2" in вывод

    типы = dict(sql("select id, type from listings"))
    assert типы[заявка] == типы[заявка_без_хвоста] == "demand"
    assert типы[куплю] == "supply"

    [(описание, переводы, поиск)] = sql(
        "select description, description_i18n, search_text from listings where id = %s", [заявка]
    )
    assert описание == "Куплю ротационную хлебопекарную печь Panemor. Требуемый объём: 1 шт."
    assert переводы == {"en": "Buying an oven. Volume: 1 pc."}
    assert "оригинальное" not in поиск and "доступу" not in поиск

    статусы = dict(sql("select id, status from companies"))
    assert статусы[ромашка] == статусы[буквы] == "hidden"
    assert статусы[живая] == "active"

    # Повтор: всё уже сделано
    assert "в запросы — 0, описаний — 0, скрыто компаний — 0" in _команда(
        "apply", "--dir", str(отчёт)
    )
