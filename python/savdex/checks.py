"""
Проверка базы: доступна ли, та ли, и что в ней лежит.

Перенос `savdex:check-postgres` из PHP — неделя 1 этапа 1
(`docs/migration-to-python.md`, раздел 8). Выбрана первой намеренно:
команда обходит всю схему и ничего не меняет, то есть знакомит
с базой на задаче, где нечего сломать.

Логика отделена от самой команды, чтобы её можно было проверить,
не запуская консоль.

## Чем отличается от PHP-версии

Перенос не дословный, и три расхождения сделаны нарочно.

**Права.** PHP-версия создаёт и удаляет пробную таблицу: ей нужно
убедиться, что хватит прав на миграции. Django миграции не применяет
никогда (правило 4.2), а `CREATE TABLE` из Django не пропустит
собственный предохранитель. Поэтому здесь проверяется обратное —
что писать нельзя, — и спрашивается у самой базы через
`has_table_privilege`, без единой попытки записи.

**Сверка двух баз.** PHP-версия сравнивала базу сайта с новой: это
осталось от переезда с SQLite на PostgreSQL, который давно закончен.
Django рискует иначе — смотреть в устаревшую копию. Поэтому вместо
сравнения показывается последняя применённая миграция Laravel:
по ней сразу видно, живая база перед нами или снимок недельной
давности.

**Адрес.** `TARGET_DB_URL` заменён на `DATABASE_URL` и переменные
`DB_*`, которые читает `settings.py`.

Остальное — построчно то же самое, вплоть до склонений.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from savdex.text import plural

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

OK = "✓"
NOTE = "•"
PROBLEM = "✗"


@dataclass
class Report:
    """Строки отчёта, советы к ним и признак «работать нельзя»."""

    rows: list[tuple[str, str, str]] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    blocked: bool = False

    def ok(self, what: str, value: str) -> None:
        self.rows.append((OK, what, value))

    def note(self, what: str, value: str, advice: str) -> None:
        self.rows.append((NOTE, what, value))
        self.advice.append(advice)

    def problem(self, what: str, value: str, advice: str) -> None:
        self.rows.append((PROBLEM, what, value))
        self.advice.append(advice)
        self.blocked = True


def reason(message: str) -> str:
    """
    Понятная причина вместо простыни драйвера.

    Перенесено из CheckPostgres::reason. Тексты те же: человек,
    который читал подсказку у PHP-версии, не должен разбираться
    заново.
    """
    known = [
        (
            "password authentication failed",
            "Пароль в адресе не подошёл. Скопируйте Internal Database URL "
            "заново — он содержит пароль целиком.",
        ),
        (
            "could not translate host name",
            "Адрес не резолвится. Изнутри Render нужен Internal Database URL, снаружи — External.",
        ),
        (
            "Name or service not known",
            "Адрес не резолвится. Изнутри Render нужен Internal Database URL, снаружи — External.",
        ),
        (
            "Connection refused",
            "База не отвечает. Проверьте, что её статус Available, а ваш адрес "
            "есть в списке Access Control.",
        ),
        (
            "timeout",
            "База не отвечает. Проверьте, что её статус Available, а ваш адрес "
            "есть в списке Access Control.",
        ),
        ("does not exist", "Базы с таким именем нет. Проверьте имя в адресе."),
        (
            "permission denied",
            "Пользователю не хватает прав. Подключайтесь под владельцем базы, "
            "которого создал Render.",
        ),
    ]

    for needle, advice in known:
        if needle in message:
            return advice

    return message[:160]


def _scalar(connection: BaseDatabaseWrapper, sql: str) -> Any:  # noqa: ANN401
    with connection.cursor() as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()

    return None if row is None else row[0]


def describe(connection: BaseDatabaseWrapper, report: Report) -> bool:
    """Что это за база: версия, имя, пользователь. False — дальше нечего смотреть."""
    if connection.vendor != "postgresql":
        report.problem(
            "Тип базы",
            connection.vendor,
            "Подключение ведёт не в PostgreSQL. Проверьте адрес: он начинается "
            "с postgres:// или postgresql://.",
        )

        return False

    version = _scalar(connection, "show server_version")
    database = _scalar(connection, "select current_database()")
    user = _scalar(connection, "select current_user")

    report.ok("Соединение", f"PostgreSQL {version}")
    report.ok("База и пользователь", f"{database} / {user}")

    return True


def check_privileges(
    connection: BaseDatabaseWrapper,
    report: Report,
    tables: list[str],
) -> None:
    """
    Django читает, но не пишет.

    Не то же, что проверяла PHP-версия (см. заголовок модуля). Права
    на запись здесь — не польза, а изъян: правила площадки живут
    в событиях моделей Eloquent, и запись мимо них расходит данные
    молча. Роль без права записи — первый замок, предохранители
    в коде — второй.

    Спрашиваем у базы, а не пробуем записать. Проба означала бы
    `CREATE`, а его не пропустит собственный предохранитель — и отчёт
    сказал бы «база отклоняет» про отказ, пришедший из нашего же кода.
    Такая проверка хуже, чем никакая: она успокаивает.
    """
    try:
        _scalar(connection, "select 1")
    except Exception as error:
        report.problem("Чтение", "не удалось", reason(str(error)))

        return

    report.ok("Чтение", "разрешено")

    if not tables:
        report.note(
            "Запись",
            "проверить не на чем",
            "В базе нет таблиц, и спросить права не о чем.",
        )

        return

    probe = "companies" if "companies" in tables else tables[0]

    with connection.cursor() as cursor:
        # Имя таблицы — параметром, а не в текст запроса: оно приходит
        # из метаданных базы, но привычка подставлять имена в строку
        # однажды встретит имя, пришедшее откуда-то ещё
        cursor.execute(
            "select right_, has_table_privilege(current_user, %s, right_) "
            "from unnest(array['INSERT', 'UPDATE', 'DELETE']) as right_",
            [probe],
        )
        granted = [row[0] for row in cursor.fetchall() if row[1]]

    if not granted:
        report.ok("Запись", f"база отклоняет — роль только на чтение (по «{probe}»)")

        return

    report.note(
        "Запись",
        f"разрешена: {', '.join(granted)} (по «{probe}»)",
        "У Django роль с правом записи. На этапах 0 и 1 ему нужно только "
        "чтение: выдайте отдельную роль с GRANT SELECT и без "
        "INSERT/UPDATE/DELETE. Пока её нет, правило «у каждой таблицы один "
        "хозяин» держится только на предохранителях в коде.",
    )


def check_schema(
    connection: BaseDatabaseWrapper,
    report: Report,
    tables: list[str],
) -> None:
    """Схема, последняя миграция Laravel и данные."""
    if not tables:
        report.note(
            "Схема",
            "таблиц нет",
            "Схему создаёт Laravel: «php artisan migrate --force». Django "
            "миграции не применяет (правило 4.2).",
        )

        return

    report.ok("Схема", plural(len(tables), "таблица", "таблицы", "таблиц"))

    _check_migrations(connection, report, tables)
    _check_data(connection, report, tables)


def _check_migrations(
    connection: BaseDatabaseWrapper,
    report: Report,
    tables: list[str],
) -> None:
    """
    Последняя применённая миграция Laravel.

    Главный признак «Django смотрит не туда». Настройки могут вести
    в снимок недельной давности, и все остальные проверки на нём
    пройдут: база доступна, схема на месте, данные есть. Расхождение
    видно только по хвосту списка миграций.
    """
    if "migrations" not in tables:
        report.note(
            "Миграции Laravel",
            "таблицы migrations нет",
            "Это не та база, с которой работает сайт: у Laravel всегда есть "
            "таблица migrations. Проверьте DATABASE_URL у службы Django.",
        )

        return

    with connection.cursor() as cursor:
        cursor.execute("select count(*), max(migration) from migrations")
        row = cursor.fetchone()

    count, last = (0, None) if row is None else row

    report.ok(
        "Миграции Laravel",
        f"{plural(count, 'применена', 'применено', 'применено')}, последняя: {last}",
    )
    report.advice.append(
        f"Сверьте последнюю миграцию с репозиторием: в database/migrations "
        f"последним по алфавиту должен лежать «{last}». Если там новее — "
        f"Django смотрит в устаревшую копию базы."
    )


def _check_data(
    connection: BaseDatabaseWrapper,
    report: Report,
    tables: list[str],
) -> None:
    if "companies" not in tables:
        report.note(
            "Данные",
            "таблицы companies нет",
            "Схема прогнана не полностью — повторите migrate на стороне Laravel.",
        )

        return

    companies = int(_scalar(connection, "select count(*) from companies") or 0)
    listings = (
        int(_scalar(connection, "select count(*) from listings") or 0)
        if "listings" in tables
        else 0
    )

    if companies == 0 and listings == 0:
        report.note(
            "Данные",
            "база пуста",
            "Ни компаний, ни объявлений. Для только что созданной базы это "
            "норма; для рабочей — повод разобраться, туда ли смотрит Django.",
        )

        return

    report.ok(
        "Данные",
        plural(companies, "компания", "компании", "компаний")
        + ", "
        + plural(listings, "объявление", "объявления", "объявлений"),
    )


def inspect(connection: BaseDatabaseWrapper) -> Report:
    """Полная проверка. Соединение уже должно быть установлено."""
    report = Report()

    if not describe(connection, report):
        return report

    # Список таблиц читается один раз и передаётся дальше: два обхода
    # схемы подряд ничего не уточняют, а на боевой базе это лишний
    # тяжёлый запрос
    tables = connection.introspection.table_names()

    check_privileges(connection, report, tables)
    check_schema(connection, report, tables)

    return report
