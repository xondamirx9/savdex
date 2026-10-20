# Резервные копии

## Что копируется и где лежит

| Что | Как | Сколько хранится |
|---|---|---|
| База `savdex-db` | GitHub Actions, задача **backup** (`.github/workflows/backup.yml`): каждую ночь в 03:30 по Ташкенту, зашифрованный файл — в хранилище S3 Uztelecom (Ташкент), `db/savdex-ГГГГ-ММ-ДД.dump.gpg` | 90 дней |
| База `savdex-db` | Render сам: история базы (Database → Recovery, Point-in-time recovery) | по тарифу Render |
| Загруженные файлы (диск `/var/data`) | Render сам: снимок диска раз в сутки (сервис savdex → Disks → Snapshots) | 7 дней |

Копия базы снимается `pg_dump` — только чтение, без блокировок: сайт
работает как обычно. Перед сохранением копия восстанавливается в пустую
базу; не восстановилась — запуск красный, и GitHub присылает письмо.

## После переезда в Uztelecom

Копии снимает машина базы ([deploy/server/backup.sh](../deploy/server/backup.sh),
cron, [deploy/README.md](../deploy/README.md)) и кладёт в то же хранилище:

| Что | Где | Сколько хранится |
|---|---|---|
| База — каждую ночь в 03:40 по Ташкенту, `pg_dump` + gpg тем же `BACKUP_PASSPHRASE` | `uz/db/savdex-ГГГГ-ММ-ДД.dump.gpg`; три последние — ещё и в `/opt/savdex/backup` на машине | 90 дней |
| База — перед каждым релизом на боевые машины, до изменения схемы (`backup.sh db release`) | `uz/db/savdex-ГГГГ-ММ-ДД-ЧЧММ-release.dump.gpg`; ночную копию не заменяет | 90 дней |
| Загруженные файлы — каждый час, только новые и изменённые, зашифрованы rclone crypt тем же паролем | `uz/files/` | всё, что когда-либо было загружено (удалённые с сайта файлы в копии остаются) |

Копия базы восстанавливается так же, как ночная копия Render (ниже):
расшифровать `gpg --decrypt` и `pg_restore`. Файлы — rclone с тем же
паролем (`rclone obscure` превращает пароль в вид, который ждёт rclone):

```sh
export RCLONE_CONFIG_S3_TYPE=s3 RCLONE_CONFIG_S3_PROVIDER=Other \
  RCLONE_CONFIG_S3_ENDPOINT=https://s3.uzcstorage.uz \
  RCLONE_CONFIG_S3_ACCESS_KEY_ID=… RCLONE_CONFIG_S3_SECRET_ACCESS_KEY=… \
  RCLONE_CONFIG_FILES_TYPE=crypt RCLONE_CONFIG_FILES_REMOTE=s3:savdex/uz/files
read -rsp 'Пароль BACKUP_PASSPHRASE: ' pass && echo
export RCLONE_CONFIG_FILES_PASSWORD="$(rclone obscure "$pass")"
rclone copy files: ./storage
```

После переезда ночная копия с Render (задача backup в GitHub) больше не
нужна: её выключить, когда новая база станет боевой.

## Настройка (один раз)

В GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

1. `BACKUP_DATABASE_URL` — в Render: база **savdex-db** → **Connect** →
   **External Database URL** (строка вида `postgresql://savdex:…@….render.com/savdex`).
2. `BACKUP_PASSPHRASE` — пароль шифрования, не короче 20 знаков. Придумать
   самому и **сохранить отдельно** (менеджер паролей, бумага в сейфе): без
   него ни одну копию не открыть, а из GitHub секрет прочитать нельзя.

3. Хранилище Uztelecom (UzCloud → Object Storage → `savdex`, значок с
   глазом — адрес и ключи):
   - секрет `S3_ACCESS_KEY` — Access Key;
   - секрет `S3_SECRET_KEY` — Secret Key;
   - переменная (вкладка **Variables**) `S3_ENDPOINT` — `https://s3.uzcstorage.uz`.

   Без них копия не сохраняется нигде, а запуск красный: в артефакты
   публичного репозитория копия не выкладывается — их может скачать
   кто угодно.

Проверить: **Actions → backup → Run workflow**. Зелёный запуск — копия
снята, проверена и сохранена.

Если запуск падает на подключении к базе: в Render **savdex-db → Access
Control** должен разрешать подключения извне (адреса машин GitHub
меняются, поэтому список — `0.0.0.0/0`; база при этом защищена паролем
и TLS).

## Восстановление

1. Скачать из хранилища Uztelecom: `aws --endpoint-url
   https://s3.uzcstorage.uz s3 cp s3://savdex/db/savdex-ГГГГ-ММ-ДД.dump.gpg .`
   (ключи — те же, что в секретах `S3_ACCESS_KEY` и `S3_SECRET_KEY`).
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
