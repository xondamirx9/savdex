#!/bin/bash
#
# Машина админки (боевая, Uztelecom): собрать образ из кода в
# /opt/savdex/src и отправить его на машину сайта по частной сети.
#
#   WEB_IP=… prod-build.sh
#
# Образ собирается здесь, а не на машине сайта: сборка несколько минут
# занимает оба ядра, и сайт бы на это время тормозил. На машине сайта
# ключ этой машины может только загрузить образ (docker load) — так его
# вписывает .github/workflows/prod.yml.
set -euo pipefail

APP_HOME=${SAVDEX_HOME:-/opt/savdex}
SRC=$APP_HOME/src
: "${WEB_IP:?частный адрес машины сайта}"

sha=$(git -C "$SRC" rev-parse HEAD)
tag=${sha:0:12}

if docker image inspect "savdex:$tag" > /dev/null 2>&1; then
    echo "── Образ savdex:$tag уже собран"
else
    echo "── Сборка образа savdex:$tag"
    DOCKER_BUILDKIT=1 docker build --pull -t "savdex:$tag" "$SRC"
fi

echo "── Образ — на машину сайта ($WEB_IP)"
docker save "savdex:$tag" \
    | ssh -i ~/.ssh/ship_to_web -o IdentitiesOnly=yes -o BatchMode=yes \
        -o StrictHostKeyChecking=yes "deploy@$WEB_IP"

docker builder prune -f --filter until=168h > /dev/null 2>&1 || true
echo "── Готово: savdex:$tag на машинах админки и сайта"
