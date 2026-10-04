"""
Ссылка для MEYOS — Ассоциации мебельщиков Узбекистана: опубликованные
мебельные объявления площадки в JSON.

Что внутри — как «Мебель и всё, что с ней связано» в окне «Выгрузка»
(savdex/data/listing_export.py): раздел «Мебель» с подразделами и
объявления других категорий с мебельными словами в заголовке; только
опубликованные. Ссылки на объявление и страницу компании есть, телефонов
и почты продавцов нет: на площадке контакт открывается за плату.

Два способа отдать:

- «Скачать JSON» на странице админки — файл, который отправляют вручную;
  работает всегда;
- постоянная ссылка /feeds/meyos.json?key=… — сайт MEYOS забирает
  свежий список сам. По умолчанию выключена; включают и выдают новую
  ссылку (старая сразу перестаёт работать) суперадмин и администратор
  (право integrations). Выключенная или с чужим ключом — 404: не
  подтверждаем, что ссылка вообще есть.

Каждое действие на странице — строка журнала; сам ключ в журнал не
пишется.
"""

from __future__ import annotations

import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from savdex import audit
from savdex.adminsite import _admin_of, site
from savdex.data import listing_export as le

#: Настройки (раздел «Интеграции»): включена ли ссылка и её ключ
ENABLED = "meyos_feed_enabled"
KEY = "meyos_feed_key"

#: Как настройки заводятся, если seed ещё не прошёл
_ROWS = {
    ENABLED: {
        "label": "Ссылка для MEYOS включена",
        "type": "boolean",
        "description": "Включается и выключается на странице «Ссылка для MEYOS».",
    },
    KEY: {
        "label": "Ключ ссылки для MEYOS",
        "type": "string",
        "description": (
            "Выдаётся на странице «Ссылка для MEYOS»; новый ключ отключает старую ссылку."
        ),
    },
}

SECTION = "integrations"


@dataclass(frozen=True)
class State:
    enabled: bool
    key: str

    @property
    def url(self) -> str:
        return le.site_url(f"/feeds/meyos.json?key={self.key}") if self.key else ""


def current() -> State:
    from savdex.site.models import Setting

    values = dict(Setting.objects.filter(key__in=[ENABLED, KEY]).values_list("key", "value"))
    key = values.get(KEY)

    return State(enabled=values.get(ENABLED) is True, key=key if isinstance(key, str) else "")


def _save(key: str, value: Any) -> int:  # noqa: ANN401
    """Записать настройку; нет строки — завести (раздел «Интеграции»)."""
    from savdex.site.models import Setting

    row = Setting.objects.filter(key=key).first()

    if row is None:
        row = Setting(key=key, group=SECTION, sort=1 if key == ENABLED else 2, **_ROWS[key])

    row.value = value
    row.save()

    return int(row.pk)


# ── Содержимое ──────────────────────────────────────────────────────


def payload() -> dict[str, Any]:
    """Опубликованные мебельные объявления — для MEYOS, без контактов."""
    records = le.select(
        categories=le.furniture_ids(), with_keywords=True, status="active"
    ).prefetch_related("images")
    labels = le.category_labels()
    cities = le.city_names()
    items = [le.as_json(r, categories=labels, cities=cities, internal=False) for r in records]

    return {
        "source": "savdex.uz",
        "generated_at": timezone.now().isoformat(),
        "count": len(items),
        "items": items,
    }


def _json(data: dict[str, Any], *, status: int = 200) -> HttpResponse:
    return HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
        status=status,
    )


# ── Постоянная ссылка ───────────────────────────────────────────────


def feed(request: HttpRequest) -> HttpResponse:
    """/feeds/meyos.json?key=…: только включённая и только со своим ключом."""
    state = current()
    given = request.GET.get("key", "")

    if not (state.enabled and state.key and hmac.compare_digest(given, state.key)):
        return _json({"error": "not_found"}, status=404)

    response = _json(payload())
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex"

    return response


# ── Страница в админке ──────────────────────────────────────────────


def _journal(request: HttpRequest, row: int, before: str, after: str, note: str) -> None:
    audit.record(
        connection,
        action="updated",
        section=SECTION,
        actor=_admin_of(request),
        subject_type="App\\Models\\Setting",
        subject_id=row,
        subject_label="Ссылка для MEYOS",
        changes={"before": {"ссылка": before}, "after": {"ссылка": after}},
        note=note,
        ip=audit.client_ip(request),
    )


#: Файл JSON от MEYOS — не больше
MAX_IMPORT_BYTES = 20 * 1024 * 1024


def import_form() -> type[Any]:
    """Окно загрузки из Excel без книг — вместо них файл JSON."""
    from django import forms

    from savdex.data.admin import WorkbooksForm

    class ImportForm(WorkbooksForm):
        workbooks = None
        file = forms.FileField(
            label="Файл JSON",
            widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}),
        )
        field_order = ("file", "default_company", "default_type", "publish", "replace")

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            # Подсказки окна Excel говорят о книге и столбцах — здесь записи
            self.fields["default_company"].label = "Компания для записей без компании"
            self.fields["default_company"].help_text = (
                "Название или ИНН компании из раздела «Компании». Ей достанутся записи, где "
                "компания не указана или её нет на площадке. Пусто — служебной компании "
                "(Anjir Group); передать настоящему владельцу — действием «Передать "
                "компании…» в списке объявлений."
            )
            self.fields["default_type"].help_text = (
                "Когда в записи нет поля type, а заголовок не начинается с «Куплю», "
                "«Требуется», «Продам»…"
            )
            self.fields["publish"].help_text = (
                "Новые объявления из файла сразу появятся на сайте, без проверки. Ждавшие "
                "проверки с прошлой загрузки тоже опубликуются; отклонённые — нет."
            )
            self.fields["replace"].help_text = (
                "Обычно фотографии добавляются только объявлениям без фотографий — повторная "
                "загрузка того же файла не плодит одинаковые."
            )

        def clean_file(self) -> Any:  # noqa: ANN401
            upload = self.cleaned_data["file"]

            if upload.size > MAX_IMPORT_BYTES:
                raise forms.ValidationError("Файл больше 20 МБ — разбейте его на части.")

            return upload

    return ImportForm


def view(request: HttpRequest) -> HttpResponse:
    staff = _admin_of(request)

    if not staff.can("integrations.view"):
        raise PermissionDenied

    form = None
    report = None

    if request.method == "POST" and request.POST.get("act") == "import":
        form, report = _import(request)
    elif request.method == "POST":
        return _act(request)

    state = current()
    data = payload()

    return TemplateResponse(
        request,
        "admin/data/meyos.html",
        {
            **site.each_context(request),
            "title": "Ссылка для MEYOS",
            "state": state,
            "count": data["count"],
            "example": json.dumps(data["items"][0], ensure_ascii=False, indent=2)
            if data["items"]
            else "",
            "can_edit": staff.can("integrations.edit"),
            "can_import": staff.can("listings.import"),
            "import_form": form or import_form()(),
            "report": report,
            "keywords": ", ".join(le.keywords()),
            "keywords_url": le.keywords_url(staff),
        },
    )


def _import(request: HttpRequest) -> tuple[Any, dict[str, Any] | None]:
    """«Принять объявления»: файл JSON — объявлениями, как книга Excel."""
    from savdex.data import json_import

    staff = _admin_of(request)

    if not staff.can("listings.import"):
        raise PermissionDenied

    form = import_form()(request.POST, request.FILES)

    if not form.is_valid():
        return form, None

    try:
        result = json_import.import_json(
            form.cleaned_data["file"].read(),
            admin_id=staff.id,
            replace=bool(form.cleaned_data.get("replace")),
            ip=audit.client_ip(request),
            default_company=form.cleaned_data.get("default_company"),
            default_type=form.cleaned_data.get("default_type") or "supply",
            publish=bool(form.cleaned_data.get("publish")),
            source="MEYOS, JSON",
        )
    except json_import.UnreadableJsonError as error:
        form.add_error("file", str(error))

        return form, None

    return import_form()(), dict(result)


def _act(request: HttpRequest) -> HttpResponse:
    staff = _admin_of(request)
    act = request.POST.get("act", "")
    back = HttpResponseRedirect(reverse("savdex_admin:integrations_meyos"))

    if act == "download":
        # Файл для отправки вручную — и при выключенной ссылке
        data = payload()
        audit.record(
            connection,
            action="exported",
            section="listings",
            actor=staff,
            note=f"Для MEYOS: мебельные объявления, JSON, {data['count']} шт.",
            ip=audit.client_ip(request),
        )
        response = _json(data)
        stamp = timezone.localtime().strftime("%Y-%m-%d-%H%M")
        response["Content-Disposition"] = f'attachment; filename="savdex-meyos-{stamp}.json"'

        return response

    if not staff.can("integrations.edit"):
        raise PermissionDenied

    state = current()

    if act == "enable" and not state.enabled:
        if not state.key:
            _save(KEY, secrets.token_urlsafe(24))

        row = _save(ENABLED, True)
        _journal(request, row, "выключена", "включена", "Ссылка для MEYOS включена")
        messages.success(request, "Ссылка включена — отправьте её MEYOS.")
    elif act == "disable" and state.enabled:
        row = _save(ENABLED, False)
        _journal(request, row, "включена", "выключена", "Ссылка для MEYOS выключена")
        messages.success(request, "Ссылка выключена: по ней больше ничего не отдаётся.")
    elif act == "regenerate":
        row = _save(KEY, secrets.token_urlsafe(24))
        _journal(
            request, row, "прежняя", "новая", "Выдана новая ссылка для MEYOS, прежняя не работает"
        )
        messages.success(request, "Новая ссылка выдана. Прежняя больше не работает.")
    elif act not in ("enable", "disable"):
        raise Http404

    return back
