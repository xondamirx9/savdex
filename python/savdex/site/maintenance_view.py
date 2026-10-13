"""
«Технические работы» — страница админки: включить заставку на сайте на
30, 60, 90 минут, на 2 часа или до своего времени, продлить, снять.

Заставку показывает сайт (MaintenanceOverlay) по настройке
maintenance_until — времени окончания по Ташкенту. Эта страница пишет
только её, поэтому право на неё отдельное (раздел maintenance), а не
«Настройки площадки»: модератору и контент-менеджеру не нужны
реквизиты и банковский счёт, чтобы закрыть сайт на обновление.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from savdex import audit
from savdex.adminsite import _admin_of, site
from savdex.web.shared import _TASHKENT, maintenance

SECTION = "maintenance"
KEY = "maintenance_until"

#: Кнопки «на N минут»
PRESETS = (30, 60, 90, 120)

_ROW = {
    "group": "general",
    "label": "Технические работы до",
    "type": "string",
    "sort": 90,
}


def _value() -> str:
    from savdex.site.models import Setting

    value = Setting.objects.filter(key=KEY).values_list("value", flat=True).first()

    return value if isinstance(value, str) else ""


def _save(value: str) -> int:
    """Записать время окончания; строки нет — завести (как SettingSeeder)."""
    from savdex.site.models import Setting

    row = Setting.objects.filter(key=KEY).first()

    if row is None:
        row = Setting(key=KEY, **_ROW)

    row.value = value
    row.save()

    return int(row.pk)


def _text(moment: datetime) -> str:
    """Время по Ташкенту в виде, который читает настройка: «2026-10-13 18:30»."""
    return moment.astimezone(_TASHKENT).strftime("%Y-%m-%d %H:%M")


def _journal(request: HttpRequest, row: int, before: str, after: str, note: str) -> None:
    audit.record(
        connection,
        action="updated",
        section=SECTION,
        actor=_admin_of(request),
        subject_type="App\\Models\\Setting",
        subject_id=row,
        subject_label="Технические работы",
        changes={"before": {"до": before or "—"}, "after": {"до": after or "—"}},
        note=note,
        ip=audit.client_ip(request),
    )


def view(request: HttpRequest) -> HttpResponse:
    staff = _admin_of(request)

    if not staff.can("maintenance.view"):
        raise PermissionDenied

    if request.method == "POST":
        return _act(request)

    value = _value()
    active = maintenance({KEY: value})
    until = datetime.fromisoformat(active["until"].replace("Z", "+00:00")) if active else None
    left = int((until - datetime.now(UTC)).total_seconds() // 60) + 1 if until else 0

    return TemplateResponse(
        request,
        "admin/site/maintenance.html",
        {
            **site.each_context(request),
            "title": "Технические работы",
            "active": active is not None,
            "until": _text(until) if until else "",
            "left": left,
            "presets": PRESETS,
            "can_edit": staff.can("maintenance.edit"),
            "default_until": _text(datetime.now(UTC) + timedelta(minutes=90)).replace(" ", "T"),
        },
    )


def _act(request: HttpRequest) -> HttpResponse:
    if not _admin_of(request).can("maintenance.edit"):
        raise PermissionDenied

    act = request.POST.get("act", "")
    back = HttpResponseRedirect(reverse("savdex_admin:site_maintenance"))
    before = _value()
    now = datetime.now(UTC)
    current = maintenance({KEY: before})
    ends = datetime.fromisoformat(current["until"].replace("Z", "+00:00")) if current else None

    if act == "minutes":
        try:
            minutes = int(request.POST.get("minutes", ""))
        except ValueError:
            raise Http404 from None

        if minutes not in PRESETS:
            raise Http404

        after = _text(now + timedelta(minutes=minutes))
        note = f"Технические работы включены на {minutes} мин, до {after}"
    elif act == "extend":
        if ends is None:
            messages.warning(request, "Работы не идут — продлевать нечего. Включите их заново.")

            return back

        after = _text(ends + timedelta(minutes=30))
        note = f"Технические работы продлены на 30 мин, до {after}"
    elif act == "until":
        raw = str(request.POST.get("until", "")).strip().replace("T", " ")

        try:
            moment = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=_TASHKENT)
        except ValueError:
            messages.error(request, "Укажите дату и время окончания.")

            return back

        if moment <= now:
            messages.error(request, "Это время уже прошло — укажите время в будущем.")

            return back

        after = _text(moment)
        note = f"Технические работы включены до {after}"
    elif act == "stop":
        after = ""
        note = "Технические работы сняты, сайт открыт"
    else:
        raise Http404

    row = _save(after)
    _journal(request, row, before, after, note)

    if after:
        messages.success(request, f"Сайт закрыт заставкой до {after} по Ташкенту.")
    else:
        messages.success(request, "Заставка снята — сайт снова работает.")

    return back


def menu_entry(request: HttpRequest) -> dict[str, Any] | None:
    """Пункт в меню слева (группа «Система») — тем, кому раздел открыт."""
    if not _admin_of(request).can("maintenance.view"):
        return None

    url = reverse("savdex_admin:site_maintenance")

    return {
        "name": "Технические работы",
        "object_name": "Maintenance",
        "admin_url": url,
        "add_url": None,
        "view_only": not _admin_of(request).can("maintenance.edit"),
        "perms": {"view": True, "change": True, "add": False, "delete": False},
        "icon": "admin/icons/exclamation-triangle.svg",
    }
