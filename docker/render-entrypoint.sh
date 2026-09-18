#!/bin/bash
#
# Запуск контейнера на Render (и любом хостинге, который передаёт PORT).
#
# База может быть двух видов:
#  - SQLite (по умолчанию) — живёт на эфемерном диске и пересоздаётся
#    при каждом деплое; годится только для демо-стенда;
#  - внешний Postgres (DB_CONNECTION=pgsql + DB_URL) — данные постоянные.
# Пустая база в обоих случаях распознаётся одинаково: до миграций
# в ней нет таблицы users.
set -euo pipefail

# Render говорит, на каком порту слушать, через $PORT (по умолчанию 10000).
PORT="${PORT:-10000}"
sed -ri "s/^Listen 80$/Listen ${PORT}/" /etc/apache2/ports.conf
sed -ri "s/<VirtualHost \*:80>/<VirtualHost *:${PORT}>/" /etc/apache2/sites-available/000-default.conf

# ── Потолок одновременных процессов ─────────────────────────────────
#
# Apache здесь работает в режиме prefork: один процесс на один запрос,
# и внутри каждого — весь PHP с приложением. Замер: 45–50 МБ на запрос.
#
# По умолчанию Debian разрешает 150 таких процессов. Это 7,5 ГБ
# оперативной памяти — больше, чем есть на любом разумном тарифе.
# Пока посетителей мало, потолок не достигается и всё выглядит
# исправным; на трёхстах пользователях процессы плодятся, память
# кончается, ядро убивает Apache, Render поднимает контейнер заново —
# и все триста человек, обновляя страницу, роняют его повторно.
#
# Поэтому потолок считается от реально доступной памяти, а не берётся
# из умолчания. Упереться в него — это очередь и медленный ответ;
# не упереться — это 502 и перезапуск. Очередь лучше.
#
# Числа при желании переопределяются переменными окружения.
worker_mb="${APACHE_WORKER_MB:-55}"      # замеренный вес одного процесса
reserved_mb="${APACHE_RESERVED_MB:-640}" # opcache, queue:work, schedule:work, ОС

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

workers=$(( (total_mb - reserved_mb) / worker_mb ))
# Меньше восьми — сайт перестаёт отвечать на ровном месте; больше
# шестидесяти четырёх на одном ядре бессмысленно: процессы начинают
# отнимать время друг у друга, а не обслуживать людей.
if [ "$workers" -lt 8 ]; then
    workers=8
    echo "ВНИМАНИЕ: на ${total_mb} МБ памяти восемь процессов Apache не помещаются с запасом. Тариф мал для этого приложения — при заметной посещаемости контейнер будут убивать по нехватке памяти." >&2
fi
[ "$workers" -gt 64 ] && workers=64

# ── Имя сервера ─────────────────────────────────────────────────────
#
# Без него Apache при каждом запуске дважды жалуется в журнал:
# «Could not reliably determine the server's fully qualified domain
# name». На работу это не влияет — виртуальный хост слушает <*:порт>
# и принимает всё, — но две лишние строки при каждом перезапуске
# сорят ровно там, где мы ищем настоящие.
#
# Берём настоящий адрес, который Render кладёт в RENDER_EXTERNAL_URL:
# в журнале полезнее видеть savdex.uz, чем localhost.
server_name="${RENDER_EXTERNAL_URL:-}"
server_name="${server_name#*://}"   # снять «https://»
server_name="${server_name%%/*}"    # снять путь, если он есть
[ -z "$server_name" ] && server_name=localhost

cat > /etc/apache2/conf-enabled/zz-savdex-mpm.conf <<CONF
ServerName ${server_name}

<IfModule mpm_prefork_module>
    ServerLimit           ${workers}
    MaxRequestWorkers     ${workers}
    StartServers          4
    MinSpareServers       4
    MaxSpareServers       12
    # Ноль (умолчание) — процесс живёт вечно и копит утечки. Перезапуск
    # раз в 500 запросов возвращает память системе и стоит доли секунды.
    MaxConnectionsPerChild 500
</IfModule>

# Умолчание — 300 секунд: зависший запрос держит процесс пять минут,
# и под нагрузкой они кончаются раньше, чем память. PHP всё равно
# обрывает выполнение на 120 секундах (zz-uploads.ini).
Timeout 130
CONF

echo "Apache: ${workers} процессов при ${total_mb} МБ памяти." >&2

cd /var/www/html

# Без APP_KEY Laravel не стартует. Постоянный ключ задаётся в панели
# Render (Environment → APP_KEY).
#
# Раньше недостающий ключ генерировался заново при каждом запуске, и
# издержка оказалась куда больше обещанной. Ключом шифруются куки, а в
# куках лежит номер сессии; новый ключ — старая кука не расшифровывается,
# сессия начинается с нуля, и токен CSRF на уже открытой у человека
# странице перестаёт сходиться с серверным. Браузер продолжает
# показывать рабочий сайт, но каждое нажатие возвращает 419 и не делает
# ничего. Со стороны это «после обновления перестали работать кнопки».
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
        export APP_KEY="base64:$(php -r 'echo base64_encode(random_bytes(32));')"
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

if [ "${DB_CONNECTION:-sqlite}" = "sqlite" ]; then
    DB_FILE="${DB_DATABASE:-/var/www/html/database/database.sqlite}"
    mkdir -p "$(dirname "$DB_FILE")"
    touch "$DB_FILE"
fi

php artisan package:discover --ansi

FRESH_DB=0
HAS_USERS=$(php artisan tinker --execute='echo Schema::hasTable("users") ? "yes" : "no";' 2>/dev/null | tail -1 || true)
if [ "$HAS_USERS" != "yes" ]; then
    FRESH_DB=1
fi

php artisan migrate --force

# Сидируем только свежую базу, иначе каждый перезапуск плодил бы дубли.
if [ "$FRESH_DB" = "1" ]; then
    php artisan db:seed --force
    if [ "${SEED_DEMO:-false}" = "true" ]; then
        php artisan db:seed --class=DemoDataSeeder --force
    fi
fi

# Демо-витрина обновляется и на уже засеянной базе: правки демо-объявлений
# (например, переводы заголовков) иначе не доезжали бы до стенда — Shell
# на хостинге есть не всегда. Сидер идемпотентен (firstOrNew по заголовку,
# updateOrCreate по языку), дублей не плодит; без SEED_DEMO=true не запускается.
if [ "$FRESH_DB" = "0" ] && [ "${SEED_DEMO:-false}" = "true" ]; then
    php artisan db:seed --class=CabinetDemoSeeder --force
fi

# Тарифы — на каждом деплое, а не только на свежей базе: изменение цены
# в сидере иначе не доехало бы до прода. Сидер идемпотентен
# (updateOrCreate по коду тарифа), дублей не плодит.
php artisan db:seed --class=PlanSeeder --force

# Категории — по той же причине: новые разделы (например, «Другое»)
# должны появляться на проде без консоли. Идемпотентен (updateOrCreate
# по slug), существующее не трогает.
php artisan db:seed --class=CategorySeeder --force

# География — по той же причине: страна, добавленная после прошлого
# релиза, иначе появилась бы на проде только при пересоздании базы.
# Идемпотентен (updateOrCreate по коду страны), дублей не плодит.
php artisan db:seed --class=GeoSeeder --force

# Настройки — по той же причине: настройка, добавленная после прошлого
# релиза (например, «Логотип площадки»), иначе доезжает до прода только
# миграцией, а миграция срабатывает один раз и молча. Заводит только
# недостающие строки, заполненные значения не трогает.
php artisan db:seed --class=SettingSeeder --force

# Наполнение витрины: описания пустым карточкам компаний и картинки
# объявлениям без фото. Только дополняет — заполненное не перезаписывает.
# Выключается переменной SEED_SHOWCASE=false, когда живого контента
# станет достаточно.
if [ "${SEED_SHOWCASE:-true}" = "true" ]; then
    php artisan db:seed --class=ShowcaseSeeder --force
fi

# Администратор заводится из переменных окружения: на хостинге нет
# консоли, где можно было бы выполнить savdex:admin руками. Повторные
# запуски пропускаются — иначе каждый рестарт сбрасывал бы пароль.
if [ -n "${ADMIN_EMAIL:-}" ]; then
    IS_ADMIN=$(php artisan tinker \
        --execute='echo \App\Models\User::where("email", mb_strtolower(trim((string) getenv("ADMIN_EMAIL"))))->where("is_admin", true)->exists() ? "yes" : "no";' \
        2>/dev/null | tail -1 || true)
    if [ "$IS_ADMIN" != "yes" ]; then
        ADMIN_ARGS=("$ADMIN_EMAIL")
        if [ -n "${ADMIN_PASSWORD:-}" ]; then
            ADMIN_ARGS+=(--password "$ADMIN_PASSWORD")
        fi
        php artisan savdex:admin "${ADMIN_ARGS[@]}"
    fi
fi

# Загрузки — на постоянный диск. Контейнер пересоздаётся при каждом
# деплое, и всё, что лежало в storage/app (логотипы компаний, фото
# объявлений, документы), пропадало: «загрузили лого — назавтра его
# нет». Симлинки уводят оба хранилища на смонтированный диск, где
# уже живёт база.
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
    # запуска Apache — то есть прямо в те секунды, когда сайт лежит
    # и триста человек обновляют страницу. Правим только то, что
    # действительно не принадлежит www-data.
    find /var/data/storage \( ! -user www-data -o ! -group www-data \) \
        -exec chown www-data:www-data {} + 2>/dev/null || true
fi

php artisan storage:link || true
php artisan config:cache
php artisan view:cache
# route:cache не используется: /robots.txt объявлен замыканием,
# а замыкания не сериализуются в кэш маршрутов.

# artisan выше работал от root; веб-серверу нужны права www-data.
chown -R www-data:www-data storage bootstrap/cache database

# База может лежать вне проекта — на постоянном диске (DB_DATABASE).
# Смонтированный диск принадлежит root, и без прав www-data сайт
# падает на первой же записи: «attempt to write a readonly database».
if [ "${DB_CONNECTION:-sqlite}" = "sqlite" ]; then
    chown -R www-data:www-data "$(dirname "$DB_FILE")"
fi

# Планировщик. Системного cron на Render нет, а без schedule:run
# объявления не истекают, продвижения не освобождают слоты и месячные
# лимиты не сбрасываются (см. routes/console.php). Фоновый schedule:work
# живёт рядом с веб-сервером; для одного инстанса этого достаточно.
# От www-data, а не root — иначе журнал SQLite получит владельца root,
# и сайт упадёт на первой же записи.
if command -v runuser >/dev/null 2>&1; then
    runuser -u www-data -- php artisan schedule:work >/dev/null 2>&1 &

    # Очередь задач: импорт и экспорт из админки уходят в неё,
    # и без воркера «Загрузить компании» висело бы «в обработке»
    # вечно. Живёт, пока жив контейнер; после деплоя стартует заново.
    runuser -u www-data -- php artisan queue:work --sleep=3 --tries=3 >/dev/null 2>&1 &
fi

exec "$@"
