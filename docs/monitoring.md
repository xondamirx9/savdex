# Мониторинг

Что сломалось — сообщение в Telegram-группу тревог (сейчас —
**«Вайбкодеры»**), раньше, чем заметят посетители. Всё — на бесплатных
тарифах.

| Что следит | За чем | Где настроено |
|---|---|---|
| **UptimeRobot** | сайт отвечает снаружи: раз в 5 минут `https://savdex.uz/up` | в UptimeRobot (ниже) |
| **Healthchecks.io** | резервные копии снимаются: ночная копия базы и копия файлов каждый час; из ночной копии каждое утро поднимается база ([проверка восстановления](backups.md#проверка-восстановления--каждое-утро)) | сигналы — [deploy/server/backup.sh](../deploy/server/backup.sh), проверки — в Healthchecks |
| **Grafana Cloud** | процессор, память, диск и сеть машин; память и падения контейнеров; база; запросы и ошибки сайта | агент — [deploy/monitoring](../deploy/monitoring), ставит релиз; графики — в Grafana Cloud; тревоги — [alerts.yaml](../deploy/monitoring/alerts.yaml), загружает Actions → alerts |

## Как это работает

**UptimeRobot** сам открывает сайт, как посетитель. Не ответил или
ответил ошибкой — тревога; ожил — сообщение «снова работает».

**Healthchecks.io** работает наоборот: ждёт сигнала. `backup.sh` в
начале копии шлёт «начал», в конце — «готово» или «сбой». Тревога —
если копия упала (сигнал «сбой»), зависла («начал» без конца) или не
запустилась вовсе (сигнала нет вовремя: машина базы лежит, cron
сломан, нет `backup.env`). Последнее — самое опасное: копии тихо
перестают сниматься, а узнают об этом в день, когда копия нужна.

Копия базы перед релизом (`backup.sh db release`) сигнала не шлёт: она
не по расписанию и заслонила бы собой пропущенную ночную.

Проверка восстановления (`backup.sh check`, каждое утро в 05:10) шлёт
вместе с сигналом итог одной строкой — он виден в Healthchecks у
сигнала: «копия … поднимается: таблиц 48, users 100%…» или причина
сбоя. Без данных из базы: Healthchecks — не в Узбекистане.

## Что нужно один раз

1. **Telegram:** группа тревог — в ней те, кому нужны тревоги. Наш бот
   для Grafana — **@savdex_alerts_bot** («SavdEx тревоги», создан у
   @BotFather); UptimeRobot и Healthchecks подключают к группе своих.
   Токен бота — только в секреты GitHub, не в чат и не в код.
2. **UptimeRobot** (uptimerobot.com):
   - Integrations → **Telegram** — подключить группу;
   - New monitor → HTTP(s): `https://savdex.uz/up`, интервал 5 минут,
     уведомления — в Telegram.
3. **Healthchecks.io:**
   - Integrations → **Telegram** — подключить группу;
   - проверка `savdex-db-backup`: Period — 1 day, Grace — 2 hours
     (копия базы — в 03:40 по Ташкенту);
   - проверка `savdex-files-backup`: Period — 1 hour, Grace — 30 minutes;
   - проверка `savdex-restore-check`: Period — 1 day, Grace — 3 hours
     (проверка восстановления — в 05:10 по Ташкенту);
   - их Ping URL (`https://hc-ping.com/…`) — в GitHub → Settings →
     Secrets and variables → Actions, секретами **`HC_PING_DB`**,
     **`HC_PING_FILES`** и **`HC_PING_RESTORE`**. Адреса секретные: кто
     их знает, может слать сигналы вместо нас.
4. **Следующий релиз** (Actions → prod) кладёт адреса в
   `/opt/savdex/env/backup.env` на машине базы — с этой минуты копии
   шлют сигналы. До того Healthchecks будет ждать первого сигнала и
   тревог не шлёт.

Проверить, что всё дошло: в Healthchecks у проверок — время последнего
сигнала; ночная — после 03:40, файлы — каждый час в :17, проверка
восстановления — после 05:10.

## Grafana Cloud: графики

На каждой боевой машине — агент **Grafana Alloy**
([deploy/monitoring/compose.yml](../deploy/monitoring/compose.yml)).
Раз в минуту он отправляет в Grafana Cloud:

| Машина | Что | Настройки |
|---|---|---|
| все | процессор, память, диски, сеть; память, процессор и перезапуски контейнеров | [base.alloy](../deploy/monitoring/alloy/base.alloy) |
| сайт (`web`) | Caddy: запросы, коды ответа (5xx — ошибки), время ответа | [web.alloy](../deploy/monitoring/alloy/web.alloy) |
| база (`db`) | PostgreSQL: жива ли, соединения, размер, блокировки | [db.alloy](../deploy/monitoring/alloy/db.alloy) |

**Только цифры, без журналов.** В журналах сайта бывают почты и
телефоны людей, а персональные данные граждан Узбекистана должны
храниться в Узбекистане. Цифры вида «диск занят на 63%» персональных
данных не содержат.

- У каждого ряда — метка `machine` (`web`, `admin`, `db`).
- Базу агент читает ролью `savdex_monitor`: только статистика сервера
  (`pg_monitor`), данных таблиц она не видит. Роль и пароль создаёт
  [prod-db.sh](../deploy/server/prod-db.sh).
- Caddy отдаёт цифры на `127.0.0.1:9180` — только агенту своей машины.
- Бесплатный тариф — 10 000 рядов; агенты трёх машин дают около 2 000.

**Как ставится:** каждый релиз (Actions → prod), шаг «Мониторинг»:
[deploy/server/monitoring.sh](../deploy/server/monitoring.sh) ставит
или обновляет агента на машинах сайта, админки и базы и через минуту
проверяет, что Grafana Cloud принимает цифры. Не принимает (неверный
токен и т. п.) — предупреждение в запуске; релиз от этого не падает.

**Что нужно один раз** — в Grafana Cloud (регион EU Germany):
Connections → Hosted Prometheus metrics → «From my local Prometheus
server» → «Use an API token»: имя `savdex-alloy`. Из показанных
настроек `remote_write` — в GitHub → Settings → Secrets and variables
→ Actions:

| Значение | Куда |
|---|---|
| `url` | переменная `GRAFANA_PROM_URL` |
| `username` (число) | переменная `GRAFANA_PROM_USER` |
| `password` (токен `glc_…`) | секрет `GRAFANA_ALLOY_TOKEN` |

**Где смотреть:** своя Grafana — `https://redaxolotl1730.grafana.net`
(не кабинет grafana.com). Панели заведены: **Node Exporter Full**
(1860, машины: Job — `integrations/unix`, Nodename — `savdex-web`,
`savdex-admin`, `savdex-db`), **PostgreSQL Database** (9628) и панель
контейнеров (14282). Добавить ещё — «+» → Import dashboard, номер с
grafana.com/dashboards, источник — `grafanacloud-redaxolotl1730-prom`.
Пустые панели — норма: собирается только нужное для тревог.

## Тревоги в Telegram

Grafana Cloud раз в минуту проверяет правила и пишет в группу: 🔴 —
срочно, 🟠 — посмотреть сегодня, ✅ — прошло. Пока тревога не прошла,
напоминание — раз в 4 часа.

| Тревога | Когда |
|---|---|
| 🔴 Машина не на связи | машина не присылает цифры больше 5 минут: выключена, нет сети или упал агент |
| 🟠 Диск заполняется | диск занят больше чем на 85% дольше 10 минут |
| 🟠 Мало памяти | память занята больше чем на 90% дольше 10 минут |
| 🟠 Процессор загружен | больше 90% дольше 15 минут |
| 🔴 База не отвечает | агент машины базы не достучался до PostgreSQL 2 минуты |
| 🟠 База — кончаются соединения | занято больше 80% соединений |
| 🔴 Caddy не отвечает | агент машины сайта не достучался до Caddy 2 минуты |
| 🔴 Сайт отдаёт ошибки | за 10 минут не меньше 10 ответов 5xx и больше 5% всех |
| 🔴 Контейнер убит за нехватку памяти | хоть раз |
| 🔴 Контейнер перезапускается | больше 3 перезапусков за 30 минут (выкладка — один) |

**Правила — в коде:** [deploy/monitoring/alerts.yaml](../deploy/monitoring/alerts.yaml).
В Grafana они только для чтения: поменять порог, добавить или убрать
тревогу — правка файла через PR. На PR Actions → alerts проверяет файл
и ключи; после слияния сам загружает правила в Grafana и пишет в группу
«тревоги обновлены». Загрузить заново вручную — Actions → alerts → Run
workflow.

**Заглушить на время** (плановые работы, известная беда): Grafana →
Alerts & IRM → Alerting → Silences → New silence, метка
`machine` = `db` (или `alertname` = название тревоги) и срок.

**Что нужно один раз** — в GitHub → Settings → Secrets and variables →
Actions:

| Значение | Куда | Откуда |
|---|---|---|
| адрес стека `https://redaxolotl1730.grafana.net` | переменная `GRAFANA_URL` | |
| ключ `glsa_…` | секрет `GRAFANA_SA_TOKEN` | Grafana → Administration → Users and access → Service accounts → Add service account (`savdex-github`, роль Admin) → Add service account token, без срока |
| токен бота | секрет `TELEGRAM_BOT_TOKEN` | @BotFather |
| номер группы, с минусом | секрет `TELEGRAM_CHAT_ID` | бота — в группу, там `/start@savdex_alerts_bot`, затем в браузере `https://api.telegram.org/botТОКЕН/getUpdates` → `"chat":{"id":-…}` |

Группа стала супергруппой (Telegram делает это сам при некоторых
настройках) — у неё новый номер `-100…`: обновить `TELEGRAM_CHAT_ID` и
запустить Actions → alerts. Проверка ключей это заметит: «бот не видит
группу».

