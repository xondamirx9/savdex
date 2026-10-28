#!/bin/bash
#
# Резервные копии с машины базы (боевой, Uztelecom) в хранилище S3
# Uztelecom (docs/backups.md).
#
#   backup.sh db      копия базы: pg_dump, проверка, шифрование gpg —
#                     <префикс>/db/savdex-ГГГГ-ММ-ДД.dump.gpg, 90 дней
#   backup.sh db МЕТКА  то же, но отдельным файлом со временем и меткой —
#                     savdex-ГГГГ-ММ-ДД-ЧЧММ-МЕТКА.dump.gpg; ночную копию
#                     того же дня не заменяет. Так снимает копию выкладка
#                     на боевые машины перед схемой базы (метка release)
#   backup.sh files   загруженные файлы: только новые и изменённые,
#                     зашифрованы rclone crypt — <префикс>/files/
#   backup.sh check   проверка восстановления: последняя ночная копия
#                     базы — из хранилища, расшифровка, загрузка во
#                     временную базу без сети и сверка с боевой; 20
#                     случайных файлов — из копии файлов, сверка с
#                     оригиналами. Временная база и расшифрованная копия
#                     удаляются сразу: данные с машины не уходят
#
# Запускает cron пользователя deploy (ставит prod-db.sh): база — каждую
# ночь, файлы — каждый час, проверка восстановления — каждое утро. Ключи хранилища и пароль шифрования — в
# /opt/savdex/env/backup.env (кладёт .github/workflows/prod.yml из
# секретов GitHub): S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY,
# BACKUP_PASSPHRASE — тот же пароль, что у ночных копий Render, без него
# копию не открыть.
#
# Сигналы в Healthchecks.io (docs/monitoring.md): ночная копия базы — на
# HC_PING_DB, копия файлов — на HC_PING_FILES, проверка восстановления —
# на HC_PING_RESTORE (тоже из backup.env, если заданы): начало, удача
# или сбой; у проверки — ещё и итог одной строкой, без данных из базы. Сигнала нет вовремя — тревога в
# Telegram: копия не снялась, упала или зависла.
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

what=${1:?db, files или check}
label=${2:-}
if [ -n "$label" ] && ! [[ "$label" =~ ^[a-z0-9-]{1,32}$ ]]; then
    echo "Метка копии — латиница, цифры и дефис: «$label» не подходит" >&2
    exit 1
fi

if [ ! -s "$ENV_DIR/backup.env" ]; then
    echo "$(date -Iseconds) ОШИБКА: нет $ENV_DIR/backup.env — копия не снята." >&2
    exit 1
fi
# shellcheck disable=SC1091
. "$ENV_DIR/backup.env"
: "${S3_ENDPOINT:?}" "${S3_BUCKET:?}" "${S3_ACCESS_KEY:?}" "${S3_SECRET_KEY:?}" "${BACKUP_PASSPHRASE:?}"
prefix=${BACKUP_PREFIX:-uz}

# ── Сигналы в Healthchecks.io ──────────────────────────────────────
# Копия с меткой (перед релизом) сигнала не шлёт: она не по расписанию
# и заслонила бы собой пропущенную ночную
hc_url=""
if [ "$what" = db ] && [ -z "$label" ]; then
    hc_url=${HC_PING_DB:-}
elif [ "$what" = files ]; then
    hc_url=${HC_PING_FILES:-}
elif [ "$what" = check ]; then
    hc_url=${HC_PING_RESTORE:-}
fi
# hc_ping <"" | /start | /fail> [текст — виден в Healthchecks у сигнала]
hc_ping() {
    [ -n "$hc_url" ] || return 0
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "${2:-}" "$hc_url$1" 2>/dev/null \
        || echo "$(date -Iseconds) ВНИМАНИЕ: сигнал в Healthchecks не ушёл" >&2
}
# Конец — удача или сбой, по коду выхода; заодно — без расшифрованной
# копии базы на диске и без временной базы проверки
plain=""
check_dir=""
check_box=""
files_log=""
report=""
finish() {
    local status=$?
    if [ -n "$plain" ]; then
        rm -f "$plain"
    fi
    if [ -n "$check_box" ]; then
        docker rm -f "$check_box" > /dev/null 2>&1 || true
    fi
    if [ -n "$check_dir" ]; then
        rm -rf "$check_dir"
    fi
    if [ -n "$files_log" ]; then
        rm -f "$files_log"
    fi
    if [ "$status" -eq 0 ]; then
        hc_ping "" "$report"
    else
        hc_ping /fail "${report:-сбой, подробности — в журнале копий на машине базы; свободно на диске: $(disk_free)}"
    fi
}
# Сколько места на диске машины базы — в сигнал о сбое
disk_free() {
    df -h --output=avail "$WORK" 2> /dev/null | tail -n 1 | tr -d ' ' || true
}
trap finish EXIT
hc_ping /start

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

# rclone_run <каталог:путь в контейнере:ro|rw>… -- <аргументы rclone…>
rclone_run() {
    local mounts=()
    while [ "$1" != "--" ]; do
        mounts+=(-v "$1")
        shift
    done
    shift
    docker run --rm --network host "${mounts[@]}" \
        -e RCLONE_CONFIG_S3_TYPE -e RCLONE_CONFIG_S3_PROVIDER -e RCLONE_CONFIG_S3_ENDPOINT \
        -e RCLONE_CONFIG_S3_ACCESS_KEY_ID -e RCLONE_CONFIG_S3_SECRET_ACCESS_KEY \
        -e RCLONE_CONFIG_S3_FORCE_PATH_STYLE \
        -e RCLONE_CONFIG_FILES_TYPE -e RCLONE_CONFIG_FILES_REMOTE -e RCLONE_CONFIG_FILES_PASSWORD \
        "$RCLONE_IMAGE" "$@" --s3-no-check-bucket --config ""
}

# rclone <каталог машины> <путь в контейнере> <аргументы rclone…> — каталог только на чтение
rclone() {
    local dir="$1" mount="$2"
    shift 2
    rclone_run "$dir:$mount:ro" -- "$@"
}

# files_reason <вывод rclone> <код выхода> — почему копия не снялась,
# одной строкой для Healthchecks и Telegram. Без имён файлов из вывода:
# в именах загруженных файлов могут быть данные людей
files_reason() {
    local out="$1" code="$2" errors why
    errors=$(grep -c ' ERROR : ' "$out" || true)
    if grep -qi 'no space left on device' "$out"; then
        why="на машине базы кончилось место"
    elif grep -qiE 'QuotaExceeded|quota exceeded' "$out"; then
        why="хранилище S3 переполнено"
    elif grep -qiE 'InvalidAccessKeyId|SignatureDoesNotMatch|AccessDenied|403 Forbidden' "$out"; then
        why="хранилище не принимает ключи — доступ запрещён"
    elif grep -qiE 'no such host|connection refused|i/o timeout|TLS handshake|connection reset|status ?code: 5[0-9][0-9]' "$out"; then
        why="хранилище $S3_ENDPOINT недоступно или отвечает ошибкой"
    elif grep -qi 'source file is being updated' "$out"; then
        why="файл менялся, пока копировался, — следующий час его докопирует"
    elif grep -qi 'permission denied' "$out"; then
        why="нет доступа к файлу в общей папке"
    elif grep -qiE 'Cannot connect to the Docker daemon|failed to connect to the docker API|Unable to find image|pull access denied' "$out"; then
        why="не запустился rclone в Docker"
    else
        why="причина не распознана"
    fi
    echo "$why (rclone: код $code, ошибок $errors; свободно на диске: $(disk_free)) — подробно в $WORK/backup.log"
}

umask 077
mkdir -p "$WORK"

case "$what" in
    db)
        stamp=$(date +%Y-%m-%d)
        if [ -n "$label" ]; then
            stamp="$(date +%Y-%m-%d-%H%M)-$label"
        fi
        # Своё имя у каждой копии: ночная и копия перед релизом могут совпасть по времени
        plain="$WORK/savdex-$stamp.dump"
        file="savdex-$stamp.dump.gpg"
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
        # Кэш (cache/) — не копия: он восстанавливается сам. Вывод rclone —
        # целиком в журнал на машине, а причина сбоя — ещё и в Healthchecks
        files_log=$(mktemp "$WORK/files.XXXXXX")
        code=0
        rclone "$STORAGE" /data copy /data files: --exclude "/cache/**" \
            --stats-one-line --stats-log-level NOTICE > "$files_log" 2>&1 || code=$?
        cat "$files_log"
        if [ "$code" -ne 0 ]; then
            report="копия файлов не снялась: $(files_reason "$files_log" "$code")"
            echo "$(date -Iseconds) ОШИБКА: $report" >&2
            exit "$code"
        fi
        echo "$(date -Iseconds) Копия файлов: $prefix/files/"
        ;;
    check)
        # Копия, из которой ни разу не поднимались, — ещё не копия. Здесь —
        # как при аварии: копия из хранилища (не с этого диска), пароль
        # шифрования, пустая база. Итог — одной строкой: в журнал и в
        # Healthchecks; без данных из базы и без чисел строк (проценты от
        # боевой), журнал выкладки на GitHub — публичный
        started=$(date +%s)
        fail() {
            report="$1"
            echo "$(date -Iseconds) ОШИБКА проверки восстановления: $1" >&2
            exit 1
        }
        compose=(docker compose -f "$SRC/deploy/prod/db/compose.yml" --env-file "$ENV_DIR/compose.env")
        live() { "${compose[@]}" exec -T db psql -U savdex -d savdex -Atqc "$1"; }

        # Свободное место: под копию, расшифровку и временную базу
        for dir in "$WORK" "$(docker info -f '{{.DockerRootDir}}')"; do
            free=$(df --output=avail -k "$dir" | tail -n 1)
            if [ "$free" -lt 2097152 ]; then
                fail "мало места на диске ($dir: $((free / 1024)) МБ свободно, нужно 2 ГБ)"
            fi
        done

        # Последняя ночная копия — по имени, свежесть — по времени загрузки:
        # не старше 26 часов (ночная — в 03:40)
        # Время у объекта — то, что записал rclone при загрузке (время файла копии)
        status=0
        listing=$(rclone "$WORK" /work lsf --files-only --format "tp" --separator ";" \
            --time-format RFC3339 --include "savdex-????-??-??.dump.gpg" \
            "s3:$S3_BUCKET/$prefix/db/" 2> /dev/null) || status=$?
        # 3 — папки нет: в хранилище S3 это и есть «ни одной копии»
        if [ "$status" -ne 0 ] && [ "$status" -ne 3 ]; then
            fail "хранилище $S3_ENDPOINT недоступно (rclone, код $status)"
        fi
        latest=$(sort -t ";" -k 2 <<< "$listing" | tail -n 1)
        name=${latest#*;}
        if [ -z "$name" ]; then
            fail "в хранилище нет ночных копий базы ($prefix/db/)"
        fi
        uploaded=$(date -d "${latest%%;*}" +%s)
        age=$(( ($(date +%s) - uploaded) / 3600 ))
        if [ "$age" -gt 26 ]; then
            fail "последняя ночная копия $name снята $age ч назад — ночные копии не снимаются"
        fi

        check_dir=$(mktemp -d "$WORK/check.XXXXXX")
        rclone_run "$check_dir:/work:rw" -- copyto "s3:$S3_BUCKET/$prefix/db/$name" "/work/$name"
        plain="$check_dir/check.dump"
        if ! gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 \
            --output "$plain" --decrypt "$check_dir/$name" 3<<< "$BACKUP_PASSPHRASE" 2> /dev/null; then
            fail "копия $name не расшифровывается паролем BACKUP_PASSPHRASE"
        fi
        rm -f "$check_dir/$name"
        size=$(stat -c %s "$plain")

        # Временная база: без сети, вход без пароля — только изнутри
        # контейнера; удаляется вместе с данными при любом исходе (finish)
        check_box=savdex-restore-check
        docker rm -f "$check_box" > /dev/null 2>&1 || true
        docker run -d --rm --name "$check_box" --network none --memory 1g \
            -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=restore_check \
            postgres:18 -c shared_buffers=128MB -c fsync=off -c synchronous_commit=off \
            -c full_page_writes=off > /dev/null
        # По TCP: во время первого запуска образ поднимает базу только на сокете
        for _ in $(seq 1 60); do
            docker exec "$check_box" pg_isready -q -h 127.0.0.1 -U postgres && break
            sleep 1
        done
        docker exec "$check_box" pg_isready -q -h 127.0.0.1 -U postgres \
            || fail "временная база для проверки не запустилась"
        restored() { docker exec "$check_box" psql -U postgres -d restore_check -Atqc "$1"; }

        # Владельцы и права — роли боевой базы, во временной их нет: без них
        errors="$check_dir/restore.err"
        if ! docker exec -i "$check_box" pg_restore -U postgres -d restore_check \
            --no-owner --no-acl --exit-on-error < "$plain" 2> "$errors"; then
            # В тексте ошибки бывают строки данных — в итог только её начало,
            # без почт и телефонов
            first=$( (grep -m 1 'error:' "$errors" || true) | cut -c 1-160 \
                | sed -E 's/[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}/[почта]/g; s/\+?[0-9][0-9 ()-]{7,}[0-9]/[номер]/g')
            fail "копия $name не загружается в пустую базу: ${first:-pg_restore завершился с ошибкой}"
        fi
        rm -f "$plain"
        plain=""

        tables=$(restored "select count(*) from pg_tables where schemaname = 'public'")
        if [ "$tables" -lt 20 ]; then
            fail "после загрузки копии $name в базе $tables таблиц — копия неполная"
        fi
        # Главные таблицы: в копии не меньше 90% строк боевой базы (боевая
        # с ночи только растёт; меньше — копия старая или обрезанная)
        shares=""
        for table in users companies listings; do
            got=$(restored "select count(*) from $table")
            now=$(live "select count(*) from $table")
            if [ "$got" -lt 1 ]; then
                fail "в копии $name таблица $table пуста"
            fi
            share=$(( now > 0 ? got * 100 / now : 100 ))
            if [ "$share" -lt 90 ]; then
                fail "в копии $name в таблице $table $share% строк боевой базы — копия старая или неполная"
            fi
            shares="${shares:+$shares, }$table $share%"
        done
        docker rm -f "$check_box" > /dev/null 2>&1 || true
        check_box=""

        # Файлы: 20 случайных старше двух часов (свежие ещё могут ждать
        # почасовой копии) — из копии, расшифровкой, побайтно с оригиналом
        if ! rclone "$STORAGE" /data lsf -R --files-only --min-age 2h --exclude "/cache/**" /data \
            > "$check_dir/all-files.txt"; then
            fail "не читается папка файлов $STORAGE"
        fi
        shuf -n 20 "$check_dir/all-files.txt" > "$check_dir/files.txt"
        sampled=$(wc -l < "$check_dir/files.txt")
        files="файлов нет — сверять нечего"
        if [ "$sampled" -gt 0 ]; then
            if ! rclone_run "$STORAGE:/data:ro" "$check_dir:/work:ro" -- check /data files: \
                --files-from /work/files.txt --download --one-way > "$check_dir/files.log" 2>&1; then
                differ=$( (grep -oE '[0-9]+ differences found' "$check_dir/files.log" || true) \
                    | head -n 1 | grep -oE '^[0-9]+' || true)
                fail "копия файлов: из $sampled случайных файлов не совпали или не нашлись в копии: ${differ:-?}"
            fi
            files="файлы: $sampled из $sampled совпали"
        fi

        report="копия $name ($((size / 1024)) КБ, снята $age ч назад) поднимается: таблиц $tables, $shares от боевой; $files; $(( $(date +%s) - started )) с"
        echo "$(date -Iseconds) Проверка восстановления: $report"
        ;;
    *)
        echo "Что делать: db, files или check" >&2
        exit 1
        ;;
esac
