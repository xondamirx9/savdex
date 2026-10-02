# Код SAVDEX на Python

Сайт, кабинет, формы, касса и админка — Django. Как площадка переехала сюда
с Laravel — [docs/migration-to-python.md](../docs/migration-to-python.md).

## Запустить у себя

Нужен [uv](https://docs.astral.sh/uv/) и Python 3.11 или новее.

```sh
cd python
uv sync --all-groups
uv run ruff check . && uv run ruff format --check . && uv run mypy savdex
SAVDEX_PARITY_PG_URL=postgres://.../savdex_test uv run pytest -q
```

Часть проверок идёт на SQLite в памяти (`conftest.py`), остальные — на
настоящем PostgreSQL из `SAVDEX_PARITY_PG_URL`: схема из снимка
(`tests/pg_admin.свежая_база`), данные — фабрики `tests/factories.py`,
запросы — тестовым клиентом Django (`tests/web_site.py`). Без базы такие
проверки пропускаются. **В имени базы обязательно «test»** — проверки
стирают схему целиком. Ещё девять проверок (`test_check_postgres.py`)
ждут `SAVDEX_TEST_PG_URL`.

Сайт локально:

```sh
DJANGO_DATABASE_URL=postgres://... APP_KEY=base64:... uv run python manage.py runserver
```

База — `DJANGO_DATABASE_URL`, иначе `DATABASE_URL`, иначе переменные
`DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`.
`APP_KEY` шифрует куку сессии (формат Laravel — старые сессии посетителей
остались рабочими) и подписывает служебные ссылки.

## Команды

| Команда | Что делает |
|---|---|
| `schema` | Схема на пустой базе из снимка `savdex/bootstrap`, затем новые миграции SQL (`--status`, `--export`) |
| `seed` | Справочники из `savdex/bootstrap/seeds.json`: недостающее на каждом запуске, `--fresh` — на пустой базе |
| `admin <почта>` | Доступ в админку (`--role`, `--moderator`, `--if-missing`); пароль показывается один раз |
| `schedule` | Задачи по расписанию (`savdex/schedule.py`): рейтинги, истёкшие объявления, просьбы об отзыве, продвижения, периоды тарифов, курсы ЦБ, прозвон Uzum |
| `translate` | Машинный перевод: очередь текстов и недостающие переводы записей |
| `reconcile_billing` | Сверка денег: что должна была выдать оплата и что лежит в базе |
| `export_xlsx`, `run_export` | Выгрузка базы в Excel (кнопка «Выгрузить сейчас» в админке) |
| `check_postgres`, `uzum_ping` | Проверка базы; прозвон платёжного шлюза без платежа |
| `telegram_webhook` | Сообщить Telegram адрес бота (`--info`, `--delete`) |

Запускаются как `uv run python manage.py <команда>`; на сервере их
запускает `docker/render-entrypoint.sh`.

## Что здесь лежит

| Где | Зачем |
|---|---|
| `savdex/guards.py`, `savdex/apps.py` | Предохранители: запись только в объявленные таблицы, DDL — только из `schema` |
| `savdex/settings.py`, `savdex/urls.py` | Настройки; все адреса сайта, 404 на остальном (`savdex/web/fallback.py`) |
| `savdex/web/` | Страницы и формы сайта и кабинета: каркас и объект страницы Inertia, общие данные, язык, SEO, сессия, проверка ввода, ограничение частоты |
| `savdex/locale/ui/` | Словарь интерфейса на пяти языках — тексты правятся здесь |
| `savdex/payments/`, `savdex/finance/` | Касса и шлюз Uzum; счета, подписки, промокоды, возвраты, отчёты и сверки в админке |
| `savdex/adminsite.py`, `savdex/access.py`, `savdex/audit.py` | Админка: вход, права по ролям, журнал действий |
| `savdex/accounts/`, `savdex/data/`, `savdex/moderation/`, `savdex/crm/`, `savdex/support/`, `savdex/site/`, `savdex/catalogs/`, `savdex/geo/`, `savdex/billing/`, `savdex/tenders/`, `savdex/system/`, `savdex/dashboard/` | Разделы админки |
| `savdex/bootstrap/` | Снимок схемы, права роли `savdex_django`, справочники, миграции SQL |
| `savdex/laravel_session.py`, `savdex/laravel_cache.py`, `savdex/laravel_storage.py` | Форматы, доставшиеся от Laravel: кука сессии, файловый кэш, диск загрузок |

## Схема базы

Модели Django — `managed = False`, `manage.py migrate` запрещён
маршрутизатором: у схемы один источник — `manage.py schema`. Изменение —
файл `savdex/bootstrap/migrations/<дата>_<что>.sql` (подробности
в `savdex/schema.py`); применяется на следующем запуске контейнера.

## Предохранители

`savdex/guards.py` оборачивает каждый запрос к базе (и ORM, и
`cursor.execute`): запись проходит только в таблицы из `OWNED_TABLES`,
а `CREATE`/`ALTER`/`DROP` из кода сайта отказывают. Новая таблица, в
которую пишет код, — строка в `OWNED_TABLES`. Включаются предохранители
в `apps.py`; что они действительно висят на соединении после обычного
`django.setup()`, проверяет `tests/test_guard_installed.py` в отдельном
процессе.

На сервере у Django своя роль в PostgreSQL (`DJANGO_DATABASE_URL`) с
правами только на нужное — второй замок к тому же правилу; схему и
справочники ведёт владелец базы (`DB_URL`).
