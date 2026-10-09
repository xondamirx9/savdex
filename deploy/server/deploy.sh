#!/bin/bash
#
# Выкладка на тестовый сервер: собрать образ из кода, который лежит в
# /opt/savdex/src (его заранее переключает на нужный коммит
# .github/workflows/staging.yml), запустить, дождаться /up.
# Не поднялся — вернуть предыдущую версию и выйти с ошибкой.
#
#   deploy.sh [--password-stdin]
#
# Переменные:
#   SITE_DOMAIN — адрес тестового сайта (по умолчанию staging.savdex.uz);
#   с --password-stdin первая строка ввода — пароль на сайт (логин savdex).
#
# Запускается от пользователя deploy (группа docker). Пароли базы и
# APP_KEY создаются здесь при первой выкладке и с машины не уходят:
# /opt/savdex/env, права 700/600.
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
COMPOSE_FILE=$SRC/deploy/staging/compose.yml
SITE_DOMAIN=${SITE_DOMAIN:-staging.savdex.uz}
AUTH_USER=savdex
KEEP_IMAGES=3

umask 077
mkdir -p "$ENV_DIR"

# KEY=VALUE в файле: заменить строку или дописать
set_var() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

secret() { openssl rand -hex 24; }

# ── Ключи и пароли: создаются один раз ─────────────────────────────
if [ ! -s "$ENV_DIR/compose.env" ]; then
    {
        echo "# Создано deploy.sh $(date -Iseconds). Пароли — только на этой машине."
        echo "SAVDEX_HOME=$APP_HOME"
        echo "POSTGRES_PASSWORD=$(secret)"
        echo "DJANGO_DB_PASSWORD=$(secret)"
    } > "$ENV_DIR/compose.env"
fi
set_var "$ENV_DIR/compose.env" SITE_DOMAIN "$SITE_DOMAIN"

# shellcheck disable=SC1091
. "$ENV_DIR/compose.env"

if [ ! -s "$ENV_DIR/app.env" ]; then
    {
        echo "# Создано deploy.sh $(date -Iseconds). Переменные приложения тестового сервера."
        echo "APP_ENV=staging"
        echo "APP_KEY=base64:$(openssl rand -base64 32)"
        echo "DB_CONNECTION=pgsql"
        # Владелец базы — для схемы при запуске (render-entrypoint),
        # роль Django — для самого сайта
        echo "DB_URL=postgresql://savdex:${POSTGRES_PASSWORD}@db:5432/savdex"
        echo "DJANGO_DATABASE_URL=postgresql://savdex_django:${DJANGO_DB_PASSWORD}@db:5432/savdex"
        echo "CACHE_STORE=file"
        echo "LOG_CHANNEL=stderr"
        # Письма не уходят наружу, а пишутся в журнал
        echo "MAIL_MAILER=log"
    } > "$ENV_DIR/app.env"
fi
set_var "$ENV_DIR/app.env" APP_URL "https://$SITE_DOMAIN"
set_var "$ENV_DIR/app.env" DJANGO_ALLOWED_HOSTS "$SITE_DOMAIN,127.0.0.1,localhost"

# ── Пароль на сайт ─────────────────────────────────────────────────
if [ "${1:-}" = "--password-stdin" ]; then
    IFS= read -r password || true
    # Остальным командам ввод не нужен — и случайно не достанется
    exec </dev/null
    if [ -n "$password" ]; then
        hash=$(printf '%s\n' "$password" | docker run --rm -i caddy:2 caddy hash-password)
        printf 'basic_auth {\n\t%s %s\n}\n' "$AUTH_USER" "$hash" > "$ENV_DIR/auth.caddy"
    fi
    unset password
fi
if [ ! -s "$ENV_DIR/auth.caddy" ]; then
    echo "ОШИБКА: нет пароля на тестовый сайт — задайте секрет STAGING_PASSWORD в GitHub." >&2
    exit 1
fi
# Caddy в контейнере читает файл не от deploy
chmod 644 "$ENV_DIR/auth.caddy"

# ── Сборка ─────────────────────────────────────────────────────────
sha=$(git -C "$SRC" rev-parse HEAD)
tag=${sha:0:12}
echo "── Сборка образа savdex:$tag"
DOCKER_BUILDKIT=1 docker build --pull -t "savdex:$tag" "$SRC"

compose() {
    SAVDEX_TAG="$1" docker compose -f "$COMPOSE_FILE" --env-file "$ENV_DIR/compose.env" "${@:2}"
}

wait_healthy() {
    local container status
    container=$(compose "$1" ps -q app)
    for _ in $(seq 1 "${DEPLOY_WAIT_TRIES:-60}"); do
        status=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)
        case "$status" in
            healthy) return 0 ;;
            unhealthy|missing) return 1 ;;
        esac
        sleep 10
    done
    return 1
}

previous=$(cat "$APP_HOME/current-tag" 2>/dev/null || true)

echo "── Запуск savdex:$tag"
compose "$tag" up -d --remove-orphans

if wait_healthy "$tag"; then
    echo "$tag" > "$APP_HOME/current-tag"
    echo "$(date -Iseconds) $tag $sha" >> "$APP_HOME/releases.log"
    echo "── Готово: https://$SITE_DOMAIN работает на $tag"
else
    echo "ОШИБКА: savdex:$tag не поднялся. Последние строки журнала:" >&2
    compose "$tag" logs --tail 80 app >&2 || true
    if [ -n "$previous" ] && [ "$previous" != "$tag" ]; then
        echo "── Возврат на $previous" >&2
        compose "$previous" up -d --remove-orphans
        wait_healthy "$previous" || echo "ВНИМАНИЕ: и предыдущая версия не поднялась" >&2
    fi
    exit 1
fi

# ── Уборка: текущая, предыдущая и ещё одна версия; кэш сборки — неделя ──
# docker image ls — от новых к старым
docker image ls savdex --format '{{.Tag}}' \
    | grep -v -x -e "$tag" -e "${previous:-$tag}" \
    | tail -n +"$((KEEP_IMAGES - 1))" \
    | xargs -r -I{} docker image rm "savdex:{}" >/dev/null 2>&1 || true
docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
