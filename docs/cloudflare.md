# Cloudflare перед сайтом

Боевой сайт `savdex.uz` — машина сайта в Uztelecom (Caddy → приложение,
[deploy/README.md](../deploy/README.md)). Cloudflare встаёт между
посетителями и Caddy:

```
посетитель ──HTTPS──▶ Cloudflare ──HTTPS──▶ Caddy (машина сайта) ──▶ приложение
```

Что даёт: защита от DDoS и ботов, кэш статики по всему миру, адрес
машины сайта скрыт — в обход Cloudflare к сайту не подключиться.

## Что делает код

Всё включается одной переменной GitHub `PROD_CLOUDFLARE=true`:

| Где | Что |
|---|---|
| Caddy ([deploy/server/prod-app.sh](../deploy/server/prod-app.sh)) | адрес посетителя — из `CF-Connecting-IP`, но только от адресов Cloudflare ([deploy/server/cloudflare-ips.txt](../deploy/server/cloudflare-ips.txt)); приложению уходит одним значением `X-Forwarded-For` — присланное посетителем не доходит. Замки от перебора, журнал и сессии видят настоящий адрес |
| Файрвол ([deploy/server/bootstrap.sh](../deploy/server/bootstrap.sh)) | порты 80 и 443 машины сайта открыты только адресам Cloudflare (ufw и цепочка `DOCKER-USER`: порты Caddy Docker публикует в обход ufw). SSH (22) — как был |
| Сертификат | секреты `CF_ORIGIN_CERT` и `CF_ORIGIN_KEY` — Origin-сертификат Cloudflare для Caddy ([.github/workflows/prod.yml](../.github/workflows/prod.yml) кладёт в `/opt/savdex/env/tls`). Без них — Let's Encrypt, как раньше |

## Включение: по шагам

Порядок важен: файрвол закрывается **последним**, когда сайт уже идёт
через Cloudflare. Закрыть раньше — сайт недоступен всем.

### 1. Домен в Cloudflare

1. Зарегистрироваться на [dash.cloudflare.com](https://dash.cloudflare.com),
   **Add a domain** → `savdex.uz`, тариф **Free**.
2. Cloudflare сам перенесёт DNS-записи. **Сверить со списком у Ahost
   все записи**, особенно:
   - `savdex.uz` (A) → IP машины сайта — **оранжевое облако** (Proxied);
   - `www` — если есть, тоже Proxied;
   - `staging`, `preview`, `new` (A) — **серое облако** (DNS only):
     тестовые сервера за Cloudflare не прячутся, их Caddy сам выпускает
     сертификат;
   - **почта: MX, SPF/DKIM/DMARC (TXT), `mail`, `autodiscover` и т. п. —
     только серое облако.** Почту Cloudflare не проксирует: с оранжевым
     облаком письма перестанут доходить.
3. У Ahost (регистратор домена) сменить NS-серверы домена на два, которые
   покажет Cloudflare. Переключение — от пары минут до суток; Cloudflare
   пришлёт письмо, когда домен станет **Active**.

### 2. Настройки Cloudflare

- **SSL/TLS → Overview → Full (strict).** Не Flexible: с Flexible
  Cloudflare ходит к сайту по HTTP, а сайт уводит на HTTPS — бесконечный
  редирект.
- **SSL/TLS → Edge Certificates:** Always Use HTTPS — On, Minimum TLS
  Version — 1.2. HSTS здесь **не включать**: его ставит сам сайт
  (python/savdex/settings.py).
- **Security → Bots:** Bot Fight Mode — **Off**. Он не различает людей и
  серверы: перестанут доходить колбэки оплаты Uzum
  (`/payments/uzum/callback/…`) и вебхук Telegram (`/telegram/webhook/…`).
  Если нужен строже — правило WAF с исключением для этих путей.
- **Caching:** по умолчанию Cloudflare кэширует только статику (картинки,
  CSS, JS) — страницы и кабинет не кэшируются. Правил «Cache Everything»
  не добавлять: личные страницы попадут в общий кэш.

Проверить: сайт открывается, в ответе есть заголовок `cf-ray`:

```sh
curl -sI https://savdex.uz | grep -i cf-ray
```

### 3. Origin-сертификат (рекомендуется)

**SSL/TLS → Origin Server → Create Certificate**: ключ RSA (2048),
адреса `savdex.uz` и `*.savdex.uz`, срок 15 лет → **Create**.

В GitHub (**Settings → Secrets and variables → Actions → New repository
secret**):
- `CF_ORIGIN_CERT` — текст из поля **Origin Certificate** целиком, с
  `-----BEGIN CERTIFICATE-----`;
- `CF_ORIGIN_KEY` — текст из **Private Key** целиком. Cloudflare
  показывает ключ **один раз**: потеряли — выпустить новый.

Без Origin-сертификата Caddy продлевает Let's Encrypt через Cloudflare —
обычно работает, но зависит от настроек Cloudflare. Origin-сертификат
этой зависимости не имеет. Браузеры ему не доверяют — только Cloudflare,
поэтому включать его, лишь когда домен уже Proxied (шаг 1).

### 4. Включить в GitHub и выложить

1. **Settings → Secrets and variables → Actions → Variables:**
   `PROD_CLOUDFLARE` = `true`.
2. **Actions → prod → Run workflow** с галочкой **«Сначала подготовить
   чистые машины»**. Подготовка повторно ничего не ломает; на машине
   сайта она закроет 80 и 443 для всех, кроме Cloudflare. Затем — обычный
   релиз: Caddy с новыми настройками и сертификатом.

### 5. Проверка

- Сайт открывается, вход, оплата, загрузка файлов — как обычно.
- Войти администратором и открыть `https://savdex.uz/py/whoami`: поле
  `ip` — **ваш** адрес (сверить с [2ip.ru](https://2ip.ru)), а не адрес
  Cloudflare.
- В обход Cloudflare сайт не открывается (ответа нет):

  ```sh
  curl -m 10 -k --resolve savdex.uz:443:<IP машины сайта> https://savdex.uz/up
  ```

## Выключить (откат)

1. `PROD_CLOUDFLARE` = `false` (или удалить переменную).
2. **prod → Run workflow** с «подготовить машины»: 80 и 443 снова открыты
   всем, Caddy перестаёт читать `CF-Connecting-IP`.
3. Секреты `CF_ORIGIN_CERT` и `CF_ORIGIN_KEY` удалить: Caddy вернётся к
   Let's Encrypt. Пока они есть, напрямую (без Cloudflare) браузеры
   сертификату не поверят.
4. В Cloudflare у записи `savdex.uz` — серое облако (или NS обратно на
   Ahost).

Порядок важен: сначала файрвол (шаги 1–2), потом облако (шаг 4). С
серым облаком и ещё закрытым файрволом сайт недоступен всем.

## Обслуживание

- **Адреса Cloudflare** меняются редко. Раз в полгода сверить
  [deploy/server/cloudflare-ips.txt](../deploy/server/cloudflare-ips.txt)
  и `CLOUDFLARE_NETWORKS` в python/savdex/audit.py с
  <https://www.cloudflare.com/ips/>. Изменились — поправить оба и
  запустить prod с «подготовить машины».
- **Мини-сайты на своих доменах** (docs/microsites.md, «Что дальше») —
  через Cloudflare for SaaS, когда до них дойдёт.
