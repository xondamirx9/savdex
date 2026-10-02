"""
Этапы воронок лидов и сделок: колонки досок (savdex/crm/board.py).

Этапы лежат в crm_stages, их правит администратор (раздел «Этапы
воронки»): заводит новые, переименовывает, меняет порядок, удаляет
пустые. Код этапа — то, что пишется в crm_leads.status /
crm_deals.stage; у новых он «s» и случайные знаки: название меняется,
код — никогда.

Системные этапы (models.SYSTEM_STAGES) не удаляются: «new» — вход, по
одному закрытому «успеху» и «отказу» на воронку. Новые этапы — только
рабочие: закрытые колонки на доске всегда в конце.

Окно при переводе на этап спрашивает поля, которые администратор выбрал
для этапа (Stage.fields): «не спрашивать», «можно заполнить»,
«обязательно». Каталог полей — FIELDS.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable

from django.db.models import Max

from savdex.crm.models import Stage

#: Что окно может спросить при переводе на этап, по воронкам:
#: ключ → (подпись, пояснение для администратора)
FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "leads": {
        "owner": ("Ответственный", "Кто берётся за работу; уже назначенный — выбран заранее"),
        "comment": ("Комментарий", "Дописывается в заметку лида с датой и именем"),
        "contact_name": ("Имя обратившегося", ""),
        "contact_phone": ("Телефон", ""),
        "contact_email": ("Почта", ""),
        "source": ("Откуда пришёл", ""),
        "task": ("Следующий шаг", "Задача со сроком — появится в «Задачах» у ответственного"),
        "lost_reason": ("Причина отказа", "На этапе отказа спрашивается всегда"),
    },
    "deals": {
        "owner": ("Ответственный", "Кто ведёт сделку; уже назначенный — выбран заранее"),
        "amount": ("Сумма", "Сумма и валюта; уже указанная — подставлена заранее"),
        "expected_close_at": ("Когда закрыть", "Ожидаемая дата закрытия"),
        "comment": ("Комментарий", "Дописывается в заметку сделки с датой и именем"),
        "task": ("Следующий шаг", "Задача со сроком — появится в «Задачах» у ответственного"),
        "lost_reason": ("Причина проигрыша", "На этапе проигрыша спрашивается всегда"),
    },
}

#: Как спрашивать поле
MODES = {"": "Не спрашивать", "optional": "Можно заполнить", "required": "Обязательно"}

#: Порядок колонок: рабочие по порядку, затем успех, затем отказ
_KIND_ORDER = {"open": 0, "won": 1, "lost": 2}


def ordered(stages: Iterable[Stage]) -> list[Stage]:
    return sorted(stages, key=lambda s: (_KIND_ORDER.get(s.kind, 0), s.position, s.id))


def of(pipeline: str) -> list[Stage]:
    """Этапы воронки в порядке колонок доски."""
    return ordered(Stage.objects.filter(pipeline=pipeline))


def names(pipeline: str) -> dict[str, str]:
    """Код этапа → название."""
    return {stage.code: stage.name for stage in of(pipeline)}


def asked(stage: Stage) -> dict[str, str]:
    """
    Поля окна этапа: ключ → «optional» или «required», в порядке
    каталога. Причина отказа на закрытом «отказе» — обязательна всегда:
    без неё отказ потом не разобрать.
    """
    catalog = FIELDS.get(stage.pipeline, {})
    chosen = stage.fields if isinstance(stage.fields, dict) else {}
    fields = {
        key: str(chosen[key])
        for key in catalog
        if key in chosen and chosen[key] in ("optional", "required")
    }

    if stage.kind == "lost":
        fields["lost_reason"] = "required"
    else:
        fields.pop("lost_reason", None)

    return {key: fields[key] for key in catalog if key in fields}


def new_code() -> str:
    """Код нового этапа: «s» и восемь случайных знаков (столбец — 20)."""
    return "s" + secrets.token_hex(4)


def next_position(pipeline: str) -> int:
    """Новый рабочий этап — последним среди рабочих."""
    top = Stage.objects.filter(pipeline=pipeline, kind="open").aggregate(top=Max("position"))

    return int(top["top"] or 0) + 1
