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

# Тарифы — на каждом деплое, а не только на свежей базе: изменение цены
# в сидере иначе не доехало бы до прода. Сидер идемпотентен
# (updateOrCreate по коду тарифа), дублей не плодит.
php artisan db:seed --class=PlanSeeder --force

# Категории — по той же причине: новые разделы (например, «Другое»)
# должны появляться на проде без консоли. Идемпотентен (updateOrCreate
# по slug), существующее не трогает.
php artisan db:seed --class=CategorySeeder --force

# Наполнение витрины: описания пустым карточкам компаний и картинки
# объявлениям без фото. Только дополняет — заполненное не перезаписывает.
# Выключается переменной SEED_SHOWCASE=false, когда живого контента
# станет достаточно.
if [ "${SEED_SHOWCASE:-true}" = "true" ]; then
    php artisan db:seed --class=ShowcaseSeeder --force
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

# Загрузки — на постоянный диск. Контейнер пересоздаётся при каждом
# деплое, и всё, что лежало в storage/app (логотипы компаний, фото
# объявлений, документы), пропадало: «загрузили лого — назавтра его
# нет». Симлинки уводят оба хранилища на смонтированный диск, где
# уже живёт база.
if [ -d /var/data ]; then
    for dir in public private; do
        mkdir -p "/var/data/storage/$dir"
        if [ -d "storage/app/$dir" ] && [ ! -L "storage/app/$dir" ]; then
            cp -a "storage/app/$dir/." "/var/data/storage/$dir/" 2>/dev/null || true
            rm -rf "storage/app/$dir"
        fi
        ln -sfn "/var/data/storage/$dir" "storage/app/$dir"
    done
    # chown -R storage ниже по симлинкам не проходит — цель явно
    chown -R www-data:www-data /var/data/storage
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

# Планировщик. Системного cron на Render нет, а без schedule:run
# объявления не истекают, продвижения не освобождают слоты и месячные
# лимиты не сбрасываются (см. routes/console.php). Фоновый schedule:work
# живёт рядом с веб-сервером; для одного инстанса этого достаточно.
# От www-data, а не root — иначе журнал SQLite получит владельца root,
# и сайт упадёт на первой же записи.
if command -v runuser >/dev/null 2>&1; then
    runuser -u www-data -- php artisan schedule:work >/dev/null 2>&1 &
fi

exec "$@"
