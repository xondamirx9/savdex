"""
Предохранители переноса.

Проверяется не «функция возвращает значение», а обещание: пока таблица
принадлежит Laravel, запись в неё из Django не проходит. На это
обещание опирается весь план переноса, поэтому оно закрыто тестами
первым, до единой строки кода площадки.
"""

from __future__ import annotations

import pytest
from django.db import connection

from savdex import guards
from savdex.guards import MigrationFromDjangoError, WriteToForeignTableError


class TestРазборЗапроса:
    @pytest.mark.parametrize(
        ("sql", "expected"),
        [
            ("insert into listings (id) values (1)", "listings"),
            ('INSERT INTO "companies" (id) VALUES (1)', "companies"),
            ("update reviews set rating = 5", "reviews"),
            ("UPDATE ONLY payments SET status = 'paid'", "payments"),
            ("delete from banner_images where id = 1", "banner_images"),
            ("truncate table search_hits", "search_hits"),
            ("insert into public.wallets (id) values (1)", "wallets"),
        ],
    )
    def test_таблица_находится(self, sql, expected):
        assert guards.table_of(sql) == expected

    @pytest.mark.parametrize(
        "sql",
        [
            "select * from listings",
            "  SELECT count(*) FROM companies WHERE status = 'active'",
            "with recent as (select 1) select * from recent",
        ],
    )
    def test_чтение_не_считается_записью(self, sql):
        assert guards.table_of(sql) is None


class TestУзкоеРазрешение:
    """
    Неделя 5: команда admin пишет в users, которой Django не владеет.

    Разрешение действует только внутри блока, который его заявил, и
    только на заявленную таблицу.
    """

    def test_внутри_блока_запись_проходит(self):
        with guards.allowed_writes("users"):
            guards.check("update users set is_admin = true where id = 1")

    def test_вне_блока_снова_запрет(self):
        with guards.allowed_writes("users"):
            pass

        with pytest.raises(WriteToForeignTableError, match="«users»"):
            guards.check("update users set is_admin = true where id = 1")

    def test_разрешение_не_распространяется_на_другие_таблицы(self):
        with guards.allowed_writes("users"), pytest.raises(WriteToForeignTableError):
            guards.check("update companies set status = 'active'")

    def test_незаявленную_таблицу_разрешить_нельзя(self):
        with pytest.raises(ValueError, match="SHARED_WRITES"), guards.allowed_writes("failed_jobs"):
            pass

    def test_исключение_внутри_блока_снимает_разрешение(self):
        with pytest.raises(RuntimeError), guards.allowed_writes("users"):
            raise RuntimeError("сбой посреди записи")

        with pytest.raises(WriteToForeignTableError):
            guards.check("delete from users where id = 1")

    def test_разрешение_не_утекает_в_другой_поток(self):
        import threading

        итог: list[str] = []

        def сосед() -> None:
            try:
                guards.check("update users set status = 'blocked'")
            except WriteToForeignTableError:
                итог.append("запрет")
            else:
                итог.append("прошло")

        with guards.allowed_writes("users"):
            поток = threading.Thread(target=сосед)
            поток.start()
            поток.join()

        assert итог == ["запрет"]


class TestЗапретЗаписи:
    """Правило 4.1: у каждой таблицы один хозяин."""

    @pytest.mark.parametrize(
        "sql",
        [
            # Деньги — у Laravel дольше всех (этап 7, месяц сверки)
            "insert into payments (id) values (1)",
            "update wallets set credits = 5",
            "delete from refunds where id = 1",
        ],
    )
    def test_чужая_таблица_отказывает(self, sql):
        with pytest.raises(WriteToForeignTableError, match="принадлежит Laravel"):
            guards.check(sql)

    def test_в_сообщении_названа_таблица(self):
        """Иначе разбираться придётся по стеку вызовов."""
        with pytest.raises(WriteToForeignTableError, match="«payments»"):
            guards.check("insert into payments (id) values (1)")

    def test_чтение_проходит(self):
        guards.check("select * from listings where status = 'active'")

    def test_своя_таблица_проходит(self, monkeypatch):
        """Так будет выглядеть переход хозяина на этапе 2."""
        monkeypatch.setattr(guards, "OWNED_TABLES", frozenset({"countries"}))

        guards.check("update countries set code = 'uz'")

    def test_журнал_действий_общий(self):
        """
        Исключение из правила 4.1 (раздел 5.1 документа).

        В журнал пишут обе стороны: таблица добавляемая, изменение
        и удаление запрещены самой моделью.
        """
        guards.check("insert into admin_actions (action) values ('created')")


class TestЗапретМиграций:
    """Правило 4.2: схему меняет только Laravel."""

    @pytest.mark.parametrize(
        "sql",
        [
            "create table foo (id integer)",
            "ALTER TABLE listings ADD COLUMN foo integer",
            "drop index reviews_unique_per_company",
            "rename table a to b",
        ],
    )
    def test_ddl_отказывает(self, sql):
        with pytest.raises(MigrationFromDjangoError, match="только Laravel"):
            guards.check(sql)

    def test_миграции_django_не_применяются(self):
        router = guards.LaravelOwnsSchema()

        assert router.allow_migrate("default", "savdex") is False


class TestПредохранительНаСоединении:
    """
    Проверка через настоящий курсор.

    Обёртку можно было бы повесить и не заметить, что она не повешена:
    все тесты выше зовут check() напрямую. Этот зовёт базу.
    """

    def test_запись_через_курсор_отказывает(self, db):
        with pytest.raises(WriteToForeignTableError), connection.cursor() as cursor:
            cursor.execute("insert into payments (id) values (1)")

    def test_чтение_через_курсор_проходит(self, db):
        with connection.cursor() as cursor:
            cursor.execute("select 1")

            assert cursor.fetchone() == (1,)
