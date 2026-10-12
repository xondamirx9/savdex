#!/bin/bash
#
# Резервные копии с машины базы (боевой, Uztelecom) в хранилище S3
# Uztelecom (docs/backups.md).
#
#   backup.sh db      копия базы: pg_dump, проверка, шифрование gpg —
#                     <префикс>/db/savdex-ГГГГ-ММ-ДД.dump.gpg, 90 дней
#   backup.sh files   загруженные файлы: только новые и изменённые,
#                     зашифрованы rclone crypt — <префикс>/files/
#
# Запускает cron пользователя deploy (ставит prod-db.sh): база — каждую
# ночь, файлы — каждый час. Ключи хранилища и пароль шифрования — в
# /opt/savdex/env/backup.env (кладёт .github/workflows/prod.yml из
# секретов GitHub): S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY,
# BACKUP_PASSPHRASE — тот же пароль, что у ночных копий Render, без него
# копию не открыть.
#
# rclone — из образа Docker, от root контейнера: файлы в общей папке
# принадлежат www-data, и не всё из них может читать deploy.
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
ENV_DIR=$APP_HOME/env
WORK=$APP_HOME/backup
STORAGE=/srv/savdex/storage
RCLONE_IMAGE=rclone/rclone:1.68
KEEP_DAYS=90

what=${1:?db или files}

if [ ! -s "$ENV_DIR/backup.env" ]; then
    echo "$(date -Iseconds) ОШИБКА: нет $ENV_DIR/backup.env — копия не снята." >&2
    exit 1
fi
# shellcheck disable=SC1091
. "$ENV_DIR/backup.env"
: "${S3_ENDPOINT:?}" "${S3_BUCKET:?}" "${S3_ACCESS_KEY:?}" "${S3_SECRET_KEY:?}" "${BACKUP_PASSPHRASE:?}"
prefix=${BACKUP_PREFIX:-uz}

# Хранилище — remote «s3», зашифрованные файлы поверх него — «files».
# Значения уходят в контейнер через окружение (-e ИМЯ без значения):
# в списке процессов их не видно
export RCLONE_CONFIG_S3_TYPE=s3
export RCLONE_CONFIG_S3_PROVIDER=Other
export RCLONE_CONFIG_S3_ENDPOINT="$S3_ENDPOINT"
export RCLONE_CONFIG_S3_ACCESS_KEY_ID="$S3_ACCESS_KEY"
export RCLONE_CONFIG_S3_SECRET_ACCESS_KEY="$S3_SECRET_KEY"
export RCLONE_CONFIG_S3_FORCE_PATH_STYLE=true
export RCLONE_CONFIG_FILES_TYPE=crypt
export RCLONE_CONFIG_FILES_REMOTE="s3:$S3_BUCKET/$prefix/files"
RCLONE_CONFIG_FILES_PASSWORD=$(docker run --rm -i "$RCLONE_IMAGE" obscure - --config "" <<< "$BACKUP_PASSPHRASE")
export RCLONE_CONFIG_FILES_PASSWORD

# rclone <каталог машины> <путь в контейнере> <аргументы rclone…>
rclone() {
    local dir="$1" mount="$2"
    shift 2
    docker run --rm --network host -v "$dir:$mount:ro" \
        -e RCLONE_CONFIG_S3_TYPE -e RCLONE_CONFIG_S3_PROVIDER -e RCLONE_CONFIG_S3_ENDPOINT \
        -e RCLONE_CONFIG_S3_ACCESS_KEY_ID -e RCLONE_CONFIG_S3_SECRET_ACCESS_KEY \
        -e RCLONE_CONFIG_S3_FORCE_PATH_STYLE \
        -e RCLONE_CONFIG_FILES_TYPE -e RCLONE_CONFIG_FILES_REMOTE -e RCLONE_CONFIG_FILES_PASSWORD \
        "$RCLONE_IMAGE" "$@" --s3-no-check-bucket --config ""
}

umask 077
mkdir -p "$WORK"

case "$what" in
    db)
        stamp=$(date +%Y-%m-%d)
        plain="$WORK/savdex.dump"
        file="savdex-$stamp.dump.gpg"
        trap 'rm -f "$plain"' EXIT
        compose=(docker compose -f "$SRC/deploy/prod/db/compose.yml" --env-file "$ENV_DIR/compose.env")

        "${compose[@]}" exec -T db pg_dump -U savdex --format=custom --compress=9 savdex > "$plain"
        size=$(stat -c %s "$plain")
        tables=$("${compose[@]}" exec -T db pg_restore --list < "$plain" | grep -c 'TABLE DATA' || true)
        if [ "$size" -lt 50000 ] || [ "$tables" -lt 20 ]; then
            echo "$(date -Iseconds) ОШИБКА: копия базы подозрительно мала ($size байт, таблиц с данными: $tables)." >&2
            exit 1
        fi

        gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 \
            --passphrase-fd 3 --output "$WORK/$file" "$plain" 3<<< "$BACKUP_PASSPHRASE"
        rm -f "$plain"

        rclone "$WORK" /work copyto "/work/$file" "s3:$S3_BUCKET/$prefix/db/$file"
        rclone "$WORK" /work delete --min-age "${KEEP_DAYS}d" "s3:$S3_BUCKET/$prefix/db/"
        # На машине — три последние ночи: быстрое восстановление без хранилища
        find "$WORK" -maxdepth 1 -name 'savdex-*.dump.gpg' -mtime +3 -delete
        echo "$(date -Iseconds) Копия базы: $prefix/db/$file, $((size / 1024)) КБ"
        ;;
    files)
        rclone "$STORAGE" /data copy /data files: --stats-one-line --stats-log-level NOTICE
        echo "$(date -Iseconds) Копия файлов: $prefix/files/"
        ;;
    *)
        echo "Что копировать: db или files" >&2
        exit 1
        ;;
esac
