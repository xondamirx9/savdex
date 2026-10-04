"""
Журнал действий — admin_actions глазами Django (этап 6), только чтение.

Пишут в журнал обе админки (Django — через audit.record, Laravel — через
AdminLog и AuditObserver), поэтому таблица остаётся общей и дописываемой
(APPEND_ONLY_SHARED); раздел только показывает. Записи журнала не
изменяются и не удаляются — как AdminAction::booted у Laravel.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.catalog import LaravelJSONField, UTCDateTimeField

#: AdminAction::ACTIONS
ACTIONS = {
    "created": "Создание",
    "updated": "Изменение",
    "deleted": "Удаление",
    "force_deleted": "Удаление навсегда",
    "restored": "Восстановление",
    "approved": "Одобрение",
    "rejected": "Отклонение",
    "returned": "Возврат на исправление",
    "hidden": "Скрытие",
    "blocked": "Блокировка",
    "unblocked": "Разблокировка",
    "granted": "Выдача прав",
    "revoked": "Отзыв прав",
    "exported": "Выгрузка",
    "downloaded": "Скачивание",
    "imported": "Загрузка",
    "refunded": "Возврат средств",
    "paid": "Проведение оплаты",
    "sent": "Отправка",
}


class AdminAction(models.Model):
    """App\\Models\\AdminAction: кто, когда, что и с чем."""

    user_id = models.BigIntegerField(null=True)
    user_name = models.CharField("кто", max_length=120)
    user_role = models.CharField(max_length=20, null=True)
    action = models.CharField("что сделал", max_length=40, choices=list(ACTIONS.items()))
    section = models.CharField("раздел", max_length=40)
    subject_type = models.CharField(max_length=255, null=True)
    subject_id = models.BigIntegerField(null=True)
    subject_label = models.CharField("с чем", max_length=200, null=True)
    changes = LaravelJSONField(null=True)
    note = models.TextField("формулировка", null=True)
    ip = models.CharField("адрес", max_length=45, null=True)
    created_at = UTCDateTimeField("когда")

    class Meta:
        managed = False
        db_table = "admin_actions"
        verbose_name = "запись журнала"
        verbose_name_plural = "журнал действий"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{ACTIONS.get(self.action, self.action)}: {self.subject_label or '—'}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Записи журнала действий не изменяются.")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise RuntimeError("Записи журнала действий не удаляются.")
