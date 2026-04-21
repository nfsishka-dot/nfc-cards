#!/usr/bin/env bash
# Production deploy v4 — release-based (blue/green style): releases/release_* + current symlink.
# Запуск на VPS: bash -s < deploy/v4-deploy.sh
#
# Не меняет содержимое .env (только source). Общий venv: /var/www/nfc-cards/venv
# Откат: только переключение symlink current → предыдущий release (без git reset на проде).
#
# Переменные (env или .env на сервере):
#   GIT_ORIGIN, DEPLOY_BRANCH=main
#   HEALTHCHECK_BASE, DEPLOY_HEALTHCHECK_PUBLIC_URL
#
# Ограничение: после успешного migrate БД уже может быть «впереди» кода; откат symlink
# возвращает старый код — при необходимости миграции откатывать вручную (редко).
#
set -euo pipefail

BASE="/var/www/nfc-cards"
RELEASES="$BASE/releases"
VENV="$BASE/venv"
ENV_FILE="$BASE/.env"
SHARED_MEDIA="$BASE/shared/media"
LOCK_FILE="/var/lock/nfc-deploy.lock"
GIT_ORIGIN="${GIT_ORIGIN:-https://github.com/nfsishka-dot/nfc-cards.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

FINAL_MSG="DEPLOY STATUS: FAILED"

log() { echo "[v4-deploy] $*"; }

sc_reload() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl reload "$1" 2>/dev/null || systemctl restart "$1"
  else
    sudo -n systemctl reload "$1" 2>/dev/null || sudo -n systemctl restart "$1"
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

  for url in "${base}/" "${base}/admin/"; do
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "$url" || echo "000")"
    log "healthcheck: $url -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) return 1 ;;
    esac
  done

  if [[ -n "$third" ]]; then
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "$third" || echo "000")"
    log "healthcheck (public): $third -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) return 1 ;;
    esac
  else
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "${base}/" || echo "000")"
    log "healthcheck (fallback): ${base}/ -> HTTP $code"
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

ensure_shared_media() {
  mkdir -p "$SHARED_MEDIA"
  local u="${SUDO_USER:-deploy}"
  if id "$u" &>/dev/null; then
    chown -R "$u:$u" "$SHARED_MEDIA" 2>/dev/null || true
  fi
}

link_shared_media_into_release() {
  local rel_root="$1"
  local mdir="$rel_root/sources/site_admin/media"
  rm -rf "$mdir"
  ln -sfn "$SHARED_MEDIA" "$mdir"
  log "symlink media -> $SHARED_MEDIA"
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
Description=nfc_cards gunicorn (v4 current symlink)
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
  log "systemd app.service aligned to WorkingDirectory=${dj}"
}

release_lock() {
  if [[ "${USE_FLOCK:-}" == "1" ]]; then
    flock -u 200 2>/dev/null || true
  fi
  rmdir "${LOCK_FILE}.dir" 2>/dev/null || true
}

acquire_lock() {
  mkdir -p /var/lock
  if command -v flock >/dev/null 2>&1; then
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
      log "lock held: $LOCK_FILE"
      echo "DEPLOY STATUS: FAILED"
      exit 1
    fi
    USE_FLOCK=1
    log "lock acquired (flock)"
  else
    if ! mkdir "${LOCK_FILE}.dir" 2>/dev/null; then
      log "lock busy"
      echo "DEPLOY STATUS: FAILED"
      exit 1
    fi
    log "lock acquired (mkdir)"
  fi
}

trap 'release_lock' EXIT

# -----------------------------------------------------------------------------
acquire_lock

if [[ $EUID -ne 0 ]]; then
  log "run as root: sudo bash $0"
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  log "missing $ENV_FILE"
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

mkdir -p "$RELEASES" "$BASE/logs" "$BASE/shared"
ensure_venv
ensure_shared_media

NEW_NAME="release_$(date +%Y%m%d_%H%M%S)"
NEW_PATH="$RELEASES/$NEW_NAME"
log "STEP 1: create release $NEW_PATH"

OLD_CURRENT=""
if [[ -L "$BASE/current" ]]; then
  OLD_CURRENT="$(readlink -f "$BASE/current" || true)"
  log "previous active release: ${OLD_CURRENT:-none}"
fi

log "STEP 2: git clone --depth 1 branch ${DEPLOY_BRANCH}"
git clone --depth 1 --branch "$DEPLOY_BRANCH" "$GIT_ORIGIN" "$NEW_PATH"

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$NEW_PATH" 2>/dev/null || true

link_shared_media_into_release "$NEW_PATH"

DJANGO_DIR="$NEW_PATH/sources/site_admin"

log "STEP 3: pip install"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$DJANGO_DIR/requirements.txt" -q

load_env

log "STEP 4: preflight (check + migrate --plan)"
cd "$DJANGO_DIR"
"$VENV/bin/python" manage.py check --fail-level ERROR
"$VENV/bin/python" manage.py migrate --plan --noinput

log "STEP 5: migrate"
"$VENV/bin/python" manage.py migrate --noinput
"$VENV/bin/python" manage.py migrate --check

log "STEP 6: collectstatic --clear"
"$VENV/bin/python" manage.py collectstatic --noinput --clear -v 0

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$NEW_PATH" 2>/dev/null || true

log "STEP 7: switch symlink current -> $NEW_PATH (not live until reload)"
ln -sfn "$NEW_PATH" "$BASE/current"

write_systemd_and_starter

log "STEP 8: start/reload gunicorn + reload nginx"
sc_start_or_reload_app
sc_reload nginx
sleep 3

log "STEP 9: healthcheck"
if healthcheck_all; then
  FINAL_MSG="DEPLOY STATUS: SUCCESS"
  log "$FINAL_MSG"
  log "active release: $(readlink -f "$BASE/current")"
  echo "$FINAL_MSG"
  exit 0
fi

log "healthcheck FAILED — rollback symlink"
if [[ -n "$OLD_CURRENT" && -d "$OLD_CURRENT" ]]; then
  ln -sfn "$OLD_CURRENT" "$BASE/current"
  write_systemd_and_starter
  sc_start_or_reload_app
  sc_reload nginx
  sleep 3
  if healthcheck_all; then
    FINAL_MSG="DEPLOY STATUS: ROLLBACK EXECUTED"
    log "$FINAL_MSG"
    log "WARN: DB may include migrations from failed release — verify if needed"
    echo "$FINAL_MSG"
    exit 1
  fi
fi

FINAL_MSG="DEPLOY STATUS: FAILED"
log "$FINAL_MSG"
echo "$FINAL_MSG"
exit 2
