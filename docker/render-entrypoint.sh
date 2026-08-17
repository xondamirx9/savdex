#!/bin/bash
#
# Запуск контейнера на Render (и любом хостинге, который передаёт PORT).
#
# База может быть двух видов:
#  - SQLite (по умолчанию) — живёт на эфемерном диске и пересоздаётся
#    при каждом деплое; годится только для демо-стенда;
#  - внешний Postgres (DB_CONNECTION=pgsql + DB_URL) — данные постоянные.
# Пустая база в обоих случаях распознаётся одинаково: до миграций
# в ней нет таблицы users.
set -euo pipefail

# Render говорит, на каком порту слушать, через $PORT (по умолчанию 10000).
PORT="${PORT:-10000}"
sed -ri "s/^Listen 80$/Listen ${PORT}/" /etc/apache2/ports.conf
sed -ri "s/<VirtualHost \*:80>/<VirtualHost *:${PORT}>/" /etc/apache2/sites-available/000-default.conf

cd /var/www/html

# Без APP_KEY Laravel не стартует. Постоянный ключ задаётся в панели
# Render (Environment → APP_KEY); пока его нет — живём на временном,
# издержка только в том, что сессии сбрасываются при перезапуске.
if [ -z "${APP_KEY:-}" ]; then
    export APP_KEY="base64:$(php -r 'echo base64_encode(random_bytes(32));')"
    echo "APP_KEY не задан — сгенерирован временный ключ, сессии не переживут перезапуск." >&2
fi

# Публичный адрес сервиса Render кладёт в RENDER_EXTERNAL_URL.
if [ -z "${APP_URL:-}" ] && [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
    export APP_URL="${RENDER_EXTERNAL_URL}"
fi

if [ "${DB_CONNECTION:-sqlite}" = "sqlite" ]; then
    DB_FILE="${DB_DATABASE:-/var/www/html/database/database.sqlite}"
    mkdir -p "$(dirname "$DB_FILE")"
    touch "$DB_FILE"
fi

php artisan package:discover --ansi

FRESH_DB=0
HAS_USERS=$(php artisan tinker --execute='echo Schema::hasTable("users") ? "yes" : "no";' 2>/dev/null | tail -1 || true)
if [ "$HAS_USERS" != "yes" ]; then
    FRESH_DB=1
fi

php artisan migrate --force

# Сидируем только свежую базу, иначе каждый перезапуск плодил бы дубли.
if [ "$FRESH_DB" = "1" ]; then
    php artisan db:seed --force
    if [ "${SEED_DEMO:-false}" = "true" ]; then
        php artisan db:seed --class=DemoDataSeeder --force
    fi
fi

# Администратор заводится из переменных окружения: на хостинге нет
# консоли, где можно было бы выполнить savdex:admin руками. Повторные
# запуски пропускаются — иначе каждый рестарт сбрасывал бы пароль.
if [ -n "${ADMIN_EMAIL:-}" ]; then
    IS_ADMIN=$(php artisan tinker \
        --execute='echo \App\Models\User::where("email", mb_strtolower(trim((string) getenv("ADMIN_EMAIL"))))->where("is_admin", true)->exists() ? "yes" : "no";' \
        2>/dev/null | tail -1 || true)
    if [ "$IS_ADMIN" != "yes" ]; then
        ADMIN_ARGS=("$ADMIN_EMAIL")
        if [ -n "${ADMIN_PASSWORD:-}" ]; then
            ADMIN_ARGS+=(--password "$ADMIN_PASSWORD")
        fi
        php artisan savdex:admin "${ADMIN_ARGS[@]}"
    fi
fi

php artisan storage:link || true
php artisan config:cache
php artisan view:cache
# route:cache не используется: /robots.txt объявлен замыканием,
# а замыкания не сериализуются в кэш маршрутов.

# artisan выше работал от root; веб-серверу нужны права www-data.
chown -R www-data:www-data storage bootstrap/cache database

# База может лежать вне проекта — на постоянном диске (DB_DATABASE).
# Смонтированный диск принадлежит root, и без прав www-data сайт
# падает на первой же записи: «attempt to write a readonly database».
if [ "${DB_CONNECTION:-sqlite}" = "sqlite" ]; then
    chown -R www-data:www-data "$(dirname "$DB_FILE")"
fi

exec "$@"
