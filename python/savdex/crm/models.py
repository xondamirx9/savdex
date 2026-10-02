"""
CRM — таблицы crm_* глазами Django (этап 6). Схема — у Laravel
(managed = False), хозяин записи — Django: кроме разделов админки в эти
таблицы никто не пишет.

Правила моделей App\\Models\\Crm\\*:

- SoftDeletes у всех, кроме коммуникаций: удаление — deleted_at и
  updated_at, строка остаётся; списки её не видят (менеджер Alive).
  Запись разговора удаляется насовсем: «удалённая, но восстановимая»
  история переговоров — история, которой нельзя верить.
- Кто завёл контакт и задачу — created_by, кто записал разговор —
  author_id; ставит раздел при создании.
- Сделка (Deal::saving): выиграна или проиграна — дата закрытия ставится
  сама, если её нет; вернулась в работу — снимается.
- Задача и разговор привязаны к лиду или сделке полиморфно, как у
  Eloquent: subject_type — имя класса Laravel, subject_id — номер.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from savdex.accounts.models import User
from savdex.catalog import Timestamped, UTCDateTimeField, now


class Alive(models.Manager):  # type: ignore[type-arg]
    """SoftDeletingScope: удалённые не видны."""

    def get_queryset(self) -> models.QuerySet[Any]:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleting(Timestamped):
    """SoftDeletes::runSoftDelete: deleted_at и updated_at — одно время."""

    deleted_at = UTCDateTimeField(null=True, editable=False)

    objects = Alive()
    everything = models.Manager()

    class Meta:
        abstract = True

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        stamp = now()
        type(self).everything.filter(pk=self.pk).update(deleted_at=stamp, updated_at=stamp)
        self.deleted_at = self.updated_at = stamp

        return 1, {self._meta.label: 1}


class Company(models.Model):
    """Компания площадки — только для выбора и подписи (таблица этапа 5)."""

    name = models.CharField("название", max_length=190)
    deleted_at = UTCDateTimeField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "companies"
        ordering = ("name", "id")

    def __str__(self) -> str:
        return self.name


class Contact(SoftDeleting):
    """App\\Models\\Crm\\Contact: человек у клиента."""

    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    name = models.CharField("имя", max_length=160)
    position = models.CharField("должность", max_length=120, null=True, blank=True)
    phone = models.CharField("телефон", max_length=40, null=True, blank=True)
    email = models.EmailField("почта", max_length=160, null=True, blank=True)
    telegram = models.CharField(
        "Telegram", max_length=80, null=True, blank=True, help_text="Без @, например ivanov"
    )
    note = models.TextField("заметка", null=True, blank=True)
    created_by = models.BigIntegerField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "crm_contacts"
        verbose_name = "контакт"
        verbose_name_plural = "контакты"
        ordering = ("name", "id")

    def __str__(self) -> str:
        """Contact::label: имя и должность."""
        return f"{self.name}, {self.position}" if self.position else self.name


#: Этапы по умолчанию — те, с которыми заводится воронка (миграция
#: crm_stages). Настоящие этапы — в crm_stages, их правит администратор
#: (savdex/crm/stages.py); здесь — коды, на которых держится код
LEAD_STATUSES = {
    "new": "Новый",
    "working": "В работе",
    "qualified": "Квалифицирован",
    "converted": "Стал сделкой",
    "lost": "Отказ",
}

#: Lead::SOURCES
LEAD_SOURCES = {
    "site": "Форма на сайте",
    "call": "Звонок",
    "email": "Почта",
    "referral": "Рекомендация",
    "event": "Выставка",
    "outbound": "Холодный контакт",
    "other": "Другое",
}

DEAL_STAGES = {
    "new": "Новая",
    "negotiation": "Переговоры",
    "proposal": "Предложение отправлено",
    "won": "Выиграна",
    "lost": "Проиграна",
}

#: Deal::CURRENCIES — подпись суммы
CURRENCIES = {"UZS": "сум", "USD": "$", "EUR": "€", "RUB": "₽"}


def _owner(verbose: str) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        User,
        verbose_name=verbose,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )


def _link(model: type[models.Model] | str, verbose: str) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        model,
        verbose_name=verbose,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )


#: Воронки (crm_stages.pipeline)
PIPELINES = {"leads": "Лиды", "deals": "Сделки"}

#: Колонки доски: в работе, успех, отказ. Закрытые («успех» и «отказ») —
#: по одной на воронку, системные
STAGE_KINDS = {"open": "в работе", "won": "успех", "lost": "отказ"}

#: Системные этапы не удаляются: «new» — вход (с него начинает новый лид
#: и сделка из лида), закрытые — «В сделку», причина отказа, отчёты
SYSTEM_STAGES = {"leads": ("new", "converted", "lost"), "deals": ("new", "won", "lost")}


class Stage(Timestamped):
    """
    Этап воронки — колонка доски лидов или сделок (savdex/crm/board.py).

    Код этапа лежит в crm_leads.status / crm_deals.stage. fields — поля
    окна при переводе на этап (каталог — savdex/crm/stages.FIELDS):
    {"owner": "required", "comment": "optional"}. limit_days — сколько
    дней на этапе нормально; дольше — карточка на доске красная.
    """

    pipeline = models.CharField("воронка", max_length=10, choices=list(PIPELINES.items()))
    code = models.CharField("код", max_length=20, editable=False)
    name = models.CharField("название", max_length=80)
    kind = models.CharField(
        "колонка", max_length=10, default="open", choices=list(STAGE_KINDS.items()), editable=False
    )
    position = models.IntegerField("порядок", default=0, editable=False)
    limit_days = models.PositiveIntegerField(
        "сколько дней нормально",
        null=True,
        blank=True,
        help_text="Карточка, которая лежит на этапе дольше, на доске красная. Пусто — не следить",
    )
    fields = models.JSONField("поля окна", default=dict, editable=False)

    class Meta:
        managed = False
        db_table = "crm_stages"
        verbose_name = "этап воронки"
        verbose_name_plural = "этапы воронки"
        ordering = ("pipeline", "position", "id")

    def __str__(self) -> str:
        return f"{PIPELINES.get(self.pipeline, self.pipeline)}: {self.name}"

    @property
    def is_system(self) -> bool:
        return self.code in SYSTEM_STAGES.get(self.pipeline, ())

    @property
    def is_open(self) -> bool:
        return self.kind == "open"


class OnStage(SoftDeleting):
    """
    Карточка доски: лид или сделка. stage_changed_at — когда карточка
    пришла на свой этап («дней на этапе», закрытые за неделю); ставится
    само при каждой смене этапа, откуда бы она ни пришла — доска, форма,
    «Взять себе», «В сделку».
    """

    #: Столбец с кодом этапа
    stage_field: ClassVar[str]

    stage_changed_at = UTCDateTimeField("на этапе с", null=True, editable=False)

    class Meta:
        abstract = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Этап, с которым запись прочитана: сменился ли он к записи
        self._stage_loaded = self.__dict__.get(self.stage_field)

    def save(self, *args: Any, **kwargs: Any) -> None:
        current = getattr(self, self.stage_field)

        if (
            self._state.adding
            or self.stage_changed_at is None
            or current != getattr(self, "_stage_loaded", current)
        ):
            self.stage_changed_at = now()

        super().save(*args, **kwargs)
        self._stage_loaded = current


class Lead(OnStage):
    """App\\Models\\Crm\\Lead: заявка, которую ещё не превратили в сделку."""

    stage_field = "status"

    title = models.CharField("что нужно клиенту", max_length=200)
    source = models.CharField(
        "откуда", max_length=40, default="site", choices=list(LEAD_SOURCES.items())
    )
    company = _link(Company, "компания")
    contact = _link(Contact, "контакт")
    contact_name = models.CharField("имя обратившегося", max_length=160, null=True, blank=True)
    contact_phone = models.CharField("телефон", max_length=40, null=True, blank=True)
    contact_email = models.EmailField("почта", max_length=160, null=True, blank=True)
    owner = _owner("ответственный")
    status = models.CharField("этап", max_length=20, default="new")
    lost_reason = models.TextField("причина отказа", null=True, blank=True)
    note = models.TextField("заметка", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "crm_leads"
        verbose_name = "лид"
        verbose_name_plural = "лиды"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        """Lead::scopeOpen."""
        return self.status not in ("converted", "lost")

    def contact_label(self) -> str | None:
        """Lead::contactName: контакт из справочника — иначе имя из заявки."""
        contact = self.contact

        if contact is not None and contact.deleted_at is None:
            return str(contact.name)

        return self.contact_name


class Deal(OnStage):
    """App\\Models\\Crm\\Deal: сделка с суммой и этапом."""

    stage_field = "stage"

    title = models.CharField("сделка", max_length=200)
    company = _link(Company, "компания")
    contact = _link(Contact, "контакт")
    lead = _link(Lead, "из лида")
    owner = _owner("ответственный")
    amount = models.BigIntegerField("сумма", default=0)
    currency = models.CharField(
        "валюта", max_length=3, default="UZS", choices=list(CURRENCIES.items())
    )
    stage = models.CharField("этап", max_length=20, default="new")
    expected_close_at = models.DateField(
        "ожидаемое закрытие",
        null=True,
        blank=True,
        help_text="Когда рассчитываете закрыть — по этой дате видны просроченные",
    )
    closed_at = UTCDateTimeField("закрыта", null=True, blank=True, editable=False)
    lost_reason = models.TextField("причина проигрыша", null=True, blank=True)
    note = models.TextField("заметка", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "crm_deals"
        verbose_name = "сделка"
        verbose_name_plural = "сделки"
        ordering = ("expected_close_at", "id")

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        """Deal::scopeOpen."""
        return self.stage not in ("won", "lost")

    def money(self) -> str:
        """Deal::money: «46 386 000 сум»."""
        sign = CURRENCIES.get(self.currency, self.currency)

        return f"{self.amount:,}".replace(",", " ") + " " + sign

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Deal::saving: дата закрытия — сама."""
        if not self.is_open and self.closed_at is None:
            self.closed_at = now()

        if self.is_open:
            self.closed_at = None

        super().save(*args, **kwargs)


#: Полиморфная привязка (morphTo): имя класса Laravel → модель
SUBJECTS: dict[str, tuple[str, type[SoftDeleting]]] = {
    "App\\Models\\Crm\\Lead": ("Лид", Lead),
    "App\\Models\\Crm\\Deal": ("Сделка", Deal),
}


class WithSubject(models.Model):
    """nullableMorphs('subject'): к лиду, к сделке или ни к чему."""

    subject_type = models.CharField(max_length=255, null=True, blank=True, editable=False)
    subject_id = models.BigIntegerField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def subject(self) -> SoftDeleting | None:
        """$record->subject: удалённый в корзину — как и у Eloquent, не найден."""
        kind = SUBJECTS.get(self.subject_type or "")

        if kind is None or self.subject_id is None:
            return None

        cache: dict[tuple[str, int], SoftDeleting | None] = self.__dict__.setdefault(
            "_subject_cache", {}
        )
        key = (str(self.subject_type), int(self.subject_id))

        if key not in cache:
            cache[key] = kind[1].objects.filter(pk=self.subject_id).first()

        return cache[key]

    def subject_title(self) -> str | None:
        subject = self.subject()

        return str(subject) if subject is not None else None


class Task(SoftDeleting, WithSubject):
    """App\\Models\\Crm\\Task: что сделать и к какому сроку."""

    title = models.CharField("что сделать", max_length=200)
    description = models.TextField("что именно", null=True, blank=True)
    assignee = _owner("исполнитель")
    created_by = models.BigIntegerField(null=True, editable=False)
    due_at = UTCDateTimeField("срок", null=True, blank=True)
    done_at = UTCDateTimeField("выполнена", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "crm_tasks"
        verbose_name = "задача"
        verbose_name_plural = "задачи"
        ordering = ("due_at", "id")

    def __str__(self) -> str:
        return self.title

    @property
    def is_done(self) -> bool:
        return self.done_at is not None

    @property
    def is_overdue(self) -> bool:
        """
        Task::isOverdue: выполненная просроченной не считается, даже если
        сделана позже срока — список «горит» показывает то, что ещё
        требует действий.
        """
        return not self.is_done and self.due_at is not None and self.due_at < now()


#: Communication::TYPES
COMMUNICATION_TYPES = {
    "call": "Звонок",
    "email": "Письмо",
    "meeting": "Встреча",
    "message": "Сообщение",
}


class Communication(Timestamped, WithSubject):
    """App\\Models\\Crm\\Communication: запись состоявшегося разговора."""

    type = models.CharField(
        "что было", max_length=20, default="call", choices=list(COMMUNICATION_TYPES.items())
    )
    happened_at = UTCDateTimeField("когда")
    summary = models.CharField("о чём", max_length=200)
    body = models.TextField(
        "как прошло",
        null=True,
        blank=True,
        help_text="Что просили, о чём договорились, что обещали и к какому сроку",
    )
    author = _owner("кто записал")
    contact = _link(Contact, "с кем")

    class Meta:
        managed = False
        db_table = "crm_communications"
        verbose_name = "запись разговора"
        verbose_name_plural = "коммуникации"
        ordering = ("-happened_at", "-id")

    def __str__(self) -> str:
        return self.summary
