"""
Раздел «Пользователи» в админке Django: удаление аккаунта в два шага.

1. «Отключить» — как SoftDeletes::delete у Laravel: deleted_at и
   updated_at. Войти нельзя, адрес почты сразу свободен для новой
   регистрации (индекс уникальности — только среди действующих), запись
   остаётся в базе.
2. Отключённый находится отбором «Отключённые» и поиском по почте — и
   «Восстановить» (если адрес не занял новый аккаунт) или «Удалить
   навсегда» (только отключённый, только суперадмин, как canForceDelete
   у Filament). Связанные строки база правит сама по внешним ключам:
   избранное, уведомления, резюме удаляются, у объявлений, платежей и
   отзывов остаётся пустая ссылка.

С этапа 6 раздел заменяет «Пользователей» Filament целиком: заведение
и правка (accounts/editing.py), «Подтвердить почту», «Выдать пароль»,
«Заблокировать» и выгрузка. Права — раздел users в AdminAccess; каждое
действие — строка журнала admin_actions, как AuditObserver у Laravel
(отключение — deleted, восстановление — restored, навсегда —
force_deleted).
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.utils import flatten_fieldsets
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, connections, transaction
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex import access, audit
from savdex.accounts import editing
from savdex.accounts.models import STATUSES, User
from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.catalog import now
from savdex.guards import allowed_writes
from savdex.text import numeric


class StateFilter(admin.SimpleListFilter):
    """Действующие и отключённые — как TrashedFilter у Filament."""

    title = "состояние"
    parameter_name = "state"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("active", "Действующие"), ("disabled", "Отключённые")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[User]) -> QuerySet[User]:
        if self.value() == "active":
            return queryset.filter(deleted_at__isnull=True)

        if self.value() == "disabled":
            return queryset.filter(deleted_at__isnull=False)

        return queryset


@register(User, section="users")
class UserAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\User"
    title_add = "Новый пользователь"
    title_list = "Пользователи"
    title_change = "Пользователь"

    change_form_template = "admin/accounts/user/change_form.html"
    change_list_template = "admin/accounts/user/change_list.html"
    form = editing.UserForm
    list_display = (
        "person",
        "company",
        "company_role_label",
        "role",
        "verified",
        "state",
        "last_login_at",
    )
    list_filter = (StateFilter, "status", "is_admin")
    search_fields = ("name", "email", "phone")
    list_per_page = 50
    fieldsets = (
        ("Человек", {"fields": ("name", "email", "phone", "email_verified_at")}),
        ("Компания", {"fields": ("company_id", "company_role")}),
        ("Админка", {"fields": ("is_admin", "admin_role")}),
        (
            "Состояние",
            {"fields": ("status", "deleted_at", "created_at", "last_login_at")},
        ),
    )
    actions = ("disable", "restore", "force_delete")

    # ── Права ──

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Завести доступ вручную (§6.3 ТЗ): право users.create."""
        return _admin_of(request).can("users.create")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return _admin_of(request).can("users.edit")

    # ── Форма ──

    def _roles_editable(self, request: HttpRequest) -> bool:
        """Выдавать доступ в панель может только тот, кому открыта правка ролей."""
        return _admin_of(request).can("roles.edit")

    def _staff_guarded(self, request: HttpRequest, user: Any) -> bool:  # noqa: ANN401
        """
        Чужая учётка сотрудника без права roles.edit: почту, пароль и статус
        не трогать. Иначе администратор выдал бы суперадмину новый пароль
        (или сменил почту и сбросил его письмом) и вошёл бы под ним — та же
        граница, что у роли и личных прав. У Filament её не было.
        """
        return (
            isinstance(user, User)
            and user.is_admin
            and user.pk != _admin_of(request).id
            and not self._roles_editable(request)
        )

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        if not self.has_change_permission(request, obj) and obj is not None:
            return super().get_fieldsets(request, obj)

        guarded = self._staff_guarded(request, obj)
        sets: list[Any] = [
            (
                "Человек",
                {
                    "fields": ("name", "phone", "locale")
                    if guarded
                    else ("name", "email", "phone", "locale")
                },
            ),
            ("Компания", {"fields": ("company_id", "company_role")}),
        ]

        if self._roles_editable(request):
            sets += [
                ("Доступ в админку", {"fields": ("is_admin", "admin_role", "status")}),
                (
                    "Личные права",
                    {
                        "fields": ("grant", "revoke"),
                        "classes": ("collapse",),
                        "description": "Поверх роли. Списки пусты у всех, кроме тех, кому "
                        "что-то выдали отдельно",
                    },
                ),
            ]
        elif not guarded:
            sets.append(("Статус", {"fields": ("status",)}))

        if obj is None:
            sets.append(("Пароль", {"fields": ("password", "must_change_password")}))

        return sets

    def get_form(
        self,
        request: HttpRequest,
        obj: Any = None,  # noqa: ANN401
        change: bool = False,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        form = super().get_form(request, obj, change=change, **kwargs)
        # Только поля своих разделов формы: роль и личные права — с roles.edit
        form.allowed = frozenset(flatten_fieldsets(self.get_fieldsets(request, obj)))

        return form

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:  # noqa: ANN401
        if obj is not None and not self.has_change_permission(request, obj):
            return (
                "name",
                "email",
                "phone",
                "email_verified_at",
                "company_id",
                "company_role",
                "is_admin",
                "admin_role",
                "status",
                "deleted_at",
                "created_at",
                "last_login_at",
            )

        return ()

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:  # noqa: ANN401
        """Только поля формы — прямым запросом; новый — с паролем."""
        if not change:
            obj.must_change_password = bool(form.cleaned_data.get("must_change_password"))
            password = str(form.cleaned_data["password"])
            editing.write(obj, form.columns(), password=password)
            # Пароль показывается один раз: хранить его в открытом виде негде
            messages.warning(request, f"Пароль выдан — передайте лично: {password}")

            return

        editing.write(obj, form.columns())

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        # Стандартное удаление Django стёрло бы и действующий аккаунт —
        # мимо шага «отключить»; вместо него — действия ниже
        return False

    def has_disable_permission(self, request: HttpRequest) -> bool:
        """UserResource::canDelete: право users.delete."""
        return _admin_of(request).can("users.delete")

    def has_restore_permission(self, request: HttpRequest) -> bool:
        """UserResource::canRestore: то же право users.delete."""
        return _admin_of(request).can("users.delete")

    def has_force_delete_permission(self, request: HttpRequest) -> bool:
        """UserResource::canForceDelete: только суперадмин."""
        return _admin_of(request).is_superadmin

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        # SavdexModelAdmin убирает массовые действия у справочников; здесь
        # они и есть раздел — отобранные по правам (allowed_permissions)
        return super(SavdexModelAdmin, self).get_actions(request)

    # ── Список ──

    def get_queryset(self, request: HttpRequest) -> QuerySet[User]:
        queryset: QuerySet[User] = super().get_queryset(request)

        return queryset.annotate(
            company_name=RawSQL(
                "select name from companies where companies.id = users.company_id", []
            )
        )

    @admin.display(description="имя", ordering="name")
    def person(self, obj: User) -> str:
        return format_html("{}<br><small>{}</small>", obj.name, obj.email)

    @admin.display(description="компания")
    def company(self, obj: User) -> str:
        return getattr(obj, "company_name", None) or "без компании"

    @admin.display(description="роль")
    def company_role_label(self, obj: User) -> str:
        # Роль есть только там, где есть компания: default 'owner' иначе
        # делал бы владельцем администратора без компании
        if obj.company_id is None:
            return "—"

        return "Владелец" if obj.company_role == "owner" else "Сотрудник"

    @admin.display(description="почта", boolean=True)
    def verified(self, obj: User) -> bool:
        return obj.email_verified_at is not None

    @admin.display(description="состояние", ordering="deleted_at")
    def state(self, obj: User) -> str:
        if obj.deleted_at is not None:
            return f"Отключён {obj.deleted_at:%d.%m.%Y}"

        return STATUSES.get(obj.status, obj.status)

    @admin.display(description="в админке")
    def role(self, obj: User) -> str:
        if not obj.is_admin:
            return "—"

        return access.ROLES.get(obj.admin_role or "", "Роль не назначена")

    # ── Действия ──

    @admin.action(description="Отключить выбранные", permissions=["disable"])
    def disable(self, request: HttpRequest, queryset: QuerySet[User]) -> None:
        me = _admin_of(request).id
        done = 0

        for user in queryset.filter(deleted_at__isnull=True):
            # Отключить себя — остаться без доступа к панели
            if user.pk == me:
                self.message_user(request, "Себя отключить нельзя.", messages.WARNING)
                continue

            stamp = now()

            if self._write(
                "update users set deleted_at = %s, updated_at = %s "
                "where id = %s and deleted_at is null",
                [stamp, stamp, user.pk],
            ):
                user.deleted_at = user.updated_at = stamp
                self.journal(request, "deleted", user)
                done += 1

        if done:
            self.message_user(
                request,
                f"Отключено: {done}. Их адреса почты свободны для новой регистрации.",
                messages.SUCCESS,
            )

    @admin.action(description="Восстановить выбранные", permissions=["restore"])
    def restore(self, request: HttpRequest, queryset: QuerySet[User]) -> None:
        done = 0

        for user in queryset.filter(deleted_at__isnull=False):
            # Двух действующих с одной почтой быть не может: адрес мог
            # занять новый аккаунт, пока этот был отключён
            # (без учёта регистра, как ищет вход)
            if User.objects.filter(email__iexact=user.email, deleted_at__isnull=True).exclude(
                pk=user.pk
            ):
                self.message_user(
                    request,
                    f"Не восстановлен: адрес {user.email} уже занят другим аккаунтом.",
                    messages.ERROR,
                )
                continue

            stamp = now()

            try:
                restored = self._write(
                    "update users set deleted_at = null, updated_at = %s "
                    "where id = %s and deleted_at is not null",
                    [stamp, user.pk],
                )
            except IntegrityError:
                # Адрес заняли между проверкой и записью
                self.message_user(
                    request,
                    f"Не восстановлен: адрес {user.email} уже занят другим аккаунтом.",
                    messages.ERROR,
                )
                continue

            if restored:
                user.deleted_at = None
                user.updated_at = stamp
                self.journal(request, "restored", user)
                done += 1

        if done:
            self.message_user(request, f"Восстановлено: {done}.", messages.SUCCESS)

    @admin.action(description="Удалить навсегда выбранные", permissions=["force_delete"])
    def force_delete(self, request: HttpRequest, queryset: QuerySet[User]) -> HttpResponse | None:
        me = _admin_of(request).id
        # Навсегда — только отключённые, как User::booted у Laravel
        targets = list(queryset.filter(deleted_at__isnull=False).exclude(pk=me))
        skipped = queryset.count() - len(targets)

        if not targets:
            self.message_user(
                request,
                "Навсегда удаляются только отключённые аккаунты — сначала отключите.",
                messages.WARNING,
            )

            return None

        # Сначала — страница подтверждения, как у удаления в Django
        if request.POST.get("post") != "yes":
            return TemplateResponse(
                request,
                "admin/accounts/user/force_delete.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Удалить навсегда?",
                    "opts": self.model._meta,
                    "targets": targets,
                    "skipped": skipped,
                    "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                },
            )

        done = 0

        for user in targets:
            if self._write("delete from users where id = %s and deleted_at is not null", [user.pk]):
                self.journal(request, "force_deleted", user)
                done += 1

        self.message_user(request, f"Удалено навсегда: {done}.", messages.SUCCESS)

        if skipped:
            self.message_user(
                request,
                f"Не удалено: {skipped} — действующие аккаунты и свой навсегда не удаляются.",
                messages.WARNING,
            )

        return None

    # ── Подтвердить почту, выдать пароль, заблокировать; выгрузка ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/act/",
                self.admin_site.admin_view(self.act_view),
                name="accounts_user_act",
            ),
            path(
                "export/",
                self.admin_site.admin_view(self.export_view),
                name="accounts_user_export",
            ),
            *super().get_urls(),
        ]

    def act_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        user = User.objects.filter(pk=int(object_id) if numeric(object_id) else 0).first()

        # «Отключить» и «Восстановить» на странице пользователя — те же
        # действия, что над отмеченными в списке (себя не отключить, занятую
        # почту не восстановить, журнал), и с теми же правами
        if request.method == "POST" and user is not None:
            todo = request.POST.get("act", "")
            page = reverse("savdex_admin:accounts_user_change", args=[user.pk])

            if todo == "disable" and user.deleted_at is None:
                if not self.has_disable_permission(request):
                    raise PermissionDenied

                self.disable(request, User.objects.filter(pk=user.pk))

                return HttpResponseRedirect(page)

            if todo == "restore" and user.deleted_at is not None:
                if not self.has_restore_permission(request):
                    raise PermissionDenied

                self.restore(request, User.objects.filter(pk=user.pk))

                return HttpResponseRedirect(page)

        if (
            request.method != "POST"
            or user is None
            or user.deleted_at is not None
            or not self.has_change_permission(request, user)
        ):
            raise PermissionDenied

        page = reverse("savdex_admin:accounts_user_change", args=[user.pk])
        todo = request.POST.get("act", "")
        before = self.snapshot(user)

        if todo in ("password", "status") and self._staff_guarded(request, user):
            raise PermissionDenied

        if todo == "verify" and user.email_verified_at is None:
            self._verify_email(request, user)
            messages.success(request, f"Почта подтверждена: {user.email}")
        elif todo == "password":
            password = editing.set_password(user)
            messages.warning(request, f"Пароль выдан — передайте лично: {password}")
        elif todo == "status":
            # Заблокировать себя — остаться без доступа к панели
            if user.pk == _admin_of(request).id:
                raise PermissionDenied

            editing.write(user, {"status": "blocked" if user.status == "active" else "active"})
            messages.success(request, "Статус изменён.")
        else:
            return HttpResponseRedirect(page)

        self.journal_changes(request, user, before)

        return HttpResponseRedirect(page)

    def journal_changes(self, request: HttpRequest, user: User, before: dict[str, Any]) -> None:
        """
        Как AuditObserver::updated у User: изменившиеся поля; смена статуса
        на «заблокирован» и обратно — «blocked» и «unblocked».
        """
        after = self.snapshot(user)
        changed = {
            k: v for k, v in after.items() if before.get(k) != v and k not in ("updated_at",)
        }

        if not changed:
            return

        self.journal(
            request,
            audit.update_action(before, changed),
            user,
            {"before": {k: before.get(k) for k in changed}, "after": changed},
        )

    def _verify_email(self, request: HttpRequest, user: User) -> None:
        """
        Ручное подтверждение (§6.3 ТЗ): снимает ограничение на публикацию и
        раскрытие контактов — событие в ленте компании и уведомление человеку.
        """
        from savdex.moderation.services import notify_user
        from savdex.web.account_actions import CONFIRM_SKIPPED

        stamp = timezone.now().replace(microsecond=0)
        naive = stamp.replace(tzinfo=None)

        with (
            allowed_writes("users", "activity_events", "companies"),
            connections["default"].cursor() as cursor,
        ):
            # Метка «Не подтверждено» (код пропущен при регистрации) — прочь
            for query in CONFIRM_SKIPPED:
                cursor.execute(query, [user.pk])

            cursor.execute(
                "update users set email_verified_at = %s, updated_at = %s where id = %s",
                [naive, naive, user.pk],
            )

            if user.company_id is not None:
                cursor.execute(
                    "insert into activity_events (company_id, type, tone, message, url, "
                    "created_at, updated_at) values (%s, 'system', 'success', %s, null, %s, %s)",
                    [
                        user.company_id,
                        f"Почта {user.email} подтверждена администратором",
                        naive,
                        naive,
                    ],
                )

        user.email_verified_at = stamp
        notify_user(
            user.pk,
            "system",
            "Почта подтверждена",
            "success",
            None,
            "Администратор подтвердил ваш адрес вручную. Публикация объявлений и "
            "раскрытие контактов доступны.",
        )

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        user = User.objects.filter(pk=int(object_id) if numeric(object_id) else 0).first()
        extra = dict(extra_context or {})

        if user is not None and user.deleted_at is None:
            editable = self.has_change_permission(request, user)
            extra["can_verify"] = editable and user.email_verified_at is None
            guarded = self._staff_guarded(request, user)
            extra["can_password"] = editable and not guarded
            extra["can_status"] = editable and not guarded and user.pk != _admin_of(request).id
            extra["can_disable"] = (
                self.has_disable_permission(request) and user.pk != _admin_of(request).id
            )
        elif user is not None:
            extra["disabled_note"] = self.state(user)
            extra["can_restore"] = self.has_restore_permission(request)

        return super().change_view(request, object_id, form_url, extra)

    def export_view(self, request: HttpRequest) -> HttpResponse:
        """UserExporter: список с отборами экрана, право users.export."""
        if not _admin_of(request).can("users.export"):
            raise PermissionDenied

        from savdex import admin_export

        query = request.GET.copy()
        file_format = query.pop("format", ["xlsx"])[-1]
        request.GET = query  # type: ignore[assignment]
        records = self.get_changelist_instance(request).get_queryset(request).order_by("-id")

        return admin_export.respond(
            request,
            section="users",
            filename="users",
            file_format="csv" if file_format == "csv" else "xlsx",
            columns=USER_EXPORT,
            records=records.iterator(),
        )

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        query = request.GET.urlencode()

        return super().changelist_view(
            request,
            {
                "can_export": _admin_of(request).can("users.export"),
                "export_url": reverse("savdex_admin:accounts_user_export")
                + (f"?{query}" if query else ""),
                "export_sep": "&" if query else "?",
                **(extra_context or {}),
            },
        )

    @staticmethod
    def _write(query: str, params: list[Any]) -> bool:
        """Один запрос к users в своей транзакции; True — строка изменена."""
        connection = connections["default"]

        with (
            transaction.atomic(using=connection.alias),
            connection.cursor() as cursor,
            allowed_writes("users"),
        ):
            cursor.execute(query, params)

            return bool(cursor.rowcount > 0)


#: UserExporter::getColumns
USER_EXPORT: list[tuple[str, Any]] = [
    ("Имя", lambda u: u.name),
    ("Почта", lambda u: u.email),
    ("Телефон", lambda u: u.phone),
    ("Компания", lambda u: getattr(u, "company_name", None)),
    ("Роль в компании", lambda u: "Владелец" if u.company_role == "owner" else "Сотрудник"),
    (
        "Роль в админке",
        lambda u: access.ROLES.get(u.admin_role or "", "Роль не назначена") if u.is_admin else None,
    ),
    ("Почта подтверждена", lambda u: u.email_verified_at),
    ("Статус", lambda u: "Активен" if u.status == "active" else "Заблокирован"),
    ("Последний вход", lambda u: u.last_login_at),
    ("Регистрация", lambda u: u.created_at),
]

# «Роли и права» — в своём модуле; импорт его регистрирует
from savdex.accounts import roles_admin  # noqa: E402, F401
