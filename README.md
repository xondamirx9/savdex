# SAVDEX

B2B-площадка для Узбекистана и Центральной Азии: поставщики и закупщики находят
друг друга по объявлениям и карточкам компаний.

Размещение бесплатное. Площадка зарабатывает на раскрытии контактов, тарифных
подписках и продвижении; комиссии со сделок нет — сделка идёт мимо площадки,
и брать за неё процент не с чего.

## Стек

| | Версия | Примечание |
|---|---|---|
| Python | 3.11+ (в образе 3.13) | зависимости — `uv`, по `python/uv.lock` |
| Django | 5.2 | сайт, кабинет, формы, админка, задачи по расписанию |
| PostgreSQL | 16 | единственная база |
| Inertia + React | 19 | TypeScript в strict-режиме; страницы собирает Vite |
| Tailwind CSS | 4 | |

Площадка переехала с Laravel на Django; PHP в проекте больше нет. Как шёл
перенос и почему — [docs/migration-to-python.md](docs/migration-to-python.md).

## Запуск

Нужны [uv](https://docs.astral.sh/uv/), Node.js 22 и PostgreSQL.

```bash
npm ci && npm run build                  # фронтенд: public/build
cd python
uv sync --all-groups
export DJANGO_DATABASE_URL=postgres://savdex:...@127.0.0.1:5432/savdex
export APP_KEY="base64:$(openssl rand -base64 32)"
uv run python manage.py schema           # схема на пустой базе
uv run python manage.py seed --fresh     # справочники: страны, города, тарифы, категории
uv run python manage.py admin you@example.com --name="Имя"
uv run python manage.py runserver
```

Сайт — `http://127.0.0.1:8000`, админка — `/py/admin/`.

Готового администратора в справочниках нет намеренно: учётка с известным
паролем, приехавшая на прод, — открытая дверь. Доступ выдаёт команда `admin`;
пароль показывается один раз и требует смены при первом входе.

## Проверки перед коммитом

```bash
cd python
uv run ruff check . && uv run ruff format --check . && uv run mypy savdex
SAVDEX_PARITY_PG_URL=postgres://.../savdex_test uv run pytest -q
npx tsc --noEmit                         # из корня репозитория
```

В имени проверочной базы обязательно «test»: проверки стирают схему целиком.

## Устройство

```
python/savdex/            Django: настройки, адреса, предохранители записи
  web/                    страницы и формы сайта и кабинета (Inertia)
  payments/, finance/     касса, шлюз Uzum, счета, подписки, возвраты, сверки
  data/, moderation/,     админка: компании, объявления, отзывы, CRM,
  crm/, support/, …       поддержка, справочники, рассылки, выгрузки
  bootstrap/              снимок схемы, права роли, справочники, миграции SQL
  schedule.py             задачи по расписанию
python/tests/             проверки pytest на настоящем PostgreSQL
resources/js/pages/       React-страницы витрины и кабинета
resources/legal/          юридические документы
docker/                   Apache перед Django, скрипт запуска контейнера
```

Подробнее о коде Python — [python/README.md](python/README.md).

## На сервере

Образ (`Dockerfile`) — Debian с Apache, Python и собранным фронтендом.
Apache отдаёт готовые файлы из `public/`, остальное передаёт Django
(gunicorn); рядом — задачи по расписанию, машинный перевод и сверка денег
(`docker/render-entrypoint.sh`). Сборку и запуск контейнера целиком
проверяет CI (`.github/workflows/docker.yml`).
