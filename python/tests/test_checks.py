"""
Проверка базы: разбор ошибок и сборка отчёта.

Части, которым база не нужна. То, что требует настоящего PostgreSQL, —
в test_check_postgres.py.
"""

from __future__ import annotations

import pytest

from savdex.checks import NOTE, OK, PROBLEM, Report, reason


class TestПонятнаяПричина:
    """
    Тексты подсказок те же, что у PHP-версии.

    Человек, который однажды читал подсказку про Internal Database URL,
    не должен разбираться заново из-за того, что половина площадки
    переехала на другой язык.
    """

    @pytest.mark.parametrize(
        ("message", "фрагмент"),
        [
            ('FATAL: password authentication failed for user "savdex"', "Пароль в адресе"),
            ("could not translate host name to address", "не резолвится"),
            ("Name or service not known", "не резолвится"),
            ("connection to server failed: Connection refused", "не отвечает"),
            ("connection timeout expired", "не отвечает"),
            ('FATAL: database "savdex" does not exist', "Базы с таким именем нет"),
            ("permission denied for table companies", "не хватает прав"),
        ],
    )
    def test_известная_ошибка_объясняется(self, message, фрагмент):
        assert фрагмент in reason(message)

    def test_незнакомая_ошибка_обрезается(self):
        """Простыня драйвера в отчёте не помещается и ничего не объясняет."""
        assert len(reason("ы" * 500)) == 160

    def test_незнакомая_ошибка_не_теряется(self):
        assert reason("что-то невиданное") == "что-то невиданное"


class TestОтчёт:
    def test_хорошее_не_мешает_работать(self):
        report = Report()
        report.ok("Схема", "75 таблиц")

        assert report.blocked is False
        assert report.advice == []
        assert report.rows == [(OK, "Схема", "75 таблиц")]

    def test_замечание_даёт_совет_но_не_блокирует(self):
        report = Report()
        report.note("Данные", "база пуста", "Проверьте, туда ли смотрит Django.")

        assert report.blocked is False
        assert report.advice == ["Проверьте, туда ли смотрит Django."]
        assert report.rows[0][0] == NOTE

    def test_поломка_блокирует(self):
        report = Report()
        report.problem("Соединение", "не установлено", "Проверьте адрес.")

        assert report.blocked is True
        assert report.rows[0][0] == PROBLEM

    def test_одна_поломка_среди_хорошего_всё_равно_блокирует(self):
        """Иначе отчёт заканчивается словами «всё в порядке» при сломанной базе."""
        report = Report()
        report.ok("Схема", "75 таблиц")
        report.problem("Права", "нет", "Выдайте права.")
        report.ok("Данные", "350 компаний")

        assert report.blocked is True
