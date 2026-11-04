#!/usr/bin/env bash
# Одинарные кавычки с «$…» — намеренно: ищется и подставляется сам текст
# shellcheck disable=SC2016
# Проверка настроек Caddy до выкладки — в CI (.github/workflows/docker.yml).
#
# Caddyfile боевых машин и превью пишут скрипты выкладки (prod-app.sh,
# preview.sh) из своего текста, а тестовый лежит файлом
# (deploy/staging/Caddyfile). Ошибка в нём видна только на машине: reload
# её отвергнет, но битый файл останется, и Caddy не поднимется при
# следующем перезапуске — сайта нет. Поэтому здесь:
#
# 1. все три Caddyfile собираются так же, как при выкладке, и проверяются
#    самим Caddy (caddy validate);
# 2. боевой поднимается перед заглушкой приложения: обычная страница
#    открывается, тело в 100 МиБ (самая большая честная загрузка) доходит,
#    131 МиБ — 413, и с Content-Length, и «кусками» (Т4, request_body).
#
# Нужны docker и curl. Запуск: deploy/server/caddy-check.sh
set -euo pipefail

SRC=$(cd "$(dirname "$0")/../.." && pwd)
CADDY_IMAGE=${CADDY_IMAGE:-caddy:2}
APP_IMAGE=${APP_IMAGE:-python:3.12-alpine}
PORT=${CADDY_CHECK_PORT:-18080}
WORK=$(mktemp -d)
NET=caddy-check-$$

# shellcheck disable=SC2329 # вызывается из trap
cleanup() {
    docker rm -f "$NET-caddy" "$NET-app" > /dev/null 2>&1 || true
    docker network rm "$NET" > /dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

# Текст между «cat > … <<CADDY» и «CADDY» в скрипте выкладки
heredoc() {
    awk -v start="$2" 'index($0, start) { on = 1; next } on && /^CADDY$/ { exit } on' "$1"
}

mkdir -p "$WORK/prod" "$WORK/preview" "$WORK/staging/sites"
heredoc "$SRC/deploy/server/prod-app.sh" 'cat > "$ENV_DIR/Caddyfile" <<CADDY' \
    | sed -e "s/\$SITE_DOMAIN/:$PORT/g" -e 's/\$ADMIN_IP/app/g' > "$WORK/prod/Caddyfile"
heredoc "$SRC/deploy/server/preview.sh" 'cat > "$SITES/preview.caddy" <<CADDY' \
    | sed -e 's/\$DOMAIN/:8082/g' -e 's/\$tag/check/g' > "$WORK/preview/Caddyfile"
cp "$SRC/deploy/staging/Caddyfile" "$WORK/staging/Caddyfile"

for site in prod preview staging; do
    if [ ! -s "$WORK/$site/Caddyfile" ]; then
        echo "ОШИБКА: Caddyfile ($site) не собран — изменился скрипт выкладки?" >&2
        exit 1
    fi
    : > "$WORK/$site/auth.caddy"
    echo "── caddy validate: $site"
    if ! out=$(docker run --rm -e SITE_DOMAIN=:8081 \
        -v "$WORK/$site/Caddyfile:/etc/caddy/Caddyfile:ro" \
        -v "$WORK/$site/auth.caddy:/etc/caddy/auth.caddy:ro" \
        -v "$WORK/staging/sites:/etc/caddy/sites:ro" \
        "$CADDY_IMAGE" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1); then
        echo "ОШИБКА: Caddyfile ($site) не принят Caddy:" >&2
        tail -5 <<< "$out" >&2
        exit 1
    fi
done

# Заглушка приложения: читает тело целиком (и «кусками») и отвечает, сколько пришло
cat > "$WORK/app.py" <<'PY'
import http.server


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        n = 0
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            while size := int(self.rfile.readline().strip() or b"0", 16):
                while size:
                    n += len(chunk := self.rfile.read(min(size, 1 << 20)))
                    size -= len(chunk)
                self.rfile.readline()
            self.rfile.readline()
        else:
            left = int(self.headers.get("Content-Length") or 0)
            while left:
                n += len(chunk := self.rfile.read(min(left, 1 << 20)))
                left -= len(chunk)
        self.reply(n)

    def do_GET(self):
        self.reply(0)

    def reply(self, n):
        body = f"got {n}\n".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("0.0.0.0", 10000), H).serve_forever()
PY

docker network create "$NET" > /dev/null
docker run -d --name "$NET-app" --network "$NET" --network-alias app \
    -v "$WORK/app.py:/app.py:ro" "$APP_IMAGE" python /app.py > /dev/null
docker run -d --name "$NET-caddy" --network "$NET" -p "127.0.0.1:$PORT:$PORT" \
    -v "$WORK/prod/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$WORK/prod/auth.caddy:/etc/caddy/auth.caddy:ro" \
    "$CADDY_IMAGE" > /dev/null

url="http://127.0.0.1:$PORT"
for _ in $(seq 1 30); do
    curl -fsS -o /dev/null "$url/" 2> /dev/null && break
    sleep 1
done

MiB=$((1024 * 1024))
head -c $((100 * MiB)) /dev/zero > "$WORK/100"
head -c $((131 * MiB)) /dev/zero > "$WORK/131"

# check <что> <ожидаемый код> <curl…>
failed=0
check() {
    local name=$1 want=$2 got
    shift 2
    got=$(curl -s -o /dev/null -w '%{http_code}' "$@" || true)
    if [ "$got" = "$want" ]; then
        echo "   ок: $name — $got"
    else
        echo "ОШИБКА: $name — $got, ждали $want" >&2
        failed=1
    fi
}

echo "── Боевой Caddyfile перед заглушкой приложения"
check "страница" 200 "$url/"
check "100 МиБ" 200 --data-binary "@$WORK/100" "$url/cabinet/it-tasks"
check "131 МиБ" 413 --data-binary "@$WORK/131" "$url/cabinet/it-tasks"
check "131 МиБ кусками" 413 -H "Transfer-Encoding: chunked" --data-binary "@$WORK/131" \
    "$url/cabinet/it-tasks"
check "131 МиБ в админку" 413 --data-binary "@$WORK/131" "$url/py/admin/"

exit "$failed"
