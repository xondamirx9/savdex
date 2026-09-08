#!/usr/bin/env bash
#
# Прокси со статическим IP для запросов SAVDEX → Uzum Checkout.
#
# Зачем: Uzum открывает API только с одного конкретного адреса, а у
# хостинга (Render) адреса общие и плавающие. Маленький VPS с фиксированным
# IP пропускает через себя только запросы к Uzum; сайт живёт где жил.
#
# Запуск на свежем Ubuntu 22.04/24.04 от root:
#     curl -fsSL <raw-url этого файла> | bash
# или скопировать файл на сервер и выполнить: bash uzum-proxy-setup.sh
#
# В конце печатает готовое значение PAYMENTS_UZUM_PROXY для Render
# и IP, который нужно отправить Uzum в белый список.
#
# Что закрыто:
#   - логин/пароль на прокси;
#   - файрвол пускает к прокси только исходящие диапазоны Render;
#   - прокси ходит только на *.uzumcheckout.uz (CONNECT на 443);
#   - трафик до Uzum — сквозной TLS, прокси видит только адрес назначения.
set -euo pipefail

PROXY_USER="${PROXY_USER:-savdex}"
PROXY_PASS="${PROXY_PASS:-$(openssl rand -hex 16)}"
PROXY_PORT="${PROXY_PORT:-3128}"
# Исходящие адреса Render (Connect → Outbound на странице сервиса)
ALLOW_FROM="${ALLOW_FROM:-74.220.48.0/24 74.220.56.0/24}"
UPSTREAM_PATTERN="${UPSTREAM_PATTERN:-*uzumcheckout.uz}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y tinyproxy ufw unattended-upgrades curl

cat > /etc/tinyproxy/tinyproxy.conf <<EOF
User tinyproxy
Group tinyproxy
Port ${PROXY_PORT}
Listen 0.0.0.0
Timeout 30
MaxClients 20
LogLevel Warning
PidFile "/run/tinyproxy/tinyproxy.pid"
DisableViaHeader Yes

# Кто может пользоваться прокси: только с паролем и только с адресов Render
BasicAuth ${PROXY_USER} ${PROXY_PASS}
$(for net in ${ALLOW_FROM}; do echo "Allow ${net}"; done)

# Только туннели на 443 и только к Uzum
ConnectPort 443
FilterType fnmatch
FilterURLs No
FilterCaseSensitive No
FilterDefaultDeny Yes
Filter "/etc/tinyproxy/filter"
EOF

echo "${UPSTREAM_PATTERN}" > /etc/tinyproxy/filter

# Файрвол: SSH для вас, порт прокси — только для Render
ufw allow OpenSSH
for net in ${ALLOW_FROM}; do
    ufw allow from "${net}" to any port "${PROXY_PORT}" proto tcp
done
ufw --force enable

systemctl enable unattended-upgrades >/dev/null 2>&1 || true
systemctl enable tinyproxy
systemctl restart tinyproxy

IP="$(curl -4 -fsS https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"

echo
echo "Готово. Впишите в Render → Environment:"
echo
echo "  PAYMENTS_UZUM_PROXY=http://${PROXY_USER}:${PROXY_PASS}@${IP}:${PROXY_PORT}"
echo
echo "IP для белого списка Uzum: ${IP}"
echo
echo "Сохраните пароль: второй раз скрипт его не покажет"
