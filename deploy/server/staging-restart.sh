#!/bin/bash
#
# Перезапуск приложения тестового сервера с новыми настройками
# (/opt/savdex/env/app.env — например, после env-merge.sh), той же версии.
#
#   staging-restart.sh
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
COMPOSE_FILE=$APP_HOME/src/deploy/staging/compose.yml
ENV_DIR=$APP_HOME/env
TAG=$(cat "$APP_HOME/current-tag")

compose() {
    SAVDEX_TAG="$TAG" docker compose -f "$COMPOSE_FILE" --env-file "$ENV_DIR/compose.env" "$@"
}

echo "── Перезапуск savdex:$TAG с новыми настройками"
compose up -d --force-recreate app
container=$(compose ps -q app)
for _ in $(seq 1 60); do
    case "$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)" in
        healthy) echo "── Готово"; exit 0 ;;
        unhealthy|missing) break ;;
    esac
    sleep 10
done
echo "ОШИБКА: приложение не поднялось. Последние строки журнала:" >&2
compose logs --tail 60 app >&2 || true
exit 1
