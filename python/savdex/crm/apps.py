from __future__ import annotations

from django.apps import AppConfig


class CrmConfig(AppConfig):
    """CRM: контакты, лиды, сделки, задачи, коммуникации (этап 6)."""

    name = "savdex.crm"
    label = "crm"
    verbose_name = "CRM"
