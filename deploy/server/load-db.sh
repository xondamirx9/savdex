#!/bin/bash
#
# Копия боевой базы — на тестовый сервер: база тестового стирается и
# заполняется из дампа (pg_dump --format=custom), сайт перезапускается.
#
#   load-db.sh /opt/savdex/restore/prod.dump
#
# Запускает .github/workflows/staging.yml (галочка «копия боевой базы»)
# от пользователя deploy. Дамп после загрузки удаляется: в нём личные
# данные пользователей.
#
# Писем и сообщений настоящим людям тестовый сервер не шлёт: почта —
# в журнал (MAIL_MAILER=log), ящики рассылки и поддержки, Telegram,
# WhatsApp и Uzum не настроены — их ключи только в окружении боевого.
set -euo pipefail

DUMP=${1:?путь к дампу}
APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
TAG=$(cat "$APP_HOME/current-tag")

trap 'rm -f "$DUMP"' EXIT

compose() {
    SAVDEX_TAG="$TAG" docker compose -f "$SRC/deploy/staging/compose.yml" \
        --env-file "$ENV_DIR/compose.env" "$@"
}

# Журнал Actions публичный: почты и телефоны из копии в него не попадают
redact() {
    sed -E 's/[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}/[почта]/g; s/\+?[0-9][0-9 ()-]{7,}[0-9]/[номер]/g'
}

psql_db() {
    compose exec -T db psql -v ON_ERROR_STOP=1 -U savdex "$@"
}

echo "── Сайт останавливается на время загрузки"
compose stop app

echo "── База тестового пересоздаётся"
psql_db -d postgres -c "drop database if exists savdex with (force)"
psql_db -d postgres -c "create database savdex owner savdex"

echo "── Роли из копии"
# Права (GRANT) переносятся как на боевой. Но права одной таблицы идут
# одной командой: если в ней есть служебная роль Render, которой здесь
# нет, PostgreSQL отбрасывает всю команду — вместе с правами роли сайта
# savdex_django. Поэтому все роли, упомянутые в правах копии, заводятся
# заранее — без права входа
roles=$(compose exec -T db pg_restore --schema-only --no-owner -f - < "$DUMP" \
    | grep -oE '( TO | FROM | FOR ROLE )[a-z_][a-z0-9_]*[;, ]' \
    | sed -E 's/^ (TO|FROM|FOR ROLE) //; s/[;, ]$//' | sort -u)
for role in $roles; do
    psql_db -d postgres -q -c "do \$\$ begin if not exists (select from pg_roles where rolname = '$role') then create role \"$role\" nologin; end if; end \$\$"
done
echo "   ${roles//$'\n'/, }"

echo "── Загрузка копии"
log=$(mktemp)
if ! compose exec -T db pg_restore --no-owner --role=savdex -U savdex -d savdex < "$DUMP" 2> "$log"; then
    if grep -v -E '^pg_restore: (while PROCESSING TOC|from TOC entry)|^pg_restore: error: could not execute query: ERROR: +role ".*" does not exist|^pg_restore: warning: errors ignored on restore|^Command was: |^(GRANT|REVOKE|ALTER DEFAULT) |^[[:space:]]*$' "$log" | grep -q .; then
        echo "ОШИБКА: копия загрузилась не целиком:" >&2
        redact < "$log" | tail -n 30 >&2
        rm -f "$log"
        exit 1
    fi
fi
rm -f "$log"

# Права роли сайта — ещё и по снимку схемы, на случай если на боевой их
# выдавали иначе. Строки про таблицы, которых в копии нет, пропускаются
compose exec -T db psql -q -U savdex -d savdex -f - \
    < "$SRC/python/savdex/bootstrap/grants.sql" > /dev/null 2>&1 || true

for table in users companies listings; do
    n=$(psql_db -d savdex -Atq -c "select count(*) from $table")
    echo "   $table: $n"
    if [ "$n" -lt 1 ]; then
        echo "ОШИБКА: после загрузки таблица $table пуста." >&2
        exit 1
    fi
done

echo "── Сайт запускается"
compose start app
container=$(compose ps -q app)
for _ in $(seq 1 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)
    case "$status" in
        healthy)
            echo "── Готово: на тестовом сервере копия боевой базы"
            exit 0
            ;;
        unhealthy|missing)
            break
            ;;
    esac
    sleep 10
done

echo "ОШИБКА: сайт с копией базы не поднялся. Последние строки журнала:" >&2
compose logs --tail 60 app 2>&1 | redact >&2 || true
exit 1
