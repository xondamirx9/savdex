#!/bin/bash
#
# Тестовый сервер — заново, на демо-данных: база и загруженные файлы
# стираются, схема и справочники создаются заново, затем придуманные
# компании, объявления и отзывы (manage.py demo, python/savdex/demo.py).
#
#   staging-reset.sh
#
# Запускает .github/workflows/staging.yml (галочка «сбросить на
# демо-данные») от пользователя deploy, после выкладки. Копии боевой базы
# на тестовом больше нет: письма и SMS отсюда уходят по-настоящему, а
# демо-учётки — с почтами-заглушками (.test), на которые сайт не пишет.
# Данные — на диске самой машины: база в /opt/savdex/pg, файлы —
# в /opt/savdex/data.
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
COMPOSE_FILE=$SRC/deploy/staging/compose.yml
TAG=$(cat "$APP_HOME/current-tag" 2>/dev/null || true)

if [ -z "$TAG" ]; then
    echo "ОШИБКА: на машине нет выложенной версии — сначала выкладка (deploy.sh)." >&2
    exit 1
fi

compose() {
    SAVDEX_TAG="$TAG" docker compose -f "$COMPOSE_FILE" --env-file "$ENV_DIR/compose.env" "$@"
}

# Журнал Actions публичный: из строк журнала убираются пароли в адресах
# (postgresql://user:pass@), значения ключей и токенов, длинные секреты,
# почты и телефоны (база может быть копией боевой)
redact() {
    sed -E \
        -e 's#(://)[^/@[:space:]]+@#\1[скрыто]@#g' \
        -e 's/(Bearer|Basic)[[:space:]]+[[:alnum:]._~+\/=-]+/\1 [скрыто]/g' \
        -e 's/((key|token|secret|passw[a-z]*|pwd|auth[a-z]*|signature|dsn)[[:alnum:]_-]*[\x22\x27]?[[:space:]]*[:=][[:space:]]*[\x22\x27]?)[^[:space:]\x22\x27,;&]+/\1[скрыто]/Ig' \
        -e 's/[0-9]{6,}:[[:alnum:]_-]{30,}/[токен]/g' \
        -e 's/[[:alnum:]+\/_-]{32,}={0,2}/[скрыто]/g' \
        -e 's/[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}/[почта]/g' \
        -e 's/\+?[0-9][0-9 ()-]{7,}[0-9]/[номер]/g'
}

psql_db() {
    compose exec -T db psql -v ON_ERROR_STOP=1 -U savdex "$@"
}

wait_healthy() {
    local container status
    container=$(compose ps -q app)
    for _ in $(seq 1 60); do
        status=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)
        case "$status" in
            healthy) return 0 ;;
            unhealthy|missing) return 1 ;;
        esac
        sleep 10
    done
    return 1
}

echo "── Сайт останавливается"
compose stop app

echo "── База пересоздаётся"
psql_db -d postgres -c "drop database if exists savdex with (force)"
psql_db -d postgres -c "create database savdex owner savdex"
# Права роли сайта на саму базу (deploy/postgres-initdb) — для новой базы
# заново; права на таблицы выдаёт схема при запуске
psql_db -d savdex -c "grant connect on database savdex to savdex_django" \
    -c "grant usage on schema public to savdex_django"

echo "── Загруженные файлы стираются"
# Файлы принадлежат www-data контейнера — стирает сам контейнер
compose run --rm --no-deps -T --entrypoint sh app \
    -c 'rm -rf /var/data/storage/public /var/data/storage/private /var/data/storage/schedule.json'

echo "── Сайт запускается: схема и справочники заново"
compose up -d app
if ! wait_healthy; then
    echo "ОШИБКА: сайт не поднялся на пустой базе. Последние строки журнала:" >&2
    compose logs --tail 60 app 2>&1 | redact >&2 || true
    exit 1
fi

echo "── Демо-данные"
# Под владельцем базы — как разовый запуск migrate (docker/render-entrypoint.sh)
compose exec -T -u www-data app sh -c \
    'cd /var/www/html && DJANGO_DATABASE_URL="$DB_URL" python/.venv/bin/python python/manage.py demo'

# Отметка «боевых данных здесь нет»: только с ней staging.yml переносит
# на тестовый ключи почты и SMS (письма отсюда пойдут по-настоящему)
date -Iseconds > "$APP_HOME/demo-data"

echo "── Готово: тестовый сервер на демо-данных"
