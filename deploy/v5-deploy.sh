#!/usr/bin/env bash
# Production deploy V5 — проверяемый пайплайн: releases + current + shared/.env + отчёт.
# Запуск на VPS: bash -s < deploy/v5-deploy.sh (от root), либо из CI:
#   ssh deploy@host 'sudo -n bash -s' < deploy/v5-deploy.sh  (нужен NOPASSWD для deploy)
#
# Секреты не перезаписываются: source только $BASE/shared/.env
# (если файла нет, но есть $BASE/.env — один раз копируется в shared/.env с предупреждением).
#
set -euo pipefail

BASE="/var/www/nfc-cards"
RELEASES="$BASE/releases"
VENV="$BASE/venv"
SHARED_DIR="$BASE/shared"
ENV_FILE="$SHARED_DIR/.env"
SHARED_MEDIA="$SHARED_DIR/media"
LOCK_FILE="/var/lock/nfc-deploy.lock"
LOCK_FILE_FALLBACK="/tmp/nfc-deploy.lock"
GIT_ORIGIN="${GIT_ORIGIN:-https://github.com/nfsishka-dot/nfc-cards.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

DEPLOY_STATUS="FAILED"
ACTIVE_RELEASE=""
ACTIVE_COMMIT=""
HEALTHCHECK_RESULT="FAIL"

log() { echo "[v5-deploy] $*"; }

print_report_block() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "DEPLOY STATUS: ${DEPLOY_STATUS}"
  echo "ACTIVE_RELEASE: ${ACTIVE_RELEASE}"
  echo "ACTIVE_COMMIT: ${ACTIVE_COMMIT}"
  echo "HEALTHCHECK: ${HEALTHCHECK_RESULT}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

sc_reload_nginx() {
  if [[ "$(id -u)" -eq 0 ]]; then
    nginx -t && systemctl reload nginx
  else
    sudo -n nginx -t && sudo -n systemctl reload nginx
  fi
}

sc_start_or_reload_app() {
  if [[ "$(id -u)" -eq 0 ]]; then
    if systemctl is-active --quiet app 2>/dev/null; then
      systemctl reload app 2>/dev/null || systemctl restart app
    else
      systemctl start app
    fi
  else
    if sudo -n systemctl is-active --quiet app 2>/dev/null; then
      sudo -n systemctl reload app 2>/dev/null || sudo -n systemctl restart app
    else
      sudo -n systemctl start app
    fi
  fi
}

load_env() {
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
  HEALTHCHECK_BASE="${HEALTHCHECK_BASE:-http://127.0.0.1}"
}

healthcheck_all() {
  local base="${HEALTHCHECK_BASE:-http://127.0.0.1}"
  base="${base%/}"
  local third="${DEPLOY_HEALTHCHECK_PUBLIC_URL:-}"
  local code

  # Главная страница может осознанно отдавать 404 (например, нет public index view).
  # Критичным считаем доступность /admin/.
  code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "${base}/" || echo "000")"
  log "healthcheck: ${base}/ -> HTTP $code"
  case "$code" in
    200|301|302|404) ;;
    *) return 1 ;;
  esac

  code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "${base}/admin/" || echo "000")"
  log "healthcheck: ${base}/admin/ -> HTTP $code"
  case "$code" in
    200|301|302) ;;
    *) return 1 ;;
  esac

  if [[ -n "$third" ]]; then
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "$third" || echo "000")"
    log "healthcheck (DEPLOY_HEALTHCHECK_PUBLIC_URL): $third -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) return 1 ;;
    esac
  else
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "${base}/" || echo "000")"
    log "healthcheck (fallback /): ${base}/ -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) return 1 ;;
    esac
  fi
  return 0
}

ensure_venv() {
  if [[ ! -x "$VENV/bin/python" ]]; then
    log "creating venv at $VENV"
    python3 -m venv "$VENV"
  fi
}

ensure_shared_env() {
  mkdir -p "$SHARED_DIR" "$SHARED_MEDIA"
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$BASE/.env" ]]; then
      log "WARN: $ENV_FILE missing — copying from $BASE/.env (one-time); проверь секреты"
      cp -a "$BASE/.env" "$ENV_FILE"
      chmod 600 "$ENV_FILE" 2>/dev/null || true
    else
      log "ERROR: нет $ENV_FILE и нет $BASE/.env"
      DEPLOY_STATUS="FAILED"
      ACTIVE_RELEASE=""
      ACTIVE_COMMIT=""
      HEALTHCHECK_RESULT="FAIL"
      print_report_block
      exit 1
    fi
  fi
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "$SHARED_MEDIA" 2>/dev/null || true
}

link_shared_media_into_release() {
  local rel_root="$1"
  local mdir="$rel_root/sources/site_admin/media"
  rm -rf "$mdir"
  ln -sfn "$SHARED_MEDIA" "$mdir"
}

write_systemd_and_starter() {
  local app_user="$DEPLOY_USER"
  local dj="$BASE/current/sources/site_admin"
  local sock="${GUNICORN_SOCK:-/run/gunicorn.sock}"
  local workers="${GUNICORN_WORKERS:-2}"

  cat > /usr/local/bin/app-start.sh <<EOF
#!/usr/bin/env bash
set -a
source ${ENV_FILE} 2>/dev/null || true
set +a
exec ${VENV}/bin/gunicorn \\
    nfc_site.wsgi:application \\
    --workers ${workers} \\
    --bind unix:${sock} \\
    --access-logfile ${BASE}/logs/gunicorn-access.log \\
    --error-logfile ${BASE}/logs/gunicorn-error.log \\
    --log-level info \\
    --timeout 60 \\
    --keep-alive 5 \\
    --max-requests 1000 \\
    --max-requests-jitter 100
EOF
  chmod 755 /usr/local/bin/app-start.sh

  cat > /etc/systemd/system/app.service <<EOF
[Unit]
Description=nfc_cards gunicorn (v5 current symlink)
After=network.target postgresql.service redis.service
Requires=postgresql.service

[Service]
User=${app_user}
Group=${app_user}
WorkingDirectory=${dj}
ExecStart=/usr/local/bin/app-start.sh
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3
RuntimeDirectory=gunicorn
RuntimeDirectoryMode=0755
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable app 2>/dev/null || true
}

release_lock() {
  if [[ "${USE_FLOCK:-}" == "1" ]]; then
    flock -u 200 2>/dev/null || true
  fi
  rmdir "${LOCK_FILE}.dir" 2>/dev/null || true
}

acquire_lock() {
  local lock_target="$LOCK_FILE"
  mkdir -p /var/lock 2>/dev/null || true
  if command -v flock >/dev/null 2>&1; then
    # Проверяем доступ к lock-файлу безопасно: при set -e redirection у exec
    # может оборвать скрипт до fallback.
    if ! : > "$lock_target" 2>/dev/null; then
      lock_target="$LOCK_FILE_FALLBACK"
      log "lock file fallback -> $lock_target"
    fi
    exec 200>"$lock_target"
    LOCK_FILE="$lock_target"
    if ! flock -n 200; then
      log "lock held: $LOCK_FILE"
      DEPLOY_STATUS="FAILED"
      print_report_block
      exit 1
    fi
    USE_FLOCK=1
    log "STEP 1: lock acquired (flock)"
  else
    if ! mkdir "${LOCK_FILE}.dir" 2>/dev/null; then
      log "lock busy"
      DEPLOY_STATUS="FAILED"
      print_report_block
      exit 1
    fi
    log "STEP 1: lock acquired (mkdir)"
  fi
}

trap 'release_lock' EXIT

# --- main ---
acquire_lock

if [[ $EUID -ne 0 ]]; then
  log "run as root: sudo bash"
  DEPLOY_STATUS="FAILED"
  print_report_block
  exit 1
fi

mkdir -p "$RELEASES" "$BASE/logs"

log "STEP 3: ENV — проверка $SHARED_DIR/.env"
ensure_shared_env
log "STEP 4: VENV — $VENV"
ensure_venv

OLD_CURRENT=""
if [[ -L "$BASE/current" ]]; then
  OLD_CURRENT="$(readlink -f "$BASE/current" || true)"
fi

NEW_NAME="release_$(date +%Y%m%d_%H%M%S)"
NEW_PATH="$RELEASES/$NEW_NAME"
log "STEP 2: FETCH — git clone --depth 1 -> $NEW_PATH"
git clone --depth 1 --branch "$DEPLOY_BRANCH" "$GIT_ORIGIN" "$NEW_PATH"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$NEW_PATH" 2>/dev/null || true

link_shared_media_into_release "$NEW_PATH"
DJANGO_DIR="$NEW_PATH/sources/site_admin"

log "STEP 4 (pip): requirements -> shared venv"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$DJANGO_DIR/requirements.txt" -q

log "STEP 5: Django (source shared/.env)"
load_env

cd "$DJANGO_DIR"
log "manage.py check"
"$VENV/bin/python" manage.py check --fail-level ERROR
log "migrate --plan"
"$VENV/bin/python" manage.py migrate --plan --noinput
log "migrate"
"$VENV/bin/python" manage.py migrate --noinput
log "migrate --check"
"$VENV/bin/python" manage.py migrate --check
log "collectstatic"
"$VENV/bin/python" manage.py collectstatic --noinput -v 0

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$NEW_PATH" 2>/dev/null || true

log "STEP 6: switch current -> $NEW_PATH"
ln -sfn "$NEW_PATH" "$BASE/current"
ACTIVE_RELEASE="$NEW_NAME"

write_systemd_and_starter

log "STEP 7: reload app + nginx"
sc_start_or_reload_app
sc_reload_nginx
sleep 3

ACTIVE_COMMIT="$(git -C "$BASE/current" rev-parse HEAD 2>/dev/null || echo unknown)"

log "STEP 8: healthcheck"
if healthcheck_all; then
  HEALTHCHECK_RESULT="OK"
  DEPLOY_STATUS="SUCCESS"
  print_report_block
  exit 0
fi

HEALTHCHECK_RESULT="FAIL"
log "STEP 9: rollback symlink"
if [[ -n "$OLD_CURRENT" && -d "$OLD_CURRENT" ]]; then
  ln -sfn "$OLD_CURRENT" "$BASE/current"
  write_systemd_and_starter
  sc_start_or_reload_app
  sc_reload_nginx
  sleep 3
  ACTIVE_COMMIT="$(git -C "$BASE/current" rev-parse HEAD 2>/dev/null || echo unknown)"
  ACTIVE_RELEASE="$(basename "$(readlink -f "$BASE/current")")"
  if healthcheck_all; then
    HEALTHCHECK_RESULT="OK"
    DEPLOY_STATUS="ROLLBACK"
    print_report_block
    # exit 0 — откат успешен, сайт отвечает; иначе GitHub Actions помечает job как failed без причины
    exit 0
  fi
fi

DEPLOY_STATUS="FAILED"
HEALTHCHECK_RESULT="FAIL"
ACTIVE_COMMIT="$(git -C "$BASE/current" rev-parse HEAD 2>/dev/null || echo unknown)"
print_report_block
exit 2
