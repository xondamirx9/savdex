#!/bin/bash
#
# Копия загруженных файлов боевого с Render — в общую папку файлов
# Uztelecom (prod.yml, галочка «копия с Render», до переезда): логотипы,
# фото объявлений, баннеры (storage/public) и документы компаний,
# вложения писем поддержки, выгрузки (storage/private). Файлы заменяются
# целиком.
#
#   SAVDEX_DATA_DIR=/srv/savdex SAVDEX_TOOL_IMAGE=postgres:18 \
#       load-files.sh /opt/savdex/restore/files.tgz
#
# Архив — tar.gz с каталогами public и private из /var/data/storage
# Render. Запускается от пользователя deploy. Архив после загрузки
# удаляется: в документах — личные данные. Сайт не останавливается:
# новые каталоги раскладываются рядом и подменяют старые переименованием.
#
# Тестовый сервер копию файлов боевого больше не берёт: у него свои
# демо-данные (staging-reset.sh).
set -euo pipefail

ARCHIVE=${1:?путь к архиву}
APP_HOME=${SAVDEX_HOME:-/opt/savdex}
DATA_DIR=${SAVDEX_DATA_DIR:-$APP_HOME/data}
TOOL_IMAGE=${SAVDEX_TOOL_IMAGE:-savdex:$(cat "$APP_HOME/current-tag")}

trap 'rm -f "$ARCHIVE"' EXIT

# Файлы на диске принадлежат www-data контейнера сайта (uid 33), а не
# deploy: раскладывает их root в одноразовом контейнере (в нём есть tar)
docker run --rm --network none --user root --entrypoint bash \
    -v "$DATA_DIR:/var/data" \
    -v "$ARCHIVE:/restore/files.tgz:ro" \
    "$TOOL_IMAGE" -euo pipefail -c '
        cd /var/data
        rm -rf storage.incoming
        mkdir -p storage storage.incoming
        tar -xzf /restore/files.tgz -C storage.incoming --no-same-owner
        if [ ! -d storage.incoming/public ]; then
            echo "ОШИБКА: в архиве нет каталога public." >&2
            rm -rf storage.incoming
            exit 1
        fi
        for dir in public private; do
            mkdir -p "storage.incoming/$dir"
            echo "   $dir: $(find "storage.incoming/$dir" -type f | wc -l) файлов, $(du -sh "storage.incoming/$dir" | cut -f1)"
            rm -rf "storage/$dir.old"
            if [ -d "storage/$dir" ]; then
                mv "storage/$dir" "storage/$dir.old"
            fi
            mv "storage.incoming/$dir" "storage/$dir"
            rm -rf "storage/$dir.old"
        done
        rm -rf storage.incoming
        chown -R 33:33 storage/public storage/private
    '

echo "── Готово: копия файлов боевого разложена"
