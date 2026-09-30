"""
Админка Django без своих таблиц.

Админка Django рассчитана на свои таблицы: пользователи и права
(auth), типы моделей (contenttypes), журнал правок (django_admin_log),
сессии. Здесь таблицы заводит только Laravel, и у каждой из этих вещей
уже есть хозяин на стороне Laravel:

- пользователь — тот, кто пришёл по пропуску (savdex/bridge.py), его
  права — копия AdminAccess (savdex/access.py);
- журнал — admin_actions, общий с Laravel (savdex/audit.py);
- пароль, выход из системы, история — в админке Laravel.

Ниже — те несколько мест, где админка Django сама полезла бы в свои
таблицы, и чем они закрыты. Каждое проверено тестом: страница раздела
открывается, сохраняется и удаляет, не трогая ни одной таблицы Django.
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib import admin, messages
from django.contrib.admin import options
from django.db import connections, models
from django.http import Http404, HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import URLPattern, URLResolver

from savdex import access, audit

if TYPE_CHECKING:
    from django.forms import Form
    from django.utils.functional import _StrPromise as StrPromise


# ── Типы моделей ────────────────────────────────────────────────────


class _NoContentType:
    """Вместо записи django_content_type: номер нужен только ссылкам «смотреть на сайте»."""

    pk = None
    id = None


def _no_content_type(obj: Any) -> _NoContentType:  # noqa: ANN401
    return _NoContentType()


# Форма правки берёт номер типа модели на каждой странице — таблицы
# django_content_type нет, и без замены страница падала бы. Номер
# нужен только ссылке «смотреть на сайте», а она выключена (view_on_site)
options.get_content_type_for_model = _no_content_type  # type: ignore[assignment]


# ── Пользователь ────────────────────────────────────────────────────


#: Действие админки Django → действие AdminAccess
_ACTIONS = {"view": "view", "add": "create", "change": "edit", "delete": "delete"}


class StaffUser:
    """
    Сотрудник глазами админки Django: request.user.

    Отвечает на её вопросы («можно ли geo.change_country») матрицей
    AdminAccess: у каждой модели свой раздел прав (SECTIONS ниже).
    """

    is_active = True
    is_staff = True
    is_anonymous = False
    is_authenticated = True

    def __init__(self, admin_: access.Admin) -> None:
        self.admin = admin_
        self.pk = self.id = admin_.id
        self.is_superuser = admin_.is_superadmin

    def get_username(self) -> str:
        return self.admin.email

    def get_short_name(self) -> str:
        return self.admin.name

    def get_full_name(self) -> str:
        return self.admin.name

    def __str__(self) -> str:
        return self.admin.name

    def has_perm(self, perm: str, obj: Any = None) -> bool:  # noqa: ANN401
        """«geo.change_country» → «catalogs.edit»."""
        app_label, _, codename = perm.partition(".")
        action, _, model_name = codename.partition("_")
        section = SECTIONS.get(f"{app_label}.{model_name}")

        if section is None or action not in _ACTIONS:
            return False

        return self.admin.can(f"{section}.{_ACTIONS[action]}")

    def has_perms(self, perms: list[str], obj: Any = None) -> bool:  # noqa: ANN401
        return all(self.has_perm(p, obj) for p in perms)

    def has_module_perms(self, app_label: str) -> bool:
        return any(
            key.startswith(f"{app_label}.") and self.admin.can(f"{section}.view")
            for key, section in SECTIONS.items()
        )

    def get_all_permissions(self, obj: Any = None) -> set[str]:  # noqa: ANN401
        return set()


#: Модель админки → раздел AdminAccess. Модели нет в списке — нет и прав
SECTIONS: dict[str, str] = {}


def _admin_of(request: HttpRequest) -> access.Admin:
    admin_ = getattr(request, "admin", None)

    if not isinstance(admin_, access.Admin):
        raise Http404

    return admin_


# ── Сайт ────────────────────────────────────────────────────────────


#: Значки разделов в меню — Heroicons, как в Filament. Файлы лежат
#: в templates/admin/icons/; раздела нет в списке — общий значок
ICONS = {
    "geo.Country": "globe-alt",
    "geo.City": "building-office-2",
    "catalogs.CompanyType": "tag",
    "catalogs.Category": "squares-2x2",
    "billing.CreditPack": "ticket",
    "billing.Plan": "rectangle-stack",
    "site.Setting": "cog-6-tooth",
    "site.Banner": "megaphone",
    "site.NewsPost": "newspaper",
    "site.Page": "document-text",
    "site.LandingBlock": "home",
    "tenders.Tender": "clipboard-document-list",
    "accounts.User": "users",
    "accounts.StaffMember": "shield-check",
    "crm.Contact": "identification",
    "crm.Lead": "funnel",
    "crm.Deal": "briefcase",
    "crm.Task": "check-circle",
    "crm.Communication": "chat-bubble-left-right",
    "support.Ticket": "lifebuoy",
    "journal.AdminAction": "clock",
    "moderation.Review": "star",
    "moderation.PlatformReview": "chat-bubble-bottom-center-text",
    "moderation.CompanyDocument": "document-check",
    "moderation.Resume": "user-circle",
    "data.ItTask": "code-bracket",
    "data.Listing": "shopping-bag",
    "data.CompanyRecord": "building-office",
    "system.Broadcast": "paper-airplane",
    "finance.Payment": "credit-card",
    "finance.Refund": "arrow-uturn-left",
    "finance.Complaint": "exclamation-triangle",
    "finance.WalletTransaction": "banknotes",
    "finance.PromoCode": "receipt-percent",
    "finance.Subscription": "arrow-path",
}
DEFAULT_ICON = "rectangle-stack"


@functools.cache
def _theme_version() -> str:
    """
    Метка версии стилей админки для ссылки ?v=…: имя файла у WhiteNoise
    без хеша, и кеш браузера или прокси иначе держит старые стили.
    """
    from django.contrib.staticfiles import finders

    path = finders.find("savdex/admin-theme.css")

    if not isinstance(path, str):
        return "0"

    with open(path, "rb") as file:
        return hashlib.sha256(file.read()).hexdigest()[:10]


class SavdexAdminSite(admin.AdminSite):
    site_header = "SAVDEX · Управление"
    site_title = "SAVDEX · разделы на Python"
    index_title = "Разделы на Python"
    # «Открыть сайт» — на сайт площадки
    site_url = "/"
    enable_nav_sidebar = True

    def has_permission(self, request: HttpRequest) -> bool:
        return isinstance(getattr(request, "admin", None), access.Admin)

    def login(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        """Вход — своя страница (savdex/adminlogin.py), не django.contrib.auth."""
        from savdex import adminlogin

        return adminlogin.login_page(request)

    def logout(  # type: ignore[override]
        self,
        request: HttpRequest,
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        """Выход из админки и с сайта (одна сессия Laravel)."""
        from savdex import adminlogin

        return adminlogin.logout(request)

    def get_urls(self) -> list[URLPattern | URLResolver]:
        # Смена пароля — в админке Laravel: у Django своих паролей нет
        return [
            u
            for u in super().get_urls()
            if getattr(u, "name", None) not in {"password_change", "password_change_done"}
        ]

    def index(self, request: HttpRequest, extra_context: Any = None) -> TemplateResponse:  # noqa: ANN401
        """
        Главная: стартовый экран сотрудника (savdex/dashboard/ — вместо
        виджетов Filament), разделы и ход переноса (savdex/progress.py).
        """
        from savdex import progress
        from savdex.dashboard import widgets

        return super().index(
            request,
            {
                "dashboard": widgets.for_request(request),
                "progress": progress.summary(),
                **(extra_context or {}),
            },
        )

    def each_context(self, request: HttpRequest) -> dict[str, Any]:
        context = super().each_context(request)
        admin_ = getattr(request, "admin", None)
        context["savdex_admin"] = admin_
        context["savdex_role"] = admin_.role_label if isinstance(admin_, access.Admin) else None
        # «Выгрузка в Excel» пока на Filament — ссылка в шапке тем, кому она видна
        context["savdex_exports"] = isinstance(admin_, access.Admin) and admin_.can("backups.view")
        # Знак из раздела «Оформление» — тот же, что в шапке Filament
        from savdex.web import shared

        context["savdex_logo"] = shared.appearance_logo(shared.settings_values())
        context["savdex_theme_version"] = _theme_version()

        return context

    def get_app_list(
        self,
        request: HttpRequest,
        app_label: str | None = None,
    ) -> list[Any]:
        apps = super().get_app_list(request, app_label)

        for app in apps:
            for model in app["models"]:
                key = f"{app['app_label']}.{model['object_name']}"
                model["icon"] = f"admin/icons/{ICONS.get(key, DEFAULT_ICON)}.svg"

        return apps


site = SavdexAdminSite(name="savdex_admin")


# ── Разделы ─────────────────────────────────────────────────────────


class SavdexModelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """
    Раздел админки на Django.

    - права — по разделу AdminAccess (section);
    - журнал — admin_actions, как у Laravel: создано, изменено (что
      было и что стало), удалено;
    - истории Django нет: её место — журнал действий в админке Laravel.
    """

    #: Раздел AdminAccess, по которому решаются права
    section: ClassVar[str]

    #: Как записи называются в журнале у Laravel (App\Models\…)
    laravel_model: ClassVar[str]

    view_on_site = False

    #: Заголовки страниц по-русски: у Django один шаблон на все модели
    #: («Выберите страна для изменения»), падежей он не знает
    title_list: ClassVar[str] = ""
    title_add: ClassVar[str] = ""
    title_change: ClassVar[str] = ""

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        return super().changelist_view(
            request,
            {"title": self.title_list, **(extra_context or {})}
            if self.title_list
            else extra_context,
        )

    def add_view(
        self,
        request: HttpRequest,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        return super().add_view(
            request,
            form_url,
            {"title": self.title_add, **(extra_context or {})} if self.title_add else extra_context,
        )

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        return super().change_view(
            request,
            object_id,
            form_url,
            {"title": self.title_change, **(extra_context or {})}
            if self.title_change
            else extra_context,
        )

    def message_user(
        self,
        request: HttpRequest,
        message: str | StrPromise,
        level: int | str = messages.INFO,
        extra_tags: str = "",
        fail_silently: bool = False,
    ) -> None:
        """«Сохранено: …» вместо «Страна “…” был успешно изменен»: без падежей Django."""
        done = getattr(request, "_savdex_done", None)

        if level == messages.SUCCESS and done:
            message = done

        super().message_user(request, message, level, extra_tags, fail_silently)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    # Журнал Django не ведётся: вместо него — admin_actions (ниже)
    def log_addition(  # type: ignore[override]
        self, request: HttpRequest, obj: object, message: object
    ) -> None:
        return None

    def log_change(  # type: ignore[override]
        self, request: HttpRequest, obj: object, message: object
    ) -> None:
        return None

    def log_deletion(self, request: HttpRequest, obj: Any, object_repr: str) -> None:  # noqa: ANN401
        return None

    def log_deletions(  # type: ignore[override]
        self, request: HttpRequest, queryset: object
    ) -> None:
        return None

    def history_view(
        self,
        request: HttpRequest,
        object_id: str,
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        raise Http404

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # Массового удаления у справочников нет намеренно, как в Filament:
        # записей мало, а ошибка необратима
        return {}

    # ── Журнал ──

    @staticmethod
    def attributes(obj: models.Model) -> dict[str, Any]:
        """Поля записи, как getAttributes() у Eloquent: имя столбца → значение."""
        values: dict[str, Any] = {}

        for field in obj._meta.concrete_fields:
            value = getattr(obj, field.attname)

            if hasattr(value, "strftime"):
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, Decimal):
                # Как Eloquent с приведением decimal:7 — строкой, со всеми
                # знаками столбца. Из формы приходит «39.6542», из базы
                # «39.6542000»: без выравнивания журнал записал бы правку
                # координат, которых никто не трогал
                places = getattr(field, "decimal_places", None)
                value = str(value if places is None else value.quantize(Decimal(1).scaleb(-places)))

            values[str(field.column)] = value

        return values

    def snapshot(self, obj: models.Model) -> dict[str, Any]:
        """
        Что сравнивать в журнале: поля записи, плюс то, что раздел
        считает её частью (переводы названий и т. п.).
        """
        return self.attributes(obj)

    def journal(
        self,
        request: HttpRequest,
        action: str,
        obj: models.Model,
        changes: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        attributes = self.attributes(obj)

        audit.record(
            connections["default"],
            action=action,
            section=self.section,
            actor=_admin_of(request),
            subject_type=self.laravel_model,
            subject_id=obj.pk,
            subject_label=audit.label(attributes, self.laravel_model.rsplit("\\", 1)[-1], obj.pk),
            changes=changes,
            ip=audit.client_ip(request),
        )

    def save_related(
        self, request: HttpRequest, form: Form, formsets: list[Any], change: bool
    ) -> None:
        """После записи и её вложенных частей — одна строка журнала."""
        obj = form.instance  # type: ignore[attr-defined]
        before: dict[str, Any] = getattr(form, "_savdex_before", {})
        super().save_related(request, form, formsets, change)

        # Вложенные части (переводы) только что записаны: закэшированные
        # до правки больше не годятся — ни для журнала, ни для сообщения
        getattr(obj, "_prefetched_objects_cache", {}).clear()
        request._savdex_done = f"Сохранено: {obj}"  # type: ignore[attr-defined]

        after = self.snapshot(obj)

        if not change:
            self.journal(request, "created", obj, {"after": after})

            return

        changed = {k: v for k, v in after.items() if before.get(k) != v}
        gone = {k: None for k in before if k not in after}
        diff = {
            "before": {k: before.get(k) for k in [*changed, *gone]},
            "after": changed | gone,
        }

        # Laravel не пишет «изменено», если поменялось только время правки
        if {k for k in diff["after"] if k not in audit.NOISE}:
            self.journal(request, audit.update_action(before, changed), obj, diff)

    def get_form(
        self,
        request: HttpRequest,
        obj: Any = None,  # noqa: ANN401
        change: bool = False,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        form_class = super().get_form(request, obj, change=change, **kwargs)
        attributes = self.snapshot(obj) if obj is not None else {}

        class WithSnapshot(form_class):  # type: ignore[valid-type, misc]
            """Снимок полей до правки — для строки «было» в журнале."""

            def __init__(self, *args: Any, **kw: Any) -> None:
                super().__init__(*args, **kw)
                self._savdex_before = dict(attributes)

        WithSnapshot.__name__ = form_class.__name__

        return WithSnapshot

    def delete_model(self, request: HttpRequest, obj: models.Model) -> None:
        label = str(obj)
        super().delete_model(request, obj)
        self.journal(request, "deleted", obj)
        request._savdex_done = f"Удалено: {label}"  # type: ignore[attr-defined]

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:  # noqa: ANN401
        for obj in queryset:
            self.delete_model(request, obj)


def register(model: type[models.Model], section: str) -> Callable[[type[Any]], type[Any]]:
    """Зарегистрировать раздел: модель, её раздел прав и класс админки."""
    SECTIONS[f"{model._meta.app_label}.{model._meta.model_name}"] = section

    def wrap(admin_class: type[Any]) -> type[Any]:
        admin_class.section = section
        site.register(model, admin_class)

        return admin_class

    return wrap
