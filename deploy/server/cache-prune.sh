#!/bin/bash
#
# Машина базы (боевая, Uztelecom): удалить из общего кэша записи с
# истёкшим сроком.
#
#   cache-prune.sh
#
# Кэш сайта и админки (CACHE_STORE=file) лежит в общей папке
# /srv/savdex/storage/cache и, в отличие от Render, не пропадает при
# выкладке. Сайт удаляет просроченную запись, только если снова её
# читает, а счётчики ограничений частоты — по одному на адрес — читаются
# редко: без чистки папка росла бы бесконечно. Первые 10 знаков файла —
# срок жизни (время Unix), 9999999999 — «навсегда».
#
# Запускает cron пользователя deploy (ставит prod-db.sh) раз в сутки.
# Файлы принадлежат www-data, поэтому удаляет root одноразового
# контейнера (образ postgres:18 уже есть на машине).
set -euo pipefail

CACHE=${SAVDEX_CACHE_PATH:-/srv/savdex/storage/cache}

if [ ! -d "$CACHE" ]; then
    exit 0
fi

docker run --rm --network none -v "$CACHE:/cache" postgres:18 bash -c '
    now=$(date +%s)
    total=0
    removed=0
    while IFS= read -r -d "" file; do
        total=$((total + 1))
        expires=$(head -c 10 "$file" 2>/dev/null || true)
        if [[ "$expires" =~ ^[0-9]{10}$ ]] && [ "$expires" -lt "$now" ]; then
            rm -f "$file" && removed=$((removed + 1))
        fi
    done < <(find /cache -type f -print0)
    find /cache -mindepth 2 -type d -empty -delete
    echo "$(date -Iseconds) Кэш: удалено просроченных $removed из $total"
'
