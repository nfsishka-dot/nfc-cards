#!/usr/bin/env bash
# =============================================================================
# align-production-to-github.sh — аудит и выравнивание production под GitHub main
#
# Не изменяет содержимое .env (только проверяет наличие и использование в app-start).
#
# Использование на сервере:
#   sudo bash align-production-to-github.sh audit    # только отчёт (шаг 1 + 8 read-only)
#   sudo bash align-production-to-github.sh apply    # полный прогон (шаги 2–8)
#
# Переменные (опционально):
#   PROD_ROOT=/var/www/nfc-cards
#   DEPLOY_USER=deploy
#   GIT_ORIGIN=https://github.com/nfsishka-dot/nfc-cards.git
#   GUNICORN_SOCK=/run/gunicorn.sock
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[align]${NC} $*"; }
warn()  { echo -e "${YELLOW}[align]${NC} $*"; }
error() { echo -e "${RED}[align]${NC} $*" >&2; exit 1; }

MODE="${1:-}"
[[ "$MODE" == "audit" || "$MODE" == "apply" ]] || error "Укажи: audit | apply"

PROD_ROOT="${PROD_ROOT:-/var/www/nfc-cards}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DJANGO_ROOT="${PROD_ROOT}/sources/site_admin"
VENV="${PROD_ROOT}/venv"
ENV_FILE="${PROD_ROOT}/.env"
GIT_ORIGIN="${GIT_ORIGIN:-https://github.com/nfsishka-dot/nfc-cards.git}"
GUNICORN_SOCK="${GUNICORN_SOCK:-/run/gunicorn.sock}"
BACKUP_DIR="/root/nfc-align-backup-$(date +%Y%m%d-%H%M%S)"

# -----------------------------------------------------------------------------
report_header() {
  echo ""
  echo "══════════════════════════════════════════════════════════════"
  echo " $1"
  echo "══════════════════════════════════════════════════════════════"
}

# ШАГ 1 — отчёт (и для audit, и в начале apply)
# -----------------------------------------------------------------------------
step_audit() {
  report_header "ШАГ 1 — ТЕКУЩЕЕ СОСТОЯНИЕ"

  echo "--- ps gunicorn ---"
  ps auxww 2>/dev/null | grep -E '[g]unicorn' || echo "(нет процессов gunicorn в ps)"

  echo ""
  echo "--- cwd / exe / venv по PID gunicorn (nfc_site) ---"
  ACTIVE_DJANGO_ROOT="UNKNOWN"
  ACTIVE_VENV="UNKNOWN"
  for pid in $(pgrep -f 'gunicorn.*nfc_site' 2>/dev/null || true); do
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "?")"
    exe="$(readlink -f "/proc/$pid/exe" 2>/dev/null || echo "?")"
    echo "PID=$pid cwd=$cwd exe=$exe"
    ACTIVE_DJANGO_ROOT="$cwd"
    if [[ "$exe" == *"/venv/bin/python"* ]] || [[ "$exe" == *"/venv/bin/gunicorn"* ]]; then
      ACTIVE_VENV="$(echo "$exe" | sed -n 's|^\(.*venv\)/bin/.*|\1|p')"
    fi
  done

  echo ""
  echo "--- systemctl app.service ---"
  SYSTEMD_STATUS="unknown"
  if [[ -f /etc/systemd/system/app.service ]]; then
    systemctl status app --no-pager -l 2>&1 | head -40 || true
    SYSTEMD_STATUS="$(systemctl is-active app 2>/dev/null || echo inactive)"
    echo ""
    echo "--- systemctl cat app ---"
    systemctl cat app 2>/dev/null || true
  else
    echo "(файл /etc/systemd/system/app.service не найден)"
    SYSTEMD_STATUS="no_unit_file"
  fi

  echo ""
  echo "--- nginx proxy_pass / unix ---"
  NGINX_TARGET=""
  if [[ -d /etc/nginx/sites-enabled ]]; then
    grep -R "proxy_pass\|unix:\|upstream" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null || true
    NGINX_TARGET="$(grep -Rh "unix:" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | head -3 | tr '\n' ' ')"
  fi

  echo ""
  echo "--- find manage.py под /var/www ---"
  find /var/www -maxdepth 6 -name manage.py 2>/dev/null || true

  echo ""
  echo "--- .env ---"
  if [[ -f "$ENV_FILE" ]]; then
    echo "OK: существует $ENV_FILE (содержимое не показываем)"
    ls -la "$ENV_FILE"
  else
    echo "WARN: нет $ENV_FILE"
  fi

  echo ""
  report_header "СВОДКА (ШАГ 1)"
  echo "ACTIVE_DJANGO_ROOT (по первому PID): $ACTIVE_DJANGO_ROOT"
  echo "ACTIVE_GUNICORN_PROCESS: см. блок ps выше"
  echo "ACTIVE_VENV (эвристика по exe): $ACTIVE_VENV"
  echo "SYSTEMD_STATUS: $SYSTEMD_STATUS"
  echo "NGINX_TARGET (unix snippets): ${NGINX_TARGET:-см. grep выше}"
}

# ШАГ 3–4 — git + venv + django (только apply)
# -----------------------------------------------------------------------------
step_git_and_django() {
  [[ $EUID -eq 0 ]] || error "Нужен root для apply"

  [[ -d "${PROD_ROOT}/.git" ]] || error "Нет git в ${PROD_ROOT}"

  info "git fetch + reset --hard origin/main (от пользователя ${DEPLOY_USER})"
  sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" remote set-url origin "$GIT_ORIGIN" 2>/dev/null || \
    sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" remote add origin "$GIT_ORIGIN"
  sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" fetch origin
  sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" reset --hard origin/main

  echo ""
  echo "--- git status после reset ---"
  sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" status -sb
  echo "HEAD: $(sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" rev-parse HEAD)"
  echo "origin/main: $(sudo -u "$DEPLOY_USER" git -C "$PROD_ROOT" rev-parse origin/main)"

  [[ -f "$ENV_FILE" ]] || error "Нет $ENV_FILE — создай вручную, скрипт .env не трогает"

  info "pip install"
  "${VENV}/bin/pip" install --upgrade pip -q
  "${VENV}/bin/pip" install -r "${DJANGO_ROOT}/requirements.txt" -q

  info "migrate + collectstatic"
  cd "$DJANGO_ROOT"
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
  "${VENV}/bin/python" manage.py migrate --noinput
  "${VENV}/bin/python" manage.py collectstatic --noinput -v 0

  mkdir -p "${PROD_ROOT}/logs" "${DJANGO_ROOT}/media"
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${DJANGO_ROOT}/media" "${PROD_ROOT}/logs" 2>/dev/null || true
}

# ШАГ 5 — systemd
# -----------------------------------------------------------------------------
step_systemd() {
  [[ $EUID -eq 0 ]] || error "Нужен root"

  mkdir -p "$BACKUP_DIR"
  if [[ -f /etc/systemd/system/app.service ]]; then
    cp -a /etc/systemd/system/app.service "$BACKUP_DIR/"
  fi
  if [[ -f /usr/local/bin/app-start.sh ]]; then
    cp -a /usr/local/bin/app-start.sh "$BACKUP_DIR/"
  fi

  cat > /usr/local/bin/app-start.sh <<EOF
#!/usr/bin/env bash
set -a
source ${ENV_FILE} 2>/dev/null || true
set +a
exec ${VENV}/bin/gunicorn \\
    nfc_site.wsgi:application \\
    --workers 2 \\
    --bind unix:${GUNICORN_SOCK} \\
    --access-logfile ${PROD_ROOT}/logs/gunicorn-access.log \\
    --error-logfile ${PROD_ROOT}/logs/gunicorn-error.log \\
    --log-level info \\
    --timeout 60 \\
    --keep-alive 5 \\
    --max-requests 1000 \\
    --max-requests-jitter 100
EOF
  chmod 755 /usr/local/bin/app-start.sh

  cat > /etc/systemd/system/app.service <<EOF
[Unit]
Description=nfc_cards gunicorn (aligned ${PROD_ROOT})
After=network.target postgresql.service redis.service
Requires=postgresql.service

[Service]
User=${DEPLOY_USER}
Group=${DEPLOY_USER}
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
EOF

  systemctl daemon-reload
  systemctl enable app
  info "systemd app.service записан, бэкап: $BACKUP_DIR"
}

# ШАГ 6 — nginx: только проверка и бэкап; правка только если upstream не unix:${GUNICORN_SOCK}
# -----------------------------------------------------------------------------
step_nginx() {
  [[ $EUID -eq 0 ]] || error "Нужен root"

  mkdir -p "$BACKUP_DIR"
  for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*; do
    [[ -f "$f" ]] || continue
    cp -a "$f" "$BACKUP_DIR/" 2>/dev/null || true
  done

  # Если в sites-available/app есть upstream на другой сокет — показать diff
  APP_SITE="/etc/nginx/sites-available/app"
  if [[ -f "$APP_SITE" ]]; then
    if ! grep -q "unix:${GUNICORN_SOCK}" "$APP_SITE" 2>/dev/null; then
      warn "В $APP_SITE не найден unix:${GUNICORN_SOCK} — проверь вручную. Файл скопирован в $BACKUP_DIR"
    else
      info "nginx app: upstream указывает на ${GUNICORN_SOCK}"
    fi
  else
    warn "Нет $APP_SITE — конфиг nginx может быть другим; смотри бэкап и sites-enabled"
  fi

  nginx -t
}

# Остановить дубли gunicorn вне systemd перед restart
# -----------------------------------------------------------------------------
kill_manual_gunicorn() {
  if pgrep -f 'gunicorn.*nfc_site\.wsgi' >/dev/null 2>&1; then
    warn "Завершаю процессы gunicorn nfc_site.wsgi перед systemctl restart app"
    systemctl stop app 2>/dev/null || true
    pkill -f 'gunicorn.*nfc_site\.wsgi' || true
    sleep 2
    pkill -9 -f 'gunicorn.*nfc_site\.wsgi' 2>/dev/null || true
  fi
}

# ШАГ 7–8
# -----------------------------------------------------------------------------
step_restart_and_verify() {
  kill_manual_gunicorn
  systemctl restart app
  sleep 2
  systemctl restart nginx

  report_header "ШАГ 8 — ПРОВЕРКА"
  systemctl status app --no-pager -l | head -25 || true
  echo ""
  curl -sS -o /dev/null -w "HTTP 127.0.0.1: %{http_code}\n" http://127.0.0.1/ || true
  echo ""
  echo "Оставшиеся gunicorn (не должно быть дублей nfc_site вне systemd):"
  ps auxww | grep -E '[g]unicorn' || echo "(нет)"
}

final_report() {
  report_header "ФИНАЛЬНЫЙ ОТЧЁТ"
  echo "1) ACTIVE SYSTEM STATE: см. systemctl status app и curl выше"
  echo "2) CONFIRMED ROOT PATH: ${DJANGO_ROOT}"
  echo "3) CONFIRMED GUNICORN: systemd unit app.service, WorkingDirectory=${DJANGO_ROOT}, venv=${VENV}"
  echo "4) CONFIRMED NGINX FLOW: proxy_pass → upstream → unix:${GUNICORN_SOCK} (проверь grep в шаге 1)"
  echo "5) RISKS: старые каталоги /var/www/app не удалялись; дубли процессов — см. ps после шага 8"
  echo ""
  echo "Бэкапы конфигов: ${BACKUP_DIR}"
  echo ""
  if systemctl is-active --quiet app 2>/dev/null && curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1/ | grep -qE '200|301|302'; then
    echo "DEPLOY STATUS: STABLE"
  elif systemctl is-active --quiet app 2>/dev/null; then
    echo "DEPLOY STATUS: PARTIALLY STABLE (app active, HTTP не 200 — проверь nginx/БД)"
  else
    echo "DEPLOY STATUS: BROKEN"
  fi
}

# --- main ---
if [[ "$MODE" == "audit" ]]; then
  step_audit
  report_header "РЕЖИМ AUDIT ЗАВЕРШЁН"
  echo "Для применения: sudo bash $0 apply"
  exit 0
fi

[[ $EUID -eq 0 ]] || error "apply: запуск от root: sudo bash $0 apply"

step_audit
report_header "РЕЖИМ APPLY — синхронизация"
step_git_and_django
step_systemd
step_nginx
step_restart_and_verify
final_report
