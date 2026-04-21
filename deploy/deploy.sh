#!/usr/bin/env bash
# =============================================================================
# deploy.sh — единый деплой: GitHub (main) → VPS → venv → migrate → static → systemd
#
# Запуск на сервере (после первого git clone в PROD_ROOT):
#   sudo bash /var/www/nfc-cards/deploy/deploy.sh
# или из корня репозитория:
#   sudo bash deploy/deploy.sh
#
# Переменные окружения (опционально):
#   PROD_ROOT=/var/www/nfc-cards
#   GIT_ORIGIN=https://github.com/nfsishka-dot/nfc-cards.git
#   DEPLOY_BRANCH=main
#   DEPLOY_USER=deploy
#
# Ожидается:
#   ${PROD_ROOT}/.env — секреты (не в git)
#   ${PROD_ROOT}/.git — репозиторий
#   ${PROD_ROOT}/sources/site_admin/manage.py
#   ${PROD_ROOT}/venv/
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

if [[ $EUID -ne 0 ]]; then
    warn "Запуск без root. Перевызываю через sudo..."
    exec sudo --preserve-env=HOME,PATH bash "$0" "$@"
fi

PROD_ROOT="${PROD_ROOT:-/var/www/nfc-cards}"
GIT_ORIGIN="${GIT_ORIGIN:-https://github.com/nfsishka-dot/nfc-cards.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DJANGO_SUBDIR="${DJANGO_SUBDIR:-sources/site_admin}"

VENV="${PROD_ROOT}/venv"
ENV_FILE="${PROD_ROOT}/.env"
DJANGO_ROOT="${PROD_ROOT}/${DJANGO_SUBDIR}"

# Совместимость со старыми путями: current → корень репо
ensure_current_symlink() {
    if [[ ! -L "${PROD_ROOT}/current" ]] && [[ ! -d "${PROD_ROOT}/current" ]]; then
        info "Создаю symlink ${PROD_ROOT}/current -> ."
        ln -sfn . "${PROD_ROOT}/current"
    elif [[ -d "${PROD_ROOT}/current" ]] && [[ ! -L "${PROD_ROOT}/current" ]]; then
        warn "Существует каталог ${PROD_ROOT}/current (не symlink). Не трогаю — см. deploy/ARCHITECTURE.md"
    fi
}

# -----------------------------------------------------------------------------
# Проверки
# -----------------------------------------------------------------------------
[[ -d "${PROD_ROOT}" ]] || error "Нет каталога PROD_ROOT: ${PROD_ROOT}"

if [[ ! -d "${PROD_ROOT}/.git" ]]; then
    error "В ${PROD_ROOT} нет git-репозитория.
  Один раз выполни от ${DEPLOY_USER}:
    sudo mkdir -p ${PROD_ROOT} && sudo chown ${DEPLOY_USER}:${DEPLOY_USER} ${PROD_ROOT}
    sudo -u ${DEPLOY_USER} git clone ${GIT_ORIGIN} ${PROD_ROOT}
  Затем создай ${ENV_FILE} (см. setup-vps или скопируй с бэкапа)."
fi

[[ -f "${ENV_FILE}" ]] || error ".env не найден: ${ENV_FILE}
  Создай: nano ${ENV_FILE}"

[[ -f "${DJANGO_ROOT}/manage.py" ]] || error "manage.py не найден: ${DJANGO_ROOT}/manage.py}"

[[ -f "${VENV}/bin/python" ]] || error "venv не найден: ${VENV}
  Создай: sudo -u ${DEPLOY_USER} python3 -m venv ${VENV}"

if grep -q "MY_SERVER_IP" "${ENV_FILE}" 2>/dev/null; then
    error ".env содержит MY_SERVER_IP — замени на реальный IP/домен: ${ENV_FILE}"
fi

# -----------------------------------------------------------------------------
# Git = source of truth
# -----------------------------------------------------------------------------
info "PROD_ROOT=${PROD_ROOT}  branch=${DEPLOY_BRANCH}"

REMOTE_URL="$(sudo -u "${DEPLOY_USER}" git -C "${PROD_ROOT}" remote get-url origin 2>/dev/null || true)"
if [[ -z "${REMOTE_URL}" ]]; then
    sudo -u "${DEPLOY_USER}" git -C "${PROD_ROOT}" remote add origin "${GIT_ORIGIN}"
elif [[ "${REMOTE_URL}" != "${GIT_ORIGIN}" ]]; then
    warn "origin был: ${REMOTE_URL} — выставляю ${GIT_ORIGIN}"
    sudo -u "${DEPLOY_USER}" git -C "${PROD_ROOT}" remote set-url origin "${GIT_ORIGIN}"
fi

info "git fetch origin && reset --hard origin/${DEPLOY_BRANCH}"
sudo -u "${DEPLOY_USER}" git -C "${PROD_ROOT}" fetch origin
sudo -u "${DEPLOY_USER}" git -C "${PROD_ROOT}" reset --hard "origin/${DEPLOY_BRANCH}"

ensure_current_symlink

HEAD="$(sudo -u "${DEPLOY_USER}" git -C "${PROD_ROOT}" rev-parse --short HEAD)"
info "Код на сервере: ${HEAD}"

# -----------------------------------------------------------------------------
# Зависимости и Django
# -----------------------------------------------------------------------------
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a
info "Переменные из .env загружены."

info "pip install -r requirements.txt ..."
"${VENV}/bin/pip" install --upgrade pip -q
"${VENV}/bin/pip" install -r "${DJANGO_ROOT}/requirements.txt" -q
info "Зависимости установлены."

info "django check ..."
cd "${DJANGO_ROOT}"
"${VENV}/bin/python" manage.py check --deploy 2>&1 | grep -v "^System check" || true
"${VENV}/bin/python" manage.py check --fail-level ERROR
info "Django check пройден."

info "migrate ..."
"${VENV}/bin/python" manage.py migrate --noinput
info "Миграции применены."

info "collectstatic ..."
"${VENV}/bin/python" manage.py collectstatic --noinput -v 0
info "Статика: ${DJANGO_ROOT}/staticfiles/"

APP_USER="${DEPLOY_USER}"
mkdir -p "${DJANGO_ROOT}/media"
mkdir -p "${PROD_ROOT}/logs"
chown -R "${APP_USER}:${APP_USER}" "${DJANGO_ROOT}/media" "${PROD_ROOT}/logs" 2>/dev/null || true

# -----------------------------------------------------------------------------
# Один gunicorn под systemd: остановить «ручные» процессы этого приложения
# -----------------------------------------------------------------------------
if pgrep -f 'gunicorn.*nfc_site\.wsgi' >/dev/null 2>&1; then
    warn "Останавливаю процессы gunicorn nfc_site.wsgi (перед systemd)"
    pkill -f 'gunicorn.*nfc_site\.wsgi' || true
    sleep 2
    pkill -9 -f 'gunicorn.*nfc_site\.wsgi' 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Перезапуск приложения и nginx
# -----------------------------------------------------------------------------
info "Перезапуск app.service ..."
if [[ -f /etc/systemd/system/app.service ]]; then
    systemctl restart app
else
    warn "Нет /etc/systemd/system/app.service — выполни deploy/setup-vps.sh или deploy/fix-systemd-unify-path.sh"
fi

sleep 2
if systemctl is-active --quiet app 2>/dev/null; then
    info "app.service активен."
else
    warn "app.service не active. Смотри: journalctl -u app -n 50 --no-pager"
fi

if nginx -t 2>/dev/null; then
    systemctl reload nginx && info "nginx перезагружен."
else
    warn "nginx -t не прошёл — проверь конфиг вручную."
fi

cat <<DONE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Деплой завершён. commit: ${HEAD}
  Логи gunicorn:  tail -f ${PROD_ROOT}/logs/gunicorn-error.log
  Логи nginx:     tail -f ${PROD_ROOT}/logs/nginx-error.log
  Статус:         systemctl status app
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DONE
