#!/bin/bash
#
# Машина базы (боевая, Uztelecom): запустить или обновить PostgreSQL,
# поставить резервные копии в расписание.
#
#   prod-db.sh
#
# Запускает .github/workflows/prod.yml от пользователя deploy; код —
# в /opt/savdex/src. Пароли базы создаются здесь при первом запуске и
# с машины уходят только в одну сторону — на машины сайта и админки
# (файл app-db.env, его забирает prod.yml).
#
# Резервные копии (deploy/server/backup.sh) — по cron пользователя
# deploy: база каждую ночь, файлы каждый час; ключи хранилища и пароль
# шифрования — в /opt/savdex/env/backup.env (кладёт prod.yml). Там же
# раз в сутки — чистка общего кэша от просроченного (cache-prune.sh).
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
COMPOSE_FILE=$SRC/deploy/prod/db/compose.yml

umask 077
mkdir -p "$ENV_DIR"

set_var() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

secret() { openssl rand -hex 24; }

# Частный адрес машины — на нём база слушает
DB_IP=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')
if [ -z "$DB_IP" ]; then
    echo "ОШИБКА: не найден частный адрес машины." >&2
    exit 1
fi

if [ ! -s "$ENV_DIR/compose.env" ]; then
    {
        echo "# Создано prod-db.sh $(date -Iseconds). Пароли — только на этой машине и в db.env сайта и админки."
        echo "SAVDEX_HOME=$APP_HOME"
        echo "POSTGRES_PASSWORD=$(secret)"
        echo "DJANGO_DB_PASSWORD=$(secret)"
    } > "$ENV_DIR/compose.env"
fi
set_var "$ENV_DIR/compose.env" DB_BIND "$DB_IP"
# Пароль роли мониторинга (savdex_monitor, ниже) — тоже один раз
if ! grep -q '^MONITOR_DB_PASSWORD=' "$ENV_DIR/compose.env"; then
    echo "MONITOR_DB_PASSWORD=$(secret)" >> "$ENV_DIR/compose.env"
fi

# shellcheck disable=SC1091
. "$ENV_DIR/compose.env"

# Адреса базы для сайта и админки: владелец — для схемы (разовый
# запуск migrate), роль Django — для самого сайта
{
    echo "DB_CONNECTION=pgsql"
    echo "DB_URL=postgresql://savdex:${POSTGRES_PASSWORD}@${DB_IP}:5432/savdex"
    echo "DJANGO_DATABASE_URL=postgresql://savdex_django:${DJANGO_DB_PASSWORD}@${DB_IP}:5432/savdex"
} > "$ENV_DIR/app-db.env"

echo "── База: PostgreSQL на $DB_IP:5432"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_DIR/compose.env" up -d

container=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_DIR/compose.env" ps -q db)
for _ in $(seq 1 30); do
    if [ "$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null)" = healthy ]; then
        break
    fi
    sleep 5
done
if [ "$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null)" != healthy ]; then
    echo "ОШИБКА: база не поднялась. Последние строки журнала:" >&2
    docker logs --tail 40 "$container" >&2 || true
    exit 1
fi

echo "── Роль мониторинга savdex_monitor"
# Для агента мониторинга (deploy/monitoring/alloy/db.alloy): только
# статистика сервера (pg_monitor) — данных таблиц роль не видит. SQL —
# через stdin: пароля нет в списке процессов
docker exec -i "$container" psql -v ON_ERROR_STOP=1 -q -U savdex -d savdex <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'savdex_monitor') THEN
        CREATE ROLE savdex_monitor LOGIN;
    END IF;
END
\$\$;
ALTER ROLE savdex_monitor WITH LOGIN CONNECTION LIMIT 3 PASSWORD '${MONITOR_DB_PASSWORD}';
GRANT pg_monitor TO savdex_monitor;
SQL

echo "── Резервные копии — в расписание"
# Время — по часам машины (Asia/Tashkent, bootstrap.sh). Строки
# SavdEx в crontab заменяются целиком, чужие не трогаются
backup="$SRC/deploy/server/backup.sh"
log="$APP_HOME/backup/backup.log"
mkdir -p "$APP_HOME/backup"
{
    crontab -l 2>/dev/null | grep -v '# savdex-backup' || true
    echo "40 3 * * * bash $backup db >> $log 2>&1 # savdex-backup"
    echo "17 * * * * bash $backup files >> $log 2>&1 # savdex-backup"
    echo "20 4 * * * bash $SRC/deploy/server/cache-prune.sh >> $log 2>&1 # savdex-backup"
} | crontab -
if [ ! -s "$ENV_DIR/backup.env" ]; then
    echo "ВНИМАНИЕ: нет $ENV_DIR/backup.env — копии в хранилище не пойдут (секреты S3_* и BACKUP_PASSPHRASE в GitHub)." >&2
fi

echo "── Готово: база работает, копии в расписании"
