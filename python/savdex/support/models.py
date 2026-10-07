"""
Обращения в поддержку — support_tickets и support_messages глазами Django
(этап 6). Схема — у Laravel (managed = False), хозяин записи — Django:
раздел админки и обращение владельца о смене данных компании
(web/company_info_actions.py).

Правила моделей App\\Models\\Support\\*:

- обращение — SoftDeletes (удаление — deleted_at и updated_at);
- Ticket::saving: закрыто — дата закрытия ставится сама, если её нет;
  открыто снова — снимается;
- кто обратился — из учётной записи, иначе имя из обращения;
- сообщение без мягкого удаления; внутренняя заметка клиенту не видна.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.accounts.models import User
from savdex.catalog import LaravelJSONField, Timestamped, UTCDateTimeField, now
from savdex.crm.models import Company, SoftDeleting

STATUS_OPEN = "open"
STATUS_WORKING = "working"
STATUS_WAITING = "waiting"
STATUS_CLOSED = "closed"

#: Ticket::STATUSES
STATUSES = {
    STATUS_OPEN: "Открыто",
    STATUS_WORKING: "В работе",
    STATUS_WAITING: "Ждёт ответа клиента",
    STATUS_CLOSED: "Закрыто",
}

#: Ticket::CHANNELS
CHANNELS = {
    "form": "Форма на сайте",
    "email": "Почта",
    "phone": "Звонок",
    "chat": "Чат",
}

#: Ticket::PRIORITIES
PRIORITIES = {"low": "Низкий", "normal": "Обычный", "high": "Срочный"}


def _user(verbose: str, related: str = "+") -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        User,
        verbose_name=verbose,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name=related,
    )


class Ticket(SoftDeleting):
    """App\\Models\\Support\\Ticket: вопрос клиента."""

    subject = models.CharField("тема", max_length=200)
    user = _user("пользователь")
    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    author_name = models.CharField("имя из обращения", max_length=160, null=True, blank=True)
    author_email = models.EmailField("почта из обращения", max_length=160, null=True, blank=True)
    assignee = _user("кто ведёт")
    status = models.CharField(
        "статус", max_length=20, default=STATUS_OPEN, choices=list(STATUSES.items())
    )
    channel = models.CharField(
        "откуда пришло", max_length=20, default="form", choices=list(CHANNELS.items())
    )
    priority = models.CharField(
        "важность", max_length=10, default="normal", choices=list(PRIORITIES.items())
    )
    last_reply_at = UTCDateTimeField("последний ответ", null=True, blank=True, editable=False)
    closed_at = UTCDateTimeField("закрыто", null=True, blank=True, editable=False)

    class Meta:
        managed = False
        db_table = "support_tickets"
        verbose_name = "обращение"
        verbose_name_plural = "обращения"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.subject

    @property
    def is_closed(self) -> bool:
        return self.status == STATUS_CLOSED

    def author(self) -> str:
        """Ticket::author: из учётной записи, иначе из самого обращения."""
        user = self.user

        # Отключённый (SoftDeletes) — как у Eloquent, не найден
        if user is not None and user.deleted_at is None:
            return str(user.name)

        return self.author_name or "неизвестно"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Ticket::saving: дата закрытия ставится и снимается сама."""
        if self.is_closed and self.closed_at is None:
            self.closed_at = now()

        if not self.is_closed:
            self.closed_at = None

        super().save(*args, **kwargs)


class Message(Timestamped):
    """App\\Models\\Support\\Message: сообщение в обращении."""

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="messages",
    )
    author = _user("автор")
    from_staff = models.BooleanField(default=False)
    is_internal = models.BooleanField("внутренняя заметка", default=False)
    body = models.TextField("текст")
    #: Вложения письма: [{"name", "path" (в storage/app/private), "size", "type"}]
    attachments = LaravelJSONField(null=True, blank=True)
    #: Message-ID письма: входящего — от дублей, ответа — для цепочки
    email_message_id = models.CharField(max_length=255, null=True, blank=True)
    #: Ответ ушёл клиенту письмом — когда; не ушёл — почему
    emailed_at = UTCDateTimeField(null=True, blank=True)
    email_error = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "support_messages"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return self.body[:60]
