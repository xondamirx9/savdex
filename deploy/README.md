# Серверы в Uztelecom Cloud

План переезда — в [docs/backlog.md](../docs/backlog.md), раздел 2. Здесь —
то, что уже работает: **тестовый сервер** `staging.savdex.uz`. Боевые
машины (сайт, админка, база) добавятся сюда же, по одной.

## Как устроен тестовый сервер

Одна машина Ubuntu 24.04, на ней три контейнера
([staging/compose.yml](staging/compose.yml)):

| Контейнер | Что делает |
|---|---|
| `caddy` | HTTPS (сертификат Let's Encrypt сам), пароль на весь сайт, передача запросов приложению. Заголовки `X-Forwarded-*` от посетителя отбрасывает и ставит свои — адрес посетителя и хост в ссылках из писем не подделать |
| `app` | тот же образ, что на Render ([Dockerfile](../Dockerfile)): Apache, сайт, админка, фоновые задачи. Собирается на самой машине |
| `db` | своя PostgreSQL 16 с тестовыми данными, роль `savdex_django` — как на боевой базе. Наружу не открыта |

На машине:

```
/opt/savdex/src           код (git, переключается на выкладываемый коммит)
/opt/savdex/data          постоянный диск приложения (/var/data): загрузки, состояние расписания
/opt/savdex/db            файлы базы
/opt/savdex/env           пароли базы, APP_KEY, хеш пароля сайта — создаются на машине и её не покидают
/opt/savdex/current-tag   какая версия сейчас работает; releases.log — история выкладок
```

Письма на тестовом не уходят наружу (`MAIL_MAILER=log`), оплата и
Telegram не подключены.

## Выкладка

[.github/workflows/staging.yml](../.github/workflows/staging.yml):

- каждое слияние в основную ветку — сюда (и, как раньше, на Render);
- вручную (Actions → staging → Run workflow) — любая ветка, чтобы
  проверить её до слияния;
- один раз — подготовка чистой машины (галочка «bootstrap»,
  [server/bootstrap.sh](server/bootstrap.sh)): обновления, Docker,
  файрвол, SSH только по ключу, пользователь `deploy`.

[server/deploy.sh](server/deploy.sh) собирает образ, запускает, ждёт
ответа `/up`. Новая версия не поднялась — возвращает предыдущую и
красит workflow в красный.

## Что нужно один раз

1. **Ключ для выкладки.** На своём компьютере (PowerShell или терминал):
   `ssh-keygen -t ed25519 -C savdex-deploy -f savdex-deploy` — без пароля
   на ключ. Получатся два файла: `savdex-deploy` (закрытый) и
   `savdex-deploy.pub` (открытый).
2. **Машина в UzCloud:** Ubuntu 24.04, 2 vCPU, 4 ГБ, диск 25 ГБ,
   публичный IP, открытые порты 22, 80, 443; при создании — открытый
   ключ `savdex-deploy.pub`.
3. **DNS у Ahost:** A-запись `staging` → IP машины.
4. **GitHub → Settings → Secrets and variables → Actions:**
   - секрет `DEPLOY_SSH_KEY` — содержимое файла `savdex-deploy` целиком;
   - секрет `STAGING_PASSWORD` — пароль на тестовый сайт (логин `savdex`);
   - переменная `STAGING_HOST` — IP машины;
   - переменная `STAGING_BOOTSTRAP_USER` — `root` или `ubuntu`, смотря
     под кем образ ОС пускает по ключу.
5. **Actions → staging → Run workflow** с галочкой «bootstrap». В
   журнале будет подсказка с ключом машины — сохранить его переменной
   `STAGING_HOST_KEY`.

Закрытый ключ и пароли — только в секреты GitHub, не в чат и не на
скриншотах. Репозиторий публичный: журналы Actions видят все, поэтому
скрипты пароли в журнал не пишут.
