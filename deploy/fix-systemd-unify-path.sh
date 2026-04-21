#!/usr/bin/env bash
# =============================================================================
# fix-systemd-unify-path.sh — выровнять systemd app.service под реальный каталог кода
#
# Сценарий: gunicorn запущен вручную из /var/www/nfc-cards/, а unit смотрит на
# /var/www/app/current/ — сервис падает и не управляет процессом.
#
# Запуск на сервере (от root):
#   sudo bash fix-systemd-unify-path.sh
#
# Переменные окружения (опционально):
#   APP_BASE_DIR=/var/www/nfc-cards   — корень дерева с кодом (как в репо)
#   DJANGO_SUBDIR=sources/site_admin  — подпапка с manage.py
#   APP_USER=deploy
#   VENV_PATH=...                     — если venv не в ${APP_BASE_DIR}/venv
#   GUNICORN_SOCK=/run/gunicorn.sock  — должен совпадать с nginx upstream
#   ENV_FILE_OVERRIDE=/path/.env     — если .env только в старом каталоге
#
# Не меняет Django settings и код приложения — только systemd и app-start.sh.
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[unify]${NC} $*"; }
warn()  { echo -e "${YELLOW}[unify]${NC} $*"; }
error() { echo -e "${RED}[unify]${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Запусти от root: sudo bash $0"

APP_BASE_DIR="${APP_BASE_DIR:-/var/www/nfc-cards}"
DJANGO_SUBDIR="${DJANGO_SUBDIR:-sources/site_admin}"
APP_USER="${APP_USER:-deploy}"
WORKERS="${WORKERS:-2}"
GUNICORN_SOCK="${GUNICORN_SOCK:-/run/gunicorn.sock}"

# Django root: PROD_ROOT/sources/site_admin (см. deploy/ARCHITECTURE.md)
DJANGO_ROOT="${APP_BASE_DIR}/${DJANGO_SUBDIR}"

if [[ -n "${ENV_FILE_OVERRIDE:-}" ]]; then
  ENV_FILE="${ENV_FILE_OVERRIDE}"
elif [[ -f "${APP_BASE_DIR}/.env" ]]; then
  ENV_FILE="${APP_BASE_DIR}/.env"
elif [[ -f "${DJANGO_ROOT}/.env" ]]; then
  ENV_FILE="${DJANGO_ROOT}/.env"
else
  ENV_FILE="${APP_BASE_DIR}/.env"
fi

if [[ -d "${APP_BASE_DIR}/venv" && -x "${APP_BASE_DIR}/venv/bin/gunicorn" ]]; then
  VENV="${APP_BASE_DIR}/venv"
elif [[ -n "${VENV_PATH:-}" && -x "${VENV_PATH}/bin/gunicorn" ]]; then
  VENV="${VENV_PATH}"
  warn "Используется VENV_PATH=${VENV} (не внутри APP_BASE_DIR)"
else
  error "Не найден venv с gunicorn. Ожидалось: ${APP_BASE_DIR}/venv
  Либо задай: export VENV_PATH=/path/to/venv"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  error "Нет .env: ${ENV_FILE}
  Создай файл или: export ENV_FILE_OVERRIDE=/path/to/.env"
fi

[[ -f "${DJANGO_ROOT}/manage.py" ]] || error "Нет manage.py: ${DJANGO_ROOT}/manage.py"

info "Продакшен-корень: ${DJANGO_ROOT}"
info "venv: ${VENV}"
info "сокет: ${GUNICORN_SOCK}"

LOG_DIR="${APP_BASE_DIR}/logs"
mkdir -p "${LOG_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${LOG_DIR}" 2>/dev/null || true

# -----------------------------------------------------------------------------
# Остановить unit и процессы gunicorn для этого приложения (не трогаем чужие)
# -----------------------------------------------------------------------------
if systemctl is-active --quiet app 2>/dev/null; then
  info "Останавливаю app.service ..."
  systemctl stop app || true
fi

# Процессы, которые слушают тот же WSGI-модуль (остатки ручного запуска)
if pgrep -f 'gunicorn.*nfc_site\.wsgi' >/dev/null 2>&1; then
  warn "Завершаю процессы gunicorn (nfc_site.wsgi), не оставляем дубликаты"
  pkill -f 'gunicorn.*nfc_site\.wsgi' || true
  sleep 2
  if pgrep -f 'gunicorn.*nfc_site\.wsgi' >/dev/null 2>&1; then
    pkill -9 -f 'gunicorn.*nfc_site\.wsgi' || true
  fi
fi

# -----------------------------------------------------------------------------
# app-start.sh — один источник правды для ExecStart
# -----------------------------------------------------------------------------
cat > /usr/local/bin/app-start.sh <<STARTSCRIPT
#!/usr/bin/env bash
set -a
source ${ENV_FILE} 2>/dev/null || true
set +a
exec ${VENV}/bin/gunicorn \\
    nfc_site.wsgi:application \\
    --workers ${WORKERS} \\
    --bind unix:${GUNICORN_SOCK} \\
    --access-logfile ${LOG_DIR}/gunicorn-access.log \\
    --error-logfile  ${LOG_DIR}/gunicorn-error.log \\
    --log-level info \\
    --timeout 60 \\
    --keep-alive 5 \\
    --max-requests 1000 \\
    --max-requests-jitter 100
STARTSCRIPT
chmod 755 /usr/local/bin/app-start.sh

# -----------------------------------------------------------------------------
# systemd unit
# -----------------------------------------------------------------------------
cat > /etc/systemd/system/app.service <<UNIT
[Unit]
Description=nfc_cards gunicorn (unified path: ${APP_BASE_DIR})
After=network.target postgresql.service redis.service
Requires=postgresql.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${DJANGO_ROOT}
ExecStart=/usr/local/bin/app-start.sh
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
RuntimeDirectory=gunicorn
RuntimeDirectoryMode=0755
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable app
systemctl start app

sleep 2
if systemctl is-active --quiet app; then
  info "app.service активен."
  systemctl status app --no-pager -l || true
else
  error "app.service не поднялся. Смотри: journalctl -u app -n 80 --no-pager"
fi

info "Проверка: curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1/ || true"
info "Дальше: убедись, что nginx proxy_pass указывает на unix:${GUNICORN_SOCK}"
