#!/usr/bin/env bash
# =============================================================================
#  deploy.sh — деплой нового кода на уже настроенный сервер
#
#  Запуск: bash /var/www/app/deploy.sh
#
#  Ожидает что:
#    - setup-vps.sh уже был выполнен
#    - код загружен в /var/www/app/current/
#      (структура: current/sources/site_admin/manage.py)
#    - /var/www/app/current/.env существует и заполнен
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# =============================================================================
# Автоподнятие привилегий: если запущен не от root — перевызываем через sudo.
# Это нужно для systemctl и nginx команд в конце скрипта.
# Остальная логика (pip, manage.py) выполняется от пользователя deploy — OK,
# потому что sudo сохраняет оригинального пользователя в SUDO_USER.
# =============================================================================
if [[ $EUID -ne 0 ]]; then
    warn "Запуск без root. Перевызываю через sudo..."
    exec sudo --preserve-env=HOME,PATH bash "$0" "$@"
fi

# =============================================================================
# Переменные — должны совпадать с setup-vps.sh
# =============================================================================
APP_DIR="/var/www/app"
CURRENT="${APP_DIR}/current"
VENV="${APP_DIR}/venv"
ENV_FILE="${CURRENT}/.env"
DJANGO_SUBDIR="sources/site_admin"      # подпапка с manage.py внутри current/
DJANGO_ROOT="${CURRENT}/${DJANGO_SUBDIR}"

# =============================================================================
# Проверки перед запуском
# =============================================================================
[[ -f "${ENV_FILE}" ]] || error ".env не найден: ${ENV_FILE}
  Создай его: nano ${ENV_FILE}
  Образец: /var/www/app/current/.env.example (если есть)"

[[ -f "${DJANGO_ROOT}/manage.py" ]] || error "manage.py не найден: ${DJANGO_ROOT}/manage.py
  Загрузи код в ${CURRENT}/
  Структура должна быть: ${CURRENT}/sources/site_admin/manage.py"

[[ -f "${VENV}/bin/python" ]] || error "venv не найден: ${VENV}
  Сначала запусти: sudo bash /root/setup-vps.sh"

# Проверяем что .env не содержит незаполненный плейсхолдер
if grep -q "MY_SERVER_IP" "${ENV_FILE}"; then
    error ".env содержит незаполненный плейсхолдер MY_SERVER_IP.
  Отредактируй: nano ${ENV_FILE}
  Замени MY_SERVER_IP на реальный IP или домен."
fi

# =============================================================================
# Загружаем переменные окружения для manage.py
# =============================================================================
set -a; source "${ENV_FILE}"; set +a
info "Переменные окружения загружены."

# =============================================================================
# Зависимости
# =============================================================================
info "pip install -r requirements.txt ..."
"${VENV}/bin/pip" install --upgrade pip -q
"${VENV}/bin/pip" install -r "${DJANGO_ROOT}/requirements.txt" -q
info "Зависимости установлены."

# =============================================================================
# Django: проверка конфигурации
# =============================================================================
info "django check ..."
cd "${DJANGO_ROOT}"
"${VENV}/bin/python" manage.py check --deploy 2>&1 | grep -v "^System check" || true
# Не падаем от предупреждений check --deploy (они ожидаемы без HTTPS),
# но явные ошибки всё равно вызовут exit 1 из-за set -e.
"${VENV}/bin/python" manage.py check --fail-level ERROR
info "Django check пройден."

# =============================================================================
# Миграции
# =============================================================================
info "migrate ..."
"${VENV}/bin/python" manage.py migrate --noinput
info "Миграции применены."

# =============================================================================
# Статика
# =============================================================================
info "collectstatic ..."
"${VENV}/bin/python" manage.py collectstatic --noinput -v 0
info "Статика собрана в ${DJANGO_ROOT}/staticfiles/"

# =============================================================================
# Права на media и logs (на случай первого запуска)
# =============================================================================
APP_USER="deploy"
mkdir -p "${DJANGO_ROOT}/media"
mkdir -p "${APP_DIR}/logs"
chown -R ${APP_USER}:${APP_USER} "${DJANGO_ROOT}/media" "${APP_DIR}/logs" 2>/dev/null || true

# =============================================================================
# Перезапуск gunicorn
# =============================================================================
info "Перезапуск gunicorn (app.service) ..."
if systemctl is-active --quiet app; then
    # Graceful reload — не режем активные соединения
    systemctl reload app 2>/dev/null || systemctl restart app
else
    systemctl start app
fi

# Даём пару секунд подняться
sleep 3

if systemctl is-active --quiet app; then
    info "app.service запущен."
else
    error "app.service не запустился.
  Диагностика:
    journalctl -u app -n 50 --no-pager
    cat /var/www/app/logs/gunicorn-error.log"
fi

# =============================================================================
# Перезагрузка nginx (на случай изменения конфига)
# =============================================================================
nginx -t && systemctl reload nginx && info "nginx перезагружен."

# =============================================================================
# Итог
# =============================================================================
SERVER_IP="${DJANGO_ALLOWED_HOSTS:-???}"
cat <<DONE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Деплой завершён.
  Открой в браузере: http://${SERVER_IP}/
  Логи gunicorn:  tail -f /var/www/app/logs/gunicorn-error.log
  Логи nginx:     tail -f /var/www/app/logs/nginx-error.log
  Статус:         systemctl status app
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DONE
