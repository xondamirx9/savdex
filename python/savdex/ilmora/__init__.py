"""
Регистрация в ILMORA через Savdex.

ILMORA — внешний демо-сайт маркетплейса абонементов в учебные центры
(своего бэкенда пока нет). Форма /register/ilmora-register на Savdex
принимает заявку и сохраняет её в ilmora_registrations; аккаунт Savdex
не заводится и вход не выполняется. Заявки видит раздел админки
«ILMORA — регистрации» (право ilmora.view, savdex/access.py).

- form.py — проверка полей (её же повторяет браузер);
- views.py — страница, отправка формы и страница оферты;
- admin.py — раздел админки, выгрузка в Excel и CSV;
- offer/ — текст публичной оферты и заявления (ru и uz).
"""

from __future__ import annotations

import os

#: Сайт ILMORA — кнопка «Перейти в ILMORA» после заявки. Сменится —
#: переменная окружения ILMORA_URL, код трогать не нужно
DEFAULT_URL = "https://maftunashareef.github.io/ilmora-demo/"


def site_url() -> str:
    """Адрес ILMORA: ILMORA_URL из окружения, иначе демо-сайт."""
    return (os.environ.get("ILMORA_URL") or "").strip() or DEFAULT_URL
