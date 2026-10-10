#!/bin/bash
#
# Подготовка чистой машины Ubuntu 24.04 в Uztelecom Cloud под SavdEx.
#
# Запускается один раз от root (или через sudo) — из GitHub Actions
# (.github/workflows/staging.yml, «подготовить сервер») по SSH-ключу,
# который вписан в машину при создании. Повторный запуск ничего не
# ломает: каждый шаг проверяет, сделан ли он уже.
#
# Что делает:
# - обновления: всё сейчас и дальше автоматически (только исправления
#   безопасности, без перезагрузки);
# - Docker и docker compose из пакетов Ubuntu; журналы контейнеров
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

echo "── Часовой пояс и обновления"
timedatectl set-timezone Asia/Tashkent 2>/dev/null || true
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade
apt-get -y -q install --no-install-recommends \
    docker.io docker-compose-v2 git ufw fail2ban unattended-upgrades ca-certificates

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
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd

echo "── fail2ban"
systemctl enable --now fail2ban

echo "── Файрвол: SSH, HTTP, HTTPS"
# Порты контейнеров Docker публикует в обход ufw — поэтому наружу
# публикуются только 80 и 443 (Caddy), а база и приложение — нет
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null
ufw --force enable >/dev/null

echo "── Готово: $(lsb_release -ds 2>/dev/null || echo Linux), $(docker --version), $(docker compose version)"
echo "Ключ этой машины (переменная STAGING_HOST_KEY в GitHub):"
cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub
