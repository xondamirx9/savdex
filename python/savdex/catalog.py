"""
Общее у справочников, которые переходят к Django: страны, города, типы
компаний и дальше по списку этапа 2.

У всех одно и то же устройство, взятое у Laravel:

- время создания и правки — в UTC, до секунды, как у Eloquent;
- названия на пяти языках в отдельной таблице переводов, с откатом
  на русский и затем на код;
- запрет удаления, пока на запись ссылаются (RefusesDeletionWhenReferenced):
  внешние ключи удалению не мешают, а обнулили бы ссылку молча или
  увели бы связанные записи каскадом.

Здесь это написано один раз, а справочник только объявляет, кто на
него ссылается и чем.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from django.db import connection, models
from django.utils import timezone

#: Языки площадки — App\\Support\\Locales::ALL
LOCALES: dict[str, str] = {
    "ru": "Русский",
    "uz": "O‘zbekcha",
    "en": "English",
    "zh": "中文",
    "tr": "Türkçe",
}


class RecordIsReferencedError(RuntimeError):
    """App\\Exceptions\\RecordIsReferenced: на запись ссылаются, удалять нельзя."""


def now() -> datetime:
    """Как Laravel: время в UTC, до секунды (столбцы timestamp(0))."""
    return timezone.now().replace(microsecond=0)


class UTCDateTimeField(models.DateTimeField):  # type: ignore[type-arg]
    """
    Столбец timestamp (без пояса), как его заводит Laravel, — в UTC.

    Django на PostgreSQL рассчитывает на timestamptz и читает timestamp
    без пояса «наивным» временем, которое не сравнить с текущим. Laravel
    пишет туда UTC (app.timezone) — так его и читаем.
    """

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:  # noqa: ANN401
        if value is not None and timezone.is_naive(value):
            return timezone.make_aware(value, UTC)

        return value


class Timestamped(models.Model):
    """created_at и updated_at, которые Eloquent ставит сам."""

    created_at = UTCDateTimeField(null=True, editable=False)
    updated_at = UTCDateTimeField(null=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        stamp = now()

        if self._state.adding and self.created_at is None:
            self.created_at = stamp

        self.updated_at = stamp
        super().save(*args, **kwargs)


class Reference:
    """
    Кто ссылается на запись справочника: таблица, её столбец и поле
    записи, на которое он указывает (обычно id, у типов компаний — код).

    Считаются и удалённые в корзину строки (PHP их пропускает): внешний
    ключ задел бы и их, и восстановленная запись вернулась бы с пустой
    ссылкой или ссылкой в никуда.
    """

    def __init__(self, table: str, column: str, label: str, *, field: str = "id") -> None:
        self.table, self.column, self.label, self.field = table, column, label, field

    def count(self, record: models.Model) -> int:
        with connection.cursor() as cursor:
            # Имена — из кода, не от человека
            cursor.execute(
                f"select count(*) from {self.table} where {self.column} = %s",
                [getattr(record, self.field)],
            )
            row = cursor.fetchone()

        return int(row[0]) if row else 0

    def subquery(self, owner_table: str) -> str:
        """То же одним подзапросом — для списка, чтобы не считать построчно."""
        return (
            f"select count(*) from {self.table} "
            f"where {self.table}.{self.column} = {owner_table}.{self.field}"
        )


class Guarded(Timestamped):
    """
    Запись, которая не удаляется, пока на неё ссылаются.

    Наследник объявляет REFERENCES, HELD_AS и INSTEAD.
    """

    #: Кто удерживает запись от удаления
    REFERENCES: ClassVar[tuple[Reference, ...]] = ()

    #: «на страну», «на город» — для отказа в удалении
    HELD_AS: ClassVar[str] = "на запись"

    #: Что предложить вместо удаления
    INSTEAD: ClassVar[str] = "Выключите запись вместо удаления."

    class Meta:
        abstract = True

    def references(self) -> dict[str, int]:
        """references(): кто ссылается на запись; пусто — удалять можно."""
        if self.pk is None:
            return {}

        counts = {ref.label: ref.count(self) for ref in self.REFERENCES}

        return {label: count for label, count in counts.items() if count}

    def held(self) -> str:
        """Можно ли удалить — объяснение для формы."""
        references = self.references()

        if not references:
            return f"Можно: {self.HELD_AS} никто не ссылается."

        parts = ", ".join(f"{what} — {count}" for what, count in references.items())

        return f"Нельзя, {self.HELD_AS} ссылаются: {parts}. {self.INSTEAD}"

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """
        Проверка в модели, а не в кнопке: кнопку обходит любой будущий
        код, а модель нет.
        """
        references = self.references()

        if references:
            parts = ", ".join(f"{what} — {count}" for what, count in references.items())

            raise RecordIsReferencedError(f"Удалить нельзя, {self.HELD_AS} ссылаются: {parts}.")

        return super().delete(*args, **kwargs)


class Catalog(Guarded):
    """
    Запись справочника с названиями на языках.

    Сверх Guarded наследник объявляет NAME_FALLBACK, а связь с
    переводами называет related_name="translations".
    """

    #: Поле, которое показывается, если названия нет ни на одном языке
    NAME_FALLBACK: ClassVar[str] = "id"

    class Meta:
        abstract = True

    def name(self, locale: str = "ru") -> str:
        """name(): название на языке, с откатом на русский и на код."""
        names = {t.locale: t.name for t in self.translations.all()}  # type: ignore[attr-defined]

        return names.get(locale) or names.get("ru") or str(getattr(self, self.NAME_FALLBACK))


class Translation(Timestamped):
    """Название записи справочника на одном языке."""

    locale = models.CharField("язык", max_length=5, choices=list(LOCALES.items()))
    name = models.CharField("название", max_length=190)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.locale}: {self.name}"
