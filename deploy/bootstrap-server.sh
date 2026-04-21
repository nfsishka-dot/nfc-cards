#!/usr/bin/env bash
# =============================================================================
# Первый клон на VPS (часто после setup-vps.sh, когда в PROD_ROOT уже есть venv/logs).
# Запуск: sudo bash bootstrap-server.sh
# Клонирует во временный каталог и rsync в PROD_ROOT (мердж с существующими venv/logs).
# =============================================================================
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Нужен root: sudo bash $0"; exit 1; }

PROD_ROOT="${PROD_ROOT:-/var/www/nfc-cards}"
GIT_ORIGIN="${GIT_ORIGIN:-https://github.com/nfsishka-dot/nfc-cards.git}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

if [[ -d "${PROD_ROOT}/.git" ]]; then
  echo "Уже есть ${PROD_ROOT}/.git — пропуск."
  exit 0
fi

mkdir -p "${PROD_ROOT}"
chown "${DEPLOY_USER}:${DEPLOY_USER}" "${PROD_ROOT}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

sudo -u "${DEPLOY_USER}" git clone "${GIT_ORIGIN}" "${TMP}/repo"
sudo rsync -a "${TMP}/repo/" "${PROD_ROOT}/"
sudo chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${PROD_ROOT}"

echo "Клон влит в ${PROD_ROOT}. Дальше: создай/проверь ${PROD_ROOT}/.env, затем sudo bash ${PROD_ROOT}/deploy/deploy.sh"
