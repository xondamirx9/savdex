"""
Запись строки чужой таблицы так, как её пишет Eloquent: только
изменившиеся поля (сравнение по значению, даты — строкой секунд),
updated_at, у администратора — строка журнала (AuditObserver: поля в
порядке столбцов таблицы, до и после).

Событие saving у модели (пересчёт search_text) передаётся в saving:
функция от строки после правки, её результат — ещё одно поле записи.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import connection

from savdex import audit
from savdex.audit import _php_json
from savdex.guards import allowed_writes
from savdex.web.listing_actions import _now, _stamp
from savdex.web.shared import Context
from savdex.web.tenders import _admin


def _same(before: Any, after: Any) -> bool:  # noqa: ANN401
    """HasAttributes::originalIsEquivalent (для простых значений и дат)."""
    before, after = _stamp(before), _stamp(after)

    if before == after:
        return True

    # Числа сравниваются строкой (strcmp): «5» и 5 — одно и то же
    def numeric(value: Any) -> bool:  # noqa: ANN401
        if isinstance(value, bool):
            return False

        try:
            float(value)
        except (TypeError, ValueError):
            return False

        return True

    return numeric(before) and numeric(after) and str(before) == str(after)


def _php_bool(value: Any) -> bool:  # noqa: ANN401
    """(bool) $value у PHP."""
    return value not in (None, False, 0, 0.0, "", "0", [], {})


def _cast_same(cast: str | None, before: Any, after: Any) -> bool:  # noqa: ANN401
    """HasAttributes::originalIsEquivalent с приведением столбца."""
    if cast == "bool":
        return _php_bool(before) is _php_bool(after)

    if cast == "json":
        return json.dumps(before) == json.dumps(after)

    if cast is not None and cast.startswith("decimal:"):
        # asDecimal: строки с заданным числом знаков, округление HalfUp
        places = Decimal(1).scaleb(-int(cast.split(":")[1]))

        try:
            return (before is None and after is None) or (
                before is not None
                and after is not None
                and Decimal(str(before)).quantize(places, ROUND_HALF_UP)
                == Decimal(str(after)).quantize(places, ROUND_HALF_UP)
            )
        except InvalidOperation:
            return _same(before, after)

    if cast == "int":
        try:
            return int(float(str(before))) == int(float(str(after)))
        except ValueError:
            return _same(before, after)

    return _same(before, after)


def _written(cast: str | None, value: Any) -> Any:  # noqa: ANN401
    """Значение столбца: массив с кастом array — текстом json_encode."""
    if cast == "json" and value is not None:
        return _php_json(value)

    return _stamp(value)


def save(
    ctx: Context,
    table: str,
    row: dict[str, Any],
    changes: dict[str, Any],
    *,
    section: str | None,
    model: str,
    saving: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    casts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """
    $model->forceFill($changes)->save(); вернуть изменившиеся поля.

    casts — приведения модели для сравнения (bool, int, json): у них
    Eloquent сравнивает приведённые значения, а не текст.
    """
    casts = casts or {}
    after = {**row, **changes}

    if saving is not None:
        after.update(saving(after))

    dirty = {
        column: after[column]
        for column in row
        if column != "updated_at" and not _cast_same(casts.get(column), row[column], after[column])
    }

    if not dirty:
        return {}

    now = _now()
    sets = ", ".join(f"{c} = %s" for c in dirty)

    with allowed_writes(table), connection.cursor() as cursor:
        cursor.execute(
            f"update {table} set {sets}, updated_at = %s where id = %s",
            [*(_written(casts.get(c), v) for c, v in dirty.items()), _stamp(now), row["id"]],
        )

    # getRawOriginal и getChanges: сырые значения — массив текстом JSON
    before = {c: _written(casts.get(c), row[c]) for c in dirty}
    row.update(dirty, updated_at=now)

    # Наблюдатель срабатывает после записи: подпись — по новым значениям
    if section is not None:
        journal(
            ctx,
            "updated",
            section,
            model,
            row,
            {"before": before, "after": {c: _written(casts.get(c), v) for c, v in dirty.items()}},
        )

    return dirty


def journal(
    ctx: Context,
    action: str,
    section: str,
    model: str,
    row: dict[str, Any],
    changes: dict[str, Any] | None,
) -> None:
    """AuditObserver: только действия администратора."""
    admin = _admin(ctx)

    if admin is None:
        return

    audit.record(
        connection,
        action=action,
        section=section,
        actor=admin,
        subject_type=f"App\\Models\\{model}",
        subject_id=row["id"],
        subject_label=audit.label(row, model, row["id"]),
        changes=changes,
        ip=audit.client_ip(ctx.request),
    )


def now() -> datetime:
    return _now()
