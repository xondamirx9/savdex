#!/bin/bash
#
# Сайт или админка (боевые, Uztelecom): запустить версию образа,
# дождаться /up; не поднялась — вернуть предыдущую и выйти с ошибкой.
#
#   SAVDEX_ROLE=web|admin DB_IP=… ADMIN_IP=… SITE_DOMAIN=… \
#       prod-app.sh <версия> [--migrate] [--password-stdin]
#
# --migrate (машина админки) — до перезапуска разовый запуск migrate:
#   схема, справочники, администратор. Сайт и админка сами схему не
#   трогают (SAVDEX_MIGRATE=0), поэтому изменения базы должны быть
#   совместимы с предыдущей версией кода: какое-то время она работает
#   на машине сайта с новой схемой.
# --password-stdin (машина сайта) — первая строка ввода: пароль на весь
#   сайт (логин savdex), на время репетиции переезда; пустая — без пароля.
#
# Образ savdex:<версия> уже должен быть на машине: его собирает
# prod-build.sh на машине админки и присылает на машину сайта. Адрес
# базы (db.env) и настройки с Render (app.env) кладёт в /opt/savdex/env
# .github/workflows/prod.yml.
set -euo pipefail

TAG=${1:?версия образа}
shift
ROLE=${SAVDEX_ROLE:?роль машины: web или admin}
APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
SITE_DOMAIN=${SITE_DOMAIN:-savdex.uz}
: "${DB_IP:?частный адрес машины базы}" "${ADMIN_IP:?частный адрес машины админки}"
AUTH_USER=savdex
KEEP_IMAGES=3

migrate=0
password_stdin=0
for arg in "$@"; do
    case "$arg" in
        --migrate) migrate=1 ;;
        --password-stdin) password_stdin=1 ;;
        *) echo "Неизвестный параметр: $arg" >&2; exit 1 ;;
    esac
done

case "$ROLE" in
    web) overlay=compose.web.yml ;;
    admin) overlay=compose.admin.yml ;;
    *) echo "Роль — web или admin, а не $ROLE" >&2; exit 1 ;;
esac

umask 077
mkdir -p "$ENV_DIR"

for file in db.env app.env; do
    if [ ! -s "$ENV_DIR/$file" ]; then
        echo "ОШИБКА: нет $ENV_DIR/$file — запустите prod.yml (адрес базы и галочка «настройки с Render»)." >&2
        exit 1
    fi
done
if ! docker image inspect "savdex:$TAG" > /dev/null 2>&1; then
    echo "ОШИБКА: на машине нет образа savdex:$TAG — его присылает prod-build.sh с машины админки." >&2
    exit 1
fi

# Частный адрес этой машины
MY_IP=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')
if [ "$ROLE" = admin ] && [ "$MY_IP" != "$ADMIN_IP" ]; then
    echo "ОШИБКА: у машины админки адрес $MY_IP, а в GitHub (PROD_ADMIN_IP) — $ADMIN_IP: Caddy машины сайта её не найдёт." >&2
    exit 1
fi

# ── Переменные роли ────────────────────────────────────────────────
{
    echo "SAVDEX_HOME=$APP_HOME"
    echo "DB_IP=$DB_IP"
    echo "ADMIN_BIND=$MY_IP"
} > "$ENV_DIR/compose.env"

{
    echo "# Пишет prod-app.sh при каждой выкладке: роль машины $ROLE"
    echo "APP_URL=https://$SITE_DOMAIN"
    echo "DJANGO_ALLOWED_HOSTS=$SITE_DOMAIN,www.$SITE_DOMAIN,127.0.0.1,localhost"
    # Схему меняет только разовый запуск migrate (--migrate)
    echo "SAVDEX_MIGRATE=0"
    # Кэш — общий для сайта и админки, в общей папке на машине базы:
    # правку настроек в админке сайт видит сразу, курсы ЦБ из расписания —
    # тоже. Кэш в базе не годится: с ним выключены ограничения частоты
    echo "CACHE_STORE=file"
    echo "SAVDEX_CACHE_DIR=/var/data/storage/cache"
    # Адрес посетителя (savdex/audit.py) — из X-Forwarded-For, который
    # Caddy пишет сам. Заголовки края сети (CF-Connecting-IP) — у Render,
    # где перед ним Cloudflare; здесь Cloudflare нет — не читать
    echo "SAVDEX_CLIENT_IP_HEADERS="
    if [ "$ROLE" = web ]; then
        # Только посетители: фоновые задачи — на машине админки, адреса
        # админки Caddy отдаёт туда же
        echo "SAVDEX_BACKGROUND=0"
        echo "PYTHON_ADMIN_WORKERS=0"
    else
        # Админка и фоновые задачи (расписание, перевод, письма, сверка).
        # Процесс сайта — один и маленький: на него приходят только /up и
        # проверка контейнера
        echo "PYTHON_WORKERS=1"
        echo "PYTHON_THREADS=2"
        echo "PYTHON_ADMIN_WORKERS=3"
        # Репетиция (адрес не savdex.uz): база — копия боевой, а ключи
        # почты, Telegram и ящика поддержки — настоящие, с Render. Фоновые
        # задачи разослали бы людям письма второй раз и забрали бы письма
        # поддержки из настоящего ящика — поэтому до переезда они
        # выключены: их делает Render
        if [ "$SITE_DOMAIN" != savdex.uz ]; then
            echo "SAVDEX_BACKGROUND=0"
        fi
    fi
} > "$ENV_DIR/role.env"

if [ "$ROLE" = admin ] && [ "$SITE_DOMAIN" != savdex.uz ]; then
    echo "── Репетиция ($SITE_DOMAIN): фоновые задачи выключены — их делает Render"
fi

if [ "$ROLE" = web ]; then
    password=""
    if [ "$password_stdin" = 1 ]; then
        IFS= read -r password || true
    fi
    exec </dev/null
    if [ -n "$password" ]; then
        hash=$(printf '%s\n' "$password" | docker run --rm -i caddy:2 caddy hash-password)
        printf 'basic_auth {\n\t%s %s\n}\n' "$AUTH_USER" "$hash" > "$ENV_DIR/auth.caddy"
        echo "── Сайт закрыт паролем (логин $AUTH_USER)"
    else
        : > "$ENV_DIR/auth.caddy"
    fi
    unset password

    # Тот же файл (не новый): Caddy в контейнере видит его через bind
    # mount, а замена файла переименованием осталась бы ему невидимой
    cat > "$ENV_DIR/Caddyfile" <<CADDY
# Пишет deploy/server/prod-app.sh при каждой выкладке — не править руками
{
	# Счётчики запросов и время ответа — для агента мониторинга
	# (deploy/monitoring/alloy/web.alloy)
	metrics
}

$SITE_DOMAIN {
	import /etc/caddy/auth.caddy
	encode zstd gzip

	# Cloudflare перед сайтом нет: его заголовки с адресом посетителя
	# ставить некому — пришедшие убираются. Адрес — в X-Forwarded-For,
	# его Caddy пишет сам
	request_header -CF-Connecting-IP
	request_header -True-Client-IP

	# Админка — на своей машине (частная сеть). Остальное — сайт.
	# Пока приложение перезапускается (выкладка), его порт закрыт: Caddy
	# держит запрос до минуты и повторяет, а не отвечает посетителю 502
	@admin path /py/admin /py/admin/* /py/login /py/logout
	handle @admin {
		reverse_proxy $ADMIN_IP:10000 {
			lb_try_duration 60s
			lb_try_interval 500ms
		}
	}
	handle {
		reverse_proxy app:10000 {
			lb_try_duration 60s
			lb_try_interval 500ms
		}
	}

	log {
		output stdout
		format console
	}
}

# Цифры Caddy — агенту мониторинга этой же машины: порт 9180 опубликован
# только на 127.0.0.1 (compose.web.yml), снаружи его не видно
http://:9180 {
	metrics
}
CADDY
    if [ "$SITE_DOMAIN" = savdex.uz ]; then
        cat >> "$ENV_DIR/Caddyfile" <<'CADDY'

www.savdex.uz {
	redir https://savdex.uz{uri} permanent
}
CADDY
    fi
    chmod 644 "$ENV_DIR/Caddyfile" "$ENV_DIR/auth.caddy"
else
    exec </dev/null
fi

compose() {
    SAVDEX_TAG="$1" docker compose -f "$SRC/deploy/prod/app/compose.yml" \
        -f "$SRC/deploy/prod/app/$overlay" --env-file "$ENV_DIR/compose.env" "${@:2}"
}

wait_healthy() {
    local container status
    container=$(compose "$1" ps -q app)
    for _ in $(seq 1 "${DEPLOY_WAIT_TRIES:-40}"); do
        status=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)
        case "$status" in
            healthy) return 0 ;;
            unhealthy|missing) return 1 ;;
        esac
        sleep 10
    done
    return 1
}

# Журнал Actions публичный: почты и телефоны заменяются заглушками
redact() {
    sed -E 's/[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}/[почта]/g; s/\+?[0-9][0-9 ()-]{7,}[0-9]/[номер]/g'
}

previous=$(cat "$APP_HOME/current-tag" 2>/dev/null || true)

if [ "$migrate" = 1 ]; then
    echo "── Схема базы: savdex:$TAG migrate"
    if ! compose "$TAG" run --rm --no-deps -T app migrate 2>&1 | redact; then
        echo "ОШИБКА: миграция не прошла — версия не выкладывается." >&2
        exit 1
    fi
fi

echo "── Запуск savdex:$TAG ($ROLE)"
compose "$TAG" up -d --remove-orphans
if [ "$ROLE" = web ]; then
    compose "$TAG" exec -T caddy caddy reload --config /etc/caddy/Caddyfile > /dev/null
fi

if wait_healthy "$TAG"; then
    echo "$TAG" > "$APP_HOME/current-tag"
    echo "$(date -Iseconds) $TAG" >> "$APP_HOME/releases.log"
    echo "── Готово: $ROLE работает на $TAG"
else
    echo "ОШИБКА: savdex:$TAG не поднялся ($ROLE). Последние строки журнала:" >&2
    compose "$TAG" logs --tail 80 app 2>&1 | redact >&2 || true
    if [ -n "$previous" ] && [ "$previous" != "$TAG" ]; then
        echo "── Возврат на $previous" >&2
        compose "$previous" up -d --remove-orphans
        wait_healthy "$previous" || echo "ВНИМАНИЕ: и предыдущая версия не поднялась" >&2
    fi
    exit 1
fi

# ── Уборка: текущая, предыдущая и ещё одна версия ───────────────────
docker image ls savdex --format '{{.Tag}}' \
    | grep -v -x -e "$TAG" -e "${previous:-$TAG}" \
    | tail -n +"$((KEEP_IMAGES - 1))" \
    | xargs -r -I{} docker image rm "savdex:{}" >/dev/null 2>&1 || true
