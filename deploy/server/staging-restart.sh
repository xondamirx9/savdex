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
compose logs --tail 60 app 2>&1 | redact >&2 || true
exit 1
