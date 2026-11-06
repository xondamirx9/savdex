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
# Нужен только docker. Запуск: deploy/server/caddy-check.sh
set -euo pipefail

SRC=$(cd "$(dirname "$0")/../.." && pwd)
CADDY_IMAGE=${CADDY_IMAGE:-caddy:2}
APP_IMAGE=${APP_IMAGE:-python:3.12-alpine}
# Порт внутри сети контейнеров — машине он не нужен
PORT=18080
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
# Порт на машину не публикуется: в CI его мог занять прошлый шаг. Запросы
# шлёт контейнер из той же сети
docker run -d --name "$NET-caddy" --network "$NET" --network-alias caddy \
    -v "$WORK/prod/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$WORK/prod/auth.caddy:/etc/caddy/auth.caddy:ro" \
    "$CADDY_IMAGE" > /dev/null

# Клиент: тело любого размера потоком, с Content-Length или «кусками».
# Ответ читает отдельный поток, пока тело ещё уходит: Caddy может ответить
# 413 сразу и закрыть соединение, не дочитав тело, — тогда отправка
# обрывается, а ответ уже прочитан
cat > "$WORK/client.py" <<'PY'
import re
import socket
import sys
import threading
import time

MiB = 1024 * 1024
host, port = sys.argv[1], int(sys.argv[2])


def send(method, path, mb=0, chunked=False):
    sock = socket.create_connection((host, port), timeout=120)
    got = bytearray()
    answered = threading.Event()

    def read():
        try:
            while b"\r\n" not in got and (data := sock.recv(65536)):
                got.extend(data)
        except OSError:
            pass
        answered.set()

    threading.Thread(target=read, daemon=True).start()
    head = f"{method} {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n"
    if chunked:
        head += "Transfer-Encoding: chunked\r\n"
    elif method == "POST":
        head += f"Content-Length: {mb * MiB}\r\n"
    block = b"\0" * MiB
    try:
        sock.sendall(head.encode() + b"\r\n")
        for _ in range(mb):
            if answered.is_set():
                break
            sock.sendall(b"%x\r\n" % MiB + block + b"\r\n" if chunked else block)
        if chunked and not answered.is_set():
            sock.sendall(b"0\r\n\r\n")
    except OSError:
        # Caddy закрыл соединение посреди тела — ответ ловит поток чтения
        pass
    answered.wait(120)
    sock.close()
    status = re.match(rb"HTTP/1\.[01] (\d{3})", bytes(got))

    return int(status.group(1)) if status else "обрыв"


for _ in range(30):
    try:
        if send("GET", "/") == 200:
            break
    except Exception:
        pass
    time.sleep(1)

failed = 0
for name, want, args in (
    ("страница", 200, ("GET", "/")),
    ("100 МиБ", 200, ("POST", "/cabinet/it-tasks", 100)),
    ("131 МиБ", 413, ("POST", "/cabinet/it-tasks", 131)),
    ("131 МиБ кусками", 413, ("POST", "/cabinet/it-tasks", 131, True)),
    ("131 МиБ в админку", 413, ("POST", "/py/admin/", 131)),
):
    got = send(*args)
    print(("   ок: " if got == want else "ОШИБКА: ") + f"{name} — {got}, ждали {want}")
    failed |= got != want

sys.exit(failed)
PY

echo "── Боевой Caddyfile перед заглушкой приложения"
docker run --rm --network "$NET" -v "$WORK/client.py:/client.py:ro" \
    "$APP_IMAGE" python /client.py caddy "$PORT"
