#!/bin/bash
#
# Роль Django в PostgreSQL — как на боевой базе: читает всё, пишет только
# разрешённое (python/savdex/bootstrap/grants.sql). Права выдаёт
# `manage.py schema` при первом запуске приложения, если роль уже есть,
# поэтому её нужно создать раньше — здесь, при создании пустой базы.
#
# Скрипт выполняется образом postgres один раз: только когда каталог
# данных пуст.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=password="$DJANGO_DB_PASSWORD" <<'SQL'
CREATE ROLE savdex_django LOGIN PASSWORD :'password';
GRANT CONNECT ON DATABASE savdex TO savdex_django;
GRANT USAGE ON SCHEMA public TO savdex_django;
SQL
