# Резервные копии

## Что копируется и где лежит

| Что | Как | Сколько хранится |
|---|---|---|
| База `savdex-db` | GitHub Actions, задача **backup** (`.github/workflows/backup.yml`): каждую ночь в 03:30 по Ташкенту, зашифрованный файл в артефактах запуска | 30 дней |
| База `savdex-db` | Render сам: история базы (Database → Recovery, Point-in-time recovery) | по тарифу Render |
| Загруженные файлы (диск `/var/data`) | Render сам: снимок диска раз в сутки (сервис savdex → Disks → Snapshots) | 7 дней |

Копия базы снимается `pg_dump` — только чтение, без блокировок: сайт
работает как обычно. Перед сохранением копия восстанавливается в пустую
базу; не восстановилась — запуск красный, и GitHub присылает письмо.

## Настройка (один раз)

В GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

1. `BACKUP_DATABASE_URL` — в Render: база **savdex-db** → **Connect** →
   **External Database URL** (строка вида `postgresql://savdex:…@….render.com/savdex`).
2. `BACKUP_PASSPHRASE` — пароль шифрования, не короче 20 знаков. Придумать
   самому и **сохранить отдельно** (менеджер паролей, бумага в сейфе): без
   него ни одну копию не открыть, а из GitHub секрет прочитать нельзя.

Проверить: **Actions → backup → Run workflow**. Зелёный запуск — копия
снята, проверена и сохранена.

Если запуск падает на подключении к базе: в Render **savdex-db → Access
Control** должен разрешать подключения извне (адреса машин GitHub
меняются, поэтому список — `0.0.0.0/0`; база при этом защищена паролем
и TLS).

## Восстановление

1. **Actions → backup** → нужный запуск → внизу **Artifacts** → скачать
   `savdex-db-ГГГГ-ММ-ДД` (zip с файлом `.dump.gpg`).
2. Расшифровать (спросит пароль `BACKUP_PASSPHRASE`):

   ```sh
   gpg --decrypt savdex-ГГГГ-ММ-ДД.dump.gpg > savdex.dump
   ```

3. Сначала — в новую пустую базу, чтобы проверить, что это нужная копия:

   ```sh
   createdb restore_check
   pg_restore --no-owner --no-acl --dbname=restore_check savdex.dump
   ```

4. Вернуть в боевую базу — только при аварии и в окно обслуживания:

   ```sh
   pg_restore --no-owner --no-acl --clean --if-exists --dbname="$DATABASE_URL" savdex.dump
   ```

   `--clean` удаляет всё, что есть в базе сейчас, и заменяет копией.
   Перед этим снять копию текущего состояния (Actions → backup → Run
   workflow).

`pg_restore` — не старше версии, которой снята копия (сейчас PostgreSQL 18):
`docker run --rm -v "$PWD:/w" -w /w postgres:18 pg_restore …`.

## При переезде в Uztelecom Cloud

Копии будут ложиться в S3-хранилище Uztelecom, а база — сохранять
изменения непрерывно (восстановление на любую секунду). Тогда копию
можно снимать с реплики, и основная база её не почувствует вовсе.
