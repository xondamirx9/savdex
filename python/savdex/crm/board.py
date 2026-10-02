"""
Доски лидов и сделок — вместо списков разделов «Лиды» и «Сделки».

Колонки — этапы воронки (savdex/crm/stages.py), карточки — лиды или
сделки, которые сотрудник видит в разделе (продавец — свои и ничьи
лиды, свои сделки; модератор и администраторы — все). Перевести
карточку можно перетаскиванием (мышью сразу, пальцем — долгим нажатием)
или кнопкой «Перевести на этап», в том числе назад.

Окно перевода спрашивает поля, которые администратор выбрал для этапа:
ответственный, комментарий, следующий шаг и т. п. Перевод — одна строка
журнала «изменено» с пометкой «Этап: «A» → «B»»; задача следующего
шага — своя строка в журнале задач.

Закрытые колонки («успех», «отказ») показывают закрытое за неделю;
всё остальное — в архиве (обычный список раздела со всеми записями).
Лид становится сделкой только кнопкой «В сделку»: перетащить лид в
колонку «Стал сделкой» нельзя — сделки бы не появилось.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django import forms
from django.db import connections, transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from savdex import audit
from savdex.accounts.models import User
from savdex.adminsite import _admin_of
from savdex.catalog import now
from savdex.crm import stages
from savdex.crm.models import (
    CURRENCIES,
    LEAD_SOURCES,
    Deal,
    Lead,
    OnStage,
    Stage,
    Task,
)

if TYPE_CHECKING:
    from savdex.crm.admin import Scoped

#: Закрытые колонки — за последнюю неделю, остальное в архиве
CLOSED_WINDOW = timedelta(days=7)

#: Больше карточек в колонке не рисуется: остальные — поиском и в архиве
PER_COLUMN = 100


# ── Окно перевода ───────────────────────────────────────────────────


def owners(section: str) -> QuerySet[User]:
    """Кого можно назначить: действующие сотрудники с правом вести раздел."""
    from savdex.crm.admin import employees

    return User.objects.filter(pk__in=employees(f"{section}.edit")).order_by("name", "id")


class _OwnerField(forms.ModelChoiceField):  # type: ignore[type-arg]
    def label_from_instance(self, obj: Any) -> str:  # noqa: ANN401
        return str(obj.name)


def form_for(stage: Stage, people: QuerySet[User]) -> type[forms.Form]:
    """Форма окна этапа: только поля, которые выбрал администратор."""
    from savdex.crm.admin import local_datetime

    fields: dict[str, forms.Field] = {}
    catalog = stages.FIELDS[stage.pipeline]

    for key, mode in stages.asked(stage).items():
        required = mode == "required"
        label = catalog[key][0]

        if key == "owner":
            fields["owner"] = _OwnerField(
                queryset=people, required=required, label=label, empty_label="—"
            )
        elif key in ("comment", "lost_reason"):
            fields[key] = forms.CharField(
                label=label, required=required, widget=forms.Textarea(attrs={"rows": 3})
            )
        elif key == "contact_name":
            fields[key] = forms.CharField(label=label, required=required, max_length=160)
        elif key == "contact_phone":
            fields[key] = forms.CharField(label=label, required=required, max_length=40)
        elif key == "contact_email":
            fields[key] = forms.EmailField(label=label, required=required, max_length=160)
        elif key == "source":
            fields[key] = forms.ChoiceField(
                label=label,
                required=required,
                choices=[("", "—"), *LEAD_SOURCES.items()],
            )
        elif key == "task":
            fields["task_title"] = forms.CharField(
                label=label,
                required=required,
                max_length=200,
                help_text="Что сделать — «Позвонить, уточнить объём»",
            )
            fields["task_due"] = local_datetime("Срок", required=required)
        elif key == "amount":
            fields["amount"] = forms.IntegerField(label=label, required=required, min_value=0)
            fields["currency"] = forms.ChoiceField(
                label="Валюта", required=False, choices=list(CURRENCIES.items())
            )
        elif key == "expected_close_at":
            fields[key] = forms.DateField(
                label=label,
                required=required,
                widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            )

    return type(f"Move{stage.code}Form", (forms.Form,), fields)


def _append(note: str | None, text: str, author: str) -> str:
    """Комментарий — в конец заметки, с датой и именем."""
    stamp = timezone.localtime(now()).strftime("%d.%m.%Y %H:%M")
    line = f"{stamp}, {author}: {text.strip()}"

    return f"{note.rstrip()}\n{line}" if note and note.strip() else line


def move(
    admin_: Scoped,
    request: HttpRequest,
    obj: OnStage,
    stage: Stage,
    data: dict[str, Any],
) -> None:
    """
    Перевести карточку на этап и записать в неё поля окна. Пустое
    необязательное поле ничего не стирает: окно дописывает, а не
    заменяет карточку.
    """
    staff = _admin_of(request)
    names = stages.names(stage.pipeline)
    before = admin_.snapshot(obj)
    was = getattr(obj, obj.stage_field)
    task: Task | None = None

    with transaction.atomic():
        if data.get("owner") is not None:
            obj.owner = data["owner"]  # type: ignore[attr-defined]

        for key in ("contact_name", "contact_phone", "contact_email", "source", "lost_reason"):
            if data.get(key):
                setattr(obj, key, data[key])

        if data.get("amount") is not None:
            obj.amount = data["amount"]  # type: ignore[attr-defined]
            obj.currency = data.get("currency") or obj.currency  # type: ignore[attr-defined]

        if data.get("expected_close_at"):
            obj.expected_close_at = data["expected_close_at"]  # type: ignore[attr-defined]

        if data.get("comment"):
            obj.note = _append(obj.note, data["comment"], staff.name)  # type: ignore[attr-defined]

        setattr(obj, obj.stage_field, stage.code)
        obj.save()

        if data.get("task_title"):
            task = Task(
                title=data["task_title"],
                due_at=data.get("task_due"),
                assignee_id=obj.owner_id or staff.id,  # type: ignore[attr-defined]
                created_by=staff.id,
                subject_type=admin_.laravel_model,
                subject_id=obj.pk,
            )
            task.save()

    after = admin_.snapshot(obj)
    changed = {k: v for k, v in after.items() if before.get(k) != v and k not in audit.NOISE}

    if changed:
        audit.record(
            connections["default"],
            action="updated",
            section=admin_.section,
            actor=staff,
            subject_type=admin_.laravel_model,
            subject_id=obj.pk,
            subject_label=str(obj),
            changes={"before": {k: before.get(k) for k in changed}, "after": changed},
            note=f"Этап: «{names.get(was, was)}» → «{stage.name}»" if was != stage.code else None,
            ip=audit.client_ip(request),
        )

    if task is not None:
        audit.record(
            connections["default"],
            action="created",
            section="tasks",
            actor=staff,
            subject_type="App\\Models\\Crm\\Task",
            subject_id=task.pk,
            subject_label=task.title,
            changes={"after": admin_.attributes(task)},
            note=f"Следующий шаг при переводе на этап «{stage.name}»",
            ip=audit.client_ip(request),
        )


# ── Доска ───────────────────────────────────────────────────────────


def days_on_stage(obj: OnStage) -> int:
    since = obj.stage_changed_at or obj.updated_at or obj.created_at

    return max((now() - since).days, 0) if since is not None else 0


def _days_label(days: int) -> str:
    if days == 0:
        return "сегодня"

    tail = days % 100
    word = (
        "дней"
        if 11 <= tail <= 14
        else {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(days % 10, "дней")
    )

    return f"{days} {word}"


def filtered(admin_: Scoped, request: HttpRequest) -> QuerySet[Any]:
    """Карточки, которые видит сотрудник, с отбором доски (чьи, поиск)."""
    staff = _admin_of(request)
    queryset: QuerySet[Any] = admin_.get_queryset(request).select_related("company", "owner")
    who = request.GET.get("owner", "")

    if who == "mine":
        queryset = queryset.filter(owner_id=staff.id)
    elif who == "none":
        queryset = queryset.filter(owner__isnull=True)
    elif who.isdigit() and not staff.scope_is_own(admin_.section):
        queryset = queryset.filter(owner_id=int(who))

    query = request.GET.get("q", "").strip()

    if query:
        found = Q(title__icontains=query) | Q(company__name__icontains=query)

        if admin_.model is Lead:
            found |= Q(contact_name__icontains=query) | Q(contact_phone__icontains=query)

        queryset = queryset.filter(found)

    return queryset


def _card(admin_: Scoped, obj: Any, stage: Stage | None, rights: dict[str, bool]) -> dict[str, Any]:  # noqa: ANN401
    days = days_on_stage(obj)
    late = bool(stage and stage.is_open and stage.limit_days and days > stage.limit_days)
    info = admin_.model._meta
    is_lead = isinstance(obj, Lead)

    if is_lead:
        contact = obj.contact if obj.contact_id else None
        live = contact is not None and contact.deleted_at is None
        who = obj.contact_label() or ""
        phone = (contact.phone if live and contact is not None else None) or obj.contact_phone or ""
    else:
        who, phone = "", ""

    name = f"savdex_admin:{info.app_label}_{info.model_name}"

    return {
        "id": obj.pk,
        "title": obj.title,
        "url": reverse(f"{name}_change", args=[obj.pk]),
        "move_url": reverse(f"{name}_move", args=[obj.pk]),
        "assign_url": reverse(f"{name}_assign", args=[obj.pk]),
        "claim_url": reverse(f"{name}_claim", args=[obj.pk]) if is_lead else "",
        "convert_url": reverse(f"{name}_convert", args=[obj.pk]) if is_lead else "",
        "company": admin_.company_label(obj.company),
        "who": who,
        "phone": phone,
        "owner": obj.owner.name if obj.owner is not None else "",
        "owner_id": obj.owner_id or "",
        "money": obj.money() if isinstance(obj, Deal) else "",
        "amount": obj.amount if isinstance(obj, Deal) else "",
        "currency": obj.currency if isinstance(obj, Deal) else "",
        "expected": obj.expected_close_at.strftime("%Y-%m-%d")
        if isinstance(obj, Deal) and obj.expected_close_at
        else "",
        "expected_label": obj.expected_close_at.strftime("%d.%m.%Y")
        if isinstance(obj, Deal) and obj.expected_close_at
        else "",
        "overdue": isinstance(obj, Deal)
        and obj.is_open
        and obj.expected_close_at is not None
        and obj.expected_close_at < timezone.localdate(),
        "days": _days_label(days),
        "late": late,
        "stage": getattr(obj, obj.stage_field),
        "can_move": rights["move"],
        "can_claim": rights["claim"] and obj.owner_id is None,
        "can_convert": rights["convert"] and is_lead and obj.is_open,
        "can_assign": rights["assign"],
    }


def build(admin_: Scoped, request: HttpRequest) -> dict[str, Any]:
    """Колонки доски с карточками и всё, что нужно окнам."""
    staff = _admin_of(request)
    section = admin_.section
    pipeline = section  # «leads» и «deals» — и раздел прав, и воронка
    columns = stages.of(pipeline)
    by_code = {stage.code: stage for stage in columns}
    queryset = filtered(admin_, request)
    rights = {
        "move": staff.can(f"{section}.edit"),
        "claim": staff.can(f"{section}.edit") and admin_.model is Lead,
        "convert": staff.can("deals.create"),
        "assign": staff.can(f"{section}.edit") and not staff.scope_is_own(section),
    }

    if admin_.model is Lead:
        queryset = queryset.select_related("contact")

    stage_column = admin_.model.stage_field
    since = now() - CLOSED_WINDOW
    board: list[dict[str, Any]] = []

    for stage in columns:
        cards = queryset.filter(**{stage_column: stage.code})
        older = 0

        if not stage.is_open:
            older = cards.filter(stage_changed_at__lt=since).count()
            cards = cards.filter(stage_changed_at__gte=since)

        total = cards.count()
        shown = list(cards.order_by("stage_changed_at", "id")[:PER_COLUMN])
        board.append(
            {
                "stage": stage,
                "cards": [_card(admin_, obj, stage, rights) for obj in shown],
                "total": total,
                "hidden": total - len(shown),
                "older": older,
                # Лид становится сделкой только кнопкой «В сделку»
                "droppable": rights["move"] and not (admin_.model is Lead and stage.kind == "won"),
            }
        )

    # Карточки с кодом, которого нет среди этапов (не должно быть: этап с
    # карточками не удаляется), — отдельной колонкой, чтобы не пропали
    lost_codes = queryset.exclude(**{f"{stage_column}__in": list(by_code)})

    if lost_codes.exists():
        board.insert(
            0,
            {
                "stage": Stage(pipeline=pipeline, code="", name="Без этапа", kind="open"),
                "cards": [
                    _card(admin_, obj, None, rights)
                    for obj in lost_codes.order_by("id")[:PER_COLUMN]
                ],
                "total": lost_codes.count(),
                "hidden": 0,
                "older": 0,
                "droppable": False,
            },
        )

    people = owners(section)
    targets = [
        {"stage": stage, "form": form_for(stage, people)()}
        for stage in columns
        if not (admin_.model is Lead and stage.kind == "won")
    ]

    return {
        "columns": board,
        "targets": targets,
        "people": people,
        "rights": rights,
        "filters": {"owner": request.GET.get("owner", ""), "q": request.GET.get("q", "")},
        "scoped": staff.scope_is_own(section),
        "can_edit_stages": staff.can("pipelines.view"),
    }
