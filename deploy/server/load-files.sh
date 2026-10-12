#!/bin/bash
#
# Копия загруженных файлов боевого — на тестовый сервер: логотипы, фото
# объявлений, баннеры (storage/public) и документы компаний, вложения
# писем поддержки, выгрузки (storage/private). Файлы тестового
# заменяются целиком.
#
#   load-files.sh /opt/savdex/restore/files.tgz
#
# Архив — tar.gz с каталогами public и private из /var/data/storage
# боевого; его снимает .github/workflows/staging.yml (галочка «копия
# файлов») по SSH с Render. Запускается от пользователя deploy. Архив
# после загрузки удаляется: в документах — личные данные.
#
# Сайт не останавливается: новые каталоги раскладываются рядом и
# подменяют старые переименованием.
set -euo pipefail

ARCHIVE=${1:?путь к архиву}
APP_HOME=${SAVDEX_HOME:-/opt/savdex}
TAG=$(cat "$APP_HOME/current-tag")

trap 'rm -f "$ARCHIVE"' EXIT

# Файлы на диске принадлежат www-data контейнера, а не deploy: раскладывает
# их root в одноразовом контейнере из образа сайта (в нём есть tar)
docker run --rm --network none --user root --entrypoint bash \
    -v "$APP_HOME/data:/var/data" \
    -v "$ARCHIVE:/restore/files.tgz:ro" \
    "savdex:$TAG" -euo pipefail -c '
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
        chown -R www-data:www-data storage/public storage/private
    '

echo "── Готово: на тестовом сервере копия файлов боевого"
