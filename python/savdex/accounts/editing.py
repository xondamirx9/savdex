"""
Правка пользователей в админке Django (этап 6) — вместо UserForm и
действий UsersTable Filament.

- Форма: имя, почта (уникальна среди действующих, хранится строчными,
  как сеттер email у User), телефон, язык, компания и роль в ней; доступ
  в админку, роль и личные права — только с правом roles.edit (иначе
  граница между администратором и суперадмином существует до первой
  попытки её обойти); статус. У чужой учётки сотрудника без roles.edit
  почта, пароль и статус не правятся — иначе администратор вошёл бы под
  суперадмином, выдав ему пароль.
- Новый пользователь: пароль генерируется (администратор придумал бы
  слабый и одинаковый для всех), показывается один раз, смена при первом
  входе — по умолчанию.
- «Подтвердить почту» (users.edit): событие в ленте компании и
  уведомление человеку; «Выдать пароль» — новый показывается один раз,
  смена при входе обязательна; «Заблокировать» / «Разблокировать» —
  не себя.

Запись — прямыми запросами только в поля формы (роль savdex_django
правит лишь выданные столбцы users), журнал — как AuditObserver у User.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django import forms
from django.db import connection
from django.utils import timezone

from savdex import access
from savdex.accounts.models import User
from savdex.admins import generate_password, hash_password
from savdex.guards import allowed_writes

#: Языки интерфейса — как в UserForm
LOCALES = {"ru": "Русский", "uz": "Oʻzbekcha", "en": "English", "zh": "中文", "tr": "Türkçe"}

#: User::ROLE_OWNER, ::ROLE_MANAGER
COMPANY_ROLES = {"owner": "Владелец", "manager": "Сотрудник"}

#: Поля формы, которые пишутся в users
FORM_COLUMNS = (
    "name",
    "email",
    "phone",
    "locale",
    "company_id",
    "company_role",
    "is_admin",
    "admin_role",
    "status",
    "admin_permissions",
)


def grantable() -> list[tuple[str, str]]:
    """AdminAccess::grantable: права хоть одной роли, по порядку разделов."""
    found: dict[str, str] = {}

    for role in access._MATRIX:
        for ability in access.abilities_for(role):
            section, _, action = ability.partition(".")
            found[ability] = (
                f"{access.SECTIONS.get(section, section)} · {access.ACTIONS.get(action, action)}"
            )

    order = list(access.SECTIONS)

    return sorted(
        found.items(),
        key=lambda item: (
            order.index(item[0].split(".")[0]) if item[0].split(".")[0] in order else len(order),
            item[0],
        ),
    )


def _companies() -> list[tuple[int, str]]:
    with connection.cursor() as cursor:
        cursor.execute("select id, name from companies where deleted_at is null order by name, id")

        return [(int(pk), str(name)) for pk, name in cursor.fetchall()]


class UserForm(forms.ModelForm):  # type: ignore[type-arg]
    name = forms.CharField(label="Имя", max_length=120)
    email = forms.EmailField(label="Почта", max_length=190)
    phone = forms.CharField(label="Телефон", max_length=20, required=False, empty_value=None)
    locale = forms.ChoiceField(label="Язык интерфейса", choices=list(LOCALES.items()))
    company_id = forms.TypedChoiceField(
        label="Компания",
        coerce=int,
        required=False,
        empty_value=None,
        help_text="Пусто — человек ещё не завёл компанию",
    )
    company_role = forms.ChoiceField(label="Роль в компании", choices=list(COMPANY_ROLES.items()))
    is_admin = forms.BooleanField(
        label="Доступ в панель управления",
        required=False,
        help_text="Отдельно от роли: снимает доступ целиком",
    )
    admin_role = forms.ChoiceField(
        label="Роль в админке",
        required=False,
        choices=[("", "—"), *access.ROLES.items()],
        help_text="Роль задаёт базовый набор прав. Разбор ролей — в docs/admin-roles.md",
    )
    status = forms.ChoiceField(
        label="Статус", choices=[("active", "Активен"), ("blocked", "Заблокирован")]
    )
    grant = forms.MultipleChoiceField(
        label="Выдать дополнительно",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    revoke = forms.MultipleChoiceField(
        label="Отобрать у роли",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Отзыв сильнее выдачи: право в обоих списках не достанется никому",
    )
    password = forms.CharField(
        label="Пароль",
        max_length=72,
        min_length=8,
        help_text="Передайте лично. Человек обязан сменить его при первом входе.",
    )
    must_change_password = forms.BooleanField(
        label="Требовать смену пароля при входе", required=False, initial=True
    )

    #: Поля, которые этому сотруднику можно показать и принять (ставит
    #: раздел). Объявленные поля Django оставляет в форме, даже если их нет
    #: на странице, — без этого присланное «is_admin» записалось бы
    allowed: ClassVar[frozenset[str] | None] = None

    class Meta:
        model = User
        fields = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        instance: User = self.instance

        if self.allowed is not None:
            for name in list(self.fields):
                if name not in self.allowed:
                    del self.fields[name]

        if "company_id" in self.fields:
            company = self.fields["company_id"]
            assert isinstance(company, forms.TypedChoiceField)
            company.choices = [("", "—"), *_companies()]

        for name in ("grant", "revoke"):
            if name in self.fields:
                field = self.fields[name]
                assert isinstance(field, forms.MultipleChoiceField)
                field.choices = grantable()

        if instance.pk is None:
            if "password" in self.fields:
                self.fields["password"].initial = generate_password(12)

            self.fields["locale"].initial = "ru"
            self.fields["company_role"].initial = "owner"
            self.fields["status"].initial = "active"

            return

        permissions = (
            instance.admin_permissions if isinstance(instance.admin_permissions, dict) else {}
        )

        for name in FORM_COLUMNS:
            if name in self.fields and name != "admin_permissions":
                self.fields[name].initial = getattr(instance, name)

        if "grant" in self.fields:
            self.fields["grant"].initial = list(permissions.get("grant") or [])
            self.fields["revoke"].initial = list(permissions.get("revoke") or [])

    def clean_email(self) -> str:
        email = str(self.cleaned_data["email"]).strip().lower()
        twins = User.objects.filter(email__iexact=email, deleted_at__isnull=True)

        if self.instance.pk is not None:
            twins = twins.exclude(pk=self.instance.pk)

        # Среди действующих: адрес отключённого аккаунта свободен
        if twins.exists():
            raise forms.ValidationError("Такая почта уже занята.")

        return email

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}

        if "is_admin" in self.fields and data.get("is_admin") and not data.get("admin_role"):
            self.add_error("admin_role", "Выберите роль в админке.")

        return data

    def columns(self) -> dict[str, Any]:
        """Значения столбцов users из формы — только из полей, что в ней есть."""
        data = self.cleaned_data
        values: dict[str, Any] = {
            name: data.get(name) for name in FORM_COLUMNS if name in self.fields
        }

        if "grant" in self.fields:
            grant = list(data.get("grant") or [])
            revoke = list(data.get("revoke") or [])
            values["admin_permissions"] = {"grant": grant, "revoke": revoke}

        if "is_admin" in values:
            values["is_admin"] = bool(values["is_admin"])

        if "admin_role" in values and not values["admin_role"]:
            values["admin_role"] = None

        return values


def write(user: User, values: dict[str, Any], *, password: str | None = None) -> None:
    """
    Новый — insert (с паролем), прежний — update только присланных полей;
    объект получает записанные значения (для журнала).
    """
    stamp = timezone.now().replace(microsecond=0)
    naive = stamp.replace(tzinfo=None)
    written = {
        column: json.dumps(value, ensure_ascii=False)
        if column == "admin_permissions" and value is not None
        else value
        for column, value in values.items()
    }

    with allowed_writes("users"), connection.cursor() as cursor:
        if user.pk is None:
            assert password is not None
            row = {
                **written,
                "password": hash_password(password),
                "must_change_password": user.must_change_password,
                "created_at": naive,
                "updated_at": naive,
            }
            cursor.execute(
                f"insert into users ({', '.join(row)}) values ({', '.join(['%s'] * len(row))}) "
                "returning id",
                list(row.values()),
            )
            user.pk = int(cursor.fetchone()[0])
            user.created_at = stamp
        else:
            sets = ", ".join(f"{column} = %s" for column in written)
            cursor.execute(
                f"update users set {sets}, updated_at = %s where id = %s",
                [*written.values(), naive, user.pk],
            )

    for column, value in values.items():
        setattr(user, column, value)

    user.updated_at = stamp


def set_password(user: User) -> str:
    """«Выдать пароль»: новый, 12 знаков без символов, смена при входе обязательна."""
    password = generate_password(12)
    stamp = timezone.now().replace(microsecond=0, tzinfo=None)

    with allowed_writes("users"), connection.cursor() as cursor:
        cursor.execute(
            "update users set password = %s, must_change_password = true, updated_at = %s "
            "where id = %s",
            [hash_password(password), stamp, user.pk],
        )

    user.must_change_password = True

    return password
