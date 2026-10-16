#!/bin/bash
#
# Подготовка чистой машины Ubuntu 24.04 в Uztelecom Cloud под SavdEx.
#
# Запускается один раз от root (или через sudo) — из GitHub Actions
# (.github/workflows/staging.yml и prod.yml, «подготовить машину») по
# SSH-ключу, который вписан в машину при создании. Повторный запуск
# ничего не ломает: каждый шаг проверяет, сделан ли он уже.
#
#   SAVDEX_ROLE=staging|web|admin|db [WEB_IP=… ADMIN_IP=…] bash bootstrap.sh
#
# Роль — что будет на машине (deploy/README.md):
# - staging (по умолчанию) — тестовый сервер целиком;
# - web — сайт: HTTP и HTTPS снаружи, общая папка файлов с машины базы;
# - admin — админка: общая папка файлов; здесь же собирается образ, и
#   ключ этой машины пускают на машину сайта только загрузить образ;
# - db — база и общая папка файлов (NFS) для web и admin (их частные
#   адреса — WEB_IP и ADMIN_IP), копии в S3 (deploy/server/backup.sh).
#
# Что делает:
# - обновления: всё сейчас и дальше автоматически (только исправления
#   безопасности, без перезагрузки);
# - Docker, docker compose и buildx (сборка образа) из пакетов Ubuntu; журналы контейнеров
#   с ротацией, иначе они однажды съедят диск;
# - файрвол: снаружи открыты только SSH, HTTP и HTTPS;
# - SSH только по ключу, root — только по ключу; fail2ban банит
#   перебор паролей;
# - пользователь deploy (без пароля, только ключ) — под ним GitHub
#   Actions выкладывает сайт; ключ — тот же, которым вошли сейчас;
# - каталог /opt/savdex: код, данные, база, ключи (env — права 700);
# - файл подкачки 2 ГБ: сборка образа на машине с 4 ГБ не упирается в память.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Нужен root: sudo bash bootstrap.sh" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
APP_HOME=/opt/savdex
ROLE=${SAVDEX_ROLE:-staging}

case "$ROLE" in
    staging|web|admin) ;;
    db)
        if [ -z "${WEB_IP:-}" ] || [ -z "${ADMIN_IP:-}" ]; then
            echo "Машине базы нужны частные адреса сайта и админки: WEB_IP и ADMIN_IP" >&2
            exit 1
        fi
        ;;
    *)
        echo "Неизвестная роль: $ROLE (staging, web, admin или db)" >&2
        exit 1
        ;;
esac
echo "── Роль машины: $ROLE"

extra_packages=()
case "$ROLE" in
    web|admin) extra_packages=(nfs-common) ;;
    db) extra_packages=(nfs-kernel-server gnupg cron) ;;
esac

echo "── Часовой пояс и обновления"
timedatectl set-timezone Asia/Tashkent 2>/dev/null || true
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade
apt-get -y -q install --no-install-recommends \
    docker.io docker-compose-v2 docker-buildx git ufw fail2ban unattended-upgrades ca-certificates curl \
    "${extra_packages[@]}"

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF

echo "── Docker: ротация журналов контейнеров"
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
    cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "local",
  "log-opts": { "max-size": "20m", "max-file": "5" }
}
JSON
    systemctl restart docker
fi
systemctl enable --now docker

echo "── Подкачка"
if ! swapon --show | grep -q .; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "── Пользователь deploy"
if ! id deploy >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash deploy
fi
usermod -aG docker deploy
passwd -l deploy >/dev/null

# Ключ — тот же, которым вошли (root или пользователь образа через sudo)
source_home=/root
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    source_home=$(getent passwd "$SUDO_USER" | cut -d: -f6)
fi
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
if [ -s "$source_home/.ssh/authorized_keys" ]; then
    touch /home/deploy/.ssh/authorized_keys
    # Дописать только новые строки: повторный запуск не плодит дубли
    sort -u "$source_home/.ssh/authorized_keys" /home/deploy/.ssh/authorized_keys \
        -o /home/deploy/.ssh/authorized_keys
fi
chown deploy:deploy /home/deploy/.ssh/authorized_keys 2>/dev/null || true
chmod 600 /home/deploy/.ssh/authorized_keys 2>/dev/null || true

echo "── Каталог $APP_HOME"
install -d -m 755 -o deploy -g deploy "$APP_HOME"
install -d -m 700 -o deploy -g deploy "$APP_HOME/env"
install -d -m 755 -o deploy -g deploy "$APP_HOME/data"

echo "── SSH: только по ключу"
cat > /etc/ssh/sshd_config.d/10-savdex.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF
# Ubuntu 24.04 запускает sshd по сокету (ssh.socket): каталога /run/sshd
# может не быть, и без него `sshd -t` отказывается проверять настройки
install -d -m 755 /run/sshd
sshd -t
if systemctl is-active --quiet ssh; then
    systemctl reload ssh
elif systemctl is-active --quiet sshd; then
    systemctl reload sshd
fi
# Демон не запущен (ждёт подключения на сокете) — настройки подхватит сам при старте

echo "── fail2ban"
systemctl enable --now fail2ban

# ── Роль ───────────────────────────────────────────────────────────

if [ "$ROLE" = db ]; then
    echo "── Общая папка файлов для сайта и админки (NFS)"
    # Все записи — от www-data контейнера сайта (uid 33): сайт и админка
    # пишут файлы, root клиента здесь не root
    install -d -m 755 -o 33 -g 33 /srv/savdex/storage /srv/savdex/storage/cache
    install -d -m 755 /etc/exports.d
    cat > /etc/exports.d/savdex.exports <<EXPORTS
/srv/savdex/storage ${WEB_IP}(rw,sync,no_subtree_check,all_squash,anonuid=33,anongid=33) ${ADMIN_IP}(rw,sync,no_subtree_check,all_squash,anonuid=33,anongid=33)
EXPORTS
    systemctl enable --now nfs-server
    exportfs -ra
    # Каталог базы — 755: образ postgres входит в него ещё до смены
    # владельца, а сами данные (pg/18/docker) PostgreSQL закрывает
    # правами 700 сам. С 700 на этом каталоге база не запускалась
    install -d -m 755 -o root -g root "$APP_HOME/pg"
    install -d -m 700 -o deploy -g deploy "$APP_HOME/backup"
fi

if [ "$ROLE" = admin ]; then
    echo "── Ключ для загрузки образа на машину сайта"
    # Образ собирается здесь и уходит на машину сайта по частной сети.
    # Там этот ключ может только одно — загрузить образ (docker load):
    # так его вписывает prod.yml
    if [ ! -s /home/deploy/.ssh/ship_to_web ]; then
        runuser -u deploy -- ssh-keygen -q -t ed25519 -N '' -C "savdex-admin-ship" \
            -f /home/deploy/.ssh/ship_to_web
    fi
fi

echo "── Файрвол"
# Порты контейнеров Docker публикует в обход ufw — поэтому наружу
# публикуются только 80 и 443 (Caddy), а база и приложение — только на
# частный адрес машины
ufw allow OpenSSH >/dev/null
case "$ROLE" in
    staging|web)
        ufw allow 80/tcp >/dev/null
        ufw allow 443/tcp >/dev/null
        ufw allow 443/udp >/dev/null
        ;;
    db)
        for ip in "$WEB_IP" "$ADMIN_IP"; do
            ufw allow from "$ip" to any port 2049 proto tcp >/dev/null
        done
        ;;
esac

# Порт, опубликованный Docker на частный адрес, ufw не закрывает: его
# видит любая машина частной сети. Цепочка DOCKER-USER — место, которое
# Docker оставляет для своих правил: база (5432) — только сайту и
# админке, приложение админки (10000) — только Caddy машины сайта.
# Контейнеры самой машины (мосты docker0, br-*) не трогаем. Правила —
# в after.rules ufw: переживают перезагрузку; блок между метками
# заменяется при повторном запуске
docker_guard() {
    local port="$1"
    shift
    local ip
    printf -- '-A DOCKER-USER -p tcp --dport %s -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN\n' "$port"
    printf -- '-A DOCKER-USER -p tcp --dport %s -i docker0 -j RETURN\n' "$port"
    printf -- '-A DOCKER-USER -p tcp --dport %s -i br-+ -j RETURN\n' "$port"
    for ip in "$@"; do
        printf -- '-A DOCKER-USER -p tcp --dport %s -s %s -j RETURN\n' "$port" "$ip"
    done
    printf -- '-A DOCKER-USER -p tcp --dport %s -j DROP\n' "$port"
}

guard_rules=""
case "$ROLE" in
    db) guard_rules=$(docker_guard 5432 "$WEB_IP" "$ADMIN_IP") ;;
    admin)
        if [ -n "${WEB_IP:-}" ]; then
            guard_rules=$(docker_guard 10000 "$WEB_IP")
        else
            echo "ВНИМАНИЕ: WEB_IP не задан — порт админки 10000 открыт всей частной сети. Запустите с WEB_IP=<частный адрес сайта>." >&2
        fi
        ;;
esac

if [ -n "$guard_rules" ]; then
    sed -i '/^# BEGIN savdex docker-user/,/^# END savdex docker-user/d' /etc/ufw/after.rules
    cat >> /etc/ufw/after.rules <<RULES
# BEGIN savdex docker-user
*filter
:DOCKER-USER - [0:0]
${guard_rules}
-A DOCKER-USER -j RETURN
COMMIT
# END savdex docker-user
RULES
fi
ufw --force enable >/dev/null
ufw reload >/dev/null

echo "── Готово: $(lsb_release -ds 2>/dev/null || echo Linux), $(docker --version), $(docker compose version)"
echo "Ключ этой машины (для known_hosts в GitHub):"
cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub
