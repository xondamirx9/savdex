# syntax=docker/dockerfile:1

# Сайт и админку обслуживает Django (python/), Apache только отдаёт
# готовые файлы из public/ и передаёт остальное Django
# (docker/apache-python.conf). PHP в проекте больше нет
# (docs/migration-to-python.md, этап 8).

# --- Фронтенд: собираем Vite-бандл ----------------------------------------
# Классы Tailwind берутся из resources/.
FROM node:22-alpine AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY vite.config.ts tsconfig.json ./
COPY resources ./resources
COPY public ./public
RUN npm run build

# --- Рабочий образ: Apache + Django ----------------------------------------
# Debian trixie — та же система (и тот же python3 3.13), что была под
# образом php:8.3-apache. proxy и proxy_http — передача Django;
# libmagic1 — тип загруженного файла по содержимому (savdex/web/filetype.py).
# Модель Apache — event (умолчание Debian): без PHP процесс на запрос
# не нужен, хватает потоков. Журналы — в вывод контейнера, как было
# у образа php.
FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 python3 libmagic1 ca-certificates tzdata \
    && a2enmod rewrite headers proxy proxy_http \
    && a2dissite 000-default \
    && ln -sfT /dev/stderr /var/log/apache2/error.log \
    && ln -sfT /dev/stdout /var/log/apache2/access.log \
    && ln -sfT /dev/stdout /var/log/apache2/other_vhosts_access.log \
    && rm -rf /var/lib/apt/lists/* /var/www/html/index.html

WORKDIR /var/www/html

# Нужное Django из корня репозитория (settings.LARAVEL_ROOT): юридические
# документы, картинки и фавикон из public/, собранный фронтенд, storage/.
# Локальные public/storage и public/build в образ не попадают: первая —
# ссылка на загрузки (её ставит render-entrypoint.sh), второй собирается
# стадией assets
COPY --chown=www-data:www-data resources/legal ./resources/legal
COPY --chown=www-data:www-data public ./public
RUN rm -rf public/storage public/build
COPY --from=assets --chown=www-data:www-data /app/public/build ./public/build
RUN mkdir -p storage/app/public storage/app/private storage/framework/cache/data storage/logs \
    && chown -R www-data:www-data storage

# --- Python ----------------------------------------------------------------
# Зависимости ставятся ровно по python/uv.lock: та же версия uv, что
# у разработчиков, --frozen запрещает тихо пересобрать список пакетов.
# Без пакетов разработки (pytest, mypy): на сервере они не нужны.
# Окружение — python/.venv; владелец root, www-data только читает
# и запускает. Байт-код собран заранее: писать его в read-only venv
# при каждом запуске некому. Стили и скрипты админки Django собираются
# в python/staticfiles — их отдаёт сам Django (whitenoise) по /py/static/.
COPY python ./python
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
RUN cd python \
    && UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --no-cache --compile-bytecode \
        --python /usr/bin/python3 \
    && .venv/bin/python -c "import django, openpyxl, psycopg, httpx, bcrypt, whitenoise, PIL, cryptography, gunicorn" \
    && .venv/bin/python manage.py collectstatic --noinput --verbosity 0

COPY docker/apache-python.conf /etc/apache2/conf-available/savdex-python.conf
COPY docker/apache-site.conf /etc/apache2/sites-available/savdex.conf
RUN a2enconf savdex-python && a2ensite savdex
COPY docker/render-entrypoint.sh /usr/local/bin/render-entrypoint
COPY docker/apache2-foreground /usr/local/bin/apache2-foreground
RUN chmod +x /usr/local/bin/render-entrypoint /usr/local/bin/apache2-foreground

ENV APP_ENV=production \
    APP_DEBUG=false \
    LOG_CHANNEL=stderr \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["render-entrypoint"]
CMD ["apache2-foreground"]
