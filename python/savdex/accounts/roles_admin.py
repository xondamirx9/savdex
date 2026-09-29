"""
«Роли и права» в админке Django (этап 6) — вместо страницы Filament Roles.

Список сотрудников (is_admin): роль, сколько прав всего, личные
исключения, статус, последний вход; отбор по роли. На странице
сотрудника:

- «Роль» (roles.edit) — с описанием, что роль открывает;
- «Личные права» (roles.edit, не у суперадмина) — выдать и отобрать
  поверх роли; отзыв сильнее выдачи;
- «Что доступно» — права по разделам: от роли и лично;
- «Отключить доступ» (roles.delete) — роль и личные права сохраняются:
  вернуть доступ — «Выдать доступ» тому же человеку.

«Выдать доступ» (roles.create) — существующему пользователю площадки.
Последнего действующего суперадмина нельзя ни понизить, ни отключить:
панель без владельца чинится только руками в базе. Каждое решение —
строка журнала «Выдача прав» / «Отзыв прав», как у Filament, и перед ней
«изменено» раздела «Пользователи» (AuditObserver у User).
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from savdex import access, audit
from savdex.accounts import editing
from savdex.accounts.models import User
from savdex.adminsite import SavdexModelAdmin, _admin_of, register


class StaffMember(User):
    """Сотрудник админки — тот же users, другой раздел прав (roles)."""

    class Meta:
        proxy = True
        verbose_name = "сотрудник"
        verbose_name_plural = "роли и права"


def _permissions(user: User) -> dict[str, list[str]]:
    raw = user.admin_permissions if isinstance(user.admin_permissions, dict) else {}

    return {
        "grant": [a for a in raw.get("grant") or [] if isinstance(a, str)],
        "revoke": [a for a in raw.get("revoke") or [] if isinstance(a, str)],
    }


def _staff(user: User) -> access.Admin:
    return access.Admin(
        id=user.pk,
        name=user.name,
        email=user.email,
        is_admin=user.is_admin,
        role=user.admin_role,
        status=user.status,
        permissions=_permissions(user),
    )


def describe_role(role: str) -> str:
    """Roles::describeRole: какие разделы открывает роль."""
    if role == access.SUPERADMIN:
        return "Все разделы без исключения, включая те, что появятся позже."

    sections = list(dict.fromkeys(a.split(".")[0] for a in access.abilities_for(role)))

    if not sections:
        return "Ничего — роль не найдена."

    return ", ".join(access.SECTIONS.get(s, s) for s in sections) + "."


def personal_summary(user: User) -> str:
    """Roles::personalSummary: «—», «+2», «−1», «+2 / −1»."""
    permissions = _permissions(user)
    grant, revoke = len(permissions["grant"]), len(permissions["revoke"])

    if grant == 0 and revoke == 0:
        return "—"

    if revoke == 0:
        return f"+{grant}"

    if grant == 0:
        return f"−{revoke}"

    return f"+{grant} / −{revoke}"


def ability_rows(user: User) -> list[tuple[str, list[str], list[str]]]:
    """Roles::abilityRows: по разделам — что от роли, что выдано лично."""
    from_role = set(access.abilities_for(user.admin_role))
    rows: dict[str, tuple[list[str], list[str]]] = {}

    for ability in _staff(user).abilities():
        section, _, action = ability.partition(".")
        name = access.SECTIONS.get(section, section)
        label = access.ACTIONS.get(action, action)
        rows.setdefault(name, ([], []))[0 if ability in from_role else 1].append(label)

    return [(name, *rows[name]) for name in sorted(rows)]


def _flatten(permissions: dict[str, list[str]]) -> str:
    """Roles::flatten: «выдано: …; отозвано: …» или «нет»."""
    parts = [
        f"{word}: {', '.join(permissions[key])}"
        for key, word in (("grant", "выдано"), ("revoke", "отозвано"))
        if permissions.get(key)
    ]

    return "; ".join(parts) if parts else "нет"


def _last_superadmin(user: User, new_role: str | None) -> bool:
    """Roles::mayChange наоборот: теряет ли панель последнего суперадмина."""
    if (
        not (user.is_admin and user.admin_role == access.SUPERADMIN)
        or new_role == access.SUPERADMIN
    ):
        return False

    return (
        not User.objects.filter(
            is_admin=True, admin_role=access.SUPERADMIN, status="active", deleted_at__isnull=True
        )
        .exclude(pk=user.pk)
        .exists()
    )


class RoleFilter(admin.SimpleListFilter):
    title = "роль"
    parameter_name = "role"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return list(access.ROLES.items())

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.filter(admin_role=self.value()) if self.value() else queryset


class GrantForm(forms.Form):
    email = forms.EmailField(
        label="Почта пользователя",
        help_text="Доступ выдаётся существующему пользователю площадки — заводить вторую "
        "учётку незачем",
    )
    admin_role = forms.ChoiceField(label="Роль", choices=list(access.ROLES.items()))

    def clean_email(self) -> User:
        email = str(self.cleaned_data["email"]).strip().lower()
        user = User.objects.filter(email__iexact=email, deleted_at__isnull=True).first()

        if user is None:
            raise forms.ValidationError("Такого пользователя нет.")

        if user.is_admin:
            raise forms.ValidationError("У него уже есть доступ в панель.")

        return user


@register(StaffMember, section="roles")
class RolesAdmin(SavdexModelAdmin):
    laravel_model = "App\\Models\\User"
    title_list = "Роли и права"
    title_change = "Сотрудник"
    change_form_template = "admin/accounts/staffmember/change_form.html"
    change_list_template = "admin/accounts/staffmember/change_list.html"

    list_display = ("member", "role", "abilities", "personal", "state", "last_login_at")
    list_filter = (RoleFilter,)
    search_fields = ("name", "email")
    ordering = ("name", "id")
    fields = ("member", "role", "abilities", "personal", "state", "last_login_at")
    readonly_fields = fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        return super().get_queryset(request).filter(is_admin=True, deleted_at__isnull=True)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    # ── Список ──

    @admin.display(description="сотрудник", ordering="name")
    def member(self, obj: User) -> str:
        return format_html("{}<br><small>{}</small>", obj.name, obj.email)

    @admin.display(description="роль", ordering="admin_role")
    def role(self, obj: User) -> str:
        return access.ROLES.get(obj.admin_role or "", "Роль не назначена")

    @admin.display(description="прав всего")
    def abilities(self, obj: User) -> str:
        staff = _staff(obj)

        return "все" if staff.is_superadmin else str(len(staff.abilities()))

    @admin.display(description="лично")
    def personal(self, obj: User) -> str:
        return personal_summary(obj)

    @admin.display(description="статус", ordering="status")
    def state(self, obj: User) -> str:
        return "Активен" if obj.status == "active" else "Заблокирован"

    # ── Действия ──

    def get_urls(self) -> list[Any]:
        return [
            path(
                "grant/",
                self.admin_site.admin_view(self.grant_view),
                name="accounts_staffmember_grant",
            ),
            path(
                "<path:object_id>/act/",
                self.admin_site.admin_view(self.act_view),
                name="accounts_staffmember_act",
            ),
            *super().get_urls(),
        ]

    def _log(
        self,
        request: HttpRequest,
        action: str,
        user: User,
        changes: dict[str, Any] | None,
        note: str | None = None,
    ) -> None:
        audit.record(
            connection,
            action=action,
            section="roles",
            actor=_admin_of(request),
            subject_type=self.laravel_model,
            subject_id=user.pk,
            subject_label=audit.label(self.attributes(user), "User", user.pk),
            changes=changes,
            note=note,
            ip=audit.client_ip(request),
        )

    def _write(self, request: HttpRequest, user: User, values: dict[str, Any]) -> None:
        """
        forceFill()->save() у Filament: запись и строка «изменено» раздела
        «Пользователи» (AuditObserver у User) — до строки о выдаче прав.
        """
        from savdex.accounts.admin import UserAdmin

        users = self.admin_site._registry[User]
        assert isinstance(users, UserAdmin)
        before = users.snapshot(user)
        editing.write(user, values)
        users.journal_changes(request, user, before)

    def grant_view(self, request: HttpRequest) -> HttpResponse:
        """«Выдать доступ»: существующему пользователю, с ролью."""
        if not _admin_of(request).can("roles.create"):
            raise PermissionDenied

        form = GrantForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            user: User = form.cleaned_data["email"]
            role = form.cleaned_data["admin_role"]
            self._write(request, user, {"is_admin": True, "admin_role": role})
            self._log(
                request,
                "granted",
                user,
                {"after": {"admin_role": role}},
                f"Выдан доступ в панель: {access.ROLES.get(role, role)}",
            )
            messages.success(request, "Доступ выдан.")

            return HttpResponseRedirect(reverse("savdex_admin:accounts_staffmember_changelist"))

        return TemplateResponse(
            request,
            "admin/accounts/staffmember/grant.html",
            {
                **self.admin_site.each_context(request),
                "title": "Выдать доступ",
                "opts": self.model._meta,
                "form": form,
                "roles": [
                    (code, label, describe_role(code)) for code, label in access.ROLES.items()
                ],
            },
        )

    def act_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        # Только сотрудники, как таблица Filament: права клиента площадки
        # раздаются через «Выдать доступ», а не по прямому адресу
        user = User.objects.filter(
            pk=int(object_id) if object_id.isdigit() else 0,
            deleted_at__isnull=True,
            is_admin=True,
        ).first()
        staff = _admin_of(request)

        if request.method != "POST" or user is None:
            raise PermissionDenied

        page = reverse("savdex_admin:accounts_staffmember_change", args=[user.pk])
        todo = request.POST.get("act", "")

        if todo == "role":
            if not staff.can("roles.edit"):
                raise PermissionDenied

            role = request.POST.get("admin_role", "")

            if role not in access.ROLES:
                return HttpResponseRedirect(page)

            if _last_superadmin(user, role):
                messages.error(
                    request,
                    "Это последний суперадмин. Сначала назначьте суперадминов кого-то ещё, "
                    "иначе панель останется без владельца.",
                )

                return HttpResponseRedirect(page)

            previous_role = user.admin_role
            self._write(request, user, {"admin_role": role})
            self._log(
                request,
                "granted",
                user,
                {"before": {"admin_role": previous_role}, "after": {"admin_role": role}},
            )
            messages.success(request, "Роль изменена.")
        elif todo == "rights":
            if not staff.can("roles.edit") or user.admin_role == access.SUPERADMIN:
                raise PermissionDenied

            allowed = {code for code, _ in editing.grantable()}
            was = _permissions(user)
            now_ = {
                "grant": [a for a in request.POST.getlist("grant") if a in allowed],
                "revoke": [a for a in request.POST.getlist("revoke") if a in allowed],
            }
            self._write(request, user, {"admin_permissions": now_})
            self._log(
                request,
                "granted",
                user,
                {"before": {"права": _flatten(was)}, "after": {"права": _flatten(now_)}},
            )
            messages.success(request, "Личные права сохранены.")
        elif todo == "access":
            if not staff.can("roles.delete"):
                raise PermissionDenied

            if user.is_admin and _last_superadmin(user, None):
                messages.error(
                    request,
                    "Это последний суперадмин. Сначала назначьте суперадминов кого-то ещё.",
                )

                return HttpResponseRedirect(page)

            self._write(request, user, {"is_admin": False})
            self._log(
                request,
                "revoked",
                user,
                {"before": {"доступ в панель": "есть"}, "after": {"доступ в панель": "нет"}},
            )
            messages.success(request, "Доступ отключён.")

            return HttpResponseRedirect(reverse("savdex_admin:accounts_staffmember_changelist"))

        return HttpResponseRedirect(page)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        user = User.objects.filter(pk=int(object_id) if object_id.isdigit() else 0).first()
        staff = _admin_of(request)
        extra = dict(extra_context or {})

        if user is not None:
            permissions = _permissions(user)
            extra.update(
                {
                    "rows": ability_rows(user),
                    "roles": [
                        (code, label, describe_role(code)) for code, label in access.ROLES.items()
                    ],
                    "current_role": user.admin_role,
                    "can_role": staff.can("roles.edit"),
                    "can_rights": staff.can("roles.edit") and user.admin_role != access.SUPERADMIN,
                    "can_access": staff.can("roles.delete"),
                    "grantable": [
                        (code, label, code in permissions["grant"], code in permissions["revoke"])
                        for code, label in editing.grantable()
                    ],
                    "stamp": timezone.now(),
                }
            )

        return super().change_view(request, object_id, form_url, extra)

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:  # noqa: ANN401
        return super().changelist_view(
            request,
            {
                "can_grant": _admin_of(request).can("roles.create"),
                "grant_url": reverse("savdex_admin:accounts_staffmember_grant"),
                **(extra_context or {}),
            },
        )
