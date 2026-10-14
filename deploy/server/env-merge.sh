#!/bin/bash
#
# Строки «ИМЯ=значение» со входа — в настройки приложения на машине
# (/opt/savdex/env/app.env): такая же переменная заменяется, новой —
# дописывается. В журнал — только имена, значения не выводятся.
#
#   env-merge.sh < строки
#
# Строки — в виде env_file docker compose (значение в кавычках, как их
# пишет deploy/server/render-env.py). Вступает в силу после перезапуска
# приложения (выкладка).
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
FILE=${SAVDEX_ENV_FILE:-$APP_HOME/env/app.env}

if [ ! -f "$FILE" ]; then
    echo "ОШИБКА: нет $FILE — сначала выкладка." >&2
    exit 1
fi

umask 077
tmp=$(mktemp "$FILE.XXXXXX")
trap 'rm -f "$tmp" "$tmp.next"' EXIT
cp "$FILE" "$tmp"

names=()
while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)= ]] || continue
    name=${BASH_REMATCH[1]}
    grep -v "^${name}=" "$tmp" > "$tmp.next" || true
    printf '%s\n' "$line" >> "$tmp.next"
    mv "$tmp.next" "$tmp"
    names+=("$name")
done

mv "$tmp" "$FILE"
echo "── В настройках: ${names[*]:-ничего}"
