#!/bin/bash
#
# Агент мониторинга Grafana Alloy на боевой машине (docs/monitoring.md,
# шаг 2): поставить или обновить, затем проверить, что цифры доходят до
# Grafana Cloud. Запускает .github/workflows/prod.yml от deploy при
# каждой выкладке, на каждой машине.
#
#   SAVDEX_MACHINE=web|admin|db monitoring.sh install < ключи
#   monitoring.sh check
#
# install — на вход строки GRAFANA_PROM_URL=…, GRAFANA_PROM_USER=…,
#   GRAFANA_ALLOY_TOKEN=… (переменные и секреты GitHub); в журнал не
#   выводятся. На машине базы — ещё адрес базы для роли savdex_monitor
#   (её и пароль создаёт prod-db.sh). Настройки агента — base.alloy и
#   файл роли машины из deploy/monitoring/alloy.
# check — через минуту-другую после install: агент жив и Grafana Cloud
#   принимает цифры (неверный токен — отказ, его видно здесь).
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
CONF=$APP_HOME/monitoring
COMPOSE_FILE=$SRC/deploy/monitoring/compose.yml

# Страница агента — на 127.0.0.1:12345. curl на машине может и не быть,
# поэтому запрос — средствами bash; на выходе — тело ответа
alloy_get() {
    # shellcheck disable=SC2016
    timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/12345 \
        && printf "GET %s HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n" "$1" >&3 \
        && cat <&3' _ "$1" 2>/dev/null | tr -d '\r' | sed '1,/^$/d'
}

# Не «| grep -q»: grep выходит на первом совпадении, запрос получает
# SIGPIPE, и pipefail валит верную проверку
alloy_ready() {
    local body
    body=$(alloy_get /-/ready)
    [[ "$body" == *"Alloy is ready"* ]]
}

check() {
    if ! alloy_ready; then
        echo "ОШИБКА: агент мониторинга не отвечает. Последние строки журнала:" >&2
        docker compose -f "$COMPOSE_FILE" logs --tail 30 alloy 2>&1 \
            | grep -v -i -E 'token|password' >&2 || true
        return 1
    fi
    # Сколько рядов отправлено и сколько Grafana Cloud отвергла (4xx —
    # неверный адрес или токен — повторять бесполезно, это и есть отказ)
    local sent failed
    read -r sent failed < <(alloy_get /metrics | awk '
        /^prometheus_remote_storage_samples_total\{/ { s += $NF }
        /^prometheus_remote_storage_samples_failed_total\{/ { f += $NF }
        END { printf "%d %d\n", s, f }')
    if [ "$failed" -gt 0 ]; then
        echo "ОШИБКА: Grafana Cloud не принимает цифры ($failed отвергнуто) — проверьте GRAFANA_PROM_URL, GRAFANA_PROM_USER и токен GRAFANA_ALLOY_TOKEN." >&2
        docker compose -f "$COMPOSE_FILE" logs --tail 10 alloy 2>&1 \
            | grep -i -E 'error|status' | grep -v -i -E 'token|password' | cut -c1-300 >&2 || true
        return 1
    fi
    if [ "$sent" -eq 0 ]; then
        echo "ОШИБКА: агент ещё ничего не отправил — первые цифры уходят через минуту после запуска." >&2
        return 1
    fi
    echo "── Мониторинг работает: отправлено $sent значений, отказов нет"
}

case "${1:-}" in
    check)
        check
        exit
        ;;
    install) ;;
    *)
        echo "Как: SAVDEX_MACHINE=web|admin|db monitoring.sh install < ключи | monitoring.sh check" >&2
        exit 1
        ;;
esac

MACHINE=${SAVDEX_MACHINE:?роль машины: web, admin или db}
case "$MACHINE" in
    web|admin|db) ;;
    *)
        echo "ОШИБКА: неизвестная роль машины «$MACHINE»" >&2
        exit 1
        ;;
esac

# ── Ключи Grafana Cloud ────────────────────────────────────────────
umask 077
mkdir -p "$ENV_DIR"
tmp=$(mktemp "$ENV_DIR/monitoring.env.XXXXXX")
trap 'rm -f "$tmp"' EXIT
{
    echo "# Пишет deploy/server/monitoring.sh при каждой выкладке — не править руками"
    # Только свои имена и значения без пробелов и кавычек: файл читает
    # docker compose как env_file, без разбора кавычек
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ "$line" =~ ^GRAFANA_(PROM_URL|PROM_USER|ALLOY_TOKEN)=[^[:space:]\"\']+$ ]]; then
            printf '%s\n' "$line"
        fi
    done
    echo "SAVDEX_MACHINE=$MACHINE"
} > "$tmp"
for key in GRAFANA_PROM_URL GRAFANA_PROM_USER GRAFANA_ALLOY_TOKEN; do
    if ! grep -q "^$key=" "$tmp"; then
        echo "ОШИБКА: нет $key (или в нём пробелы или кавычки) — агент не ставится." >&2
        exit 1
    fi
done

if [ "$MACHINE" = db ]; then
    # Адрес базы для роли мониторинга: пароль и частный адрес машины —
    # из compose.env (prod-db.sh)
    password=$(sed -n 's/^MONITOR_DB_PASSWORD=//p' "$ENV_DIR/compose.env" 2>/dev/null || true)
    db_ip=$(sed -n 's/^DB_BIND=//p' "$ENV_DIR/compose.env" 2>/dev/null || true)
    if [ -z "$password" ] || [ -z "$db_ip" ]; then
        echo "ОШИБКА: в $ENV_DIR/compose.env нет MONITOR_DB_PASSWORD или DB_BIND — сначала prod-db.sh." >&2
        exit 1
    fi
    echo "PG_MONITOR_DSN=postgresql://savdex_monitor:${password}@${db_ip}:5432/savdex?sslmode=disable" >> "$tmp"
fi
mv "$tmp" "$ENV_DIR/monitoring.env"
trap - EXIT

# ── Настройки агента: общий файл и файл роли ───────────────────────
# Тот же каталог, а не новый: контейнер видит его через bind mount
umask 022
mkdir -p "$CONF"
find "$CONF" -mindepth 1 -maxdepth 1 -name '*.alloy' -delete
cp "$SRC/deploy/monitoring/alloy/base.alloy" "$CONF/"
if [ -f "$SRC/deploy/monitoring/alloy/$MACHINE.alloy" ]; then
    cp "$SRC/deploy/monitoring/alloy/$MACHINE.alloy" "$CONF/"
fi

echo "── Агент мониторинга ($MACHINE): $(cd "$CONF" && echo *.alloy)"
# Пересоздаётся каждый раз: ключи (env_file) читаются только при создании
docker compose -f "$COMPOSE_FILE" up -d --force-recreate --remove-orphans
for _ in $(seq 1 30); do
    alloy_ready && break
    sleep 2
done
if ! alloy_ready; then
    echo "ОШИБКА: агент не поднялся. Последние строки журнала:" >&2
    docker compose -f "$COMPOSE_FILE" logs --tail 30 alloy 2>&1 \
        | grep -v -i -E 'token|password' >&2 || true
    exit 1
fi
echo "── Агент запущен"
