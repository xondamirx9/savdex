#!/bin/bash
#
# Превью ветки на машине тестового сервера — preview.savdex.uz
# (deploy/README.md, «Превью веток»): посмотреть ветку до слияния, не
# трогая тестовый. Запускает .github/workflows/preview.yml от
# пользователя deploy.
#
#   preview.sh deploy SHA ВЕТКА [--reset]   выложить коммит ветки в превью
#   preview.sh stop                         выключить превью
#
# Данные превью — свои, демо (manage.py demo), в /opt/savdex/preview:
# - другая ветка или --reset — база и файлы превью с нуля, демо заново;
# - та же ветка ещё раз — данные остаются, новая версия поверх.
#
# Код ветки — в /opt/savdex/preview/src. Сам этот скрипт и preview.yml —
# из основной ветки (workflow кладёт их в /opt/savdex/preview/tooling):
# в старой ветке их может не быть вовсе.
#
# Память машины общая с тестовым. Перед сборкой — проверка, что свободно
# не меньше PREVIEW_MIN_FREE_MB (по умолчанию 800 МБ); меньше — отказ:
# тестовый важнее. Выключенное превью память не занимает.
#
# Переменные: REPO_URL — откуда брать код; PREVIEW_DOMAIN — адрес превью
# (по умолчанию preview.savdex.uz).
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
P=$APP_HOME/preview
SRC=$P/src
ENV_DIR=$P/env
TOOLING=$P/tooling
COMPOSE_FILE=$TOOLING/deploy/staging/preview.yml
SITES=$APP_HOME/env/sites
DOMAIN=${PREVIEW_DOMAIN:-preview.savdex.uz}
MIN_FREE_MB=${PREVIEW_MIN_FREE_MB:-800}

if ! [[ "$DOMAIN" =~ ^[a-z0-9.-]+$ ]]; then
    echo "ОШИБКА: странный адрес превью «$DOMAIN»" >&2
    exit 1
fi

compose() {
    PREVIEW_TAG="$1" docker compose -f "$COMPOSE_FILE" --env-file "$ENV_DIR/compose.env" "${@:2}"
}

# Caddy тестового: он отдаёт и превью
caddy_reload() {
    local container
    container=$(docker ps -q --filter label=com.docker.compose.project=savdex-staging \
        --filter label=com.docker.compose.service=caddy)
    if [ -z "$container" ]; then
        echo "ОШИБКА: Caddy тестового не запущен" >&2
        return 1
    fi
    # Удачная перезагрузка пишет только служебный журнал — он не нужен
    local out
    if ! out=$(docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1); then
        printf '%s\n' "$out" >&2
        echo "ОШИБКА: Caddy не принял настройки" >&2
        return 1
    fi
}

# Превью нет в Caddy, пока новая версия не поднялась: вместо полусобранного
# сайта — «нет такого сайта», а не ошибки
unpublish() {
    if [ -f "$SITES/preview.caddy" ]; then
        rm -f "$SITES/preview.caddy"
        caddy_reload
    fi
}

stop_preview() {
    unpublish
    if [ -s "$ENV_DIR/compose.env" ] && [ -f "$COMPOSE_FILE" ]; then
        compose "$(cat "$P/current-tag" 2>/dev/null || echo none)" down --remove-orphans
    fi
    rm -f "$P/current-tag"
    echo "── Превью выключено, память свободна. Данные ветки $(cat "$P/branch" 2>/dev/null || echo —) — до следующего превью"
}

wait_healthy() {
    local container status
    container=$(compose "$1" ps -q preview-app)
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

case "${1:-}" in
    stop)
        stop_preview
        exit 0
        ;;
    deploy) ;;
    *)
        echo "Как: preview.sh deploy SHA ВЕТКА [--reset] | preview.sh stop" >&2
        exit 1
        ;;
esac

sha=${2:?коммит}
branch=${3:?ветка}
reset=0
[ "${4:-}" = --reset ] && reset=1
: "${REPO_URL:?адрес репозитория}"
if ! [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ОШИБКА: «$sha» — не полный хеш коммита" >&2
    exit 1
fi
tag=${sha:0:12}

# Тестовый должен быть уже выложен с поддержкой превью: общая сеть с
# Caddy и каталог для сайта превью (deploy/staging/compose.yml)
if ! docker network inspect savdex-preview-edge > /dev/null 2>&1 || [ ! -d "$SITES" ]; then
    echo "ОШИБКА: тестовый сервер ещё не готов к превью — сначала выложите на него основную ветку (workflow staging), потом превью." >&2
    exit 1
fi

umask 077
mkdir -p "$ENV_DIR"
# Каталоги данных — открытые на чтение: внутри контейнера в них ходят
# www-data и postgres. Права — только при создании: потом содержимое
# принадлежит пользователям контейнеров
for dir in "$P/data" "$P/pg"; do
    [ -d "$dir" ] || install -d -m 755 "$dir"
done

# ── Ключи и пароли превью: создаются один раз ─────────────────────
secret() { openssl rand -hex 24; }

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

set_var() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

if [ ! -s "$ENV_DIR/compose.env" ]; then
    {
        echo "# Создано preview.sh $(date -Iseconds). Пароли — только на этой машине."
        echo "PREVIEW_HOME=$P"
        echo "POSTGRES_PASSWORD=$(secret)"
        echo "DJANGO_DB_PASSWORD=$(secret)"
    } > "$ENV_DIR/compose.env"
fi
# shellcheck disable=SC1091
. "$ENV_DIR/compose.env"

if [ ! -s "$ENV_DIR/app.env" ]; then
    {
        echo "# Создано preview.sh $(date -Iseconds). Переменные превью ветки."
        echo "APP_ENV=staging"
        echo "APP_KEY=base64:$(openssl rand -base64 32)"
        echo "DB_CONNECTION=pgsql"
        echo "DB_URL=postgresql://savdex:${POSTGRES_PASSWORD}@preview-db:5432/savdex"
        echo "DJANGO_DATABASE_URL=postgresql://savdex_django:${DJANGO_DB_PASSWORD}@preview-db:5432/savdex"
        echo "CACHE_STORE=file"
        echo "LOG_CHANNEL=stderr"
        echo "MAIL_MAILER=log"
        # Память общая с тестовым: без фоновых задач (расписание, перевод,
        # рассылки), два процесса Django
        echo "SAVDEX_BACKGROUND=0"
        echo "PYTHON_WORKERS=2"
    } > "$ENV_DIR/app.env"
fi
set_var "$ENV_DIR/app.env" APP_URL "https://$DOMAIN"
set_var "$ENV_DIR/app.env" DJANGO_ALLOWED_HOSTS "$DOMAIN,127.0.0.1,localhost"
# Cloudflare перед превью нет: адрес посетителя — только из
# X-Forwarded-For, который Caddy пишет сам (python/savdex/audit.py)
set_var "$ENV_DIR/app.env" SAVDEX_CLIENT_IP_HEADERS ""

# Почта и SMS — те же ключи, что у тестового, и только когда тестовый на
# демо-данных (staging.yml переносит их туда только так): данные превью
# тоже демо, письма и коды уходят лишь тем, кто проверяет
if [ -f "$APP_HOME/demo-data" ] && [ -f "$APP_HOME/env/app.env" ]; then
    {
        grep -E '^(MAIL|TELNYX)_[A-Z_]+=' "$APP_HOME/env/app.env" | grep -v '^MAIL_FROM_NAME=' || true
        echo "MAIL_FROM_NAME='SAVDEX (превью)'"
    } | SAVDEX_ENV_FILE="$ENV_DIR/app.env" bash "$TOOLING/deploy/server/env-merge.sh" > /dev/null
fi

# ── Прежнее превью — долой, пока собирается новое ──────────────────
unpublish
old_tag=$(cat "$P/current-tag" 2>/dev/null || true)
if [ -n "$old_tag" ]; then
    echo "── Прежнее превью ($old_tag, ветка $(cat "$P/branch" 2>/dev/null || echo —)) останавливается"
    compose "$old_tag" stop preview-app || true
fi

free_mb=$(( $(awk '/MemAvailable/ {print $2}' /proc/meminfo) / 1024 ))
echo "── Свободно памяти: $free_mb МБ"
if [ "$free_mb" -lt "$MIN_FREE_MB" ]; then
    echo "ОШИБКА: на машине свободно $free_mb МБ, превью нужно не меньше $MIN_FREE_MB. Тестовый важнее — превью не запущено. Может быть, на тестовом как раз идёт сборка — попробуйте через несколько минут; если так всё время — машине нужно больше памяти (UzCloud)." >&2
    exit 1
fi

# ── Код ветки и образ ──────────────────────────────────────────────
# Код — открытым на чтение (umask 022, не 077 выше): образ копирует
# файлы с их правами, а сайт в контейнере работает от www-data — закрытый
# код он не прочитает («No module named 'savdex.wsgi'»)
(
    umask 022
    test -d "$SRC/.git" || git clone --no-checkout --filter=blob:none "$REPO_URL" "$SRC"
    git -C "$SRC" fetch --depth 1 origin "$sha"
    git -C "$SRC" checkout --force --detach FETCH_HEAD
)
# Файлы, которые прежний запуск выложил закрытыми и checkout не трогает
chmod -R go+rX "$SRC"

echo "── Сборка образа savdex-preview:$tag"
# Каждый раз, даже если образ с этим тегом есть: из кэша это секунды, а
# образ с прежними правами файлов не переиспользуется. Одна сборка за
# раз — с тестовым (deploy.sh) тоже
flock "$APP_HOME/build.lock" env DOCKER_BUILDKIT=1 docker build --pull -t "savdex-preview:$tag" "$SRC"

# ── Данные: другая ветка — с нуля ──────────────────────────────────
# Файл branch — ветка, чьи данные сейчас в превью; пишется, когда превью
# поднялось. Нет его (первый раз или прошлый запуск оборвался) — с нуля
fresh=0
if [ "$reset" = 1 ] || [ ! -f "$P/branch" ] || [ "$branch" != "$(cat "$P/branch")" ]; then
    fresh=1
    echo "── Данные превью — с нуля"
    rm -f "$P/branch"
    compose "$tag" down --remove-orphans
    # Файлы базы и загрузок принадлежат пользователям контейнеров —
    # стирает тоже контейнер
    docker run --rm -v "$P/pg:/w/pg" -v "$P/data:/w/data" postgres:18 \
        find /w/pg /w/data -mindepth 1 -delete
fi

# ── Запуск ─────────────────────────────────────────────────────────
echo "── Запуск savdex-preview:$tag"
compose "$tag" up -d --remove-orphans
if ! wait_healthy "$tag"; then
    echo "ОШИБКА: превью не поднялось. Последние строки журнала:" >&2
    compose "$tag" logs --tail 80 preview-app 2>&1 | redact >&2 || true
    # Неподнявшееся превью память не держит
    compose "$tag" stop || true
    exit 1
fi
echo "$tag" > "$P/current-tag"
echo "$branch" > "$P/branch"
echo "$(date -Iseconds) $tag $sha $branch" >> "$P/releases.log"

if [ "$fresh" = 1 ]; then
    echo "── Демо-данные"
    # Под владельцем базы — как на тестовом (staging-reset.sh); $DB_URL —
    # переменная контейнера, раскрывается там
    # shellcheck disable=SC2016
    if ! compose "$tag" exec -T -u www-data preview-app sh -c \
        'cd /var/www/html && DJANGO_DATABASE_URL="$DB_URL" python/.venv/bin/python python/manage.py demo'; then
        # Аннотация на странице запуска в GitHub: вывод идёт в журнал Actions
        echo "::warning title=Демо-данные::не заведены (в ветке нет manage.py demo или он упал) — превью на пустой базе"
    fi
fi

# ── Превью — в Caddy ───────────────────────────────────────────────
cat > "$SITES/preview.caddy" <<CADDY
# Превью $tag — пишет deploy/server/preview.sh, пока превью включено
$DOMAIN {
	import /etc/caddy/auth.caddy

	encode zstd gzip

	# Cloudflare перед сайтом нет: его заголовки с адресом посетителя
	# ставить некому — пришедшие убираются
	request_header -CF-Connecting-IP
	request_header -True-Client-IP

	reverse_proxy preview-app:10000

	log {
		output stdout
		format console
	}
}
CADDY
chmod 644 "$SITES/preview.caddy"
caddy_reload

# Уборка: образ превью — только текущий
docker image ls savdex-preview --format '{{.Tag}}' \
    | grep -v -x "$tag" \
    | xargs -r -I{} docker image rm "savdex-preview:{}" > /dev/null 2>&1 || true

echo "── Готово: https://$DOMAIN — ветка $branch ($tag)"
