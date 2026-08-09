#!/bin/bash
#
# Запуск контейнера на Render (и любом хостинге, который передаёт PORT).
#
# Диск у Render эфемерный: при каждом деплое и пробуждении контейнер
# начинается с чистого образа. Поэтому база создаётся и наполняется
# прямо здесь — свежий SQLite-файл распознаётся по нулевому размеру.
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

FRESH_DB=0
if [ "${DB_CONNECTION:-sqlite}" = "sqlite" ]; then
    DB_FILE="${DB_DATABASE:-/var/www/html/database/database.sqlite}"
    if [ ! -s "$DB_FILE" ]; then
        FRESH_DB=1
        mkdir -p "$(dirname "$DB_FILE")"
        touch "$DB_FILE"
    fi
fi

php artisan package:discover --ansi
php artisan migrate --force

# Сидируем только свежую базу, иначе каждый перезапуск плодил бы дубли.
if [ "$FRESH_DB" = "1" ]; then
    php artisan db:seed --force
    if [ "${SEED_DEMO:-false}" = "true" ]; then
        php artisan db:seed --class=DemoDataSeeder --force
    fi
fi

php artisan storage:link || true
php artisan config:cache
php artisan view:cache
# route:cache не используется: /robots.txt объявлен замыканием,
# а замыкания не сериализуются в кэш маршрутов.

# artisan выше работал от root; веб-серверу нужны права www-data.
chown -R www-data:www-data storage bootstrap/cache database

exec "$@"
