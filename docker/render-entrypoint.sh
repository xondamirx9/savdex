#!/bin/bash
#
# Запуск контейнера на Render (и любом хостинге, который передаёт PORT).
#
# Этап 8 переноса (docs/migration-to-python.md): PHP в образе нет.
# Apache отдаёт файлы из public/ и передаёт остальное Django (gunicorn
# сайта на 127.0.0.1:8001, админки — на 127.0.0.1:8002,
# docker/apache-python.conf); рядом живут фоновые
# задачи Django — расписание, перевод, сверка денег.
#
# База — только PostgreSQL (DB_CONNECTION=pgsql). SQLite осталась
# в прошлом вместе с Laravel: Django с ней не работает.
set -euo pipefail

cd /var/www/html

# ── База ────────────────────────────────────────────────────────────
#
# Без PostgreSQL сайт не поднимется. Лучше упасть здесь, до Apache:
# Render тогда считает деплой неудавшимся и оставляет работать прежний
# контейнер, а не выкладывает сайт, который на каждый запрос отвечает 500.
if [ "${DB_CONNECTION:-sqlite}" != "pgsql" ]; then
    echo "ОШИБКА: нужна база PostgreSQL — DB_CONNECTION=pgsql в Environment. SQLite с этапа 8 не поддерживается." >&2
    exit 1
fi

# ── Порт и имя сервера ──────────────────────────────────────────────
#
# Render говорит, на каком порту слушать, через $PORT (по умолчанию
# 10000); виртуальный хост (docker/apache-site.conf) принимает любой.
PORT="${PORT:-10000}"
echo "Listen ${PORT}" > /etc/apache2/ports.conf

# Без имени сервера Apache при каждом запуске жалуется в журнал
# «Could not reliably determine the server's fully qualified domain
# name». Берём настоящий адрес, который Render кладёт в RENDER_EXTERNAL_URL.
server_name="${RENDER_EXTERNAL_URL:-}"
server_name="${server_name#*://}"   # снять «https://»
server_name="${server_name%%/*}"    # снять путь, если он есть
[ -z "$server_name" ] && server_name=localhost

# ── Сколько процессов Django ────────────────────────────────────────
#
# Все запросы сайта теперь обслуживает gunicorn. Процесс Django с
# приложением весит 60–70 МБ и растёт до перезапуска (--max-requests);
# внутри — несколько потоков (gthread): запрос почти всё время ждёт
# базу, и поток на это время отдаёт процессор соседу.
#
# Процессов — сколько помещается в память с запасом, но не больше,
# чем есть смысла на имеющихся ядрах (2 × ядра + 1, совет gunicorn):
# лишние процессы не ускоряют, а отнимают память и соединения с базой.
# Упереться в потолок — это очередь и медленный ответ; не упереться —
# убитый по памяти контейнер и 502. Очередь лучше.
#
# Числа при желании переопределяются переменными окружения.
worker_mb="${PYTHON_WORKER_MB:-120}"      # процесс Django с запасом на рост
reserved_mb="${PYTHON_RESERVED_MB:-520}"  # Apache, расписание, перевод, сверка, рассылка, ОС

# Сколько памяти у контейнера: cgroup v2, затем v1, затем вся машина.
if [ -r /sys/fs/cgroup/memory.max ] && [ "$(cat /sys/fs/cgroup/memory.max)" != "max" ]; then
    total_mb=$(( $(cat /sys/fs/cgroup/memory.max) / 1048576 ))
elif [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
    limit=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)
    # v1 без ограничения возвращает заведомо огромное число
    if [ "$limit" -lt 1099511627776 ]; then
        total_mb=$(( limit / 1048576 ))
    else
        total_mb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))
    fi
else
    total_mb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))
fi

# Сколько ядер: квота cgroup v2 (cpu.max — «квота период»), иначе nproc
cpus=$(nproc)
if [ -r /sys/fs/cgroup/cpu.max ]; then
    read -r quota period < /sys/fs/cgroup/cpu.max || true
    if [ "${quota:-max}" != "max" ] && [ "${period:-0}" -gt 0 ]; then
        cpus=$(( (quota + period - 1) / period ))
    fi
fi
[ "$cpus" -lt 1 ] && cpus=1

# Админка — свой процесс gunicorn (127.0.0.1:8002, ниже): тяжёлая
# выгрузка или зависший запрос модератора занимают её потоки, а не
# потоки сайта. Её место в памяти вычитается до расчёта процессов сайта.
admin_workers="${PYTHON_ADMIN_WORKERS:-1}"
admin_threads="${PYTHON_ADMIN_THREADS:-4}"

if [ -n "${PYTHON_WORKERS:-}" ]; then
    workers="$PYTHON_WORKERS"
else
    workers=$(( (total_mb - reserved_mb - admin_workers * worker_mb) / worker_mb ))
    [ "$workers" -gt $(( 2 * cpus + 1 )) ] && workers=$(( 2 * cpus + 1 ))
    if [ "$workers" -lt 2 ]; then
        workers=2
        echo "ВНИМАНИЕ: на ${total_mb} МБ памяти два процесса Django не помещаются с запасом. Тариф мал для этого приложения — при заметной посещаемости контейнер будут убивать по нехватке памяти." >&2
    fi
fi
threads="${PYTHON_THREADS:-4}"

cat > /etc/apache2/conf-enabled/zz-savdex-server.conf <<CONF
ServerName ${server_name}

# Умолчание — 300 секунд: зависший запрос держит поток пять минут.
# Django обрывает запрос на тех же 130 секундах (gunicorn --timeout).
Timeout 130
CONF

echo "Django: сайт — ${workers} процессов × ${threads} потоков, админка — ${admin_workers} × ${admin_threads}, при ${total_mb} МБ памяти и ${cpus} ядрах." >&2

# ── Ключ ────────────────────────────────────────────────────────────
#
# APP_KEY шифрует куку сессии (тот же формат, что у Laravel) и
# подписывает пропуск в админку. Постоянный ключ задаётся в панели
# Render (Environment → APP_KEY).
#
# Новый ключ при каждом запуске — старая кука не расшифровывается,
# сессия начинается с нуля, и токен CSRF на уже открытой у человека
# странице перестаёт сходиться с серверным: каждое нажатие возвращает
# 419. Со стороны это «после обновления перестали работать кнопки».
#
# Поэтому сгенерированный ключ ложится на постоянный диск и переживает
# перезапуск. Это подпорка, а не решение: ключ из панели надёжнее —
# диск можно пересоздать, — и про подпорку надо кричать в журнал.
if [ -z "${APP_KEY:-}" ]; then
    KEY_FILE=/var/data/app_key
    if [ -d /var/data ] && [ -s "$KEY_FILE" ]; then
        export APP_KEY="$(cat "$KEY_FILE")"
        echo "ВНИМАНИЕ: APP_KEY не задан в панели Render, взят с диска. Задайте его в Environment." >&2
    else
        export APP_KEY="base64:$(python3 -c 'import base64, os; print(base64.b64encode(os.urandom(32)).decode())')"
        if [ -d /var/data ]; then
            printf '%s' "$APP_KEY" > "$KEY_FILE"
            chmod 600 "$KEY_FILE"
            echo "ВНИМАНИЕ: APP_KEY не задан в панели Render — сгенерирован и сохранён на диск. Задайте его в Environment." >&2
        else
            echo "ВНИМАНИЕ: APP_KEY не задан и сохранить его некуда — при перезапуске все сессии сбросятся, а кнопки на открытых страницах перестанут работать." >&2
        fi
    fi
fi

# Публичный адрес сервиса Render кладёт в RENDER_EXTERNAL_URL.
if [ -z "${APP_URL:-}" ] && [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
    export APP_URL="${RENDER_EXTERNAL_URL}"
fi

# ── Схема, справочники, администратор ───────────────────────────────
#
# Владельцем базы (DB_URL), а не ролью Django: ей схему менять нельзя.
# Без DB_URL — адрес из остальных переменных (DATABASE_URL, DB_HOST…,
# savdex/settings.py), но не роль Django. Схема — из снимка миграций на
# пустой базе и новые миграции SQL (python/savdex/schema.py),
# справочники — python/savdex/seeds.py, администратор — manage.py admin.
py_owner() {
    if [ -n "${DB_URL:-}" ]; then
        DJANGO_DATABASE_URL="$DB_URL" python/.venv/bin/python python/manage.py "$@"
    else
        env -u DJANGO_DATABASE_URL python/.venv/bin/python python/manage.py "$@"
    fi
}

FRESH_DB=0
if [ "$(py_owner schema --status | tail -1)" = "empty" ]; then
    FRESH_DB=1
fi
py_owner schema

# Справочники: на свежей базе — все, на каждом деплое — недостающие
# тарифы, категории, страны, города и настройки (правки из админки
# не трогаются)
if [ "$FRESH_DB" = "1" ]; then
    py_owner seed --fresh
else
    py_owner seed
fi

# Демо-наполнение (выдуманные компании и объявления) было сидерами
# Laravel и ушло вместе с ним
if [ "${SEED_DEMO:-false}" = "true" ] || [ "${SEED_SHOWCASE:-false}" = "true" ]; then
    echo "ВНИМАНИЕ: SEED_DEMO и SEED_SHOWCASE больше не работают — демо-наполнение было частью Laravel." >&2
fi

# Администратор заводится из переменных окружения: на хостинге нет
# консоли, где можно было бы выполнить команду руками. --if-missing:
# уже администратор — ничего не меняется, иначе каждый рестарт
# сбрасывал бы пароль.
if [ -n "${ADMIN_EMAIL:-}" ]; then
    ADMIN_ARGS=("$ADMIN_EMAIL" --if-missing)
    if [ -n "${ADMIN_PASSWORD:-}" ]; then
        ADMIN_ARGS+=(--password "$ADMIN_PASSWORD")
    fi
    py_owner admin "${ADMIN_ARGS[@]}"
fi

# ── Загрузки ────────────────────────────────────────────────────────
#
# Загрузки — на постоянный диск. Контейнер пересоздаётся при каждом
# деплое, и всё, что лежало бы в storage/app (логотипы компаний, фото
# объявлений, документы), пропадало: «загрузили лого — назавтра его
# нет». Симлинки уводят оба хранилища на смонтированный диск.
if [ -d /var/data ]; then
    for dir in public private; do
        mkdir -p "/var/data/storage/$dir"
        if [ -d "storage/app/$dir" ] && [ ! -L "storage/app/$dir" ]; then
            cp -a "storage/app/$dir/." "/var/data/storage/$dir/" 2>/dev/null || true
            rm -rf "storage/app/$dir"
        fi
        ln -sfn "/var/data/storage/$dir" "storage/app/$dir"
    done
    # chown -R storage ниже по симлинкам не проходит — цель явно.
    #
    # Но перебирать каждый загруженный файл на каждом старте нельзя:
    # это время растёт вместе с числом фотографий, а идёт оно до
    # запуска Apache. Правим только то, что не принадлежит www-data.
    find /var/data/storage \( ! -user www-data -o ! -group www-data \) \
        -exec chown www-data:www-data {} + 2>/dev/null || true
fi

# Публичные загрузки по адресу /storage/… — как storage:link у Laravel
ln -sfn /var/www/html/storage/app/public public/storage

# Команды выше работали от root; Django пишет в storage от www-data
chown -R www-data:www-data storage

# ── Django ──────────────────────────────────────────────────────────
#
# Упал — поднимается снова через несколько секунд: на время перезапуска
# сайт отвечает 503. set +e внутри цикла — иначе первый же ненулевой
# выход унёс бы и цикл (set -e сверху). Всё — от www-data, а не root.
run_forever() {
    local pause="$1" name="$2"
    shift 2
    (
        set +e
        while true; do
            runuser -u www-data -- "$@"
            echo "ВНИМАНИЕ: ${name} остановился, перезапуск через ${pause} секунд." >&2
            sleep "$pause"
        done
    ) &
}

# Слушает только 127.0.0.1: снаружи до Django не достучаться, только
# через Apache
run_forever 5 "Django (gunicorn)" python/.venv/bin/gunicorn savdex.wsgi \
    --chdir python \
    --bind 127.0.0.1:8001 \
    --workers "$workers" \
    --worker-class gthread \
    --threads "$threads" \
    --timeout 130 \
    --graceful-timeout 30 \
    --max-requests 1000 --max-requests-jitter 100 \
    --error-logfile -

# Админка (/py/admin/) — отдельный процесс на 127.0.0.1:8002, Apache
# передаёт её адреса туда (docker/apache-python.conf). Упала, зависла
# или выбрала всю очередь тяжёлыми запросами — сайт этого не замечает,
# и наоборот. SAVDEX_ROLE=admin ограничивает её запросы к базе по
# времени (savdex/settings.py): зависший отчёт не держит базу дольше,
# чем gunicorn ждёт ответа.
run_forever 5 "Админка Django (gunicorn)" env SAVDEX_ROLE=admin python/.venv/bin/gunicorn savdex.wsgi \
    --chdir python \
    --bind 127.0.0.1:8002 \
    --workers "$admin_workers" \
    --worker-class gthread \
    --threads "$admin_threads" \
    --timeout 130 \
    --graceful-timeout 30 \
    --max-requests 500 --max-requests-jitter 50 \
    --error-logfile -

# Задачи по расписанию (python/savdex/schedule.py): рейтинги, истёкшие
# объявления, просьбы об отзыве, чистка «Кто смотрел», продвижения,
# месячные периоды тарифов, курсы ЦБ, прозвон Uzum. Пройденное помнит
# файл состояния — на постоянном диске: в контейнере он пропадал с
# каждым деплоем, и после перезапуска задачи, чей час уже прошёл,
# считались выполненными и в тот день не шли вовсе
if [ -d /var/data ] && [ -z "${SAVDEX_SCHEDULE_STATE:-}" ]; then
    export SAVDEX_SCHEDULE_STATE=/var/data/storage/schedule.json
    if [ -f storage/app/schedule.json ] && [ ! -f "$SAVDEX_SCHEDULE_STATE" ]; then
        cp storage/app/schedule.json "$SAVDEX_SCHEDULE_STATE" 2>/dev/null || true
    fi
    chown www-data:www-data "$SAVDEX_SCHEDULE_STATE" 2>/dev/null || true
fi
run_forever 60 "Расписание Django" python/.venv/bin/python python/manage.py schedule

# Машинный перевод: проход раз в минуту. Выключается переменной
# MACHINE_TRANSLATION_ENABLED=false (savdex/translator.py)
run_forever 30 "Перевод" python/.venv/bin/python python/manage.py translate

# Письма и Telegram по уведомлениям кабинета — по галочкам в «Настройки →
# Уведомления» (python/savdex/deliveries.py): проход раз в минуту
run_forever 30 "Рассылка уведомлений" python/.venv/bin/python python/manage.py notify

# Сверка денег (python/savdex/payments/reconcile.py): раз в час — что
# должна была выдать каждая свежая оплата и что лежит в базе;
# расхождение — в журнал и письмом. Только чтение. Выключить —
# SAVDEX_PY_RECONCILE=0
if [ "${SAVDEX_PY_RECONCILE:-1}" != "0" ]; then
    run_forever 60 "Сверка денег" python/.venv/bin/python python/manage.py reconcile_billing
fi

exec "$@"
