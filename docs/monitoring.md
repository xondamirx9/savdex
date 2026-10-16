# Мониторинг

Что сломалось — сообщение в Telegram-группу **«SavdEx тревоги»**, раньше,
чем заметят посетители. Всё — на бесплатных тарифах.

| Что следит | За чем | Где настроено |
|---|---|---|
| **UptimeRobot** | сайт отвечает снаружи: раз в 5 минут `https://savdex.uz/up` | в UptimeRobot (ниже) |
| **Healthchecks.io** | резервные копии снимаются: ночная копия базы и копия файлов каждый час | сигналы — [deploy/server/backup.sh](../deploy/server/backup.sh), проверки — в Healthchecks |
| **Grafana Cloud** | процессор, память, диск и сеть машин; память и падения контейнеров; база; запросы и ошибки сайта | агент — [deploy/monitoring](../deploy/monitoring), ставит релиз; графики и тревоги — в Grafana Cloud |

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

## Что нужно один раз

1. **Telegram:** у **@BotFather** — `/newbot`, имя «SavdEx тревоги»;
   группа **«SavdEx тревоги»**, в ней — бот и те, кому нужны тревоги.
   Токен бота — только в настройки сервисов ниже, не в чат и не в код.
2. **UptimeRobot** (uptimerobot.com):
   - Integrations → **Telegram** — подключить группу;
   - New monitor → HTTP(s): `https://savdex.uz/up`, интервал 5 минут,
     уведомления — в Telegram.
3. **Healthchecks.io:**
   - Integrations → **Telegram** — подключить группу;
   - проверка `savdex-db-backup`: Period — 1 day, Grace — 2 hours
     (копия базы — в 03:40 по Ташкенту);
   - проверка `savdex-files-backup`: Period — 1 hour, Grace — 30 minutes;
   - их Ping URL (`https://hc-ping.com/…`) — в GitHub → Settings →
     Secrets and variables → Actions, секретами **`HC_PING_DB`** и
     **`HC_PING_FILES`**. Адреса секретные: кто их знает, может слать
     сигналы вместо нас.
4. **Следующий релиз** (Actions → prod) кладёт адреса в
   `/opt/savdex/env/backup.env` на машине базы — с этой минуты копии
   шлют сигналы. До того Healthchecks будет ждать первого сигнала и
   тревог не шлёт.

Проверить, что всё дошло: в Healthchecks у проверок — время последнего
сигнала; ночная — после 03:40, файлы — каждый час в :17.

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

**Где смотреть:** Grafana Cloud → Dashboards → New → Import, номера
готовых панелей: **1860** (машины), **14282** (контейнеры), **9628**
(PostgreSQL). Источник данных — `grafanacloud-…-prom`.

