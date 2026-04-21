#!/usr/bin/env bash
# Выполняется на VPS из GitHub Actions (stdin: bash -s < this file).
# Не трогает содержимое .env — только source для Django.
set -euo pipefail

PROD_ROOT="/var/www/nfc-cards"
DJANGO_ROOT="${PROD_ROOT}/sources/site_admin"
VENV="${PROD_ROOT}/venv"
ENV_FILE="${PROD_ROOT}/.env"

echo "START DEPLOY"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${ENV_FILE}"
  exit 1
fi

cd "${PROD_ROOT}"

echo "git fetch + reset --hard origin/main"
git fetch origin
git reset --hard origin/main

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

echo "pip install"
"${VENV}/bin/pip" install --upgrade pip -q
"${VENV}/bin/pip" install -r "${DJANGO_ROOT}/requirements.txt" -q

cd "${DJANGO_ROOT}"
echo "migrate"
"${VENV}/bin/python" manage.py migrate --noinput

echo "collectstatic"
"${VENV}/bin/python" manage.py collectstatic --noinput

echo "restart services"
if [[ "$(id -u)" -eq 0 ]]; then
  systemctl restart app
  systemctl restart nginx
else
  sudo -n systemctl restart app
  sudo -n systemctl restart nginx
fi

echo "DONE"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1/ || true
