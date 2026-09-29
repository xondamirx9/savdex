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

Правка полей пользователя — в Filament: здесь раздел только для чтения
плюс эти три действия. Права — раздел users в AdminAccess; каждое
действие — строка журнала admin_actions, как AuditObserver у Laravel
(отключение — deleted, восстановление — restored, навсегда —
force_deleted).
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db import IntegrityError, connections, transaction
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from savdex import access
from savdex.accounts.models import STATUSES, User
from savdex.adminsite import SavdexModelAdmin, _admin_of, register
from savdex.catalog import now
from savdex.guards import allowed_writes


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
    title_list = "Пользователи"
    title_change = "Пользователь"

    list_display = ("name", "email", "company", "state", "role", "created_at", "last_login_at")
    list_filter = (StateFilter,)
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
        # Аккаунты заводит регистрация, администраторов — Filament и команда admin
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        # Правка полей — в Filament: здесь просмотр и действия ниже
        return False

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

    @admin.display(description="компания")
    def company(self, obj: User) -> str:
        return getattr(obj, "company_name", None) or "—"

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
