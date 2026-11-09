from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "savdex.settings")

application = get_wsgi_application()


def _refuse_without_rate_limits() -> None:
    """
    Ограничения частоты (вход, регистрация, формы — web/forms.py, _throttle)
    считают только в файловом кэше: с другим хранилищем они молча
    выключены, и замок от перебора паролей не держит. Боевой и тестовый
    сайт без них не запускаются — здесь, в коде, а не только в образе
    (Dockerfile) и скрипте запуска (render-entrypoint.sh). Команды
    manage.py запросов не принимают, им проверка не нужна.
    """
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    from savdex import laravel_cache

    if not settings.DEBUG and not laravel_cache.is_file_store():
        raise ImproperlyConfigured(
            f"CACHE_STORE={os.environ.get('CACHE_STORE', 'database')} — ограничения "
            "частоты работают только с CACHE_STORE=file. Сайт не запускается."
        )


_refuse_without_rate_limits()
